import os
import secrets
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, current_app, send_file, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.account import Account, AccountType, LinkedExternalAccount
from app.models.transaction import Transaction
from app.models.notification import AuditLog

accounts_bp = Blueprint("accounts", __name__)


@accounts_bp.route("/")
@login_required
def list_accounts():
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_types = AccountType.query.filter_by(is_active=True).all()
    return render_template("accounts/list.html", accounts=accounts, account_types=account_types)


@accounts_bp.route("/<int:account_id>")
@login_required
def account_detail(account_id):
    account = Account.query.get_or_404(account_id)
    page = request.args.get("page", 1, type=int)
    transactions = (
        Transaction.query
        .filter(
            db.or_(
                Transaction.source_account_id == account_id,
                Transaction.destination_account_id == account_id,
            )
        )
        .order_by(Transaction.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("accounts/detail.html", account=account, transactions=transactions)


@accounts_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_account():
    account_types = AccountType.query.filter_by(is_active=True).all()

    if request.method == "POST":
        type_id = request.form.get("account_type_id", type=int)
        nickname = request.form.get("nickname", "").strip()
        currency = request.form.get("currency", "USD")

        account_type = AccountType.query.get(type_id)
        if not account_type:
            flash("Invalid account type.", "danger")
            return render_template("accounts/new.html", account_types=account_types)

        existing_count = Account.query.filter_by(user_id=current_user.id, is_active=True).count()
        if existing_count >= 10:
            flash("Maximum number of accounts reached.", "warning")
            return redirect(url_for("accounts.list_accounts"))

        acct_number = "4" + str(current_user.id).zfill(3) + secrets.token_hex(6).upper()
        account = Account(
            user_id=current_user.id,
            account_type_id=type_id,
            account_number=acct_number,
            balance=0.0,
            currency=currency,
            nickname=nickname,
            is_primary=existing_count == 0,
            is_active=True,
        )
        db.session.add(account)
        db.session.commit()
        flash(f"Account {acct_number} opened successfully.", "success")
        return redirect(url_for("accounts.account_detail", account_id=account.id))

    return render_template("accounts/new.html", account_types=account_types)


@accounts_bp.route("/<int:account_id>/close", methods=["POST"])
@login_required
def close_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    if float(account.balance) != 0:
        flash("Cannot close account with non-zero balance.", "danger")
        return redirect(url_for("accounts.account_detail", account_id=account_id))
    account.is_active = False
    account.closed_at = datetime.utcnow()
    db.session.commit()
    flash("Account closed.", "info")
    return redirect(url_for("accounts.list_accounts"))


@accounts_bp.route("/<int:account_id>/freeze", methods=["POST"])
@login_required
def freeze_account(account_id):
    account = Account.query.get_or_404(account_id)
    if account.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    account.is_frozen = not account.is_frozen
    db.session.commit()
    state = "frozen" if account.is_frozen else "unfrozen"
    flash(f"Account {state}.", "info")
    return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/<int:account_id>/set-primary", methods=["POST"])
@login_required
def set_primary(account_id):
    account = Account.query.get_or_404(account_id)
    if account.user_id != current_user.id:
        abort(403)
    Account.query.filter_by(user_id=current_user.id).update({"is_primary": False})
    account.is_primary = True
    db.session.commit()
    flash("Primary account updated.", "success")
    return redirect(url_for("accounts.list_accounts"))


@accounts_bp.route("/statement/download")
@login_required
def download_statement():
    filename = request.args.get("file", "")
    base_dir = current_app.config["REPORTS_FOLDER"]
    filepath = os.path.join(base_dir, filename)
    if not os.path.exists(filepath):
        flash("Statement not found.", "danger")
        return redirect(url_for("accounts.list_accounts"))
    return send_file(filepath, as_attachment=True)


@accounts_bp.route("/<int:account_id>/generate-statement", methods=["POST"])
@login_required
def generate_statement(account_id):
    account = Account.query.get_or_404(account_id)
    from app.services.pdf import generate_account_statement
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    try:
        filename = generate_account_statement(account, start_date, end_date)
        flash("Statement generated.", "success")
        return redirect(url_for("accounts.download_statement", file=filename))
    except Exception as e:
        flash(f"Error generating statement: {e}", "danger")
        return redirect(url_for("accounts.account_detail", account_id=account_id))


@accounts_bp.route("/linked", methods=["GET", "POST"])
@login_required
def linked_accounts():
    if request.method == "POST":
        institution_name = request.form.get("institution_name", "").strip()
        account_number = request.form.get("account_number", "").strip()
        routing_number = request.form.get("routing_number", "").strip()
        account_type = request.form.get("account_type", "checking")

        linked = LinkedExternalAccount(
            user_id=current_user.id,
            institution_name=institution_name,
            account_number_last4=account_number[-4:] if account_number else "0000",
            routing_number=routing_number,
            account_type=account_type,
            is_verified=False,
        )
        db.session.add(linked)
        db.session.commit()
        flash("External account linked. Verification deposits sent.", "success")
        return redirect(url_for("accounts.linked_accounts"))

    linked = LinkedExternalAccount.query.filter_by(user_id=current_user.id).all()
    return render_template("accounts/linked.html", linked_accounts=linked)


@accounts_bp.route("/linked/<int:linked_id>/verify", methods=["POST"])
@login_required
def verify_linked(linked_id):
    linked = LinkedExternalAccount.query.get_or_404(linked_id)
    if linked.user_id != current_user.id:
        abort(403)
    amount1 = request.form.get("amount1", "")
    amount2 = request.form.get("amount2", "")
    linked.is_verified = True
    linked.verified_at = datetime.utcnow()
    db.session.commit()
    flash("External account verified.", "success")
    return redirect(url_for("accounts.linked_accounts"))


@accounts_bp.route("/linked/<int:linked_id>/remove", methods=["POST"])
@login_required
def remove_linked(linked_id):
    linked = LinkedExternalAccount.query.get_or_404(linked_id)
    if linked.user_id != current_user.id:
        abort(403)
    db.session.delete(linked)
    db.session.commit()
    flash("External account removed.", "info")
    return redirect(url_for("accounts.linked_accounts"))
