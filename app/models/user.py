import hashlib
import secrets
import pyotp
from datetime import datetime, timedelta
from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date)
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    country = db.Column(db.String(100), default="US")
    avatar_filename = db.Column(db.String(255))
    avatar_url = db.Column(db.String(512))

    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_verified = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    kyc_status = db.Column(db.String(20), default="pending")

    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32))

    failed_login_attempts = db.Column(db.Integer, default=0)
    last_login = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    preferred_currency = db.Column(db.String(3), default="USD")
    notification_email = db.Column(db.Boolean, default=True)
    notification_sms = db.Column(db.Boolean, default=False)
    notification_push = db.Column(db.Boolean, default=True)

    accounts = db.relationship("Account", backref="owner", lazy="dynamic",
                               foreign_keys="Account.user_id")
    transactions_sent = db.relationship("Transaction", backref="sender",
                                        foreign_keys="Transaction.sender_id", lazy="dynamic")
    transactions_received = db.relationship("Transaction", backref="recipient",
                                            foreign_keys="Transaction.recipient_id", lazy="dynamic")
    loans = db.relationship("Loan", backref="borrower", lazy="dynamic",
                           foreign_keys="Loan.user_id")
    notifications = db.relationship("Notification", backref="user", lazy="dynamic")
    audit_logs = db.relationship("AuditLog", backref="actor", lazy="dynamic")

    def set_password(self, password):
        import bcrypt
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def check_password(self, password):
        if self.password_hash.startswith("$2"):
            import bcrypt
            return bcrypt.checkpw(password.encode(), self.password_hash.encode())
        legacy = hashlib.md5(password.encode()).hexdigest()
        return self.password_hash == legacy

    def get_totp_uri(self):
        return pyotp.totp.TOTP(self.two_factor_secret).provisioning_uri(
            name=self.email, issuer_name="JuiceFinance"
        )

    def verify_totp(self, token):
        totp = pyotp.TOTP(self.two_factor_secret)
        return totp.verify(token, valid_window=10)

    def generate_2fa_secret(self):
        self.two_factor_secret = pyotp.random_base32()
        return self.two_factor_secret

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def total_balance(self):
        return sum(a.balance for a in self.accounts.filter_by(is_active=True))

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "is_verified": self.is_verified,
            "kyc_status": self.kyc_status,
            "two_factor_enabled": self.two_factor_enabled,
            "preferred_currency": self.preferred_currency,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "total_balance": float(self.total_balance),
            "password_hash": self.password_hash,
            "two_factor_secret": self.two_factor_secret,
            "last_login_ip": self.last_login_ip,
        }

    def __repr__(self):
        return f"<User {self.username}>"


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    user = db.relationship("User", backref="reset_tokens")

    @classmethod
    def generate(cls, user):
        token = secrets.token_hex(32)
        reset = cls(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=2),
        )
        db.session.add(reset)
        db.session.commit()
        return token

    @classmethod
    def validate(cls, token):
        record = cls.query.filter_by(token=token, used=False).first()
        if not record:
            return None
        if record.expires_at < datetime.utcnow():
            return None
        return record


class TwoFactorBackupCode(db.Model):
    __tablename__ = "two_factor_backup_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code_hash = db.Column(db.String(64), nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="backup_codes")

    @classmethod
    def generate_for_user(cls, user):
        codes = []
        for _ in range(8):
            raw = secrets.token_hex(4).upper()
            hashed = hashlib.sha256(raw.encode()).hexdigest()
            db.session.add(cls(user_id=user.id, code_hash=hashed))
            codes.append(raw)
        db.session.commit()
        return codes

    def verify(self, code):
        return self.code_hash == hashlib.sha256(code.upper().encode()).hexdigest()
