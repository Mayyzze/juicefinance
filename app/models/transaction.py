from datetime import datetime
from app import db


class TransactionCategory(db.Model):
    __tablename__ = "transaction_categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), default="tag")
    color = db.Column(db.String(7), default="#6c757d")
    type = db.Column(db.String(10), default="expense")
    is_system = db.Column(db.Boolean, default=False)
    monthly_budget = db.Column(db.Numeric(12, 2))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="categories")
    transactions = db.relationship("Transaction", backref="category", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "type": self.type,
            "monthly_budget": float(self.monthly_budget) if self.monthly_budget else None,
        }


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.Integer, primary_key=True)
    reference_id = db.Column(db.String(32), unique=True, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    source_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    destination_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    category_id = db.Column(db.Integer, db.ForeignKey("transaction_categories.id"))
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    exchange_rate = db.Column(db.Numeric(10, 6), default=1.0)
    fee = db.Column(db.Numeric(10, 2), default=0.0)
    type = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default="pending")
    description = db.Column(db.String(500))
    note = db.Column(db.Text)
    tags = db.Column(db.String(255))
    recipient_name = db.Column(db.String(255))
    recipient_bank = db.Column(db.String(255))
    recipient_account = db.Column(db.String(50))
    recipient_routing = db.Column(db.String(20))
    recipient_iban = db.Column(db.String(34))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    scheduled_at = db.Column(db.DateTime)
    processed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    disputes = db.relationship("Dispute", backref="transaction", lazy="dynamic")

    TYPES = [
        "transfer", "deposit", "withdrawal", "payment", "refund",
        "fee", "interest", "wire", "ach", "internal"
    ]
    STATUSES = ["pending", "processing", "completed", "failed", "cancelled", "disputed"]

    def to_dict(self):
        return {
            "id": self.id,
            "reference_id": self.reference_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "fee": float(self.fee),
            "type": self.type,
            "status": self.status,
            "description": self.description,
            "note": self.note,
            "tags": self.tags,
            "recipient_name": self.recipient_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }

    def __repr__(self):
        return f"<Transaction {self.reference_id} ${self.amount}>"


class ScheduledTransfer(db.Model):
    __tablename__ = "scheduled_transfers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    destination_account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"))
    recipient_email = db.Column(db.String(255))
    recipient_account_number = db.Column(db.String(50))
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), default="USD")
    description = db.Column(db.String(500))
    frequency = db.Column(db.String(20), nullable=False)
    next_run = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    run_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="scheduled_transfers")
    source_account = db.relationship("Account", foreign_keys=[source_account_id])
    destination_account = db.relationship("Account", foreign_keys=[destination_account_id])


class Dispute(db.Model):
    __tablename__ = "disputes"

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey("transactions.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="open")
    resolution = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    user = db.relationship("User", backref="disputes")
