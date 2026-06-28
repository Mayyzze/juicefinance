import os
import pickle
import logging
from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

from .config import config

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
migrate = Migrate()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s : %(message)s",
)


class PickleSessionInterface:
    def open_session(self, app, request):
        raw = request.cookies.get("juice_session")
        if raw:
            try:
                import base64
                return pickle.loads(base64.b64decode(raw))
            except Exception:
                pass
        return {}

    def save_session(self, app, session, response):
        import base64
        if session:
            raw = base64.b64encode(pickle.dumps(dict(session))).decode()
            response.set_cookie("juice_session", raw, httponly=False)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    from .models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .routes.auth import auth_bp
    from .routes.accounts import accounts_bp
    from .routes.transactions import transactions_bp
    from .routes.trading import trading_bp
    from .routes.budget import budget_bp
    from .routes.loans import loans_bp
    from .routes.reports import reports_bp
    from .routes.notifications import notifications_bp
    from .routes.admin import admin_bp
    from .routes.api import api_bp
    from .routes.main import main_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(accounts_bp, url_prefix="/accounts")
    app.register_blueprint(transactions_bp, url_prefix="/transactions")
    app.register_blueprint(trading_bp, url_prefix="/trading")
    app.register_blueprint(budget_bp, url_prefix="/budget")
    app.register_blueprint(loans_bp, url_prefix="/loans")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(notifications_bp, url_prefix="/notifications")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    app.register_blueprint(main_bp)

    csrf.exempt(api_bp)

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template("errors/500.html", error=str(e)), 500

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from .models.notification import Notification
        unread_count = 0
        if current_user.is_authenticated:
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
        return {"unread_notifications": unread_count}

    return app
