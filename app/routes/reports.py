import os
import csv
import io
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, current_app, send_file, make_response
)
from flask_login import login_required, current_user
from app import db
from app.models.account import Account
from app.models.transaction import Transaction

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def index():
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
    return render_template("reports/index.html", accounts=accounts)


@reports_bp.route("/generate", methods=["POST"])
@login_required
def generate():
    report_type = request.form.get("report_type", "statement")
    account_id = request.form.get("account_id", type=int)
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    output_format = request.form.get("format", "pdf")

    if output_format == "pdf":
        from app.services.pdf import generate_account_statement
        account = Account.query.get_or_404(account_id)
        try:
            filename = generate_account_statement(account, start_date, end_date)
            filepath = os.path.join(current_app.config["REPORTS_FOLDER"], filename)
            return send_file(filepath, as_attachment=True)
        except Exception as e:
            flash(f"Error generating report: {e}", "danger")
            return redirect(url_for("reports.index"))

    elif output_format == "csv":
        account = Account.query.get(account_id)
        q = Transaction.query.filter(
            db.or_(
                Transaction.source_account_id == account_id,
                Transaction.destination_account_id == account_id,
            )
        )
        if start_date:
            try:
                q = q.filter(Transaction.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
            except ValueError:
                pass
        if end_date:
            try:
                q = q.filter(Transaction.created_at <= datetime.strptime(end_date, "%Y-%m-%d"))
            except ValueError:
                pass
        transactions = q.order_by(Transaction.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Reference", "Type", "Amount", "Currency", "Status", "Description"])
        for tx in transactions:
            writer.writerow([
                tx.created_at.strftime("%Y-%m-%d %H:%M"),
                tx.reference_id,
                tx.type,
                float(tx.amount),
                tx.currency,
                tx.status,
                tx.description or "",
            ])
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    flash("Unsupported format.", "danger")
    return redirect(url_for("reports.index"))


@reports_bp.route("/tax-summary")
@login_required
def tax_summary():
    year = request.args.get("year", datetime.utcnow().year, type=int)
    transactions = Transaction.query.filter(
        db.or_(
            Transaction.sender_id == current_user.id,
            Transaction.recipient_id == current_user.id,
        ),
        Transaction.status == "completed",
        db.extract("year", Transaction.created_at) == year,
    ).all()

    income = sum(float(t.amount) for t in transactions if t.recipient_id == current_user.id)
    expenses = sum(float(t.amount) for t in transactions if t.sender_id == current_user.id)
    fees = sum(float(t.fee) for t in transactions if t.sender_id == current_user.id)

    return render_template(
        "reports/tax_summary.html",
        year=year,
        income=income,
        expenses=expenses,
        fees=fees,
        transactions=transactions,
    )


@reports_bp.route("/custom", methods=["GET", "POST"])
@login_required
def custom_report():
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()

    if request.method == "POST":
        title = request.form.get("title", "Custom Report")
        account_ids = request.form.getlist("account_ids", type=int)
        start_date = request.form.get("start_date", "")
        end_date = request.form.get("end_date", "")
        include_charts = "include_charts" in request.form
        from app.services.pdf import generate_custom_report
        try:
            filename = generate_custom_report(
                current_user, title, account_ids, start_date, end_date, include_charts
            )
            filepath = os.path.join(current_app.config["REPORTS_FOLDER"], filename)
            return send_file(filepath, as_attachment=True)
        except Exception as e:
            flash(f"Report generation failed: {e}", "danger")

    return render_template("reports/custom.html", accounts=accounts)
