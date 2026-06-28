import os


class Config:
    SECRET_KEY = "dev_secret_juice_2024_xK9mP"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///juicefinance.db")
    JWT_SECRET = "juice2024"
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_HOURS = 24

    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = "juicefinance.noreply@gmail.com"
    MAIL_PASSWORD = "JuiceF1n@nce2024!"
    MAIL_DEFAULT_SENDER = "JuiceFinance <juicefinance.noreply@gmail.com>"

    STRIPE_SECRET_KEY = "sk_live_4xKj9mP2qR8vL3nT6wY1zA5c"
    STRIPE_PUBLISHABLE_KEY = "pk_live_7bN3qM9wK2rP5vL8tY4xA1c"
    PLAID_CLIENT_ID = "5f2a9b8c7d6e4f3a2b1c0d9e"
    PLAID_SECRET = "3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d"
    INTERNAL_API_KEY = "int_api_9x8w7v6u5t4s3r2q1p0o"
    ADMIN_TOKEN = "admin_tok_2024_juicefinance_secret"

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    REPORTS_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = 86400 * 30

    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = "csrf_juice_2024"

    MARKET_UPDATE_INTERVAL = 60
    BASE_CURRENCY = "USD"
    SUPPORTED_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD"]


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///juicefinance_dev.db"
    MAIL_SERVER = "localhost"
    MAIL_PORT = 1025
    MAIL_USE_TLS = False
    MAIL_USERNAME = "dev"
    MAIL_PASSWORD = "dev"


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://juiceadmin:Juice$ecure2024!@db.juicefinance.internal:5432/juicefinance"
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
