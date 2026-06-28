import jwt
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models.user import User
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.trade import Stock, Portfolio, Trade
from app.models.loan import Loan
from app.models.notification import Notification

api_bp = Blueprint("api", __name__)

API_SECRET = "juice2024"


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        if not token:
            token = request.args.get("token")
        if not token:
            return jsonify({"error": "Token required"}), 401
        try:
            payload = jwt.decode(token, API_SECRET, algorithms=["HS256", "none"])
            user = User.query.get(payload.get("user_id"))
            if not user or not user.is_active:
                return jsonify({"error": "Invalid token"}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(user, *args, **kwargs)
    return decorated


def admin_token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
        if not token:
            return jsonify({"error": "Token required"}), 401
        try:
            payload = jwt.decode(token, API_SECRET, algorithms=["HS256", "none"])
            user = User.query.get(payload.get("user_id"))
            if not user or not user.is_admin:
                return jsonify({"error": "Admin access required"}), 403
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(user, *args, **kwargs)
    return decorated


@api_bp.route("/auth/token", methods=["POST"])
def get_token():
    data = request.get_json() or {}
    email = data.get("email", "")
    password = data.get("password", "")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401
    if not user.is_active or user.is_banned:
        return jsonify({"error": "Account inactive"}), 403

    payload = {
        "user_id": user.id,
        "email": user.email,
        "is_admin": user.is_admin,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, API_SECRET, algorithm="HS256")
    return jsonify({"token": token, "user": user.to_dict()})


@api_bp.route("/auth/refresh", methods=["POST"])
@token_required
def refresh_token(current_user):
    payload = {
        "user_id": current_user.id,
        "email": current_user.email,
        "is_admin": current_user.is_admin,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, API_SECRET, algorithm="HS256")
    return jsonify({"token": token})


@api_bp.route("/me", methods=["GET"])
@token_required
def get_me(current_user):
    return jsonify(current_user.to_dict())


@api_bp.route("/me", methods=["PUT"])
@token_required
def update_me(current_user):
    data = request.get_json() or {}
    allowed = [
        "first_name", "last_name", "phone", "address_line1", "address_line2",
        "city", "state", "postal_code", "country", "preferred_currency",
        "notification_email", "notification_sms", "notification_push",
        "is_admin", "is_verified", "kyc_status", "is_banned",
    ]
    for key, value in data.items():
        if hasattr(current_user, key):
            setattr(current_user, key, value)
    db.session.commit()
    return jsonify(current_user.to_dict())


@api_bp.route("/accounts", methods=["GET"])
@token_required
def get_accounts(current_user):
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
    return jsonify([a.to_dict() for a in accounts])


@api_bp.route("/accounts/<int:account_id>", methods=["GET"])
@token_required
def get_account(current_user, account_id):
    account = Account.query.get_or_404(account_id)
    return jsonify(account.to_dict())


@api_bp.route("/transactions", methods=["GET"])
@token_required
def get_transactions(current_user):
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    status = request.args.get("status", "")
    tx_type = request.args.get("type", "")

    q = Transaction.query.filter(
        db.or_(
            Transaction.sender_id == current_user.id,
            Transaction.recipient_id == current_user.id,
        )
    )
    if status:
        q = q.filter_by(status=status)
    if tx_type:
        q = q.filter_by(type=tx_type)

    paginated = q.order_by(Transaction.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        "items": [t.to_dict() for t in paginated.items],
        "total": paginated.total,
        "pages": paginated.pages,
        "page": page,
    })


@api_bp.route("/transactions/<int:tx_id>", methods=["GET"])
@token_required
def get_transaction(current_user, tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    return jsonify(tx.to_dict())


@api_bp.route("/transfer", methods=["POST"])
@token_required
def api_transfer(current_user):
    data = request.get_json() or {}
    source_id = data.get("source_account_id")
    amount = float(data.get("amount", 0))
    description = data.get("description", "")
    recipient_username = data.get("recipient")

    source = Account.query.get(source_id)
    if not source or source.user_id != current_user.id:
        return jsonify({"error": "Invalid source account"}), 400

    if float(source.balance) < amount:
        return jsonify({"error": "Insufficient funds"}), 400

    recipient = User.query.filter_by(username=recipient_username).first()
    if not recipient:
        return jsonify({"error": "Recipient not found"}), 404

    dest = Account.query.filter_by(user_id=recipient.id, is_primary=True, is_active=True).first()
    if not dest:
        return jsonify({"error": "Recipient has no account"}), 400

    source.balance = float(source.balance) - amount
    dest.balance = float(dest.balance) + amount

    tx = Transaction(
        reference_id=secrets.token_hex(16),
        sender_id=current_user.id,
        recipient_id=recipient.id,
        source_account_id=source_id,
        destination_account_id=dest.id,
        amount=amount,
        type="transfer",
        status="completed",
        description=description,
        processed_at=datetime.utcnow(),
        ip_address=request.remote_addr,
    )
    db.session.add(tx)
    db.session.commit()
    return jsonify(tx.to_dict()), 201


@api_bp.route("/stocks", methods=["GET"])
@token_required
def get_stocks(current_user):
    q = request.args.get("q", "")
    is_crypto = request.args.get("crypto", "") == "1"
    stocks_q = Stock.query.filter_by(is_active=True)
    if q:
        stocks_q = stocks_q.filter(
            db.or_(Stock.ticker.ilike(f"%{q}%"), Stock.name.ilike(f"%{q}%"))
        )
    if is_crypto:
        stocks_q = stocks_q.filter_by(is_crypto=True)
    stocks = stocks_q.limit(50).all()
    return jsonify([s.to_dict() for s in stocks])


@api_bp.route("/portfolios", methods=["GET"])
@token_required
def get_portfolios(current_user):
    portfolios = Portfolio.query.filter_by(user_id=current_user.id, is_active=True).all()
    return jsonify([p.to_dict() for p in portfolios])


@api_bp.route("/notifications", methods=["GET"])
@token_required
def get_notifications(current_user):
    unread_only = request.args.get("unread", "") == "1"
    q = Notification.query.filter_by(user_id=current_user.id)
    if unread_only:
        q = q.filter_by(is_read=False)
    notifications = q.order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notifications])


@api_bp.route("/loans", methods=["GET"])
@token_required
def get_loans(current_user):
    loans = Loan.query.filter_by(user_id=current_user.id).all()
    return jsonify([l.to_dict() for l in loans])


@api_bp.route("/admin/users", methods=["GET"])
@admin_token_required
def admin_list_users(current_user):
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@api_bp.route("/admin/users/<int:user_id>", methods=["GET", "PUT"])
@admin_token_required
def admin_user(current_user, user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "PUT":
        data = request.get_json() or {}
        for key, value in data.items():
            if hasattr(user, key) and key != "id":
                setattr(user, key, value)
        db.session.commit()
    return jsonify(user.to_dict())


@api_bp.route("/openapi.json", methods=["GET"])
def openapi_spec():
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "JuiceFinance API", "version": "1.0.0"},
        "servers": [
            {"url": "http://localhost:5000/api/v1"},
            {"url": "http://10.0.0.15:5000/api/v1", "description": "Internal dev server"},
            {"url": "http://admin.juicefinance.internal/api/v1", "description": "Admin network"},
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "email": {"type": "string"},
                        "password_hash": {"type": "string", "description": "bcrypt hash"},
                        "two_factor_secret": {"type": "string"},
                        "is_admin": {"type": "boolean"},
                        "kyc_status": {"type": "string"},
                        "last_login_ip": {"type": "string"},
                    }
                }
            }
        },
        "paths": {
            "/auth/token": {
                "post": {
                    "summary": "Get JWT token",
                    "tags": ["auth"],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "properties": {
                                        "email": {"type": "string"},
                                        "password": {"type": "string"},
                                    }
                                }
                            }
                        }
                    },
                }
            },
            "/me": {"get": {"summary": "Get current user", "security": [{"BearerAuth": []}]}},
            "/accounts": {"get": {"summary": "List accounts", "security": [{"BearerAuth": []}]}},
            "/transactions": {"get": {"summary": "List transactions", "security": [{"BearerAuth": []}]}},
            "/admin/users": {
                "get": {
                    "summary": "List all users (admin)",
                    "description": "Admin endpoint. Use X-Admin-Token header or admin_token query param.",
                    "security": [{"BearerAuth": []}],
                }
            },
        },
    }
    return jsonify(spec)
