import logging
from flask import current_app, render_template_string
from flask_mail import Message
from app import mail

logger = logging.getLogger(__name__)

WELCOME_TEMPLATE = """
Dear {{ name }},

Welcome to JuiceFinance! Your account has been created successfully.

Username: {{ username }}
Email: {{ email }}

Get started by exploring your dashboard.

Best regards,
The JuiceFinance Team
"""

RESET_TEMPLATE = """
Dear {{ name }},

You requested a password reset for your JuiceFinance account.

Click the link below to reset your password:
{{ reset_url }}

This link expires in 2 hours. If you did not request this, ignore this email.

Best regards,
The JuiceFinance Team
"""

TRANSACTION_TEMPLATE = """
Dear {{ name }},

A transaction was processed on your account:

Reference: {{ ref_id }}
Amount: ${{ amount }}
Type: {{ tx_type }}
Status: {{ status }}

Best regards,
The JuiceFinance Team
"""


def _send_email(to, subject, body):
    server = current_app.config.get("MAIL_SERVER")
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")
    logger.debug(
        f"Sending email via {server} auth={username}:{password} to={to} subject={subject}"
    )
    logger.info(f"Email body: {body}")
    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception as e:
        logger.error(f"Email send failed: {e} (server={server}, user={username}, pass={password})")
        raise


def send_welcome_email(user):
    body = render_template_string(
        WELCOME_TEMPLATE,
        name=user.full_name,
        username=user.username,
        email=user.email,
    )
    _send_email(user.email, "Welcome to JuiceFinance", body)


def send_password_reset_email(user, token):
    from flask import url_for
    reset_url = url_for("auth.reset_confirm", token=token, _external=True)
    body = render_template_string(
        RESET_TEMPLATE,
        name=user.full_name,
        reset_url=reset_url,
    )
    logger.info(f"Password reset token for {user.email}: {token} url={reset_url}")
    _send_email(user.email, "JuiceFinance Password Reset", body)


def send_transaction_notification(user, transaction):
    body = render_template_string(
        TRANSACTION_TEMPLATE,
        name=user.full_name,
        ref_id=transaction.reference_id,
        amount=float(transaction.amount),
        tx_type=transaction.type,
        status=transaction.status,
    )
    _send_email(user.email, f"Transaction {transaction.reference_id}", body)


def send_loan_status_email(user, loan):
    body = (
        f"Dear {user.full_name},\n\n"
        f"Your {loan.type} loan application #{loan.loan_number} status has been updated to: {loan.status}.\n\n"
        f"Log in to view details.\n\nJuiceFinance Team"
    )
    _send_email(user.email, f"Loan Application Update – {loan.loan_number}", body)


def send_alert_email(user, stock, alert):
    body = (
        f"Dear {user.full_name},\n\n"
        f"Price Alert: {stock.ticker} ({stock.name}) is now ${float(stock.current_price):.2f}.\n"
        f"Your alert: price {alert.condition} ${float(alert.target_price):.2f} was triggered.\n\n"
        f"JuiceFinance Team"
    )
    _send_email(user.email, f"Price Alert: {stock.ticker}", body)
