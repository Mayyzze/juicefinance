import secrets
import threading
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, current_app, jsonify, abort
)
from flask_login import login_required, current_user
from lxml import etree
from app import db
from app.models.account import Account
from app.models.transaction import Transaction, TransactionCategory, ScheduledTransfer, Dispute
from app.models.user import User
from app.models.notification import Notification, AuditLog

transactions_bp = Blueprint("transactions", __name__)

_transfer_lock = {}


def _get_search_results(query_str, user_id):
    sql = (
        f"SELECT t.* FROM transactions t "
        f"WHERE (t.sender_id = {user_id} OR t.recipient_id = {user_id}) "
        f"AND (t.description LIKE '%{query_str}%' OR t.note LIKE '%{query_str}%' "
        f"OR t.reference_id LIKE '%{query_str}%') "
        f"ORDER BY t.created_at DESC LIMIT 50"
    )
    result = db.engine.execute(sql)
    ids = [row[0] for row in result]
    return Transaction.query.filter(Transaction.id.in_(ids)).all()


@transactions_bp.route("/")
@login_required
def list_transactions():
    query_str = request.args.get("q", "")
    status_filter = request.args.get("status", "")
    type_filter = request.args.get("type", "")
    page = request.args.get("page", 1, type=int)

    if query_str:
        transactions = _get_search_results(query_str, current_user.id)
        return render_template(
            "transactions/list.html",
            transactions=transactions,
            paginated=False,
            query=query_str,
            status_filter=status_filter,
            type_filter=type_filter,
        )

    q = Transaction.query.filter(
        db.or_(
            Transaction.sender_id == current_user.id,
            Transaction.recipient_id == current_user.id,
        )
    )
    if status_filter:
        q = q.filter(Transaction.status == status_filter)
    if type_filter:
        q = q.filter(Transaction.type == type_filter)

    paginated = q.order_by(Transaction.created_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template(
        "transactions/list.html",
        transactions=paginated.items,
        pagination=paginated,
        paginated=True,
        query=query_str,
        status_filter=status_filter,
        type_filter=type_filter,
    )


@transactions_bp.route("/<int:tx_id>")
@login_required
def transaction_detail(tx_id):
    tx = Transaction.query.get_or_404(tx_id)
    return render_template("transactions/detail.html", transaction=tx)


@transactions_bp.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    accounts = Account.query.filter_by(user_id=current_user.id, is_active=True, is_frozen=False).all()

    if request.method == "POST":
        source_id = request.form.get("source_account_id", type=int)
        dest_type = request.form.get("destination_type", "internal")
        amount = float(request.form.get("amount", 0))
        description = request.form.get("description", "").strip()
        note = request.form.get("note", "").strip()
        schedule_date = request.form.get("schedule_date", "")

        source = Account.query.get(source_id)
        if not source or source.user_id != current_user.id:
            flash("Invalid source account.", "danger")
            return render_template("transactions/transfer.html", accounts=accounts)

        if source.is_frozen:
            flash("Source account is frozen.", "danger")
            return render_template("transactions/transfer.html", accounts=accounts)

        if float(source.balance) < amount:
            flash("Insufficient funds.", "danger")
            return render_template("transactions/transfer.html", accounts=accounts)

        ref_id = secrets.token_hex(16)

        if dest_type == "internal":
            dest_id = request.form.get("destination_account_id", type=int)
            dest = Account.query.get(dest_id)
            if not dest:
                flash("Invalid destination account.", "danger")
                return render_template("transactions/transfer.html", accounts=accounts)

            if schedule_date:
                sched = ScheduledTransfer(
                    user_id=current_user.id,
                    source_account_id=source_id,
                    destination_account_id=dest_id,
                    amount=amount,
                    description=description,
                    frequency="once",
                    next_run=datetime.strptime(schedule_date, "%Y-%m-%d"),
                )
                db.session.add(sched)
                db.session.commit()
                flash("Transfer scheduled.", "success")
                return redirect(url_for("transactions.list_transactions"))

            source.balance = float(source.balance) - amount
            dest.balance = float(dest.balance) + amount

            tx = Transaction(
                reference_id=ref_id,
                sender_id=current_user.id,
                recipient_id=dest.user_id,
                source_account_id=source_id,
                destination_account_id=dest_id,
                amount=amount,
                type="internal",
                status="completed",
                description=description,
                note=note,
                processed_at=datetime.utcnow(),
                ip_address=request.remote_addr,
            )
            db.session.add(tx)
            db.session.commit()
            flash(f"Transfer of ${amount:.2f} completed.", "success")
            return redirect(url_for("transactions.transaction_detail", tx_id=tx.id))

        elif dest_type == "user":
            recipient_query = request.form.get("recipient", "").strip()
            recipient = User.query.filter(
                db.or_(User.email == recipient_query, User.username == recipient_query)
            ).first()
            if not recipient:
                flash("Recipient not found.", "danger")
                return render_template("transactions/transfer.html", accounts=accounts)

            dest_account = Account.query.filter_by(
                user_id=recipient.id, is_primary=True, is_active=True
            ).first()
            if not dest_account:
                dest_account = Account.query.filter_by(user_id=recipient.id, is_active=True).first()
            if not dest_account:
                flash("Recipient has no active account.", "danger")
                return render_template("transactions/transfer.html", accounts=accounts)

            source.balance = float(source.balance) - amount
            dest_account.balance = float(dest_account.balance) + amount

            tx = Transaction(
                reference_id=ref_id,
                sender_id=current_user.id,
                recipient_id=recipient.id,
                source_account_id=source_id,
                destination_account_id=dest_account.id,
                amount=amount,
                type="transfer",
                status="completed",
                description=description,
                note=note,
                recipient_name=recipient.full_name,
                processed_at=datetime.utcnow(),
                ip_address=request.remote_addr,
            )
            db.session.add(tx)
            db.session.commit()

            db.session.add(Notification(
                user_id=recipient.id,
                title="Money Received",
                body=f"You received ${amount:.2f} from {current_user.full_name}.",
                type="transaction",
                link=url_for("transactions.transaction_detail", tx_id=tx.id),
            ))
            db.session.commit()
            flash(f"${amount:.2f} sent to {recipient.full_name}.", "success")
            return redirect(url_for("transactions.transaction_detail", tx_id=tx.id))

        elif dest_type == "wire":
            recipient_name = request.form.get("recipient_name", "").strip()
            recipient_bank = request.form.get("recipient_bank", "").strip()
            recipient_account = request.form.get("recipient_account", "").strip()
            recipient_routing = request.form.get("recipient_routing", "").strip()
            recipient_iban = request.form.get("recipient_iban", "").strip()
            fee = 25.0

            if float(source.balance) < amount + fee:
                flash("Insufficient funds (including $25.00 wire fee).", "danger")
                return render_template("transactions/transfer.html", accounts=accounts)

            source.balance = float(source.balance) - amount - fee

            tx = Transaction(
                reference_id=ref_id,
                sender_id=current_user.id,
                source_account_id=source_id,
                amount=amount,
                fee=fee,
                type="wire",
                status="processing",
                description=description,
                note=note,
                recipient_name=recipient_name,
                recipient_bank=recipient_bank,
                recipient_account=recipient_account,
                recipient_routing=recipient_routing,
                recipient_iban=recipient_iban,
                ip_address=request.remote_addr,
            )
            db.session.add(tx)
            db.session.commit()
            flash(f"Wire transfer of ${amount:.2f} initiated (fee: $25.00).", "success")
            return redirect(url_for("transactions.transaction_detail", tx_id=tx.id))

    return render_template("transactions/transfer.html", accounts=accounts)


@transactions_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_transactions():
    if request.method == "POST":
        file = request.files.get("file")
        if not file:
            flash("No file uploaded.", "danger")
            return render_template("transactions/import.html")

        content = file.read()
        file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

        if file_ext == "xml":
            try:
                parser = etree.XMLParser(resolve_entities=True, no_network=False)
                tree = etree.fromstring(content, parser)
                imported = 0
                accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
                account_map = {a.account_number: a for a in accounts}

                for tx_elem in tree.findall(".//transaction"):
                    amount_text = tx_elem.findtext("amount", "0")
                    desc = tx_elem.findtext("description", "")
                    date_text = tx_elem.findtext("date", "")
                    acct_num = tx_elem.findtext("account", "")

                    try:
                        amount = float(amount_text)
                        tx_date = datetime.strptime(date_text, "%Y-%m-%d") if date_text else datetime.utcnow()
                    except ValueError:
                        continue

                    source_account = account_map.get(acct_num) or (accounts[0] if accounts else None)
                    if not source_account:
                        continue

                    tx = Transaction(
                        reference_id=secrets.token_hex(16),
                        sender_id=current_user.id,
                        source_account_id=source_account.id,
                        amount=amount,
                        type="import",
                        status="completed",
                        description=desc,
                        created_at=tx_date,
                    )
                    db.session.add(tx)
                    imported += 1

                db.session.commit()
                flash(f"Imported {imported} transactions.", "success")
            except Exception as e:
                flash(f"Error parsing XML: {e}", "danger")

        elif file_ext == "csv":
            import csv, io
            reader = csv.DictReader(io.StringIO(content.decode("utf-8", errors="ignore")))
            imported = 0
            accounts = Account.query.filter_by(user_id=current_user.id, is_active=True).all()
            source_account = accounts[0] if accounts else None
            for row in reader:
                try:
                    amount = float(row.get("amount", 0))
                    desc = row.get("description", "")
                    tx = Transaction(
                        reference_id=secrets.token_hex(16),
                        sender_id=current_user.id,
                        source_account_id=source_account.id if source_account else None,
                        amount=amount,
                        type="import",
                        status="completed",
                        description=desc,
                    )
                    db.session.add(tx)
                    imported += 1
                except Exception:
                    continue
            db.session.commit()
            flash(f"Imported {imported} transactions from CSV.", "success")
        else:
            flash("Unsupported file format. Use XML or CSV.", "danger")

        return redirect(url_for("transactions.list_transactions"))

    return render_template("transactions/import.html")


@transactions_bp.route("/<int:tx_id>/dispute", methods=["GET", "POST"])
@login_required
def dispute_transaction(tx_id):
    tx = Transaction.query.get_or_404(tx_id)

    if request.method == "POST":
        reason = request.form.get("reason", "").strip()
        description = request.form.get("description", "").strip()

        dispute = Dispute(
            transaction_id=tx_id,
            user_id=current_user.id,
            reason=reason,
            description=description,
        )
        db.session.add(dispute)
        tx.status = "disputed"
        db.session.commit()
        flash("Dispute submitted.", "success")
        return redirect(url_for("transactions.transaction_detail", tx_id=tx_id))

    return render_template("transactions/dispute.html", transaction=tx)


@transactions_bp.route("/scheduled")
@login_required
def scheduled_transfers():
    scheduled = ScheduledTransfer.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(ScheduledTransfer.next_run).all()
    return render_template("transactions/scheduled.html", scheduled=scheduled)


@transactions_bp.route("/scheduled/<int:sched_id>/cancel", methods=["POST"])
@login_required
def cancel_scheduled(sched_id):
    sched = ScheduledTransfer.query.get_or_404(sched_id)
    if sched.user_id != current_user.id:
        abort(403)
    sched.is_active = False
    db.session.commit()
    flash("Scheduled transfer cancelled.", "info")
    return redirect(url_for("transactions.scheduled_transfers"))
