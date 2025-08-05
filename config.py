# Trading Bot Configuration

# Risk Management Settings
RISK_PERCENTAGE = 60.0  # Percentage of total balance to risk per trade (60% = 0.6)
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
MAX_TRADES_HISTORY = 10  # Number of recent trades to keep in memory
PERFORMANCE_METRICS = {
    'win_rate_min': 50.0,     # Minimum win rate percentage
    'profit_factor_min': 1.5,  # Minimum profit factor
    'max_consecutive_losses': 3 # Maximum consecutive losing trades
}

# Watchdog Settings
WATCHDOG = {
    'enabled': True,
    'max_errors': 5,           # Maximum consecutive errors before restart
    'error_reset_time': 300,   # Time in seconds to reset error counter
    'heartbeat_interval': 60,  # Time in seconds between health checks
    'restart_delay': 30,       # Time in seconds to wait before restart
    'max_memory_percent': 80,  # Maximum memory usage before restart
    'max_restarts': 3,         # Maximum number of restarts per day
    'restart_window': 86400    # Time window for restart count (24 hours in seconds)
}
