from datetime import datetime
from app import db


class AccountType(db.Model):
    __tablename__ = "account_types"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    interest_rate = db.Column(db.Numeric(5, 4), default=0.0)
    min_balance = db.Column(db.Numeric(12, 2), default=0.0)
    monthly_fee = db.Column(db.Numeric(8, 2), default=0.0)
    overdraft_limit = db.Column(db.Numeric(12, 2), default=0.0)
    is_active = db.Column(db.Boolean, default=True)

    accounts = db.relationship("Account", backref="account_type", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "interest_rate": float(self.interest_rate),
            "min_balance": float(self.min_balance),
            "monthly_fee": float(self.monthly_fee),
            "overdraft_limit": float(self.overdraft_limit),
        }


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    account_type_id = db.Column(db.Integer, db.ForeignKey("account_types.id"), nullable=False)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    routing_number = db.Column(db.String(9), default="021000021")
    iban = db.Column(db.String(34))
    swift_bic = db.Column(db.String(11), default="JUICEFINXXX")
    balance = db.Column(db.Numeric(15, 2), default=0.0)
    currency = db.Column(db.String(3), default="USD")
    nickname = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    is_frozen = db.Column(db.Boolean, default=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime)
    last_transaction_at = db.Column(db.DateTime)

    transactions_from = db.relationship(
        "Transaction", backref="source_account",
        foreign_keys="Transaction.source_account_id", lazy="dynamic"
    )
    transactions_to = db.relationship(
        "Transaction", backref="destination_account",
        foreign_keys="Transaction.destination_account_id", lazy="dynamic"
    )

    @property
    def display_number(self):
        return f"****{self.account_number[-4:]}"

    @property
    def type_name(self):
        return self.account_type.name if self.account_type else "Unknown"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "account_number": self.account_number,
            "display_number": self.display_number,
            "routing_number": self.routing_number,
            "iban": self.iban,
            "type": self.type_name,
            "balance": float(self.balance),
            "currency": self.currency,
            "nickname": self.nickname,
            "is_active": self.is_active,
            "is_frozen": self.is_frozen,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Account {self.account_number}>"


class LinkedExternalAccount(db.Model):
    __tablename__ = "linked_external_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    institution_name = db.Column(db.String(255), nullable=False)
    account_name = db.Column(db.String(255))
    account_number_last4 = db.Column(db.String(4), nullable=False)
    routing_number = db.Column(db.String(9))
    account_type = db.Column(db.String(20))
    plaid_access_token = db.Column(db.String(255))
    plaid_account_id = db.Column(db.String(255))
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)

    user = db.relationship("User", backref="linked_accounts")

    def to_dict(self):
        return {
            "id": self.id,
            "institution_name": self.institution_name,
            "account_name": self.account_name,
            "account_number_last4": self.account_number_last4,
            "account_type": self.account_type,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
