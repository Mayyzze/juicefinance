from datetime import datetime
from app import db


class Stock(db.Model):
    __tablename__ = "stocks"

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    sector = db.Column(db.String(100))
    exchange = db.Column(db.String(20))
    currency = db.Column(db.String(3), default="USD")
    current_price = db.Column(db.Numeric(15, 4), nullable=False)
    previous_close = db.Column(db.Numeric(15, 4))
    day_high = db.Column(db.Numeric(15, 4))
    day_low = db.Column(db.Numeric(15, 4))
    week_52_high = db.Column(db.Numeric(15, 4))
    week_52_low = db.Column(db.Numeric(15, 4))
    market_cap = db.Column(db.BigInteger)
    pe_ratio = db.Column(db.Numeric(10, 2))
    dividend_yield = db.Column(db.Numeric(6, 4))
    volume = db.Column(db.BigInteger)
    avg_volume = db.Column(db.BigInteger)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_crypto = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    prices = db.relationship("MarketPrice", backref="stock", lazy="dynamic",
                              order_by="MarketPrice.recorded_at.desc()")
    alerts = db.relationship("PriceAlert", backref="stock", lazy="dynamic")

    @property
    def change(self):
        if self.previous_close and self.previous_close != 0:
            return float(self.current_price) - float(self.previous_close)
        return 0.0

    @property
    def change_pct(self):
        if self.previous_close and self.previous_close != 0:
            return (float(self.current_price) - float(self.previous_close)) / float(self.previous_close) * 100
        return 0.0

    def to_dict(self):
        return {
            "id": self.id,
            "ticker": self.ticker,
            "name": self.name,
            "sector": self.sector,
            "exchange": self.exchange,
            "currency": self.currency,
            "current_price": float(self.current_price),
            "previous_close": float(self.previous_close) if self.previous_close else None,
            "change": self.change,
            "change_pct": round(self.change_pct, 2),
            "day_high": float(self.day_high) if self.day_high else None,
            "day_low": float(self.day_low) if self.day_low else None,
            "market_cap": self.market_cap,
            "pe_ratio": float(self.pe_ratio) if self.pe_ratio else None,
            "dividend_yield": float(self.dividend_yield) if self.dividend_yield else None,
            "volume": self.volume,
            "is_crypto": self.is_crypto,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class MarketPrice(db.Model):
    __tablename__ = "market_prices"

    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    open_price = db.Column(db.Numeric(15, 4))
    close_price = db.Column(db.Numeric(15, 4))
    high_price = db.Column(db.Numeric(15, 4))
    low_price = db.Column(db.Numeric(15, 4))
    volume = db.Column(db.BigInteger)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Portfolio(db.Model):
    __tablename__ = "portfolios"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False, default="My Portfolio")
    description = db.Column(db.String(500))
    cash_balance = db.Column(db.Numeric(15, 2), default=0.0)
    currency = db.Column(db.String(3), default="USD")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="portfolios")
    holdings = db.relationship("PortfolioHolding", backref="portfolio", lazy="dynamic")
    trades = db.relationship("Trade", backref="portfolio", lazy="dynamic")

    @property
    def total_value(self):
        holdings_value = sum(
            float(h.quantity) * float(h.stock.current_price)
            for h in self.holdings.all()
        )
        return float(self.cash_balance) + holdings_value

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "cash_balance": float(self.cash_balance),
            "total_value": self.total_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PortfolioHolding(db.Model):
    __tablename__ = "portfolio_holdings"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    quantity = db.Column(db.Numeric(18, 8), nullable=False, default=0)
    avg_cost = db.Column(db.Numeric(15, 4), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stock = db.relationship("Stock")

    @property
    def current_value(self):
        return float(self.quantity) * float(self.stock.current_price)

    @property
    def cost_basis(self):
        return float(self.quantity) * float(self.avg_cost)

    @property
    def pnl(self):
        return self.current_value - self.cost_basis

    @property
    def pnl_pct(self):
        if self.cost_basis == 0:
            return 0.0
        return (self.pnl / self.cost_basis) * 100

    def to_dict(self):
        return {
            "id": self.id,
            "stock": self.stock.to_dict(),
            "quantity": float(self.quantity),
            "avg_cost": float(self.avg_cost),
            "current_value": self.current_value,
            "cost_basis": self.cost_basis,
            "pnl": self.pnl,
            "pnl_pct": round(self.pnl_pct, 2),
        }


class Trade(db.Model):
    __tablename__ = "trades"

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey("portfolios.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    order_type = db.Column(db.String(20), nullable=False)
    side = db.Column(db.String(4), nullable=False)
    quantity = db.Column(db.Numeric(18, 8), nullable=False)
    limit_price = db.Column(db.Numeric(15, 4))
    executed_price = db.Column(db.Numeric(15, 4))
    total_amount = db.Column(db.Numeric(15, 2))
    commission = db.Column(db.Numeric(8, 2), default=0.0)
    status = db.Column(db.String(20), default="pending")
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime)

    stock = db.relationship("Stock")

    def to_dict(self):
        return {
            "id": self.id,
            "ticker": self.stock.ticker,
            "order_type": self.order_type,
            "side": self.side,
            "quantity": float(self.quantity),
            "limit_price": float(self.limit_price) if self.limit_price else None,
            "executed_price": float(self.executed_price) if self.executed_price else None,
            "total_amount": float(self.total_amount) if self.total_amount else None,
            "commission": float(self.commission),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class PriceAlert(db.Model):
    __tablename__ = "price_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    condition = db.Column(db.String(10), nullable=False)
    target_price = db.Column(db.Numeric(15, 4), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    triggered = db.Column(db.Boolean, default=False)
    triggered_at = db.Column(db.DateTime)
    notify_email = db.Column(db.Boolean, default=True)
    notify_sms = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="price_alerts")


class Watchlist(db.Model):
    __tablename__ = "watchlists"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("stocks.id"), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(255))

    user = db.relationship("User", backref="watchlist")
    stock = db.relationship("Stock")
