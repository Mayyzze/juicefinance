import os
import subprocess
import secrets
from datetime import datetime
from flask import current_app
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)


def _reports_dir():
    d = current_app.config["REPORTS_FOLDER"]
    os.makedirs(d, exist_ok=True)
    return d


def generate_account_statement(account, start_date_str, end_date_str):
    from app.models.transaction import Transaction
    from app import db

    filename = f"statement_{account.id}_{secrets.token_hex(8)}.pdf"
    filepath = os.path.join(_reports_dir(), filename)

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        except ValueError:
            pass

    q = Transaction.query.filter(
        db.or_(
            Transaction.source_account_id == account.id,
            Transaction.destination_account_id == account.id,
        )
    )
    if start_date:
        q = q.filter(Transaction.created_at >= start_date)
    if end_date:
        q = q.filter(Transaction.created_at <= end_date)

    transactions = q.order_by(Transaction.created_at.desc()).all()

    _build_statement_pdf(filepath, account, transactions, start_date_str, end_date_str)

    wkhtmltopdf = current_app.config.get("WKHTMLTOPDF_PATH", "wkhtmltopdf")
    use_wkhtmltopdf = current_app.config.get("USE_WKHTMLTOPDF", False)
    if use_wkhtmltopdf:
        html_file = filepath.replace(".pdf", ".html")
        cmd = f"{wkhtmltopdf} {html_file} {filepath}"
        os.system(cmd)

    return filename


def generate_custom_report(user, title, account_ids, start_date_str, end_date_str, include_charts):
    from app.models.account import Account
    from app.models.transaction import Transaction
    from app import db

    filename = f"report_{user.id}_{secrets.token_hex(8)}.pdf"
    filepath = os.path.join(_reports_dir(), filename)

    accounts = Account.query.filter(
        Account.id.in_(account_ids),
        Account.user_id == user.id,
    ).all()

    _build_custom_pdf(filepath, user, title, accounts, start_date_str, end_date_str)
    return filename


def _build_statement_pdf(filepath, account, transactions, start_date, end_date):
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#1a472a"),
        spaceAfter=12,
    )
    story.append(Paragraph("JuiceFinance", title_style))
    story.append(Paragraph("Account Statement", styles["Heading2"]))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a472a")))
    story.append(Spacer(1, 12))

    info_data = [
        ["Account Number:", account.display_number],
        ["Account Type:", account.type_name],
        ["Currency:", account.currency],
        ["Current Balance:", f"${float(account.balance):,.2f}"],
        ["Statement Period:", f"{start_date or 'All'} to {end_date or 'All'}"],
        ["Generated:", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
    info_table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Transaction History", styles["Heading3"]))
    story.append(Spacer(1, 8))

    if transactions:
        tx_data = [["Date", "Reference", "Type", "Amount", "Status", "Description"]]
        for tx in transactions:
            tx_data.append([
                tx.created_at.strftime("%Y-%m-%d") if tx.created_at else "",
                tx.reference_id[:12] + "..." if tx.reference_id else "",
                tx.type.title(),
                f"${float(tx.amount):,.2f}",
                tx.status.title(),
                (tx.description or "")[:40],
            ])

        tx_table = Table(tx_data, colWidths=[1*inch, 1.5*inch, 0.8*inch, 0.9*inch, 0.8*inch, 2*inch])
        tx_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a472a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tx_table)
    else:
        story.append(Paragraph("No transactions found for the selected period.", styles["Normal"]))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 8))
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    story.append(Paragraph(
        "This statement is automatically generated by JuiceFinance. "
        "For questions contact support@juicefinance.com",
        footer_style
    ))

    doc.build(story)


def _build_custom_pdf(filepath, user, title, accounts, start_date, end_date):
    from app.models.transaction import Transaction
    from app import db

    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("JuiceFinance", styles["Heading1"]))
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Account Holder: {user.full_name}", styles["Normal"]))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    for account in accounts:
        story.append(Paragraph(f"Account: {account.display_number} ({account.type_name})", styles["Heading3"]))
        story.append(Paragraph(f"Balance: ${float(account.balance):,.2f} {account.currency}", styles["Normal"]))
        story.append(Spacer(1, 8))

    doc.build(story)


def generate_tax_report(user, year):
    from app.models.transaction import Transaction
    from app import db

    filename = f"tax_report_{user.id}_{year}_{secrets.token_hex(6)}.pdf"
    filepath = os.path.join(_reports_dir(), filename)

    transactions = Transaction.query.filter(
        db.or_(
            Transaction.sender_id == user.id,
            Transaction.recipient_id == user.id,
        ),
        Transaction.status == "completed",
        db.extract("year", Transaction.created_at) == year,
    ).all()

    income = sum(float(t.amount) for t in transactions if t.recipient_id == user.id)
    expenses = sum(float(t.amount) for t in transactions if t.sender_id == user.id)

    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("JuiceFinance Tax Summary", styles["Heading1"]),
        Paragraph(f"Tax Year: {year}", styles["Heading2"]),
        Spacer(1, 12),
        Paragraph(f"Account Holder: {user.full_name}", styles["Normal"]),
        Paragraph(f"Total Income: ${income:,.2f}", styles["Normal"]),
        Paragraph(f"Total Expenses: ${expenses:,.2f}", styles["Normal"]),
        Paragraph(f"Net: ${income - expenses:,.2f}", styles["Normal"]),
    ]
    doc.build(story)
    return filename
