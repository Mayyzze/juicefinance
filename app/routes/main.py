from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.notification import SystemAnnouncement
from app import db
from datetime import datetime

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@main_bp.route("/dashboard")
@login_required
def dashboard():
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
    recent_transactions = (
        Transaction.query
        .filter(
            db.or_(
                Transaction.sender_id == current_user.id,
                Transaction.recipient_id == current_user.id
            )
        )
        .order_by(Transaction.created_at.desc())
        .limit(10)
        .all()
    )
    announcements = SystemAnnouncement.query.filter_by(is_active=True).filter(
        db.or_(SystemAnnouncement.ends_at.is_(None),
               SystemAnnouncement.ends_at > datetime.utcnow())
    ).all()

    total_balance = sum(float(a.balance) for a in accounts)

    monthly_income = 0.0
    monthly_expenses = 0.0
    now = datetime.utcnow()
    for tx in Transaction.query.filter(
        Transaction.recipient_id == current_user.id,
        Transaction.status == "completed",
        db.extract("month", Transaction.created_at) == now.month,
        db.extract("year", Transaction.created_at) == now.year,
    ).all():
        monthly_income += float(tx.amount)
    for tx in Transaction.query.filter(
        Transaction.sender_id == current_user.id,
        Transaction.status == "completed",
        db.extract("month", Transaction.created_at) == now.month,
        db.extract("year", Transaction.created_at) == now.year,
    ).all():
        monthly_expenses += float(tx.amount)

    return render_template(
        "dashboard.html",
        accounts=accounts,
        recent_transactions=recent_transactions,
        announcements=announcements,
        total_balance=total_balance,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
    )
