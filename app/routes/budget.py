from datetime import datetime, date
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, jsonify, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.transaction import TransactionCategory, Transaction

budget_bp = Blueprint("budget", __name__)


@budget_bp.route("/")
@login_required
def overview():
    now = datetime.utcnow()
    month = request.args.get("month", now.month, type=int)
    year = request.args.get("year", now.year, type=int)

    categories = TransactionCategory.query.filter(
        db.or_(
            TransactionCategory.user_id == current_user.id,
            TransactionCategory.is_system == True,
        )
    ).all()

    spending = {}
    for cat in categories:
        txs = Transaction.query.filter(
            Transaction.sender_id == current_user.id,
            Transaction.category_id == cat.id,
            Transaction.status == "completed",
            db.extract("month", Transaction.created_at) == month,
            db.extract("year", Transaction.created_at) == year,
        ).all()
        spending[cat.id] = sum(float(t.amount) for t in txs)

    total_income = sum(
        float(t.amount)
        for t in Transaction.query.filter(
            Transaction.recipient_id == current_user.id,
            Transaction.status == "completed",
            db.extract("month", Transaction.created_at) == month,
            db.extract("year", Transaction.created_at) == year,
        ).all()
    )
    total_expenses = sum(
        float(t.amount)
        for t in Transaction.query.filter(
            Transaction.sender_id == current_user.id,
            Transaction.status == "completed",
            db.extract("month", Transaction.created_at) == month,
            db.extract("year", Transaction.created_at) == year,
        ).all()
    )

    return render_template(
        "budget/overview.html",
        categories=categories,
        spending=spending,
        total_income=total_income,
        total_expenses=total_expenses,
        month=month,
        year=year,
    )


@budget_bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        icon = request.form.get("icon", "tag")
        color = request.form.get("color", "#6c757d")
        cat_type = request.form.get("type", "expense")
        budget_str = request.form.get("monthly_budget", "")

        if not name:
            flash("Category name is required.", "danger")
            return redirect(url_for("budget.categories"))

        budget_val = None
        if budget_str:
            try:
                budget_val = float(budget_str)
            except ValueError:
                pass

        cat = TransactionCategory(
            user_id=current_user.id,
            name=name,
            icon=icon,
            color=color,
            type=cat_type,
            monthly_budget=budget_val,
        )
        db.session.add(cat)
        db.session.commit()
        flash("Category created.", "success")
        return redirect(url_for("budget.categories"))

    cats = TransactionCategory.query.filter(
        db.or_(
            TransactionCategory.user_id == current_user.id,
            TransactionCategory.is_system == True,
        )
    ).all()
    return render_template("budget/categories.html", categories=cats)


@budget_bp.route("/categories/<int:cat_id>/edit", methods=["POST"])
@login_required
def edit_category(cat_id):
    cat = TransactionCategory.query.get_or_404(cat_id)
    if cat.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    cat.name = request.form.get("name", cat.name)
    cat.icon = request.form.get("icon", cat.icon)
    cat.color = request.form.get("color", cat.color)
    cat.type = request.form.get("type", cat.type)
    budget_str = request.form.get("monthly_budget", "")
    if budget_str:
        try:
            cat.monthly_budget = float(budget_str)
        except ValueError:
            pass
    db.session.commit()
    flash("Category updated.", "success")
    return redirect(url_for("budget.categories"))


@budget_bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
@login_required
def delete_category(cat_id):
    cat = TransactionCategory.query.get_or_404(cat_id)
    if cat.user_id != current_user.id:
        abort(403)
    if cat.is_system:
        flash("Cannot delete system category.", "danger")
        return redirect(url_for("budget.categories"))
    db.session.delete(cat)
    db.session.commit()
    flash("Category deleted.", "info")
    return redirect(url_for("budget.categories"))


@budget_bp.route("/analytics")
@login_required
def analytics():
    now = datetime.utcnow()
    months_data = []
    for i in range(6):
        m = now.month - i
        y = now.year
        while m <= 0:
            m += 12
            y -= 1
        income = sum(
            float(t.amount)
            for t in Transaction.query.filter(
                Transaction.recipient_id == current_user.id,
                Transaction.status == "completed",
                db.extract("month", Transaction.created_at) == m,
                db.extract("year", Transaction.created_at) == y,
            ).all()
        )
        expenses = sum(
            float(t.amount)
            for t in Transaction.query.filter(
                Transaction.sender_id == current_user.id,
                Transaction.status == "completed",
                db.extract("month", Transaction.created_at) == m,
                db.extract("year", Transaction.created_at) == y,
            ).all()
        )
        months_data.append({"month": m, "year": y, "income": income, "expenses": expenses})

    months_data.reverse()

    categories = TransactionCategory.query.filter(
        db.or_(
            TransactionCategory.user_id == current_user.id,
            TransactionCategory.is_system == True,
        )
    ).all()

    cat_spending = []
    for cat in categories:
        total = sum(
            float(t.amount)
            for t in Transaction.query.filter(
                Transaction.sender_id == current_user.id,
                Transaction.category_id == cat.id,
                Transaction.status == "completed",
            ).all()
        )
        if total > 0:
            cat_spending.append({"name": cat.name, "color": cat.color, "total": total})

    return render_template(
        "budget/analytics.html",
        months_data=months_data,
        cat_spending=cat_spending,
    )


@budget_bp.route("/api/spending-data")
@login_required
def spending_data():
    now = datetime.utcnow()
    month = request.args.get("month", now.month, type=int)
    year = request.args.get("year", now.year, type=int)

    categories = TransactionCategory.query.filter(
        db.or_(
            TransactionCategory.user_id == current_user.id,
            TransactionCategory.is_system == True,
        )
    ).all()

    data = []
    for cat in categories:
        total = sum(
            float(t.amount)
            for t in Transaction.query.filter(
                Transaction.sender_id == current_user.id,
                Transaction.category_id == cat.id,
                Transaction.status == "completed",
                db.extract("month", Transaction.created_at) == month,
                db.extract("year", Transaction.created_at) == year,
            ).all()
        )
        data.append({"label": cat.name, "value": total, "color": cat.color})

    return jsonify(data)
