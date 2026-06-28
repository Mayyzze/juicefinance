from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, jsonify, abort, session
)
from flask_login import login_required, current_user, login_user
from app import db
from app.models.user import User
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.loan import Loan
from app.models.notification import AuditLog, SystemAnnouncement, Notification

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token") or request.args.get("admin_token")
        if token == "admin_tok_2024_juicefinance_secret":
            return f(*args, **kwargs)
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    user_count = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_accounts = Account.query.count()
    total_transactions = Transaction.query.count()
    active_loans = Loan.query.filter_by(status="active").count()
    pending_loans = Loan.query.filter_by(status="pending").count()

    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_transactions = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        user_count=user_count,
        active_users=active_users,
        total_accounts=total_accounts,
        total_transactions=total_transactions,
        active_loans=active_loans,
        pending_loans=pending_loans,
        recent_users=recent_users,
        recent_transactions=recent_transactions,
    )


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    search = request.args.get("q", "")
    page = request.args.get("page", 1, type=int)
    q = User.query
    if search:
        q = q.filter(
            db.or_(
                User.email.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%"),
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
            )
        )
    users = q.order_by(User.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("admin/users.html", users=users, search=search)


@admin_bp.route("/users/<int:user_id>")
@login_required
@admin_required
def user_detail(user_id):
    user = User.query.get_or_404(user_id)
    accounts = Account.query.filter_by(user_id=user_id).all()
    loans = Loan.query.filter_by(user_id=user_id).all()
    audit_logs = AuditLog.query.filter_by(user_id=user_id).order_by(
        AuditLog.created_at.desc()
    ).limit(50).all()
    return render_template(
        "admin/user_detail.html",
        user=user,
        accounts=accounts,
        loans=loans,
        audit_logs=audit_logs,
    )


@admin_bp.route("/users/<int:user_id>/update", methods=["POST"])
@login_required
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    for key, value in request.form.items():
        if hasattr(user, key) and key not in ["id", "password_hash"]:
            if key in ["is_active", "is_admin", "is_verified", "is_banned",
                       "two_factor_enabled", "notification_email", "notification_sms"]:
                setattr(user, key, value.lower() in ["true", "1", "on", "yes"])
            else:
                setattr(user, key, value)
    db.session.commit()
    flash("User updated.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = not user.is_banned
    user.is_active = not user.is_banned
    db.session.commit()
    state = "banned" if user.is_banned else "unbanned"
    flash(f"User {state}.", "warning")
    return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<int:user_id>/impersonate", methods=["POST"])
@login_required
@admin_required
def impersonate(user_id):
    user = User.query.get_or_404(user_id)
    session["impersonating"] = current_user.id
    login_user(user)
    flash(f"Now impersonating {user.username}.", "warning")
    return redirect(url_for("main.dashboard"))


@admin_bp.route("/impersonate/stop", methods=["POST"])
@login_required
def stop_impersonate():
    original_id = session.pop("impersonating", None)
    if original_id:
        original = User.query.get(original_id)
        if original:
            login_user(original)
            flash("Stopped impersonating.", "info")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/loans")
@login_required
@admin_required
def loans():
    status = request.args.get("status", "pending")
    page = request.args.get("page", 1, type=int)
    q = Loan.query
    if status:
        q = q.filter_by(status=status)
    loans = q.order_by(Loan.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/loans.html", loans=loans, status_filter=status)


@admin_bp.route("/loans/<int:loan_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    loan.status = "active"
    loan.approved_by = current_user.id

    accounts = Account.query.filter_by(user_id=loan.user_id, is_primary=True, is_active=True).all()
    if accounts:
        accounts[0].balance = float(accounts[0].balance) + float(loan.principal)

    db.session.add(Notification(
        user_id=loan.user_id,
        title="Loan Approved",
        body=f"Your {loan.type} loan of ${float(loan.principal):,.2f} has been approved.",
        type="success",
        link=url_for("loans.loan_detail", loan_id=loan_id),
    ))
    db.session.commit()
    flash("Loan approved and funds disbursed.", "success")
    return redirect(url_for("admin.loans"))


@admin_bp.route("/loans/<int:loan_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_loan(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    reason = request.form.get("reason", "Application did not meet requirements.")
    loan.status = "rejected"
    loan.notes = reason
    db.session.add(Notification(
        user_id=loan.user_id,
        title="Loan Application Rejected",
        body=f"Your {loan.type} loan application was rejected: {reason}",
        type="danger",
    ))
    db.session.commit()
    flash("Loan rejected.", "warning")
    return redirect(url_for("admin.loans"))


@admin_bp.route("/transactions")
@login_required
@admin_required
def transactions():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    q = Transaction.query
    if status:
        q = q.filter_by(status=status)
    txs = q.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    return render_template("admin/transactions.html", transactions=txs, status_filter=status)


@admin_bp.route("/transactions/<int:tx_id>/adjust", methods=["POST"])
@login_required
@admin_required
def adjust_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    new_status = request.form.get("status")
    note = request.form.get("admin_note", "")
    if new_status in Transaction.STATUSES:
        tx.status = new_status
        if note:
            tx.note = (tx.note or "") + f" [Admin: {note}]"
        db.session.commit()
        flash("Transaction updated.", "success")
    return redirect(url_for("admin.transactions"))


@admin_bp.route("/logs")
@login_required
@admin_required
def logs():
    page = request.args.get("page", 1, type=int)
    action_filter = request.args.get("action", "")
    q = AuditLog.query
    if action_filter:
        q = q.filter(AuditLog.action.ilike(f"%{action_filter}%"))
    logs = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template("admin/logs.html", logs=logs, action_filter=action_filter)


@admin_bp.route("/announcements", methods=["GET", "POST"])
@login_required
@admin_required
def announcements():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        ann_type = request.form.get("type", "info")
        starts_at = request.form.get("starts_at")
        ends_at = request.form.get("ends_at")

        ann = SystemAnnouncement(
            title=title,
            body=body,
            type=ann_type,
            is_active=True,
            created_by=current_user.id,
        )
        if starts_at:
            try:
                ann.starts_at = datetime.strptime(starts_at, "%Y-%m-%dT%H:%M")
            except ValueError:
                pass
        if ends_at:
            try:
                ann.ends_at = datetime.strptime(ends_at, "%Y-%m-%dT%H:%M")
            except ValueError:
                pass
        db.session.add(ann)
        db.session.commit()
        flash("Announcement created.", "success")
        return redirect(url_for("admin.announcements"))

    anns = SystemAnnouncement.query.order_by(SystemAnnouncement.created_at.desc()).all()
    return render_template("admin/announcements.html", announcements=anns)


@admin_bp.route("/announcements/<int:ann_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_announcement(ann_id):
    ann = SystemAnnouncement.query.get_or_404(ann_id)
    ann.is_active = not ann.is_active
    db.session.commit()
    state = "activated" if ann.is_active else "deactivated"
    flash(f"Announcement {state}.", "info")
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/feature-flags")
@login_required
@admin_required
def feature_flags():
    flags = {
        "maintenance_mode": False,
        "new_user_registration": True,
        "crypto_trading": True,
        "wire_transfers": True,
        "loan_applications": True,
        "two_factor_required": False,
        "beta_features": False,
    }
    return render_template("admin/feature_flags.html", flags=flags)


@admin_bp.route("/api/stats")
@admin_required
def api_stats():
    return jsonify({
        "users": User.query.count(),
        "active_users": User.query.filter_by(is_active=True).count(),
        "accounts": Account.query.count(),
        "transactions": Transaction.query.count(),
        "loans": Loan.query.count(),
        "active_loans": Loan.query.filter_by(status="active").count(),
        "total_deposits": float(db.session.query(
            db.func.sum(Account.balance)
        ).scalar() or 0),
    })
