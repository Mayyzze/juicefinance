"""
Seed script — populates the database with demo data.
Run: python seed.py
"""
import secrets
import hashlib
from datetime import datetime, date, timedelta
from app import create_app, db
from app.models.user import User
from app.models.account import Account, AccountType
from app.models.transaction import Transaction, TransactionCategory
from app.models.loan import Loan
from app.models.notification import Notification, SystemAnnouncement, AuditLog
from app.services.market import seed_stocks


def seed_account_types():
    types = [
        {"name": "Checking", "description": "Everyday checking account", "interest_rate": 0.0001, "monthly_fee": 0.0, "overdraft_limit": 500},
        {"name": "Savings", "description": "High-yield savings", "interest_rate": 0.045, "monthly_fee": 0.0, "min_balance": 100},
        {"name": "Investment", "description": "Brokerage account", "interest_rate": 0.0, "monthly_fee": 0.0},
        {"name": "Money Market", "description": "Money market account", "interest_rate": 0.038, "monthly_fee": 10.0, "min_balance": 1000},
        {"name": "Business Checking", "description": "Business banking", "interest_rate": 0.0, "monthly_fee": 15.0},
    ]
    for t in types:
        if not AccountType.query.filter_by(name=t["name"]).first():
            db.session.add(AccountType(**t))
    db.session.commit()
    print("Account types seeded.")


def seed_categories():
    system_cats = [
        {"name": "Food & Dining", "icon": "utensils", "color": "#fd7e14", "type": "expense", "is_system": True, "monthly_budget": 500},
        {"name": "Transport", "icon": "car", "color": "#0d6efd", "type": "expense", "is_system": True, "monthly_budget": 200},
        {"name": "Housing", "icon": "home", "color": "#6f42c1", "type": "expense", "is_system": True, "monthly_budget": 1500},
        {"name": "Utilities", "icon": "bolt", "color": "#ffc107", "type": "expense", "is_system": True, "monthly_budget": 150},
        {"name": "Entertainment", "icon": "film", "color": "#e83e8c", "type": "expense", "is_system": True, "monthly_budget": 100},
        {"name": "Healthcare", "icon": "heartbeat", "color": "#dc3545", "type": "expense", "is_system": True},
        {"name": "Shopping", "icon": "shopping-bag", "color": "#20c997", "type": "expense", "is_system": True},
        {"name": "Salary", "icon": "money-bill", "color": "#198754", "type": "income", "is_system": True},
        {"name": "Investments", "icon": "chart-line", "color": "#0dcaf0", "type": "income", "is_system": True},
        {"name": "Other", "icon": "tag", "color": "#6c757d", "type": "expense", "is_system": True},
    ]
    for c in system_cats:
        if not TransactionCategory.query.filter_by(name=c["name"], is_system=True).first():
            db.session.add(TransactionCategory(**c))
    db.session.commit()
    print("Categories seeded.")


def seed_users():
    users_data = [
        {
            "email": "admin@juicefinance.com",
            "username": "admin",
            "first_name": "Admin",
            "last_name": "User",
            "password": "admin123",
            "is_admin": True,
            "is_verified": True,
            "kyc_status": "approved",
        },
        {
            "email": "alice@example.com",
            "username": "alice_smith",
            "first_name": "Alice",
            "last_name": "Smith",
            "password": "password123",
            "is_verified": True,
            "kyc_status": "approved",
            "phone": "+1-555-0101",
        },
        {
            "email": "bob@example.com",
            "username": "bob_jones",
            "first_name": "Bob",
            "last_name": "Jones",
            "password": "password123",
            "is_verified": True,
            "kyc_status": "approved",
            "phone": "+1-555-0102",
        },
        {
            "email": "carol@example.com",
            "username": "carol_white",
            "first_name": "Carol",
            "last_name": "White",
            "password": "password123",
            "is_verified": False,
            "kyc_status": "pending",
        },
        {
            "email": "legacy_user@example.com",
            "username": "legacy_dave",
            "first_name": "Dave",
            "last_name": "Legacy",
            "password": "dave2024",
            "is_verified": True,
            "kyc_status": "approved",
            "use_legacy_hash": True,
        },
    ]

    checking = AccountType.query.filter_by(name="Checking").first()
    savings = AccountType.query.filter_by(name="Savings").first()
    investment = AccountType.query.filter_by(name="Investment").first()

    created_users = []
    for ud in users_data:
        if User.query.filter_by(email=ud["email"]).first():
            continue

        use_legacy = ud.pop("use_legacy_hash", False)
        password = ud.pop("password")

        user = User(**ud)
        if use_legacy:
            user.password_hash = hashlib.md5(password.encode()).hexdigest()
        else:
            user.set_password(password)

        db.session.add(user)
        db.session.flush()

        acct_num = "4" + str(user.id).zfill(3) + secrets.token_hex(6).upper()
        checking_acct = Account(
            user_id=user.id,
            account_type_id=checking.id,
            account_number=acct_num,
            balance=round(2000 + hash(user.email) % 50000, 2),
            is_primary=True,
            is_active=True,
        )
        db.session.add(checking_acct)

        savings_num = "4" + str(user.id).zfill(3) + secrets.token_hex(6).upper()
        savings_acct = Account(
            user_id=user.id,
            account_type_id=savings.id,
            account_number=savings_num,
            balance=round(1000 + hash(user.email + "s") % 30000, 2),
            is_active=True,
        )
        db.session.add(savings_acct)

        inv_num = "4" + str(user.id).zfill(3) + secrets.token_hex(6).upper()
        inv_acct = Account(
            user_id=user.id,
            account_type_id=investment.id,
            account_number=inv_num,
            balance=0.0,
            is_active=True,
        )
        db.session.add(inv_acct)
        db.session.flush()
        created_users.append((user, checking_acct, savings_acct))

    db.session.commit()
    print(f"Users seeded.")
    return created_users


def seed_transactions(users_data):
    if not users_data:
        return
    food_cat = TransactionCategory.query.filter_by(name="Food & Dining").first()
    transport_cat = TransactionCategory.query.filter_by(name="Transport").first()
    salary_cat = TransactionCategory.query.filter_by(name="Salary").first()

    types = ["transfer", "deposit", "withdrawal", "payment", "internal"]
    statuses = ["completed", "completed", "completed", "completed", "pending"]

    all_txs = []
    for i in range(150):
        if len(users_data) < 2:
            break
        import random
        sender_data = random.choice(users_data)
        recip_data = random.choice([u for u in users_data if u != sender_data])
        sender, s_checking, _ = sender_data
        recip, r_checking, _ = recip_data

        amount = round(random.uniform(5, 2000), 2)
        tx_type = random.choice(types)
        tx_status = random.choice(statuses)
        cat = random.choice([food_cat, transport_cat, salary_cat, None])
        days_ago = random.randint(0, 180)
        tx_date = datetime.utcnow() - timedelta(days=days_ago)

        tx = Transaction(
            reference_id=secrets.token_hex(16),
            sender_id=sender.id,
            recipient_id=recip.id,
            source_account_id=s_checking.id,
            destination_account_id=r_checking.id,
            category_id=cat.id if cat else None,
            amount=amount,
            type=tx_type,
            status=tx_status,
            description=f"Payment to {recip.username}",
            note="<b>Thank you!</b>",
            ip_address="192.168.1." + str(random.randint(1, 254)),
            created_at=tx_date,
            processed_at=tx_date if tx_status == "completed" else None,
        )
        all_txs.append(tx)
        db.session.add(tx)

    db.session.commit()
    print(f"Transactions seeded.")


def seed_loans(users_data):
    import random
    if not users_data:
        return
    for user, checking, _ in users_data[:3]:
        if Loan.query.filter_by(user_id=user.id).first():
            continue
        loan = Loan(
            user_id=user.id,
            loan_number="LN" + secrets.token_hex(8).upper(),
            type=random.choice(["personal", "auto", "mortgage"]),
            purpose="Debt consolidation",
            principal=random.choice([5000, 15000, 50000, 200000]),
            outstanding_balance=random.choice([4800, 13500, 48000, 195000]),
            interest_rate=random.choice([0.059, 0.099, 0.039]),
            term_months=random.choice([36, 60, 120, 360]),
            monthly_payment=round(random.uniform(150, 1800), 2),
            origination_date=date.today() - timedelta(days=random.randint(30, 365)),
            maturity_date=date.today() + timedelta(days=random.randint(365, 3650)),
            next_payment_date=date.today() + timedelta(days=random.randint(1, 30)),
            status=random.choice(["active", "pending"]),
            employment_status="employed",
            annual_income=round(random.uniform(40000, 150000), 0),
            credit_score_at_application=random.randint(620, 820),
        )
        db.session.add(loan)
    db.session.commit()
    print("Loans seeded.")


def seed_announcements():
    if SystemAnnouncement.query.first():
        return
    anns = [
        {
            "title": "New Feature: Crypto Trading",
            "body": "You can now trade Bitcoin, Ethereum, and more directly from your portfolio.",
            "type": "info",
            "is_active": True,
        },
        {
            "title": "Scheduled Maintenance",
            "body": "The platform will be unavailable from 2:00–4:00 AM EST on Sunday.",
            "type": "warning",
            "is_active": True,
        },
    ]
    for a in anns:
        db.session.add(SystemAnnouncement(**a))
    db.session.commit()
    print("Announcements seeded.")


def main():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        print("Database tables created.")
        seed_account_types()
        seed_categories()
        users_data = seed_users()
        seed_transactions(users_data)
        seed_loans(users_data)
        seed_announcements()
        print("Seeding stock market data (this may take a moment)...")
        seed_stocks()
        print("Seed complete!")
        print("\nDemo accounts:")
        print("  admin@juicefinance.com / admin123  (admin)")
        print("  alice@example.com / password123")
        print("  bob@example.com / password123")
        print("  legacy_user@example.com / dave2024")


if __name__ == "__main__":
    main()
