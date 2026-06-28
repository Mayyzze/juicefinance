import random
import math
from datetime import datetime, timedelta
from app import db


SEED_STOCKS = [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "exchange": "NASDAQ",
     "price": 182.50, "market_cap": 2850000000000, "pe": 28.4, "div": 0.0055},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "exchange": "NASDAQ",
     "price": 374.20, "market_cap": 2780000000000, "pe": 35.1, "div": 0.0072},
    {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology", "exchange": "NASDAQ",
     "price": 140.30, "market_cap": 1760000000000, "pe": 24.8, "div": 0.0},
    {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary",
     "exchange": "NASDAQ", "price": 178.10, "market_cap": 1840000000000, "pe": 62.3, "div": 0.0},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "exchange": "NASDAQ",
     "price": 625.80, "market_cap": 1540000000000, "pe": 64.2, "div": 0.0025},
    {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Communication Services",
     "exchange": "NASDAQ", "price": 485.20, "market_cap": 1240000000000, "pe": 24.7, "div": 0.0},
    {"ticker": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary",
     "exchange": "NASDAQ", "price": 248.90, "market_cap": 790000000000, "pe": 52.8, "div": 0.0},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway Inc.", "sector": "Financials",
     "exchange": "NYSE", "price": 358.40, "market_cap": 785000000000, "pe": 9.2, "div": 0.0},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials",
     "exchange": "NYSE", "price": 195.60, "market_cap": 566000000000, "pe": 11.4, "div": 0.022},
    {"ticker": "V", "name": "Visa Inc.", "sector": "Financials", "exchange": "NYSE",
     "price": 264.80, "market_cap": 559000000000, "pe": 30.2, "div": 0.0077},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare",
     "exchange": "NYSE", "price": 157.30, "market_cap": 379000000000, "pe": 15.2, "div": 0.031},
    {"ticker": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples",
     "exchange": "NYSE", "price": 163.40, "market_cap": 655000000000, "pe": 29.8, "div": 0.013},
    {"ticker": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Staples",
     "exchange": "NYSE", "price": 148.90, "market_cap": 350000000000, "pe": 24.6, "div": 0.025},
    {"ticker": "UNH", "name": "UnitedHealth Group Inc.", "sector": "Healthcare",
     "exchange": "NYSE", "price": 498.30, "market_cap": 460000000000, "pe": 21.5, "div": 0.015},
    {"ticker": "HD", "name": "The Home Depot Inc.", "sector": "Consumer Discretionary",
     "exchange": "NYSE", "price": 342.10, "market_cap": 340000000000, "pe": 22.8, "div": 0.025},
    {"ticker": "BAC", "name": "Bank of America Corp.", "sector": "Financials",
     "exchange": "NYSE", "price": 34.80, "market_cap": 275000000000, "pe": 11.2, "div": 0.026},
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy",
     "exchange": "NYSE", "price": 105.40, "market_cap": 419000000000, "pe": 13.7, "div": 0.034},
    {"ticker": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services",
     "exchange": "NASDAQ", "price": 612.50, "market_cap": 265000000000, "pe": 43.2, "div": 0.0},
    {"ticker": "INTC", "name": "Intel Corporation", "sector": "Technology",
     "exchange": "NASDAQ", "price": 32.40, "market_cap": 138000000000, "pe": 18.9, "div": 0.021},
    {"ticker": "AMD", "name": "Advanced Micro Devices Inc.", "sector": "Technology",
     "exchange": "NASDAQ", "price": 162.80, "market_cap": 263000000000, "pe": 52.4, "div": 0.0},
]

SEED_CRYPTO = [
    {"ticker": "BTC", "name": "Bitcoin", "sector": "Cryptocurrency", "exchange": "CRYPTO",
     "price": 43250.0, "market_cap": 845000000000, "pe": None, "div": 0.0},
    {"ticker": "ETH", "name": "Ethereum", "sector": "Cryptocurrency", "exchange": "CRYPTO",
     "price": 2240.50, "market_cap": 269000000000, "pe": None, "div": 0.0},
    {"ticker": "SOL", "name": "Solana", "sector": "Cryptocurrency", "exchange": "CRYPTO",
     "price": 98.30, "market_cap": 43000000000, "pe": None, "div": 0.0},
    {"ticker": "ADA", "name": "Cardano", "sector": "Cryptocurrency", "exchange": "CRYPTO",
     "price": 0.482, "market_cap": 17000000000, "pe": None, "div": 0.0},
    {"ticker": "DOT", "name": "Polkadot", "sector": "Cryptocurrency", "exchange": "CRYPTO",
     "price": 7.28, "market_cap": 9400000000, "pe": None, "div": 0.0},
]


def seed_stocks():
    from app.models.trade import Stock, MarketPrice

    for data in SEED_STOCKS + SEED_CRYPTO:
        existing = Stock.query.filter_by(ticker=data["ticker"]).first()
        if existing:
            continue

        is_crypto = data["exchange"] == "CRYPTO"
        volatility = 0.04 if is_crypto else 0.015
        prev_close = data["price"] * (1 + random.uniform(-volatility, volatility))

        stock = Stock(
            ticker=data["ticker"],
            name=data["name"],
            sector=data["sector"],
            exchange=data["exchange"],
            currency="USD",
            current_price=data["price"],
            previous_close=round(prev_close, 4),
            day_high=round(data["price"] * (1 + abs(random.uniform(0, volatility))), 4),
            day_low=round(data["price"] * (1 - abs(random.uniform(0, volatility))), 4),
            week_52_high=round(data["price"] * random.uniform(1.1, 1.5), 4),
            week_52_low=round(data["price"] * random.uniform(0.5, 0.9), 4),
            market_cap=data["market_cap"],
            pe_ratio=data["pe"],
            dividend_yield=data["div"],
            volume=random.randint(5000000, 80000000),
            avg_volume=random.randint(10000000, 100000000),
            is_active=True,
            is_crypto=is_crypto,
        )
        db.session.add(stock)
        db.session.flush()

        now = datetime.utcnow()
        for i in range(90):
            dt = now - timedelta(days=89 - i)
            drift = math.exp(random.gauss(0.0002, volatility))
            open_p = float(data["price"]) * math.exp(random.gauss(-0.01, 0.1))
            close_p = open_p * drift
            high_p = max(open_p, close_p) * (1 + abs(random.gauss(0, 0.01)))
            low_p = min(open_p, close_p) * (1 - abs(random.gauss(0, 0.01)))
            db.session.add(MarketPrice(
                stock_id=stock.id,
                open_price=round(open_p, 4),
                close_price=round(close_p, 4),
                high_price=round(high_p, 4),
                low_price=round(low_p, 4),
                volume=random.randint(5000000, 80000000),
                recorded_at=dt,
            ))

    db.session.commit()


def update_prices():
    from app.models.trade import Stock, PriceAlert
    from app.models.notification import Notification

    stocks = Stock.query.filter_by(is_active=True).all()
    for stock in stocks:
        is_crypto = stock.is_crypto
        volatility = 0.008 if is_crypto else 0.002
        change_pct = random.gauss(0.0001, volatility)
        new_price = float(stock.current_price) * (1 + change_pct)
        new_price = max(0.01, round(new_price, 4))

        stock.previous_close = stock.current_price
        stock.current_price = new_price
        stock.last_updated = datetime.utcnow()

        if stock.day_high is None or new_price > float(stock.day_high):
            stock.day_high = new_price
        if stock.day_low is None or new_price < float(stock.day_low):
            stock.day_low = new_price

        alerts = PriceAlert.query.filter_by(stock_id=stock.id, is_active=True, triggered=False).all()
        for alert in alerts:
            triggered = False
            if alert.condition == "above" and new_price >= float(alert.target_price):
                triggered = True
            elif alert.condition == "below" and new_price <= float(alert.target_price):
                triggered = True

            if triggered:
                alert.triggered = True
                alert.triggered_at = datetime.utcnow()
                db.session.add(Notification(
                    user_id=alert.user_id,
                    title=f"Price Alert: {stock.ticker}",
                    body=f"{stock.ticker} is now ${new_price:.2f} ({alert.condition} ${float(alert.target_price):.2f})",
                    type="alert",
                    icon="chart-line",
                ))

    db.session.commit()


def get_market_summary():
    from app.models.trade import Stock
    stocks = Stock.query.filter_by(is_active=True, is_crypto=False).limit(10).all()
    return [s.to_dict() for s in stocks]
