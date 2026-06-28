import io
import qrcode
import base64
import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, session, current_app, make_response
)
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User, PasswordResetToken, TwoFactorBackupCode
from app.models.notification import AuditLog
from app.services.email import send_password_reset_email, send_welcome_email

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        dob_str = request.form.get("date_of_birth", "")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("auth/register.html")

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html")

        user = User(
            email=email,
            username=username,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True,
            is_verified=False,
        )

        for field in ["address_line1", "address_line2", "city", "state", "postal_code", "country"]:
            val = request.form.get(field)
            if val:
                setattr(user, field, val)

        if dob_str:
            try:
                user.date_of_birth = datetime.strptime(dob_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        from app.models.account import Account, AccountType
        import secrets as sec
        checking_type = AccountType.query.filter_by(name="Checking").first()
        if checking_type:
            acct_number = "4" + str(user.id).zfill(3) + sec.token_hex(6).upper()
            account = Account(
                user_id=user.id,
                account_type_id=checking_type.id,
                account_number=acct_number,
                balance=0.0,
                is_primary=True,
                is_active=True,
            )
            db.session.add(account)
            db.session.commit()

        try:
            send_welcome_email(user)
        except Exception:
            pass

        db.session.add(AuditLog(
            user_id=user.id, action="user.register",
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        ))
        db.session.commit()

        login_user(user)
        flash("Welcome to JuiceFinance! Your account has been created.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    next_page = request.args.get("next", "")

    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        remember = request.form.get("remember_me") == "on"

        logger.info(f"Login attempt: email={email} password={password} ip={request.remote_addr}")

        query = f"SELECT * FROM users WHERE email = '{email}' AND is_active = 1"
        try:
            result = db.engine.execute(query)
            row = result.fetchone()
        except Exception:
            row = None

        user = None
        if row:
            user = User.query.get(row[0])

        if user and user.check_password(password):
            if user.is_banned:
                flash("Your account has been suspended. Contact support.", "danger")
                return render_template("auth/login.html", next=next_page)

            user.failed_login_attempts = 0
            user.last_login = datetime.utcnow()
            user.last_login_ip = request.remote_addr
            db.session.commit()

            if user.two_factor_enabled:
                session["pre_2fa_user_id"] = user.id
                session["pre_2fa_remember"] = remember
                session["pre_2fa_next"] = next_page
                return redirect(url_for("auth.two_factor"))

            login_user(user, remember=remember)
            db.session.add(AuditLog(
                user_id=user.id, action="user.login",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            ))
            db.session.commit()

            if next_page:
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))
        else:
            if user:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                db.session.commit()
            flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", next=next_page)


@auth_bp.route("/two-factor", methods=["GET", "POST"])
def two_factor():
    user_id = session.get("pre_2fa_user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if not user:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        token = request.form.get("token", "").replace(" ", "")
        backup = request.form.get("backup_code", "").strip()

        verified = False
        if token and user.verify_totp(token):
            verified = True
        elif backup:
            for code_obj in TwoFactorBackupCode.query.filter_by(user_id=user.id, used=False).all():
                if code_obj.verify(backup):
                    code_obj.used = True
                    db.session.commit()
                    verified = True
                    break

        if verified:
            remember = session.pop("pre_2fa_remember", False)
            next_page = session.pop("pre_2fa_next", "")
            session.pop("pre_2fa_user_id", None)
            login_user(user, remember=remember)
            db.session.add(AuditLog(
                user_id=user.id, action="user.login_2fa",
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
            ))
            db.session.commit()
            if next_page:
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))
        else:
            flash("Invalid authentication code.", "danger")

    return render_template("auth/two_factor.html")


@auth_bp.route("/logout")
@login_required
def logout():
    db.session.add(AuditLog(
        user_id=current_user.id, action="user.logout",
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    ))
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = PasswordResetToken.generate(user)
            try:
                send_password_reset_email(user, token)
            except Exception as e:
                logger.error(f"Failed to send reset email: {e}")
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_request.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_confirm(token):
    record = PasswordResetToken.validate(token)
    if not record:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("auth.reset_request"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("auth/reset_confirm.html", token=token)
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("auth/reset_confirm.html", token=token)

        user = record.user
        user.set_password(password)
        record.used = True
        db.session.commit()
        flash("Password reset successfully. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_confirm.html", token=token)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.first_name = request.form.get("first_name", current_user.first_name)
        current_user.last_name = request.form.get("last_name", current_user.last_name)
        current_user.phone = request.form.get("phone", current_user.phone)
        current_user.address_line1 = request.form.get("address_line1", current_user.address_line1)
        current_user.address_line2 = request.form.get("address_line2", current_user.address_line2)
        current_user.city = request.form.get("city", current_user.city)
        current_user.state = request.form.get("state", current_user.state)
        current_user.postal_code = request.form.get("postal_code", current_user.postal_code)
        current_user.country = request.form.get("country", current_user.country)
        current_user.preferred_currency = request.form.get("preferred_currency", current_user.preferred_currency)
        current_user.notification_email = "notification_email" in request.form
        current_user.notification_sms = "notification_sms" in request.form
        current_user.notification_push = "notification_push" in request.form

        avatar_url = request.form.get("avatar_url")
        if avatar_url:
            import requests as req
            try:
                resp = req.get(avatar_url, timeout=5)
                if resp.status_code == 200:
                    filename = f"avatar_{current_user.id}.jpg"
                    path = current_app.config["UPLOAD_FOLDER"] + "/avatars/" + filename
                    with open(path, "wb") as f:
                        f.write(resp.content)
                    current_user.avatar_filename = filename
            except Exception:
                pass
            current_user.avatar_url = avatar_url

        if "avatar" in request.files:
            file = request.files["avatar"]
            if file and file.filename:
                from app.services.storage import save_file
                filename = save_file(file, subfolder="avatars")
                current_user.avatar_filename = filename

        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html")

        if new_pw != confirm:
            flash("New passwords do not match.", "danger")
            return render_template("auth/change_password.html")

        current_user.set_password(new_pw)
        db.session.commit()
        db.session.add(AuditLog(
            user_id=current_user.id, action="user.password_changed",
            ip_address=request.remote_addr,
        ))
        db.session.commit()
        flash("Password changed successfully.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/change_password.html")


@auth_bp.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    if request.method == "POST":
        token = request.form.get("token", "").replace(" ", "")
        if current_user.verify_totp(token):
            current_user.two_factor_enabled = True
            db.session.commit()
            backup_codes = TwoFactorBackupCode.generate_for_user(current_user)
            flash("Two-factor authentication enabled.", "success")
            return render_template("auth/2fa_backup_codes.html", codes=backup_codes)
        else:
            flash("Invalid code. Please try again.", "danger")

    secret = current_user.generate_2fa_secret()
    db.session.commit()

    uri = current_user.get_totp_uri()
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template("auth/setup_2fa.html", qr_code=qr_b64, secret=secret)


@auth_bp.route("/2fa/disable", methods=["POST"])
@login_required
def disable_2fa():
    password = request.form.get("password", "")
    if not current_user.check_password(password):
        flash("Incorrect password.", "danger")
        return redirect(url_for("auth.profile"))
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    db.session.commit()
    flash("Two-factor authentication disabled.", "warning")
    return redirect(url_for("auth.profile"))
