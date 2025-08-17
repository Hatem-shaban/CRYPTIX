# Trading Bot Configuration

# Risk Management Settings
RISK_PERCENTAGE = 2.0  # Percentage of total balance to risk per trade (2% = conservative)
MIN_TRADE_USDT = 10.0  # Minimum trade size in USDT
MAX_DRAWDOWN = 15.0  # Maximum drawdown percentage allowed

# Trading Strategy Parameters
RSI_PERIOD = 14  # Standard RSI period
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_THRESHOLD = 1000000  # Minimum 24h volume in USDT

# Time Filters
AVOID_TRADING_HOURS = [0, 1, 2, 3]  # Hours to avoid trading (UTC)

# Position Sizing
DEFAULT_QUANTITY = 0.001  # Default fallback quantity
POSITION_SIZE_ADJUSTMENTS = {
    'volatility_factor': 1.0,  # Reduce position size in high volatility
    'trend_factor': 1.2,  # Increase position size in strong trends
}

# Trading Pairs
DEFAULT_PAIR = "BTCUSDT"
MONITORED_BASE_ASSETS = ["BTC", "ETH", "BNB", "XRP", "SOL", "MATIC", "DOT", "ADA"]
QUOTE_ASSET = "USDT"

# Technical Analysis
PERIOD_FAST = 5   # Fast moving average period
PERIOD_SLOW = 20  # Slow moving average period
ATR_PERIOD = 14   # Average True Range period

# Statistical Parameters
ZSCORE_THRESHOLD = 2.0  # Z-score threshold for statistical signals
VAR_CONFIDENCE = 0.95   # Value at Risk confidence level

# Strategy Thresholds
STRICT_STRATEGY = {
    'min_signals': 5,      # Minimum signals required for trade
    'volatility_max': 0.3, # Maximum allowed volatility
    'trend_strength': 0.02 # Minimum trend strength required
}

MODERATE_STRATEGY = {
    'min_signals': 3,
    'volatility_max': 0.4,
    'trend_strength': 0.015
}

ADAPTIVE_STRATEGY = {
    'score_threshold': 70,
    'volatility_adjustment': True,
    'trend_following': True
}

# Performance Tracking
MAX_TRADES_HISTORY = 100  # Number of recent trades to keep in memory
PERFORMANCE_METRICS = {
    'win_rate_min': 50.0,     # Minimum win rate percentage
    'profit_factor_min': 1.5,  # Minimum profit factor
    'max_consecutive_losses': 3 # Maximum consecutive losing trades
}

# Daily Risk Limits (NEW)
MAX_DAILY_LOSS = 50.0  # Maximum daily loss in USD
MAX_CONSECUTIVE_LOSSES = 5  # Stop trading after this many losses
MAX_PORTFOLIO_EXPOSURE = 80.0  # Maximum percentage of portfolio at risk

# Intelligent Timing System (AI TRADING WOLF)
TIMING_SYSTEM = {
    'base_interval': 300,           # Base scanning interval (5 minutes)
    'regime_check_interval': 300,   # Market regime check frequency (5 minutes)
    'breakout_scan_threshold': 40,  # Minimum score for breakout opportunities
    'hunting_mode_triggers': 3,     # Number of triggers needed for hunting mode
    'max_quick_scans': 5,          # Maximum quick scans before full scan
    'volatility_thresholds': {
        'extreme': 1.5,            # Hourly volatility threshold for extreme regime
        'volatile': 0.8,           # Hourly volatility threshold for volatile regime
        'quiet': 0.3               # Hourly volatility threshold for quiet regime
    },
    'volume_surge_thresholds': {
        'extreme': 3.0,            # Volume surge multiplier for extreme conditions
        'volatile': 2.0,           # Volume surge multiplier for volatile conditions
        'significant': 1.5         # Volume surge multiplier for significant activity
    }
}

# Market Hours for Enhanced Timing
MARKET_HOURS = {
    'us_market': list(range(16, 24)) + list(range(0, 1)),  # 2:30 PM - 11 PM Cairo time
    'asian_market': list(range(2, 10)),                     # 2 AM - 10 AM Cairo time
    'european_market': list(range(10, 18)),                 # 10 AM - 6 PM Cairo time
    'high_activity_hours': list(range(14, 23)),             # Peak trading hours
}

# Auto Trading Settings
AUTO_TRADING = True  # Enable automatic trade execution

# API Rate Limiting (NEW)
API_RATE_LIMITS = {
    'calls_per_minute': 1200,  # Binance limit
    'calls_per_second': 10,    # Conservative limit
    'weight_per_minute': 6000  # Weight-based limiting
}

# Telegram Notification Settings
TELEGRAM = {
    'enabled': True,  # Enable/disable Telegram notifications
    'bot_token': '8102715880:AAF5ojmyT4nBADozEXABD5qkngmszVcC6Rw',  # Your Telegram bot token (get from @BotFather)
    'chat_id': '2086996577',    # Your chat ID (get from @userinfobot)
    'notifications': {
        'signals': True,           # Send trading signal notifications
        'trades': True,            # Send trade execution notifications
        'errors': True,            # Send error notifications
        'daily_summary': True,     # Send daily performance summary
        'bot_status': True         # Send bot start/stop notifications
    },
    'message_format': {
        'include_emoji': True,     # Include emojis in messages
        'include_price': True,     # Include current price in messages
        'include_indicators': True, # Include technical indicators
        'include_profit_loss': True # Include P&L information
    },
    'rate_limiting': {
        'max_messages_per_minute': 20,  # Rate limit to avoid spam
        'batch_notifications': True      # Batch similar notifications
    }
}
