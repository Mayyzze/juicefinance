from datetime import datetime
from app import db


class Loan(db.Model):
    __tablename__ = "loans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    loan_number = db.Column(db.String(20), unique=True, nullable=False)
    type = db.Column(db.String(30), nullable=False)
    purpose = db.Column(db.String(255))
    principal = db.Column(db.Numeric(15, 2), nullable=False)
    outstanding_balance = db.Column(db.Numeric(15, 2), nullable=False)
    interest_rate = db.Column(db.Numeric(6, 4), nullable=False)
    term_months = db.Column(db.Integer, nullable=False)
    monthly_payment = db.Column(db.Numeric(12, 2))
    origination_date = db.Column(db.Date)
    maturity_date = db.Column(db.Date)
    next_payment_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="pending")
    credit_score_at_application = db.Column(db.Integer)
    employment_status = db.Column(db.String(50))
    annual_income = db.Column(db.Numeric(15, 2))
    collateral_description = db.Column(db.String(500))
    notes = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    payments = db.relationship("LoanPayment", backref="loan", lazy="dynamic",
                               order_by="LoanPayment.created_at.desc()")
    documents = db.relationship("LoanDocument", backref="loan", lazy="dynamic")
    approver = db.relationship("User", foreign_keys=[approved_by])

    TYPES = ["personal", "auto", "mortgage", "student", "business", "line_of_credit"]
    STATUSES = ["pending", "under_review", "approved", "active", "paid_off", "defaulted", "rejected"]

    @property
    def total_paid(self):
        return sum(float(p.amount) for p in self.payments.filter_by(status="completed").all())

    @property
    def progress_pct(self):
        if float(self.principal) == 0:
            return 0
        return (self.total_paid / float(self.principal)) * 100

    def to_dict(self):
        return {
            "id": self.id,
            "loan_number": self.loan_number,
            "type": self.type,
            "purpose": self.purpose,
            "principal": float(self.principal),
            "outstanding_balance": float(self.outstanding_balance),
            "interest_rate": float(self.interest_rate),
            "term_months": self.term_months,
            "monthly_payment": float(self.monthly_payment) if self.monthly_payment else None,
            "status": self.status,
            "origination_date": self.origination_date.isoformat() if self.origination_date else None,
            "maturity_date": self.maturity_date.isoformat() if self.maturity_date else None,
            "next_payment_date": self.next_payment_date.isoformat() if self.next_payment_date else None,
            "total_paid": self.total_paid,
            "progress_pct": self.progress_pct,
        }

    def __repr__(self):
        return f"<Loan {self.loan_number}>"


class LoanPayment(db.Model):
    __tablename__ = "loan_payments"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    principal_portion = db.Column(db.Numeric(12, 2))
    interest_portion = db.Column(db.Numeric(12, 2))
    fee_portion = db.Column(db.Numeric(12, 2), default=0.0)
    status = db.Column(db.String(20), default="pending")
    payment_date = db.Column(db.Date)
    source_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    reference = db.Column(db.String(32))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    source_account = db.relationship("Account")


class LoanDocument(db.Model):
    __tablename__ = "loan_documents"

    id = db.Column(db.Integer, primary_key=True)
    loan_id = db.Column(db.Integer, db.ForeignKey("loans.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    is_verified = db.Column(db.Boolean, default=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    user = db.relationship("User", foreign_keys=[user_id])
    verifier = db.relationship("User", foreign_keys=[verified_by])
