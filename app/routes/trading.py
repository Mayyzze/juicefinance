from datetime import datetime
from flask import (
    Blueprint, render_template, redirect, url_for, request,
    flash, jsonify, abort
)
from flask_login import login_required, current_user
from app import db
from app.models.trade import (
    Stock, Portfolio, PortfolioHolding, Trade, PriceAlert, Watchlist
)
from app.models.notification import Notification

trading_bp = Blueprint("trading", __name__)


@trading_bp.route("/")
@login_required
def portfolio_overview():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id, is_active=True).all()
    if not portfolios:
        portfolio = Portfolio(user_id=current_user.id, name="My Portfolio", cash_balance=0.0)
        db.session.add(portfolio)
        db.session.commit()
        portfolios = [portfolio]

    watchlist = (
        Watchlist.query.filter_by(user_id=current_user.id)
        .join(Stock)
        .filter(Stock.is_active == True)
        .all()
    )
    top_stocks = Stock.query.filter_by(is_active=True, is_crypto=False).limit(10).all()
    top_crypto = Stock.query.filter_by(is_active=True, is_crypto=True).limit(5).all()

    return render_template(
        "trading/portfolio.html",
        portfolios=portfolios,
        watchlist=watchlist,
        top_stocks=top_stocks,
        top_crypto=top_crypto,
    )


@trading_bp.route("/portfolio/<int:portfolio_id>")
@login_required
def portfolio_detail(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    holdings = portfolio.holdings.join(Stock).filter(Stock.is_active == True).all()
    recent_trades = portfolio.trades.order_by(Trade.created_at.desc()).limit(20).all()
    return render_template(
        "trading/portfolio_detail.html",
        portfolio=portfolio,
        holdings=holdings,
        recent_trades=recent_trades,
    )


@trading_bp.route("/portfolio/<int:portfolio_id>/fund", methods=["POST"])
@login_required
def fund_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    if portfolio.user_id != current_user.id:
        abort(403)
    amount = float(request.form.get("amount", 0))
    from app.models.account import Account
    account_id = request.form.get("account_id", type=int)
    account = Account.query.get(account_id)
    if not account or account.user_id != current_user.id:
        flash("Invalid account.", "danger")
        return redirect(url_for("trading.portfolio_detail", portfolio_id=portfolio_id))
    if float(account.balance) < amount:
        flash("Insufficient funds.", "danger")
        return redirect(url_for("trading.portfolio_detail", portfolio_id=portfolio_id))
    account.balance = float(account.balance) - amount
    portfolio.cash_balance = float(portfolio.cash_balance) + amount
    db.session.commit()
    flash(f"${amount:.2f} added to portfolio.", "success")
    return redirect(url_for("trading.portfolio_detail", portfolio_id=portfolio_id))


@trading_bp.route("/trade", methods=["GET", "POST"])
@login_required
def place_trade():
    portfolios = Portfolio.query.filter_by(user_id=current_user.id, is_active=True).all()
    stocks = Stock.query.filter_by(is_active=True).order_by(Stock.ticker).all()

    if request.method == "POST":
        portfolio_id = request.form.get("portfolio_id", type=int)
        ticker = request.form.get("ticker", "").upper().strip()
        side = request.form.get("side", "buy")
        order_type = request.form.get("order_type", "market")
        quantity = float(request.form.get("quantity", 0))
        limit_price = request.form.get("limit_price")

        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio or portfolio.user_id != current_user.id:
            flash("Invalid portfolio.", "danger")
            return render_template("trading/trade.html", portfolios=portfolios, stocks=stocks)

        stock = Stock.query.filter_by(ticker=ticker, is_active=True).first()
        if not stock:
            flash(f"Stock {ticker} not found.", "danger")
            return render_template("trading/trade.html", portfolios=portfolios, stocks=stocks)

        exec_price = float(stock.current_price)
        if order_type == "limit" and limit_price:
            exec_price = float(limit_price)

        total = exec_price * quantity
        commission = max(1.0, total * 0.001)

        if side == "buy":
            if float(portfolio.cash_balance) < total + commission:
                flash("Insufficient portfolio cash.", "danger")
                return render_template("trading/trade.html", portfolios=portfolios, stocks=stocks)

            portfolio.cash_balance = float(portfolio.cash_balance) - total - commission

            holding = PortfolioHolding.query.filter_by(
                portfolio_id=portfolio_id, stock_id=stock.id
            ).first()
            if holding:
                old_total = float(holding.quantity) * float(holding.avg_cost)
                new_total = quantity * exec_price
                new_qty = float(holding.quantity) + quantity
                holding.avg_cost = (old_total + new_total) / new_qty
                holding.quantity = new_qty
            else:
                holding = PortfolioHolding(
                    portfolio_id=portfolio_id,
                    stock_id=stock.id,
                    quantity=quantity,
                    avg_cost=exec_price,
                )
                db.session.add(holding)

        elif side == "sell":
            holding = PortfolioHolding.query.filter_by(
                portfolio_id=portfolio_id, stock_id=stock.id
            ).first()
            if not holding or float(holding.quantity) < quantity:
                flash("Insufficient shares.", "danger")
                return render_template("trading/trade.html", portfolios=portfolios, stocks=stocks)

            holding.quantity = float(holding.quantity) - quantity
            if float(holding.quantity) <= 0:
                db.session.delete(holding)

            portfolio.cash_balance = float(portfolio.cash_balance) + total - commission

        trade = Trade(
            portfolio_id=portfolio_id,
            stock_id=stock.id,
            order_type=order_type,
            side=side,
            quantity=quantity,
            limit_price=float(limit_price) if limit_price else None,
            executed_price=exec_price,
            total_amount=total,
            commission=commission,
            status="executed",
            executed_at=datetime.utcnow(),
        )
        db.session.add(trade)
        db.session.commit()
        flash(f"Order executed: {side.upper()} {quantity} {ticker} @ ${exec_price:.2f}", "success")
        return redirect(url_for("trading.trade_history", portfolio_id=portfolio_id))

    return render_template("trading/trade.html", portfolios=portfolios, stocks=stocks)


@trading_bp.route("/history")
@login_required
def trade_history():
    portfolio_id = request.args.get("portfolio_id", type=int)
    portfolio = None
    if portfolio_id:
        portfolio = Portfolio.query.get(portfolio_id)

    page = request.args.get("page", 1, type=int)
    q = Trade.query.join(Portfolio).filter(Portfolio.user_id == current_user.id)
    if portfolio_id:
        q = q.filter(Trade.portfolio_id == portfolio_id)
    trades = q.order_by(Trade.created_at.desc()).paginate(page=page, per_page=25, error_out=False)

    return render_template("trading/history.html", trades=trades, portfolio=portfolio)


@trading_bp.route("/stocks")
@login_required
def stock_list():
    query_str = request.args.get("q", "")
    sector = request.args.get("sector", "")
    is_crypto = request.args.get("crypto", "") == "1"

    q = Stock.query.filter_by(is_active=True)
    if query_str:
        q = q.filter(
            db.or_(
                Stock.ticker.ilike(f"%{query_str}%"),
                Stock.name.ilike(f"%{query_str}%"),
            )
        )
    if sector:
        q = q.filter(Stock.sector == sector)
    if is_crypto:
        q = q.filter(Stock.is_crypto == True)

    stocks = q.order_by(Stock.ticker).all()
    sectors = db.session.query(Stock.sector).distinct().filter(Stock.sector.isnot(None)).all()
    return render_template("trading/stocks.html", stocks=stocks, sectors=sectors, query=query_str)


@trading_bp.route("/stocks/<ticker>")
@login_required
def stock_detail(ticker):
    stock = Stock.query.filter_by(ticker=ticker.upper()).first_or_404()
    in_watchlist = Watchlist.query.filter_by(
        user_id=current_user.id, stock_id=stock.id
    ).first() is not None
    prices = stock.prices.limit(90).all()
    return render_template(
        "trading/stock_detail.html",
        stock=stock,
        in_watchlist=in_watchlist,
        prices=prices,
    )


@trading_bp.route("/alerts", methods=["GET", "POST"])
@login_required
def price_alerts():
    if request.method == "POST":
        ticker = request.form.get("ticker", "").upper().strip()
        condition = request.form.get("condition", "above")
        target_price = float(request.form.get("target_price", 0))
        notify_email = "notify_email" in request.form
        notify_sms = "notify_sms" in request.form

        stock = Stock.query.filter_by(ticker=ticker).first()
        if not stock:
            flash(f"Stock {ticker} not found.", "danger")
            return redirect(url_for("trading.price_alerts"))

        alert = PriceAlert(
            user_id=current_user.id,
            stock_id=stock.id,
            condition=condition,
            target_price=target_price,
            notify_email=notify_email,
            notify_sms=notify_sms,
        )
        db.session.add(alert)
        db.session.commit()
        flash("Price alert created.", "success")
        return redirect(url_for("trading.price_alerts"))

    alerts = PriceAlert.query.filter_by(user_id=current_user.id).join(Stock).all()
    stocks = Stock.query.filter_by(is_active=True).order_by(Stock.ticker).all()
    return render_template("trading/alerts.html", alerts=alerts, stocks=stocks)


@trading_bp.route("/alerts/<int:alert_id>/delete", methods=["POST"])
@login_required
def delete_alert(alert_id):
    alert = PriceAlert.query.get_or_404(alert_id)
    if alert.user_id != current_user.id:
        abort(403)
    db.session.delete(alert)
    db.session.commit()
    flash("Alert deleted.", "info")
    return redirect(url_for("trading.price_alerts"))


@trading_bp.route("/watchlist/add", methods=["POST"])
@login_required
def add_to_watchlist():
    ticker = request.form.get("ticker", "").upper()
    stock = Stock.query.filter_by(ticker=ticker).first()
    if not stock:
        flash("Stock not found.", "danger")
        return redirect(url_for("trading.portfolio_overview"))

    existing = Watchlist.query.filter_by(user_id=current_user.id, stock_id=stock.id).first()
    if not existing:
        db.session.add(Watchlist(user_id=current_user.id, stock_id=stock.id))
        db.session.commit()
        flash(f"{ticker} added to watchlist.", "success")
    return redirect(url_for("trading.stock_detail", ticker=ticker))


@trading_bp.route("/watchlist/remove", methods=["POST"])
@login_required
def remove_from_watchlist():
    ticker = request.form.get("ticker", "").upper()
    stock = Stock.query.filter_by(ticker=ticker).first()
    if stock:
        Watchlist.query.filter_by(user_id=current_user.id, stock_id=stock.id).delete()
        db.session.commit()
        flash(f"{ticker} removed from watchlist.", "info")
    return redirect(url_for("trading.stock_detail", ticker=ticker))


@trading_bp.route("/api/price/<ticker>")
@login_required
def get_price(ticker):
    stock = Stock.query.filter_by(ticker=ticker.upper()).first()
    if not stock:
        return jsonify({"error": "Not found"}), 404
    return jsonify(stock.to_dict())
