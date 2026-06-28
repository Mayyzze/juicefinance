import os
import secrets
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, current_app, send_file, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.loan import Loan, LoanPayment, LoanDocument
from app.models.account import Account
from app.models.notification import Notification

loans_bp = Blueprint("loans", __name__)


def calculate_monthly_payment(principal, annual_rate, term_months):
    if annual_rate == 0:
        return principal / term_months
    r = annual_rate / 12
    return principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1)


@loans_bp.route("/")
@login_required
def list_loans():
    loans = Loan.query.filter_by(user_id=current_user.id).order_by(Loan.created_at.desc()).all()
    return render_template("loans/list.html", loans=loans)


@loans_bp.route("/<int:loan_id>")
@login_required
def loan_detail(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    payments = loan.payments.all()
    documents = loan.documents.all()
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
    return render_template(
        "loans/detail.html",
        loan=loan,
        payments=payments,
        documents=documents,
        accounts=accounts,
    )


@loans_bp.route("/apply", methods=["GET", "POST"])
@login_required
def apply():
    if request.method == "POST":
        loan_type = request.form.get("type", "personal")
        purpose = request.form.get("purpose", "").strip()
        principal = float(request.form.get("amount", 0))
        term_months = int(request.form.get("term_months", 12))
        employment_status = request.form.get("employment_status", "employed")
        annual_income = float(request.form.get("annual_income", 0))
        credit_score = request.form.get("credit_score", type=int)
        collateral = request.form.get("collateral_description", "").strip()

        interest_rate_map = {
            "personal": 0.099,
            "auto": 0.059,
            "mortgage": 0.039,
            "student": 0.055,
            "business": 0.075,
            "line_of_credit": 0.089,
        }
        rate = interest_rate_map.get(loan_type, 0.099)
        monthly_payment = calculate_monthly_payment(principal, rate, term_months)

        loan_number = "LN" + secrets.token_hex(8).upper()
        origination = date.today()
        maturity = origination + relativedelta(months=term_months)
        next_payment = origination + relativedelta(months=1)

        loan = Loan(
            user_id=current_user.id,
            loan_number=loan_number,
            type=loan_type,
            purpose=purpose,
            principal=principal,
            outstanding_balance=principal,
            interest_rate=rate,
            term_months=term_months,
            monthly_payment=monthly_payment,
            origination_date=origination,
            maturity_date=maturity,
            next_payment_date=next_payment,
            status="pending",
            credit_score_at_application=credit_score,
            employment_status=employment_status,
            annual_income=annual_income,
            collateral_description=collateral,
        )
        db.session.add(loan)
        db.session.commit()

        db.session.add(Notification(
            user_id=current_user.id,
            title="Loan Application Received",
            body=f"Your {loan_type} loan application for ${principal:,.2f} is under review.",
            type="info",
            link=url_for("loans.loan_detail", loan_id=loan.id),
        ))
        db.session.commit()

        flash("Loan application submitted. We will review it within 2-3 business days.", "success")
        return redirect(url_for("loans.loan_detail", loan_id=loan.id))

    return render_template("loans/apply.html", loan_types=Loan.TYPES)


@loans_bp.route("/<int:loan_id>/pay", methods=["POST"])
@login_required
def make_payment(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.user_id != current_user.id:
        abort(403)

    if loan.status != "active":
        flash("Loan is not active.", "danger")
        return redirect(url_for("loans.loan_detail", loan_id=loan_id))

    account_id = request.form.get("account_id", type=int)
    amount = float(request.form.get("amount", 0))

    account = Account.query.get(account_id)
    if not account or account.user_id != current_user.id:
        flash("Invalid account.", "danger")
        return redirect(url_for("loans.loan_detail", loan_id=loan_id))

    if float(account.balance) < amount:
        flash("Insufficient funds.", "danger")
        return redirect(url_for("loans.loan_detail", loan_id=loan_id))

    balance = float(loan.outstanding_balance)
    rate = float(loan.interest_rate)
    interest = balance * (rate / 12)
    principal_portion = max(0, amount - interest)
    interest_portion = min(amount, interest)

    account.balance = float(account.balance) - amount
    loan.outstanding_balance = max(0, balance - principal_portion)

    if float(loan.outstanding_balance) <= 0:
        loan.status = "paid_off"

    loan.next_payment_date = loan.next_payment_date + relativedelta(months=1) if loan.next_payment_date else None

    payment = LoanPayment(
        loan_id=loan_id,
        amount=amount,
        principal_portion=principal_portion,
        interest_portion=interest_portion,
        status="completed",
        payment_date=date.today(),
        source_account_id=account_id,
        reference=secrets.token_hex(8),
    )
    db.session.add(payment)
    db.session.commit()
    flash(f"Payment of ${amount:.2f} processed.", "success")
    return redirect(url_for("loans.loan_detail", loan_id=loan_id))


@loans_bp.route("/<int:loan_id>/upload-document", methods=["POST"])
@login_required
def upload_document(loan_id):
    loan = Loan.query.get_or_404(loan_id)
    if loan.user_id != current_user.id:
        abort(403)

    file = request.files.get("document")
    doc_type = request.form.get("document_type", "other")

    if not file or not file.filename:
        flash("No file selected.", "danger")
        return redirect(url_for("loans.loan_detail", loan_id=loan_id))

    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "documents")
    stored_filename = file.filename
    filepath = os.path.join(upload_dir, stored_filename)
    file.save(filepath)

    doc = LoanDocument(
        loan_id=loan_id,
        user_id=current_user.id,
        document_type=doc_type,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_size=os.path.getsize(filepath),
        mime_type=file.content_type,
    )
    db.session.add(doc)
    db.session.commit()
    flash("Document uploaded.", "success")
    return redirect(url_for("loans.loan_detail", loan_id=loan_id))


@loans_bp.route("/documents/<int:doc_id>/download")
@login_required
def download_document(doc_id):
    doc = LoanDocument.query.get_or_404(doc_id)
    loan = Loan.query.get(doc.loan_id)
    if loan.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], "documents", doc.stored_filename)
    if not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=doc.original_filename)


@loans_bp.route("/calculator")
def calculator():
    return render_template("loans/calculator.html", loan_types=Loan.TYPES)


@loans_bp.route("/api/calculate", methods=["POST"])
def api_calculate():
    from flask import jsonify
    data = request.get_json() or {}
    principal = float(data.get("principal", 0))
    rate = float(data.get("rate", 0.09)) / 100
    term = int(data.get("term_months", 12))
    monthly = calculate_monthly_payment(principal, rate, term)
    total = monthly * term
    return jsonify({
        "monthly_payment": round(monthly, 2),
        "total_repayment": round(total, 2),
        "total_interest": round(total - principal, 2),
    })
