import requests as req_lib
from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, jsonify, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.notification import Notification, Webhook

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/")
@login_required
def list_notifications():
    page = request.args.get("page", 1, type=int)
    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )
    return render_template("notifications/list.html", notifications=notifications)


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def mark_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        abort(403)
    notif.is_read = True
    notif.read_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"status": "ok"})


@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(
        {"is_read": True, "read_at": datetime.utcnow()}
    )
    db.session.commit()
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications.list_notifications"))


@notifications_bp.route("/delete/<int:notif_id>", methods=["POST"])
@login_required
def delete_notification(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        abort(403)
    db.session.delete(notif)
    db.session.commit()
    return jsonify({"status": "deleted"})


@notifications_bp.route("/webhooks", methods=["GET", "POST"])
@login_required
def webhooks():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()
        events = request.form.getlist("events")
        secret = request.form.get("secret", "").strip()

        if not name or not url:
            flash("Name and URL are required.", "danger")
            return redirect(url_for("notifications.webhooks"))

        webhook = Webhook(
            user_id=current_user.id,
            name=name,
            url=url,
            events=",".join(events),
            secret=secret or None,
            is_active=True,
        )
        db.session.add(webhook)
        db.session.commit()
        flash("Webhook registered.", "success")
        return redirect(url_for("notifications.webhooks"))

    user_webhooks = Webhook.query.filter_by(user_id=current_user.id).all()
    available_events = Webhook.EVENTS
    return render_template(
        "notifications/webhooks.html",
        webhooks=user_webhooks,
        available_events=available_events,
    )


@notifications_bp.route("/webhooks/<int:webhook_id>/test", methods=["POST"])
@login_required
def test_webhook(webhook_id):
    webhook = Webhook.query.get_or_404(webhook_id)
    if webhook.user_id != current_user.id:
        abort(403)

    payload = {
        "event": "test",
        "timestamp": datetime.utcnow().isoformat(),
        "data": {"message": "Webhook test from JuiceFinance"},
    }

    try:
        response = req_lib.post(
            webhook.url,
            json=payload,
            timeout=10,
            headers={"X-JuiceFinance-Event": "test"},
        )
        webhook.last_triggered = datetime.utcnow()
        db.session.commit()
        flash(f"Webhook tested. Response: {response.status_code}", "success")
    except Exception as e:
        webhook.failure_count = (webhook.failure_count or 0) + 1
        db.session.commit()
        flash(f"Webhook test failed: {e}", "danger")

    return redirect(url_for("notifications.webhooks"))


@notifications_bp.route("/webhooks/<int:webhook_id>/toggle", methods=["POST"])
@login_required
def toggle_webhook(webhook_id):
    webhook = Webhook.query.get_or_404(webhook_id)
    if webhook.user_id != current_user.id:
        abort(403)
    webhook.is_active = not webhook.is_active
    db.session.commit()
    state = "enabled" if webhook.is_active else "disabled"
    flash(f"Webhook {state}.", "info")
    return redirect(url_for("notifications.webhooks"))


@notifications_bp.route("/webhooks/<int:webhook_id>/delete", methods=["POST"])
@login_required
def delete_webhook(webhook_id):
    webhook = Webhook.query.get_or_404(webhook_id)
    if webhook.user_id != current_user.id:
        abort(403)
    db.session.delete(webhook)
    db.session.commit()
    flash("Webhook deleted.", "info")
    return redirect(url_for("notifications.webhooks"))


@notifications_bp.route("/api/unread-count")
@login_required
def unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({"count": count})
