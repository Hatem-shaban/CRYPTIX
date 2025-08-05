from flask import Flask, render_template_string, jsonify, redirect, send_file
from binance.client import Client
from binance.exceptions import BinanceAPIException
from dotenv import load_dotenv
import config  # Import trading configuration
import os, time, threading, subprocess
import pandas as pd
import numpy as np
from datetime import datetime
from textblob import TextBlob
import requests  # Added for Coinbase API calls
import pytz
import csv
from pathlib import Path
import io
import zipfile
# from keep_alive import keep_alive  # Disabled to avoid Flask conflicts
import sys
import json
from datetime import datetime, timedelta

# Install psutil if not present
try:
    import psutil
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil

# Initialize watchdog state
watchdog_state = {
    'error_count': 0,
    'last_error_time': None,
    'last_heartbeat': None,
    'restart_count': 0,
    'last_restart_time': datetime.now(),
    'process': psutil.Process()
}

def check_memory_usage():
    """Check if memory usage is within acceptable limits"""
    try:
        memory_percent = watchdog_state['process'].memory_percent()
        return memory_percent < config.WATCHDOG['max_memory_percent']
    except Exception as e:
        log_error_to_csv(str(e), "WATCHDOG", "check_memory_usage", "WARNING")
        return True  # Default to true if check fails

def can_restart():
    """Check if the bot can restart based on configured limits"""
    if not watchdog_state['last_restart_time']:
        return True
        
    time_since_last = (datetime.now() - watchdog_state['last_restart_time']).total_seconds()
    
    # Reset counter if outside window
    if time_since_last > config.WATCHDOG['restart_window']:
        watchdog_state['restart_count'] = 0
        watchdog_state['last_restart_time'] = datetime.now()
        return True
        
    return watchdog_state['restart_count'] < config.WATCHDOG['max_restarts']

def restart_bot():
    """Restart the bot process"""
    try:
        if can_restart():
            log_error_to_csv("Bot restart initiated", "WATCHDOG", "restart_bot", "INFO")
            watchdog_state['restart_count'] += 1
            watchdog_state['last_restart_time'] = datetime.now()
            
            # Save current state if needed
            save_bot_state()
            
            # Wait specified delay before restart
            time.sleep(config.WATCHDOG['restart_delay'])
            
            # Restart the process
            python = sys.executable
            os.execl(python, python, *sys.argv)
        else:
            log_error_to_csv("Max restarts exceeded, manual intervention required", "WATCHDOG", "restart_bot", "ERROR")
    except Exception as e:
        log_error_to_csv(f"Restart failed: {str(e)}", "WATCHDOG", "restart_bot", "ERROR")

def watchdog_monitor():
    """Main watchdog monitoring function"""
    if not config.WATCHDOG['enabled']:
        return
        
    try:
        current_time = datetime.now()
        
        # Check error count
        if watchdog_state['error_count'] >= config.WATCHDOG['max_errors']:
            if (current_time - watchdog_state['last_error_time']).total_seconds() < config.WATCHDOG['error_reset_time']:
                log_error_to_csv("Too many consecutive errors", "WATCHDOG", "watchdog_monitor", "ERROR")
                restart_bot()
            else:
                # Reset error count if outside time window
                watchdog_state['error_count'] = 0
        
        # Check memory usage
        if not check_memory_usage():
            log_error_to_csv("Memory usage exceeded threshold", "WATCHDOG", "watchdog_monitor", "WARNING")
            restart_bot()
        
        # Update heartbeat
        watchdog_state['last_heartbeat'] = current_time
        
    except Exception as e:
        log_error_to_csv(str(e), "WATCHDOG", "watchdog_monitor", "ERROR")

def save_bot_state():
    """Save critical bot state before restart"""
    try:
        state_data = {
            'bot_status': bot_status,
            'trading_summary': bot_status['trading_summary'],
            'last_trades': bot_status['trading_summary']['trades_history']
        }
        
        # Save to temporary file
        with open('bot_state.tmp', 'w') as f:
            json.dump(state_data, f)
    except Exception as e:
        log_error_to_csv(f"Failed to save state: {str(e)}", "WATCHDOG", "save_bot_state", "WARNING")

def load_bot_state():
    """Load bot state after restart"""
    try:
        if os.path.exists('bot_state.tmp'):
            with open('bot_state.tmp', 'r') as f:
                state_data = json.load(f)
                
            # Restore critical state
            bot_status.update(state_data['bot_status'])
            bot_status['trading_summary'] = state_data['trading_summary']
            bot_status['trading_summary']['trades_history'] = state_data['last_trades']
            
            # Clean up
            os.remove('bot_state.tmp')
    except Exception as e:
        log_error_to_csv(f"Failed to load state: {str(e)}", "WATCHDOG", "load_bot_state", "WARNING")

# Start watchdog thread
def start_watchdog():
    """Start the watchdog monitoring thread"""
    if config.WATCHDOG['enabled']:
        def watchdog_thread():
            while True:
                watchdog_monitor()
                time.sleep(config.WATCHDOG['heartbeat_interval'])
        
        threading.Thread(target=watchdog_thread, daemon=True).start()

# keep_alive()  # Disabled to avoid Flask conflicts
# Load environment variables
load_dotenv()

# Load previous state if exists
load_bot_state()

# Start watchdog monitoring
start_watchdog()

# Cairo timezone
CAIRO_TZ = pytz.timezone('Africa/Cairo')

def get_cairo_time():
    """Get current time in Cairo, Egypt timezone"""
    return datetime.now(CAIRO_TZ)

def format_cairo_time(dt=None):
    """Format datetime to Cairo timezone string"""
    if dt is None:
        dt = get_cairo_time()
    elif dt.tzinfo is None:
        # If naive datetime, assume it's UTC and convert to Cairo
        dt = pytz.UTC.localize(dt).astimezone(CAIRO_TZ)
    elif dt.tzinfo != CAIRO_TZ:
        # Convert to Cairo timezone
        dt = dt.astimezone(CAIRO_TZ)
    
    return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

def get_time_remaining_for_next_signal():
    """Calculate time remaining until next signal in a human-readable format"""
    try:
        if not bot_status.get('next_signal_time') or not bot_status.get('running'):
            return "Not scheduled"
        
        next_signal = bot_status['next_signal_time']
        current_time = get_cairo_time()
        
        # If next_signal is naive datetime, make it timezone-aware
        if next_signal.tzinfo is None:
            next_signal = CAIRO_TZ.localize(next_signal)
        
        time_diff = next_signal - current_time
        
        if time_diff.total_seconds() <= 0:
            return "Signal due now"
        
        # Convert to minutes and seconds
        total_seconds = int(time_diff.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    except Exception as e:
        return "Unknown"

# CSV Trade History Logging
def setup_csv_logging():
    """Initialize CSV logging directories and files while preserving existing data"""
    # Create logs directory if it doesn't exist
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Define CSV file paths
    csv_files = {
        'trades': logs_dir / 'trade_history.csv',
        'signals': logs_dir / 'signal_history.csv',
        'performance': logs_dir / 'daily_performance.csv',
        'errors': logs_dir / 'error_log.csv'
    }
    
    # Define headers for each file type
    trade_headers = [
        'timestamp', 'cairo_time', 'signal', 'symbol', 'quantity', 'price', 
        'value', 'fee', 'status', 'order_id', 'rsi', 'macd_trend', 'sentiment',
        'balance_before', 'balance_after', 'profit_loss'
    ]
    
    signal_headers = [
        'timestamp', 'cairo_time', 'signal', 'symbol', 'price', 'rsi', 'macd', 'macd_trend',
        'sentiment', 'sma5', 'sma20', 'reason'
    ]
    
    performance_headers = [
        'date', 'total_trades', 'successful_trades', 'failed_trades', 'win_rate',
        'total_revenue', 'daily_pnl', 'total_volume', 'max_drawdown'
    ]
    
    error_headers = [
        'timestamp', 'cairo_time', 'error_type', 'error_message', 'function_name',
        'severity', 'bot_status'
    ]
    
    headers_map = {
        'trades': trade_headers,
        'signals': signal_headers,
        'performance': performance_headers,
        'errors': error_headers
    }
    
    # Initialize CSV files while preserving existing data
    for file_type, file_path in csv_files.items():
        if not file_path.exists():
            # Create new file with headers if it doesn't exist
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers_map[file_type])
        else:
            # File exists - verify headers
            try:
                with open(file_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    existing_headers = next(reader, None)
                    
                    # If file is empty or headers don't match, initialize with headers while preserving data
                    if not existing_headers or existing_headers != headers_map[file_type]:
                        # Read existing data
                        f.seek(0)
                        existing_data = list(reader)
                        
                        # Rewrite file with correct headers and preserved data
                        with open(file_path, 'w', newline='', encoding='utf-8') as f_write:
                            writer = csv.writer(f_write)
                            writer.writerow(headers_map[file_type])
                            writer.writerows(existing_data)
            except Exception as e:
                print(f"Error verifying {file_type} log file: {e}")
                # If there's an error, backup the existing file and create a new one
                backup_path = file_path.with_suffix('.csv.bak')
                try:
                    if file_path.exists():
                        file_path.rename(backup_path)
                    with open(file_path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(headers_map[file_type])
                except Exception as be:
                    print(f"Error creating backup of {file_type} log file: {be}")
    
    return csv_files

def log_trade_to_csv(trade_info, additional_data=None):
    """Log trade information to CSV file"""
    try:
        csv_files = setup_csv_logging()
        
        # Prepare trade data
        trade_data = [
            trade_info.get('timestamp', ''),
            format_cairo_time(),
            trade_info.get('signal', ''),
            trade_info.get('symbol', ''),
            trade_info.get('quantity', 0),
            trade_info.get('price', 0),
            trade_info.get('value', 0),
            trade_info.get('fee', 0),
            trade_info.get('status', ''),
            trade_info.get('order_id', ''),
            additional_data.get('rsi', 0) if additional_data else 0,
            additional_data.get('macd_trend', '') if additional_data else '',
            additional_data.get('sentiment', '') if additional_data else '',
            additional_data.get('balance_before', 0) if additional_data else 0,
            additional_data.get('balance_after', 0) if additional_data else 0,
            additional_data.get('profit_loss', 0) if additional_data else 0
        ]
        
        # Write to CSV
        with open(csv_files['trades'], 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(trade_data)
            
        print(f"Trade logged to CSV: {trade_info.get('signal', 'UNKNOWN')} at {trade_info.get('price', 0)}")
        
    except Exception as e:
        print(f"Error logging trade to CSV: {e}")

def log_signal_to_csv(signal, price, indicators, reason=""):
    """Log trading signal to CSV file"""
    try:
        csv_files = setup_csv_logging()
        
        signal_data = [
            datetime.now().isoformat(),
            format_cairo_time(),
            signal,
            indicators.get('symbol', 'UNKNOWN'),  # Include symbol in logging
            price,
            indicators.get('rsi', 0),
            indicators.get('macd', 0),
            indicators.get('macd_trend', ''),
            indicators.get('sentiment', ''),
            indicators.get('sma5', 0),
            indicators.get('sma20', 0),
            reason
        ]
        
        with open(csv_files['signals'], 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(signal_data)
            
    except Exception as e:
        print(f"Error logging signal to CSV: {e}")

def log_daily_performance():
    """Log daily performance summary to CSV"""
    try:
        csv_files = setup_csv_logging()
        
        # Calculate daily P&L and metrics
        today = get_cairo_time().strftime('%Y-%m-%d')
        trading_summary = bot_status.get('trading_summary', {})
        
        performance_data = [
            today,
            trading_summary.get('successful_trades', 0) + trading_summary.get('failed_trades', 0),
            trading_summary.get('successful_trades', 0),
            trading_summary.get('failed_trades', 0),
            trading_summary.get('win_rate', 0),
            trading_summary.get('total_revenue', 0),
            trading_summary.get('total_revenue', 0),  # Daily P&L (simplified)
            trading_summary.get('total_buy_volume', 0) + trading_summary.get('total_sell_volume', 0),
            0  # Max drawdown (to be calculated)
        ]
        
        with open(csv_files['performance'], 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(performance_data)
            
    except Exception as e:
        print(f"Error logging daily performance to CSV: {e}")

def log_error_to_csv(error_message, error_type="GENERAL", function_name="", severity="ERROR"):
    """Log errors to CSV file"""
    try:
        csv_files = setup_csv_logging()
        
        error_data = [
            datetime.now().isoformat(),
            format_cairo_time(),
            error_type,
            str(error_message),
            function_name,
            severity,
            bot_status.get('running', False)
        ]
        
        with open(csv_files['errors'], 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(error_data)
            
        print(f"Error logged to CSV: {error_type} - {error_message}")
            
    except Exception as e:
        print(f"Error logging error to CSV: {e}")

def get_csv_trade_history(days=30): #Hatem Need to confirm the need
    """Read and return trade history from CSV"""
    try:
        csv_files = setup_csv_logging()
        
        if not csv_files['trades'].exists():
            return []
        
        # Read CSV file
        df = pd.read_csv(csv_files['trades'])
        
        # Filter by date if needed
        if days > 0:
            cutoff_date = get_cairo_time() - pd.Timedelta(days=days)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df[df['timestamp'] >= cutoff_date]
        
        # Convert to list of dictionaries
        return df.to_dict('records')
        
    except Exception as e:
        print(f"Error reading CSV trade history: {e}")
        return []

# Global bot status
bot_status = {
    'running': False,
    'auto_start': True,  # Enable auto-start by default
    'auto_restart': True,  # Enable auto-restart on failures
    'last_signal': 'UNKNOWN',
    'current_symbol': 'BTCUSDT',  # Track currently analyzed symbol
    'last_price': 0,
    'last_update': None,
    'api_connected': False,
    'total_trades': 0,
    'errors': [],
    'start_time': get_cairo_time(),
    'consecutive_errors': 0,
    'rsi': 50,
    'macd': {'macd': 0, 'signal': 0, 'trend': 'NEUTRAL'},
    'sentiment': 'neutral',
    'monitored_pairs': {},  # Track all monitored pairs' status
    'trading_strategy': 'STRICT',  # Current trading strategy (STRICT, MODERATE, ADAPTIVE)
    'next_signal_time': None,  # Track when next signal will be generated
    'signal_interval': 1800,  # Signal generation interval in seconds (30 minutes)
    'trading_summary': {
        'total_revenue': 0.0,
        'successful_trades': 0,
        'failed_trades': 0,
        'total_buy_volume': 0.0,
        'total_sell_volume': 0.0,
        'average_trade_size': 0.0,
        'win_rate': 0.0,
        'trades_history': []  # Last 10 trades for display
    }
}

app = Flask(__name__)

# Initialize CSV logging on startup
setup_csv_logging()

api_key = os.getenv("API_KEY")
api_secret = os.getenv("API_SECRET")
client = None

# Lightweight sentiment analysis function
def get_sentiment_score(text):
    """Enhanced sentiment scoring with crypto-specific keyword weighting"""
    try:
        blob = TextBlob(text)
        base_sentiment = blob.sentiment.polarity
        
        # Crypto-specific keywords for better sentiment analysis
        bullish_keywords = ['moon', 'bullish', 'buy', 'hodl', 'pump', 'rally', 'breakout', 'surge', 'gains', 'profit']
        bearish_keywords = ['dump', 'crash', 'sell', 'bearish', 'drop', 'fall', 'loss', 'decline', 'dip', 'correction']
        
        text_lower = text.lower()
        keyword_boost = 0
        
        # Apply keyword boosting
        for keyword in bullish_keywords:
            if keyword in text_lower:
                keyword_boost += 0.1
                
        for keyword in bearish_keywords:
            if keyword in text_lower:
                keyword_boost -= 0.1
        
        # Combine base sentiment with keyword boost
        enhanced_sentiment = base_sentiment + keyword_boost
        
        # Ensure sentiment stays within bounds [-1, 1]
        return max(-1, min(1, enhanced_sentiment))
    except Exception as e:
        print(f"Sentiment scoring error: {e}")
        return 0

def initialize_client():
    global client, bot_status
    try:
        if not api_key or not api_secret:
            bot_status['errors'].append("API credentials missing")
            return False
        client = Client(api_key, api_secret, testnet=True)
        client.get_account()
        bot_status['api_connected'] = True
        return True
    except Exception as e:
        bot_status['errors'].append(str(e))
        bot_status['api_connected'] = False
        client = None
        return False

# Market data based sentiment analysis is used instead of social sentiment

def fetch_coinbase_data():

    try:
        # Using requests to fetch Coinbase public API data
        base_url = "https://api.exchange.coinbase.com"  # Updated to new API endpoint
        headers = {
            'User-Agent': 'Binance-AI-Bot/1.0',
            'Accept': 'application/json'
        }
        
        # Implement rate limiting (sleep between requests)
        time.sleep(0.35)  # ~3 requests per second max
        
        print("Fetching Coinbase order book...")  # Debug log
        # Get order book with error handling
        order_book_response = requests.get(
            f"{base_url}/products/BTC-USD/book?level=2",
            headers=headers,
            timeout=5
        )
        if order_book_response.status_code == 429:
            log_error_to_csv("Coinbase rate limit exceeded", "API_RATE_LIMIT", "fetch_coinbase_data", "WARNING")
            time.sleep(1)  # Wait longer on rate limit
            order_book_response = requests.get(f"{base_url}/products/BTC-USD/book?level=2", headers=headers)
        elif order_book_response.status_code != 200:
            error_msg = f"Coinbase order book request failed with status {order_book_response.status_code}: {order_book_response.text}"
            print(error_msg)  # Debug log
            log_error_to_csv(error_msg, "COINBASE_ERROR", "fetch_coinbase_data", "ERROR")
            return None
            
        try:
            order_book = order_book_response.json()
            if not isinstance(order_book, dict) or 'bids' not in order_book or 'asks' not in order_book:
                error_msg = f"Invalid order book response format: {order_book}"
                print(error_msg)  # Debug log
                log_error_to_csv(error_msg, "COINBASE_ERROR", "fetch_coinbase_data", "ERROR")
                return None
        except ValueError as e:
            error_msg = f"Failed to parse order book JSON: {e}"
            print(error_msg)  # Debug log
            log_error_to_csv(error_msg, "COINBASE_ERROR", "fetch_coinbase_data", "ERROR")
            return None
        
        # Implement rate limiting between requests
        time.sleep(0.35)
        
        # Get recent trades with error handling
        trades_response = requests.get(
            f"{base_url}/products/BTC-USD/trades",
            headers=headers,
            timeout=5
        )
        if trades_response.status_code == 429:
            log_error_to_csv("Coinbase rate limit exceeded", "API_RATE_LIMIT", "fetch_coinbase_data", "WARNING")
            time.sleep(1)
            trades_response = requests.get(f"{base_url}/products/BTC-USD/trades", headers=headers)
        trades = trades_response.json()
        
        return {
            'order_book': order_book,
            'recent_trades': trades,
            'timestamp': datetime.now().timestamp()
        }
    except Exception as e:
        print(f"Coinbase data fetch error: {e}")
        return None

def analyze_market_sentiment():
    """Analyze market sentiment from multiple sources"""
    try:
        # Initialize sentiment components
        order_book_sentiment = 0
        trade_flow_sentiment = 0
        print("\nAnalyzing market sentiment from order book and trade data...")  # Debug log
        
        # 1. Order Book Analysis
        cb_data = fetch_coinbase_data()
        if cb_data:
            order_book = cb_data['order_book']
            if 'bids' in order_book and 'asks' in order_book:
                # Calculate buy/sell pressure
                bid_volume = sum(float(bid[1]) for bid in order_book['bids'][:10])
                ask_volume = sum(float(ask[1]) for ask in order_book['asks'][:10])
                
                # Normalize order book sentiment
                total_volume = bid_volume + ask_volume
                if total_volume > 0:
                    order_book_sentiment = (bid_volume - ask_volume) / total_volume
        
            # 3. Recent Trade Flow Analysis
            if 'recent_trades' in cb_data:
                recent_trades = cb_data['recent_trades']
                buy_volume = sum(float(trade['size']) for trade in recent_trades if trade['side'] == 'buy')
                sell_volume = sum(float(trade['size']) for trade in recent_trades if trade['side'] == 'sell')
                
                total_trade_volume = buy_volume + sell_volume
                if total_trade_volume > 0:
                    trade_flow_sentiment = (buy_volume - sell_volume) / total_trade_volume
        
        # Market data based sentiment weights
        weights = {
            'order_book': 0.6,  # Order book pressure weight
            'trade_flow': 0.4   # Recent trade flow weight
        }
        
        # Calculate combined sentiment using market data
        combined_sentiment = (
            weights['order_book'] * order_book_sentiment +
            weights['trade_flow'] * trade_flow_sentiment
        )
        
        # Advanced sentiment thresholds with confidence levels
        sentiment_data = {
            'value': combined_sentiment,
            'components': {
                'order_book_sentiment': order_book_sentiment,
                'trade_flow_sentiment': trade_flow_sentiment
            },
            'confidence': min(1.0, abs(combined_sentiment) * 2)  # Confidence score 0-1
        }
        
        # Determine sentiment with confidence threshold
        if abs(combined_sentiment) < 0.1:
            return "neutral"
        elif combined_sentiment > 0:
            return "bullish" if sentiment_data['confidence'] > 0.5 else "neutral"
        else:
            return "bearish" if sentiment_data['confidence'] > 0.5 else "neutral"
            
    except Exception as e:
        bot_status['errors'].append(f"Market sentiment analysis failed: {e}")
        return "neutral"

def calculate_rsi(prices, period=None):
    """Calculate RSI using proper Wilder's smoothing method"""
    period = period or config.RSI_PERIOD
    try:
        if len(prices) < period + 1:
            return 50  # Neutral RSI when insufficient data
            
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Use Wilder's smoothing (similar to EMA) for more accurate RSI
        alpha = 1.0 / period
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        # Apply Wilder's smoothing to the rest of the data
        for i in range(period, len(gains)):
            avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
            avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss
        
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Ensure RSI is within bounds
        return max(0, min(100, rsi))
    except Exception as e:
        print(f"RSI calculation error: {e}")
        return 50

def calculate_sma(df, period=20):
    """Calculate Simple Moving Average efficiently"""
    try:
        if df is None or len(df) < period:
            return pd.Series([])
        
        # Use pandas rolling for efficiency
        return df['close'].rolling(window=period).mean()
    except Exception as e:
        print(f"SMA calculation error: {e}")
        return pd.Series([])

def calculate_macd(prices, fast=None, slow=None, signal=None):
    """Calculate MACD using configuration parameters"""
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL
    """Calculate MACD with signal line and histogram"""
    try:
        if len(prices) < slow:
            return {"macd": 0, "signal": 0, "histogram": 0, "trend": "NEUTRAL"}
        
        # Calculate exponential moving averages for more accurate MACD
        def ema(data, period):
            alpha = 2 / (period + 1)
            ema_values = [data[0]]  # Start with first value
            for price in data[1:]:
                ema_values.append(alpha * price + (1 - alpha) * ema_values[-1])
            return np.array(ema_values)
        
        fast_ema = ema(prices, fast)
        slow_ema = ema(prices, slow)
        
        # MACD line = Fast EMA - Slow EMA
        macd_line = fast_ema - slow_ema
        
        # Signal line = EMA of MACD line
        signal_line = ema(macd_line, signal)
        
        # Histogram = MACD - Signal
        histogram = macd_line - signal_line
        
        # Current values
        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        current_histogram = histogram[-1]
        
        # Determine trend based on MACD crossover and histogram
        if current_macd > current_signal and current_histogram > 0:
            trend = "BULLISH"
        elif current_macd < current_signal and current_histogram < 0:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"
        
        return {
            "macd": round(current_macd, 6),
            "signal": round(current_signal, 6),
            "histogram": round(current_histogram, 6),
            "trend": trend
        }
    except Exception as e:
        print(f"MACD calculation error: {e}")
        return {"macd": 0, "signal": 0, "histogram": 0, "trend": "NEUTRAL"}

def fetch_data(symbol="BTCUSDT", interval="1h", limit=100):
    """Fetch historical price data from Binance."""
    try:
        print(f"\n=== Fetching data for {symbol} ===")  # Debug log
        if client:
            print("Using Binance client...")  # Debug log
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            print(f"Received {len(klines)} candles from Binance")  # Debug log
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 
                                             'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 
                                             'taker_buy_quote_asset_volume', 'ignore'])
            
            # Convert numeric columns to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
        else:
            error_msg = "Trading client not initialized. Cannot fetch market data."
            log_error_to_csv(error_msg, "CLIENT_ERROR", "fetch_data", "ERROR")
            return None
        
        # Calculate technical indicators
        df['sma5'] = df['close'].rolling(5).mean()
        df['sma20'] = df['close'].rolling(20).mean()
        
        # Add Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        df['bb_upper'] = df['bb_middle'] + 2 * df['close'].rolling(window=20).std()
        df['bb_lower'] = df['bb_middle'] - 2 * df['close'].rolling(window=20).std()
        
        # Calculate RSI
        prices = df['close'].values
        df['rsi'] = calculate_rsi(prices)
        
        # Calculate MACD
        macd_data = calculate_macd(prices)
        df['macd'] = macd_data['macd']
        df['macd_signal'] = macd_data['signal']
        df['macd_histogram'] = macd_data['histogram']
        df['macd_trend'] = macd_data['trend']
        
        # Add volatility measure
        df['volatility'] = df['close'].pct_change().rolling(window=20).std() * np.sqrt(252)
        
        # Calculate Average True Range (ATR)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df['atr'] = ranges.max(axis=1).rolling(14).mean()
        
        # Add volume trend
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_trend'] = df['volume'] / df['volume_sma']
        
        return df
        
    except Exception as e:
        error_msg = f"Error fetching data for {symbol}: {e}"
        log_error_to_csv(error_msg, "DATA_FETCH_ERROR", "fetch_data", "ERROR")
        bot_status['errors'].append(error_msg)
        return None

def scan_trading_pairs(base_assets=None, quote_asset=None, min_volume_usdt=None):
    """Scan trading pairs using configuration parameters"""
    base_assets = base_assets or config.MONITORED_BASE_ASSETS
    quote_asset = quote_asset or config.QUOTE_ASSET
    min_volume_usdt = min_volume_usdt or config.VOLUME_THRESHOLD
    """Scan multiple trading pairs for opportunities."""
    try:
        opportunities = []
        if not client:
            return opportunities
            
        # Get 24hr ticker for all symbols
        tickers = client.get_ticker()
        
        # Filter for pairs we're interested in
        for ticker in tickers:
            symbol = ticker['symbol']
            if not symbol.endswith(quote_asset):
                continue
                
            base_asset = symbol[:-len(quote_asset)]
            if base_asset not in base_assets:
                continue
                
            volume_usdt = float(ticker['quoteVolume'])  # Volume in USDT
            if volume_usdt < min_volume_usdt:
                continue
                
            print(f"\nAnalyzing {symbol}...")
            
            # Fetch detailed data for analysis
            df = fetch_data(symbol=symbol)
            if df is None or len(df) < 30:  # Minimum data requirement
                continue
                
            # Get current market conditions
            current_price = float(df['close'].iloc[-1])
            current_volume = float(df['volume'].iloc[-1])
            rsi = float(df['rsi'].iloc[-1])
            macd_trend = df['macd_trend'].iloc[-1]
            
            # Calculate score components
            score = 0
            reasons = []
            
            # 1. RSI Analysis (0-30 points)
            if rsi < 30:
                score += 30
                reasons.append(f"RSI oversold ({rsi:.1f})")
            elif rsi > 70:
                score -= 30
                reasons.append(f"RSI overbought ({rsi:.1f})")
                
            # 2. MACD Analysis (0-20 points)
            if macd_trend == "BULLISH":
                score += 20
                reasons.append("MACD bullish crossover")
            elif macd_trend == "BEARISH":
                score -= 20
                reasons.append("MACD bearish crossover")
            
            # 3. Volume Analysis (0-20 points)
            volume_ratio = current_volume / df['volume'].mean()
            if volume_ratio > 1.5:
                score += 20
                reasons.append(f"High volume ({volume_ratio:.1f}x average)")
            
            # 4. Trend Analysis (0-20 points)
            sma5 = df['sma5'].iloc[-1]
            sma20 = df['sma20'].iloc[-1]
            if sma5 > sma20:
                score += (sma5/sma20 - 1) * 100
                reasons.append(f"Uptrend (SMA5 > SMA20)")
            else:
                score -= (sma20/sma5 - 1) * 100
                reasons.append(f"Downtrend (SMA5 < SMA20)")
            
            # 5. Volatility Analysis (0-10 points)
            volatility = df['volatility'].iloc[-1]
            if 0.1 <= volatility <= 0.4:  # Reasonable volatility range
                score += 10
                reasons.append(f"Optimal volatility ({volatility:.2f})")
            elif volatility > 0.4:
                score -= 10
                reasons.append(f"Excessive volatility ({volatility:.2f})")
            
            # Add sentiment for major pairs
            if base_asset in ["BTC", "ETH"]:
                sentiment = analyze_market_sentiment()
                if sentiment == "bullish":
                    score *= 1.2
                    reasons.append("Bullish market sentiment")
                elif sentiment == "bearish":
                    score *= 0.8
                    reasons.append("Bearish market sentiment")
            
            # Generate trading signal
            signal = "HOLD"
            if score >= 50:
                signal = "BUY"
            elif score <= -50:
                signal = "SELL"
            
            # Add to opportunities if significant
            if abs(score) >= 30:
                opportunities.append({
                    'symbol': symbol,
                    'signal': signal,
                    'score': score,
                    'price': current_price,
                    'volume_24h': volume_usdt,
                    'rsi': rsi,
                    'macd_trend': macd_trend,
                    'volume_ratio': volume_ratio,
                    'volatility': volatility,
                    'reasons': reasons
                })
                
                print(f"Found opportunity for {symbol}:")
                print(f"Signal: {signal}")
                print(f"Score: {score:.1f}")
                print(f"Current price: ${current_price:.2f}")
                print(f"24h Volume: ${volume_usdt:,.0f}")
                print("Reasons:", ", ".join(reasons))
        
        # Sort by absolute score (highest opportunity first)
        opportunities.sort(key=lambda x: abs(x['score']), reverse=True)
        
        return opportunities
        
    except Exception as e:
        error_msg = f"Error scanning trading pairs: {e}"
        log_error_to_csv(error_msg, "SCAN_ERROR", "scan_trading_pairs", "ERROR")
        print(error_msg)
        return []

def analyze_trading_pairs():
    """Analyze all available trading pairs and find the best opportunities"""
    pairs_analysis = []
    default_result = {"symbol": "BTCUSDT", "signal": "HOLD", "score": 0}
    
    try:
        if not client:
            return default_result
        
        try:
            exchange_info = client.get_exchange_info()
        except Exception as e:
            log_error_to_csv(str(e), "PAIR_ANALYSIS", "analyze_trading_pairs", "ERROR")
            return default_result
        
        # Get all USDT pairs with good volume
        for symbol_info in exchange_info['symbols']:
            # Skip non-USDT or non-trading pairs
            if not (symbol_info['quoteAsset'] == 'USDT' and symbol_info['status'] == 'TRADING'):
                continue
            
            symbol = symbol_info['symbol']
            
            # Get 24hr stats
            try:
                # Get basic market stats
                ticker = client.get_ticker(symbol=symbol)
                volume_usdt = float(ticker['quoteVolume'])
                trades_24h = int(ticker['count'])
            except Exception as e:
                log_error_to_csv(str(e), "PAIR_ANALYSIS", f"analyze_trading_pairs_{symbol}_stats", "WARNING")
                continue

                # Filter out low volume/activity pairs
                if volume_usdt < 1000000 or trades_24h < 1000:  # Minimum $1M volume and 1000 trades
                    continue
                
                try:
                    # Get detailed market data
                    df = fetch_data(symbol=symbol)
                    if df is None or df.empty:
                        continue
                    
                    # Calculate metrics
                    volatility = df['close'].pct_change().std() * np.sqrt(252)
                    rsi = calculate_rsi(df['close'].values)
                    macd_data = calculate_macd(df['close'].values)
                    
                    # Get sentiment for major coins
                    sentiment = 'neutral'
                    if symbol in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']:
                        sentiment = analyze_market_sentiment()
                    
                    # Calculate trend metrics
                    trend_strength = 0
                    trend_score = 0
                    if 'sma5' in df.columns and 'sma20' in df.columns:
                        trend_strength = abs(df['sma5'].iloc[-1] - df['sma20'].iloc[-1]) / df['sma20'].iloc[-1]
                        trend_score = 1 if df['sma5'].iloc[-1] > df['sma20'].iloc[-1] else -1
                    
                    momentum = df['close'].pct_change(5).iloc[-1]
                    volume_trend = df['volume'].iloc[-1] / df['volume'].rolling(20).mean().iloc[-1]
                    
                    # Composite score calculation
                    price_potential = 0
                    if rsi < 30:  # Oversold
                        price_potential = 1
                    elif rsi > 70:  # Overbought
                        price_potential = -1
                        
                    momentum_score = momentum * 100  # Convert to percentage
                    
                    # Calculate final opportunity score
                    base_score = (
                        price_potential * 0.3 +  # RSI weight
                        trend_score * 0.3 +      # Trend weight
                        momentum_score * 0.2 +    # Momentum weight
                        (volume_trend - 1) * 0.2  # Volume trend weight
                    )
                    
                    # Apply volatility adjustment if configured
                    if config.ADAPTIVE_STRATEGY['volatility_adjustment']:
                        score = base_score * (1 - (volatility/config.MODERATE_STRATEGY['volatility_max']))
                    else:
                        score = base_score
                    
                    # Add sentiment boost for major coins
                    if sentiment == 'bullish':
                        score *= 1.2
                    elif sentiment == 'bearish':
                        score *= 0.8
                    
                    # Generate signal based on composite analysis
                    signal = "HOLD"
                    if score > 0.5:  # Strong bullish signal
                        signal = "BUY"
                    elif score < -0.5:  # Strong bearish signal
                        signal = "SELL"
                    
                    # Store analysis results
                    pairs_analysis.append({
                        "symbol": symbol,
                        "signal": signal,
                        "score": score,
                        "volume_usdt": volume_usdt,
                        "volatility": volatility,
                        "rsi": rsi,
                        "trend_strength": trend_strength,
                        "volume_trend": volume_trend,
                        "sentiment": sentiment
                    })
                
                except Exception as e:
                    log_error_to_csv(str(e), "PAIR_ANALYSIS", f"analyze_trading_pairs_{symbol}_analysis", "WARNING")
                    continue
        
        # Sort by absolute score (highest opportunity regardless of buy/sell)
        if pairs_analysis:
            pairs_analysis.sort(key=lambda x: abs(x['score']), reverse=True)
            return pairs_analysis[0]
        
        return {"symbol": "BTCUSDT", "signal": "HOLD", "score": 0}
            
    except Exception as e:
        log_error_to_csv(str(e), "PAIR_ANALYSIS", "analyze_trading_pairs", "ERROR")
        return {"symbol": "BTCUSDT", "signal": "HOLD", "score": 0}

def strict_strategy(df, symbol, indicators):
    """
    Conservative trading strategy with strict entry/exit conditions
    - Requires strong confirmation from multiple indicators
    - Focuses on minimizing risk
    - High threshold for entry/exit points
    """
    if df is None or len(df) < 30:
        return "HOLD", "Insufficient data"
        
    # Extract indicators
    rsi = indicators['rsi']
    macd_trend = indicators['macd_trend']
    sentiment = indicators['sentiment']
    sma5 = indicators['sma5']
    sma20 = indicators['sma20']
    volatility = indicators['volatility']
    current_price = indicators['current_price']
    
    # Get strict strategy thresholds from config
    strict_config = config.STRICT_STRATEGY
    
    # Strict buy conditions with configurable thresholds
    buy_conditions = [
        rsi < config.RSI_OVERSOLD,  # Strong oversold
        macd_trend == "BULLISH",
        sma5 > sma20,  # Clear uptrend
        sentiment == "bullish",
        volatility < strict_config['volatility_max']  # Configurable volatility threshold
    ]
    
    # Strict sell conditions
    sell_conditions = [
        rsi > 70,  # Strong overbought
        macd_trend == "BEARISH",
        sma5 < sma20,  # Clear downtrend
        sentiment == "bearish",
        volatility < 0.3  # Low volatility
    ]
    
    if all(buy_conditions):
        return "BUY", "Strong buy signal with multiple confirmations"
    elif all(sell_conditions):
        return "SELL", "Strong sell signal with multiple confirmations"
    
    return "HOLD", "Waiting for stronger signals"

def moderate_strategy(df, symbol, indicators):
    """
    Balanced trading strategy with moderate entry/exit conditions
    - More frequent trades
    - Balanced risk/reward
    - Moderate thresholds from configuration
    """
    if df is None or len(df) < 30:
        return "HOLD", "Insufficient data"
        
    # Extract indicators
    rsi = indicators['rsi']
    macd_trend = indicators['macd_trend']
    sentiment = indicators['sentiment']
    sma5 = indicators['sma5']
    sma20 = indicators['sma20']
    
    # Get moderate strategy config
    moderate_config = config.MODERATE_STRATEGY
    min_signals = moderate_config['min_signals']
    
    # Buy signals with configurable thresholds
    buy_signals = 0
    if rsi < config.RSI_OVERSOLD + 10: buy_signals += 1  # Less strict RSI
    if macd_trend == "BULLISH": buy_signals += 2
    if sma5 > sma20 and abs(sma5 - sma20)/sma20 > moderate_config['trend_strength']: buy_signals += 1
    if sentiment == "bullish": buy_signals += 1
    
    # Sell signals (less strict)
    sell_signals = 0
    if rsi > 60: sell_signals += 1  # Less strict RSI
    if macd_trend == "BEARISH": sell_signals += 2
    if sma5 < sma20: sell_signals += 1
    if sentiment == "bearish": sell_signals += 1
    
    if buy_signals >= 3:
        return "BUY", f"Moderate buy signal ({buy_signals} confirmations)"
    elif sell_signals >= 3:
        return "SELL", f"Moderate sell signal ({sell_signals} confirmations)"
    
    return "HOLD", "Insufficient signals for trade"

def adaptive_strategy(df, symbol, indicators):
    """
    Smart strategy that adapts based on market conditions using configuration parameters
    - Uses volatility and trend strength
    - Adjusts thresholds dynamically based on config
    - Considers market regime with configurable settings
    """
    if df is None or len(df) < 30:
        return "HOLD", "Insufficient data"
        
    # Extract indicators
    rsi = indicators['rsi']
    macd_trend = indicators['macd_trend']
    sentiment = indicators['sentiment']
    volatility = indicators['volatility']
    current_price = indicators['current_price']
    sma5 = indicators['sma5']
    sma20 = indicators['sma20']
    
    # Get adaptive strategy settings
    adaptive_config = config.ADAPTIVE_STRATEGY
    
    # Calculate market regime using config thresholds
    is_high_volatility = volatility > config.MODERATE_STRATEGY['volatility_max']
    trend_strength = abs((sma5 - sma20) / sma20)
    is_strong_trend = trend_strength > config.STRICT_STRATEGY['trend_strength']
    
    # Adjust thresholds based on market conditions
    if is_high_volatility:
        rsi_buy = 35  # More conservative in high volatility
        rsi_sell = 65
    else:
        rsi_buy = 40  # More aggressive in low volatility
        rsi_sell = 60
        
    # Score-based system (0-100)
    score = 50  # Start neutral
    
    # Adjust score based on indicators
    if rsi < rsi_buy: score += 20
    elif rsi > rsi_sell: score -= 20
    
    if macd_trend == "BULLISH": score += 15
    elif macd_trend == "BEARISH": score -= 15
    
    if sentiment == "bullish": score += 10
    elif sentiment == "bearish": score -= 10
    
    if sma5 > sma20: score += 5
    else: score -= 5
    
    # Adjust score based on market regime
    if is_high_volatility:
        score = score * 0.8  # Reduce conviction in high volatility
    if is_strong_trend:
        score = score * 1.2  # Increase conviction in strong trends
        
    # Use configurable score threshold for decisions
    score_threshold = adaptive_config['score_threshold']
    
    if score >= score_threshold:
        return "BUY", f"Adaptive buy signal (Score: {score:.0f}, Threshold: {score_threshold})"
    elif score <= -score_threshold:
        return "SELL", f"Adaptive sell signal (Score: {score:.0f}, Threshold: {score_threshold})"
    
    return "HOLD", f"Neutral conditions (Score: {score:.0f}, Threshold: ±{score_threshold})"

def signal_generator(df, symbol="BTCUSDT"):
    print("\n=== Generating Trading Signal ===")  # Debug log
    if df is None or len(df) < 30:
        print(f"Insufficient data for {symbol}")  # Debug log
        signal = "HOLD"
        bot_status.update({
            'last_signal': signal,
            'last_update': format_cairo_time()
        })
        log_signal_to_csv(signal, 0, {"symbol": symbol}, "Insufficient data")
        return signal
    
    # Enhanced risk management checks
    daily_pnl = bot_status['trading_summary'].get('total_revenue', 0)
    consecutive_losses = bot_status.get('consecutive_losses', 0)
    
    # Stop trading if daily loss limit exceeded
    if daily_pnl < -config.MAX_DAILY_LOSS:
        log_signal_to_csv("HOLD", 0, {"symbol": symbol}, f"Daily loss limit exceeded: ${daily_pnl}")
        return "HOLD"
    
    # Reduce activity after consecutive losses
    if consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
        log_signal_to_csv("HOLD", 0, {"symbol": symbol}, f"Too many consecutive losses: {consecutive_losses}")
        return "HOLD"
    
    sentiment = analyze_market_sentiment()
    
    # Get the latest technical indicators with error handling
    try:
        rsi = df['rsi'] if isinstance(df['rsi'], (int, float)) else df['rsi'].iloc[-1] if hasattr(df['rsi'], 'iloc') else df['rsi']
        macd = df['macd'] if isinstance(df['macd'], (int, float)) else df['macd'].iloc[-1] if hasattr(df['macd'], 'iloc') else df['macd']
        macd_trend = df['macd_trend'].iloc[-1] if hasattr(df['macd_trend'], 'iloc') else df['macd_trend']
        sma5 = df['sma5'].iloc[-1]
        sma20 = df['sma20'].iloc[-1]
        current_price = df['close'].iloc[-1] if hasattr(df['close'], 'iloc') else df['close']
        volatility = df['volatility'].iloc[-1] if 'volatility' in df else df['close'].pct_change().std() * np.sqrt(252)
    except Exception as e:
        log_error_to_csv(f"Error extracting indicators: {str(e)}", "INDICATOR_ERROR", "signal_generator", "ERROR")
        return "HOLD"
    
    # Handle NaN values
    if pd.isna(rsi) or pd.isna(macd) or pd.isna(sma5) or pd.isna(sma20):
        log_signal_to_csv("HOLD", current_price, {'rsi': rsi, 'macd': macd, 'sentiment': sentiment}, "NaN values detected")
        return "HOLD"
        
    # Prepare indicators dictionary for strategies
    indicators = {
        'rsi': rsi,
        'macd': macd,
        'macd_trend': macd_trend,
        'sentiment': sentiment,
        'sma5': sma5,
        'sma20': sma20,
        'current_price': current_price,
        'volatility': volatility
    }
    
    # Use selected strategy with enhanced error handling
    try:
        strategy = bot_status.get('trading_strategy', 'STRICT')
        print(f"Using strategy: {strategy}")  # Debug log
        
        if strategy == 'STRICT':
            signal, reason = strict_strategy(df, symbol, indicators)
        elif strategy == 'MODERATE':
            signal, reason = moderate_strategy(df, symbol, indicators)
        elif strategy == 'ADAPTIVE':
            signal, reason = adaptive_strategy(df, symbol, indicators)
        else:
            print(f"Unknown strategy {strategy}, defaulting to STRICT")  # Debug log
            signal, reason = strict_strategy(df, symbol, indicators)  # Default to strict
            
        # Update bot status with latest signal and timestamp
        current_time = format_cairo_time()
        bot_status.update({
            'last_signal': signal,
            'last_update': current_time,
            'last_strategy': strategy
        })
            
        print(f"Strategy {strategy} generated signal: {signal} - {reason}")  # Debug log
        
        # Log strategy decision to signals log instead of error log
        log_signal_to_csv(
            signal,
            current_price,
            indicators,
            f"Strategy {strategy} - {reason}"
        )
        
    except Exception as e:
        error_msg = f"Error in strategy execution: {str(e)}"
        print(error_msg)  # Debug log
        log_error_to_csv(error_msg, "STRATEGY_ERROR", "signal_generator", "ERROR")
        signal, reason = "HOLD", f"Strategy error: {str(e)}"
    
    return signal
    
    # Prepare indicators for logging
    indicators = {
        'rsi': rsi,
        'macd': macd,
        'macd_trend': macd_trend,
        'sentiment': sentiment,
        'sma5': sma5,
        'sma20': sma20
    }
    
    # Statistical and facts-based trading strategy
    # Calculate actual market volatility using standard deviation of returns
    returns = df['close'].pct_change().dropna()
    volatility = returns.std() * np.sqrt(252)  # Annualized volatility
    
    # Calculate statistical price ranges
    price_std = df['close'].std()
    current_price = df['close'].iloc[-1]
    price_zscore = (current_price - df['close'].mean()) / price_std
    
    # Calculate True Range for actual market range
    df['tr'] = pd.DataFrame({
        'hl': df['high'] - df['low'],
        'hc': abs(df['high'] - df['close'].shift(1)),
        'lc': abs(df['low'] - df['close'].shift(1))
    }).max(axis=1)
    
    # Use statistical ATR for actual market range measurement
    atr = df['tr'].rolling(14).mean().iloc[-1]
    if pd.isna(atr):
        atr = df['tr'].median()  # Use median for more robustness
        atr = df['tr'].median()  # Use median for more robustness
    
    # Position sizing based on statistical volatility measurement
    position_size_factor = 1.0 / (1 + volatility)  # Inversely proportional to volatility
    
    # Calculate RSI thresholds based on historical distribution
    rsi_series = df['rsi'].dropna()
    rsi_std = rsi_series.std()
    rsi_mean = rsi_series.mean()
    
    # Use statistical bounds for RSI (mean ± 2 standard deviations)
    rsi_buy = max(10, rsi_mean - 2 * rsi_std)  # Statistical lower bound
    rsi_sell = min(90, rsi_mean + 2 * rsi_std)  # Statistical upper bound
    
    # Volume trend (comparing to 20-period average volume)
    volume_ma = df['volume'].rolling(20).mean().iloc[-1]
    volume_trend = df['volume'].iloc[-1] / volume_ma
    
    # Trend strength and momentum
    trend_strength = abs(sma5 - sma20) / sma20
    momentum = df['close'].pct_change(5).iloc[-1]  # 5-period momentum
    
    # Maximum drawdown control (trailing 20 periods)
    rolling_max = df['close'].rolling(20).max()
    drawdown = (rolling_max - df['close']) / rolling_max
    current_drawdown = drawdown.iloc[-1]
    max_allowed_drawdown = 0.15  # 15% maximum drawdown limit
    
    # Time-based filters (avoid trading during high volatility periods)
    current_time = pd.Timestamp.now(tz='UTC')
    is_favorable_time = True
    if current_time.hour in [0, 1, 2, 3]:  # Avoid trading during typical high volatility hours
        is_favorable_time = False
    
    buy_signals = 0
    sell_signals = 0
    
    # Statistical analysis based trading decisions
    
    # Calculate statistical stop-loss using Value at Risk (VaR)
    returns_sorted = np.sort(returns)
    var_95 = returns_sorted[int(0.05 * len(returns))]  # 95% VaR
    stop_loss_pct = abs(var_95 * 100)  # Use VaR as stop-loss
    
    # Volume analysis using statistical significance
    volume_zscore = (df['volume'].iloc[-1] - df['volume'].mean()) / df['volume'].std()
    significant_volume = abs(volume_zscore) > 2  # Volume is statistically significant
    
    # Price momentum using statistical significance
    returns_mean = returns.mean()
    returns_std = returns.std()
    momentum_zscore = (returns.iloc[-1] - returns_mean) / returns_std
    
    # Buy signals based on statistical evidence
    if rsi < rsi_buy: buy_signals += 1  # Statistically oversold
    if price_zscore < -2: buy_signals += 1  # Price statistically low
    if momentum_zscore > 1: buy_signals += 1  # Statistically significant upward momentum
    if significant_volume and volume_zscore > 0: buy_signals += 1  # Statistically significant volume increase
    if macd > 2 * df['macd'].std(): buy_signals += 1  # MACD shows statistically significant trend
    
    # Sell signals based on statistical evidence
    if rsi > rsi_sell: sell_signals += 1  # Statistically overbought
    if price_zscore > 2: sell_signals += 1  # Price statistically high
    if momentum_zscore < -1: sell_signals += 1  # Statistically significant downward momentum
    if significant_volume and volume_zscore < 0: sell_signals += 1  # Statistically significant volume decrease
    if macd < -2 * df['macd'].std(): sell_signals += 1  # MACD shows statistically significant negative trend
    
    # Statistical stop-loss check
    if returns.iloc[-1] < var_95: 
        sell_signals += 2  # Strong sell if price moves beyond VaR threshold
    
    # Generate signal based on signal count with position sizing and risk management
    # Update indicators with risk metrics and symbol
    indicators.update({
        'symbol': symbol,
        'volatility': volatility,
        'atr': atr,
        'drawdown': current_drawdown,
        'position_size': position_size_factor,
        'stop_loss_pct': stop_loss_pct if 'stop_loss_pct' in locals() else None
    })
    
    if buy_signals >= 4:  # Require more confirming signals (4 out of 5)
        reason = (f"BUY: RSI={rsi:.1f}, MACD={macd:.6f}, "
                 f"SMA5/SMA20={sma5:.2f}/{sma20:.2f}, Vol={volume_trend:.2f}, "
                 f"Position={position_size_factor:.1f}, StopLoss={stop_loss_pct:.1f}%")
        log_signal_to_csv("BUY", current_price, indicators, reason)
        return "BUY"
    elif sell_signals >= 4 or (sell_signals >= 3 and current_drawdown > stop_loss_pct/100):
        reason = (f"SELL: RSI={rsi:.1f}, MACD={macd:.6f}, "
                 f"SMA5/SMA20={sma5:.2f}/{sma20:.2f}, Vol={volume_trend:.2f}, "
                 f"Drawdown={current_drawdown*100:.1f}%, StopLoss={stop_loss_pct:.1f}%")
        log_signal_to_csv("SELL", current_price, indicators, reason)
        return "SELL"
    else:
        reason = (f"HOLD: RSI={rsi:.1f}, MACD={macd:.6f}, "
                 f"SMA5={sma5:.2f}, SMA20={sma20:.2f}, "
                 f"Vol={volume_trend:.2f}, Drawdown={current_drawdown*100:.1f}%")
        log_signal_to_csv("HOLD", current_price, indicators, reason)
        return "HOLD"

def update_trade_tracking(trade_result, profit_loss=0):
    """Track consecutive wins/losses for smart risk management"""
    try:
        if trade_result == 'success':
            if profit_loss > 0:
                bot_status['consecutive_losses'] = 0  # Reset on profitable trade
                bot_status['consecutive_wins'] = bot_status.get('consecutive_wins', 0) + 1
            else:
                bot_status['consecutive_losses'] = bot_status.get('consecutive_losses', 0) + 1
                bot_status['consecutive_wins'] = 0
        else:
            bot_status['consecutive_losses'] = bot_status.get('consecutive_losses', 0) + 1
            bot_status['consecutive_wins'] = 0
            
        # Log if consecutive losses are getting high
        if bot_status['consecutive_losses'] >= 3:
            log_error_to_csv(
                f"Consecutive losses: {bot_status['consecutive_losses']}", 
                "RISK_WARNING", 
                "update_trade_tracking", 
                "WARNING"
            )
    except Exception as e:
        log_error_to_csv(str(e), "TRACKING_ERROR", "update_trade_tracking", "ERROR")

def execute_trade(signal, symbol="BTCUSDT", qty=None):
    print("\n=== Trade Execution Debug Log ===")
    print(f"Attempting trade: {signal} for {symbol}")
    print(f"Initial quantity: {qty}")
    
    if signal == "HOLD":
        print("Signal is HOLD - no action needed")
        return f"Signal: {signal} - No action taken"
        
    # Get symbol info for precision and filters
    symbol_info = None
    try:
        if client:
            print("Getting exchange info from Binance API...")
            exchange_info = client.get_exchange_info()
            symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == symbol), None)
            if symbol_info:
                print(f"Symbol info found for {symbol}:")
                print(f"Base Asset: {symbol_info['baseAsset']}")
                print(f"Quote Asset: {symbol_info['quoteAsset']}")
                print(f"Minimum Lot Size: {next((f['minQty'] for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), 'unknown')}")
                
                # Get current ticker info
                ticker = client.get_ticker(symbol=symbol)
                print(f"Current {symbol} price: ${float(ticker['lastPrice']):.2f}")
                print(f"24h Volume: {float(ticker['volume']):.2f} {symbol_info['baseAsset']}")
                print(f"24h Price Change: {float(ticker['priceChangePercent']):.2f}%")
            else:
                print(f"Warning: No symbol info found for {symbol}")
        else:
            print("Warning: Client not initialized - running in demo mode")
    except Exception as e:
        log_error_to_csv(str(e), "SYMBOL_INFO_ERROR", "execute_trade", "ERROR")
        print(f"Error getting symbol info: {e}")
        return f"Failed to get symbol info: {e}"
    
    # Calculate position size based on available balance and risk management
    try:
        if client:
            print("\n=== Balance Check ===")
            balance = client.get_account()
            usdt_balance = float(next((b['free'] for b in balance['balances'] if b['asset'] == 'USDT'), 0))
            btc_balance = float(next((b['free'] for b in balance['balances'] if b['asset'] == 'BTC'), 0))
            print(f"Available USDT balance: {usdt_balance}")
            print(f"Available BTC balance: {btc_balance}")
            
            # Calculate risk amount based on configuration
            risk_amount = usdt_balance * (config.RISK_PERCENTAGE / 100)
            print(f"Risk amount ({config.RISK_PERCENTAGE}% of balance): {risk_amount} USDT")
            
            # Get current market price
            print("\n=== Price Check ===")
            ticker = client.get_ticker(symbol=symbol)
            current_price = float(ticker['lastPrice'])
            print(f"Current {symbol} price: {current_price}")
            print(f"24h price change: {ticker['priceChangePercent']}%")
            
            if symbol_info:
                print("\n=== Position Sizing ===")
                # Get lot size filter
                lot_size_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                min_qty = float(lot_size_filter['minQty']) if lot_size_filter else 0.001
                print(f"Minimum allowed quantity: {min_qty}")
                
                # Calculate quantity based on risk amount and current price
                raw_qty = risk_amount / current_price
                print(f"Raw quantity (before adjustments): {raw_qty}")
                qty = max(min_qty, raw_qty)
                print(f"Quantity after minimum check: {qty}")
                
                # Round to correct precision
                step_size = float(lot_size_filter['stepSize']) if lot_size_filter else 0.001
                precision = len(str(step_size).split('.')[-1])
                qty = round(qty - (qty % float(step_size)), precision)
                print(f"Final quantity after rounding (step size {step_size}): {qty}")
                print(f"Estimated trade value: {qty * current_price} USDT")
    except Exception as e:
        log_error_to_csv(str(e), "POSITION_SIZE_ERROR", "execute_trade", "ERROR")
        qty = 0.001  # Fallback to minimum quantity
    
    # Create trade info structure
    trade_info = {
        'timestamp': format_cairo_time(),
        'signal': signal,
        'symbol': symbol,
        'quantity': qty,
        'status': 'simulated',
        'price': 0,
        'value': 0,
        'fee': 0
    }
    
    if client is None:
        error_msg = "Trading client not initialized. Cannot execute trade."
        log_error_to_csv(error_msg, "CLIENT_ERROR", "execute_trade", "ERROR")
        return error_msg
    
    try:
        print("\n=== Trade Execution ===")
        if signal == "BUY":
            print("Processing BUY order...")
            usdt = float([x['free'] for x in client.get_account()['balances'] if x['asset'] == 'USDT'][0])
            print(f"USDT available for buy: {usdt}")
            if usdt < 10: 
                print("Insufficient USDT balance (minimum 10 USDT required)")
                trade_info['status'] = 'insufficient_funds'
                bot_status['trading_summary']['failed_trades'] += 1
                return "Insufficient USDT"
            
            order = client.order_market_buy(symbol=symbol, quantity=qty)
            trade_info['price'] = float(order['fills'][0]['price']) if order['fills'] else 0
            trade_info['value'] = float(order['cummulativeQuoteQty'])
            trade_info['fee'] = sum([float(fill['commission']) for fill in order['fills']])
            trade_info['status'] = 'success'
            
            # Update trading summary
            bot_status['trading_summary']['total_buy_volume'] += trade_info['value']
            bot_status['trading_summary']['successful_trades'] += 1
            
        elif signal == "SELL":
            print("Processing SELL order...")
            # Extract base asset from symbol (e.g., "BTC" from "BTCUSDT")
            base_asset = symbol[:-4] if symbol.endswith('USDT') else symbol.split(symbol_info['quoteAsset'])[0]
            base_balance = float([x['free'] for x in client.get_account()['balances'] if x['asset'] == base_asset][0])
            print(f"{base_asset} available for sell: {base_balance}")
            
            if base_balance < qty:
                print(f"Insufficient {base_asset} balance (have: {base_balance}, need: {qty})")
                trade_info['status'] = 'insufficient_funds'
                bot_status['trading_summary']['failed_trades'] += 1
                log_error_to_csv(f"Insufficient {base_asset} for sell order", "BALANCE_ERROR", "execute_trade", "WARNING")
                return f"Insufficient {base_asset}"
            
            print(f"Placing market sell order: {qty} {base_asset}")
            order = client.order_market_sell(symbol=symbol, quantity=qty)
            trade_info['price'] = float(order['fills'][0]['price']) if order['fills'] else 0
            trade_info['value'] = float(order['cummulativeQuoteQty'])
            trade_info['fee'] = sum([float(fill['commission']) for fill in order['fills']])
            trade_info['status'] = 'success'
            
            # Update trading summary
            bot_status['trading_summary']['total_sell_volume'] += trade_info['value']
            bot_status['trading_summary']['successful_trades'] += 1
            
            # Calculate revenue (sell value minus average buy cost)
            if bot_status['trading_summary']['total_buy_volume'] > 0:
                avg_buy_price = bot_status['trading_summary']['total_buy_volume'] / (bot_status['trading_summary']['successful_trades'] / 2)  # Rough estimate
                revenue = trade_info['value'] - (qty * avg_buy_price)
                bot_status['trading_summary']['total_revenue'] += revenue
        
        # Update trade history (keep last 10 trades)
        bot_status['trading_summary']['trades_history'].insert(0, trade_info)
        if len(bot_status['trading_summary']['trades_history']) > 10:
            bot_status['trading_summary']['trades_history'].pop()
        
        # Log real trade to CSV
        try:
            balance_before = balance_after = 0
            if client:
                account = client.get_account()
                usdt_balance = float([x['free'] for x in account['balances'] if x['asset'] == 'USDT'][0])
                btc_balance = float([x['free'] for x in account['balances'] if x['asset'] == 'BTC'][0])
                balance_after = usdt_balance + (btc_balance * trade_info['price'])
            
            additional_data = {
                'rsi': bot_status.get('rsi', 50),
                'macd_trend': bot_status.get('macd', {}).get('trend', 'NEUTRAL'),
                'sentiment': bot_status.get('sentiment', 'neutral'),
                'balance_before': balance_before,
                'balance_after': balance_after,
                'profit_loss': revenue if signal == "SELL" and 'revenue' in locals() else 0,
                'order_id': order.get('orderId', '') if 'order' in locals() else ''
            }
            trade_info['order_id'] = additional_data['order_id']
            log_trade_to_csv(trade_info, additional_data)
        except Exception as csv_error:
            log_error_to_csv(f"CSV logging error: {csv_error}", "CSV_ERROR", "execute_trade", "WARNING")
        
        # Update statistics
        total_trades = bot_status['trading_summary']['successful_trades'] + bot_status['trading_summary']['failed_trades']
        bot_status['total_trades'] = total_trades
        
        if total_trades > 0:
            bot_status['trading_summary']['win_rate'] = (bot_status['trading_summary']['successful_trades'] / total_trades) * 100
            bot_status['trading_summary']['average_trade_size'] = (
                bot_status['trading_summary']['total_buy_volume'] + bot_status['trading_summary']['total_sell_volume']
            ) / total_trades if total_trades > 0 else 0
        
        # Update smart trade tracking
        profit_loss = revenue if signal == "SELL" and 'revenue' in locals() else 0
        update_trade_tracking('success', profit_loss)
        
        return f"{signal} order executed: {order['orderId']} at ${trade_info['price']:.2f}"
        
    except BinanceAPIException as e:
        trade_info['status'] = 'api_error'
        bot_status['trading_summary']['failed_trades'] += 1
        bot_status['trading_summary']['trades_history'].insert(0, trade_info)
        bot_status['errors'].append(str(e))
        
        # Update smart trade tracking for failed trades
        update_trade_tracking('failed', -1)  # Mark as loss
        
        # Log failed trade to CSV
        additional_data = {
            'rsi': bot_status.get('rsi', 50),
            'macd_trend': bot_status.get('macd', {}).get('trend', 'NEUTRAL'),
            'sentiment': bot_status.get('sentiment', 'neutral'),
            'balance_before': 0,
            'balance_after': 0,
            'profit_loss': 0
        }
        log_trade_to_csv(trade_info, additional_data)
        log_error_to_csv(str(e), "API_ERROR", "execute_trade", "ERROR")
        
        return f"Order failed: {str(e)}"

def scan_trading_pairs(base_assets, quote_asset="USDT", min_volume_usdt=1000000):
    """Smart multi-coin scanner for best trading opportunities"""
    opportunities = []
    
    for base in base_assets:
        try:
            symbol = f"{base}{quote_asset}"
            
            # Get 24h ticker statistics
            ticker = client.get_ticker(symbol=symbol)
            volume_usdt = float(ticker['quoteVolume'])
            price_change_pct = float(ticker['priceChangePercent'])
            
            # Skip if volume too low
            if volume_usdt < min_volume_usdt:
                continue
            
            # Fetch market data
            df = fetch_data(symbol=symbol, limit=50)  # Smaller dataset for scanning
            if df is None or len(df) < 20:
                continue
            
            # Calculate technical indicators
            current_price = float(df['close'].iloc[-1])
            rsi = calculate_rsi(df, period=14)
            macd_result = calculate_macd(df)
            sma_fast = calculate_sma(df, period=10)
            sma_slow = calculate_sma(df, period=20)
            
            if len(rsi) == 0 or macd_result is None:
                continue
            
            current_rsi = rsi.iloc[-1]
            macd_line = macd_result['macd'].iloc[-1] if len(macd_result['macd']) > 0 else 0
            signal_line = macd_result['signal'].iloc[-1] if len(macd_result['signal']) > 0 else 0
            
            # Score the opportunity (0-100)
            opportunity_score = 0
            signals = []
            
            # RSI scoring
            if current_rsi < 30:  # Oversold
                opportunity_score += 30
                signals.append("RSI_OVERSOLD")
            elif current_rsi > 70:  # Overbought
                opportunity_score += 20
                signals.append("RSI_OVERBOUGHT")
            elif 45 <= current_rsi <= 55:  # Neutral zone
                opportunity_score += 10
                signals.append("RSI_NEUTRAL")
            
            # MACD scoring
            if macd_line > signal_line:
                opportunity_score += 20
                signals.append("MACD_BULLISH")
            else:
                signals.append("MACD_BEARISH")
            
            # Price momentum scoring
            if abs(price_change_pct) > 5:  # High volatility
                opportunity_score += 15
                signals.append("HIGH_VOLATILITY")
            
            # Volume scoring
            if volume_usdt > min_volume_usdt * 5:  # Very high volume
                opportunity_score += 15
                signals.append("HIGH_VOLUME")
            
            # SMA trend scoring
            if current_price > sma_fast.iloc[-1] > sma_slow.iloc[-1]:
                opportunity_score += 10
                signals.append("UPTREND")
            elif current_price < sma_fast.iloc[-1] < sma_slow.iloc[-1]:
                opportunity_score += 10
                signals.append("DOWNTREND")
            
            opportunities.append({
                'symbol': symbol,
                'score': opportunity_score,
                'price': current_price,
                'volume_usdt': volume_usdt,
                'price_change_pct': price_change_pct,
                'rsi': current_rsi,
                'macd_trend': 'BULLISH' if macd_line > signal_line else 'BEARISH',
                'signals': signals,
                'data': df  # Include data for immediate analysis if selected
            })
            
        except Exception as e:
            print(f"Error scanning {base}{quote_asset}: {e}")
            continue
    
    # Sort by opportunity score (highest first)
    opportunities.sort(key=lambda x: x['score'], reverse=True)
    
    # Log top opportunities
    if opportunities:
        print(f"\n=== Top Trading Opportunities ===")
        for i, opp in enumerate(opportunities[:5]):  # Show top 5
            print(f"{i+1}. {opp['symbol']}: Score {opp['score']}, RSI {opp['rsi']:.1f}, "
                  f"Change {opp['price_change_pct']:.2f}%, Signals: {', '.join(opp['signals'])}")
    
    return opportunities

def trading_loop():
    """Enhanced trading loop with multi-coin scanning and robust error handling"""
    bot_status['running'] = True
    consecutive_errors = 0
    max_consecutive_errors = 5
    error_sleep_time = 300  # 5 minutes initial sleep on error
    scan_interval = 1800  # Scan every 30 minutes
    print("\n=== Starting Trading Loop ===")  # Debug log
    
    # Initialize trading summary if not exists
    if 'trading_summary' not in bot_status:
        bot_status['trading_summary'] = {
            'successful_trades': 0,
            'failed_trades': 0,
            'total_trades': 0,
            'total_buy_volume': 0.0,
            'total_sell_volume': 0.0,
            'total_revenue': 0.0,
            'win_rate': 0.0,
            'average_trade_size': 0.0,
            'trades_history': []
        }
    
    # Initialize multi-coin tracking
    bot_status['monitored_pairs'] = {}
    
    # Set initial next signal time
    bot_status['next_signal_time'] = get_cairo_time() + timedelta(seconds=scan_interval)
    bot_status['signal_interval'] = scan_interval
    
    while bot_status['running']:
        try:
            # Health check - ensure API connection is valid
            if not bot_status['api_connected']:
                initialize_client()
                if not bot_status['api_connected']:
                    raise Exception("Failed to connect to API")
            
            print("\n=== Scanning Trading Pairs ===")
            print(f"Time: {format_cairo_time()}")
            
            # Scan for trading opportunities across multiple pairs
            opportunities = scan_trading_pairs(
                base_assets=["BTC", "ETH", "BNB", "XRP", "SOL", "MATIC", "DOT", "ADA"],
                quote_asset="USDT",
                min_volume_usdt=1000000
            )
            
            if not opportunities:
                print("No significant trading opportunities found")
                # Generate signal for default pair even if no opportunities found
                current_symbol = "BTCUSDT"
                df = fetch_data(symbol=current_symbol)
                if df is not None:
                    signal = signal_generator(df, current_symbol)
                    current_price = float(df['close'].iloc[-1])
                    # Update bot status for default pair
                    bot_status.update({
                        'current_symbol': current_symbol,
                        'last_signal': signal,
                        'last_price': current_price,
                        'last_update': format_cairo_time(),
                        'rsi': float(df['rsi'].iloc[-1]),
                        'macd': {
                            'macd': float(df['macd'].iloc[-1]),
                            'signal': float(df['macd_signal'].iloc[-1]),
                            'trend': df['macd_trend'].iloc[-1]
                        }
                    })
                    print(f"Default pair signal: {signal} for {current_symbol}")
                
                # Set next signal time before sleeping
                bot_status['next_signal_time'] = get_cairo_time() + timedelta(seconds=scan_interval)
                print(f"Next signal expected at: {format_cairo_time(bot_status['next_signal_time'])}")
                
                time.sleep(scan_interval)  # Use scan interval instead of 1 hour
                continue
            
            # Process each opportunity in order of potential (highest scores first)
            for opportunity in opportunities[:3]:  # Look at top 3 opportunities
                current_symbol = opportunity['symbol']
                current_score = opportunity['score']
                df = opportunity['data']  # Get the pre-fetched data
                
                print(f"\n=== Analyzing {current_symbol} ===")
                print(f"Score: {current_score:.1f}")
                print(f"RSI: {opportunity['rsi']:.1f}")
                print(f"MACD Trend: {opportunity['macd_trend']}")
                print("Signals:", ", ".join(opportunity['signals']))
                
                # Generate detailed signal using the full data
                signal = signal_generator(df, current_symbol)
                current_price = opportunity['price']
                
                print(f"Generated Signal: {signal}")
                
                # Initialize or update pair tracking
                if current_symbol not in bot_status['monitored_pairs']:
                    bot_status['monitored_pairs'][current_symbol] = {
                        'last_signal': 'HOLD',
                        'last_price': 0,
                        'rsi': 50,
                        'macd': {'macd': 0, 'signal': 0, 'trend': 'NEUTRAL'},
                        'sentiment': 'neutral',
                        'total_trades': 0,
                        'successful_trades': 0,
                        'last_trade_time': None
                    }
                
                # Update current data for this pair
                bot_status['monitored_pairs'][current_symbol].update({
                    'last_signal': signal,
                    'last_price': current_price,
                    'rsi': opportunity['rsi'],
                    'macd': {'trend': opportunity['macd_trend']},
                    'last_update': format_cairo_time(),
                    'opportunity_score': current_score
                })
                
                # Update main bot status with best opportunity
                if current_symbol == opportunities[0]['symbol']:  # Best opportunity
                    bot_status.update({
                        'current_symbol': current_symbol,
                        'last_signal': signal,
                        'last_price': current_price,
                        'last_update': format_cairo_time(),
                        'rsi': opportunity['rsi'],
                        'macd': {'trend': opportunity['macd_trend']},
                        'opportunity_score': current_score
                    })
                
                # Execute trade if conditions are met
                if signal in ["BUY", "SELL"] and config.AUTO_TRADING:
                    # Additional safety checks before trading
                    if (bot_status.get('consecutive_losses', 0) < config.MAX_CONSECUTIVE_LOSSES and
                        bot_status.get('daily_loss', 0) < config.MAX_DAILY_LOSS):
                        
                        print(f"Executing {signal} for {current_symbol}")
                        result = execute_trade(signal, current_symbol)
                        print(f"Trade result: {result}")
                        
                        # Update pair tracking
                        bot_status['monitored_pairs'][current_symbol]['total_trades'] += 1
                        if "executed" in result.lower():
                            bot_status['monitored_pairs'][current_symbol]['successful_trades'] += 1
                        
                        # Only trade one opportunity per cycle to avoid overtrading
                        break
                    else:
                        print(f"Trading halted due to risk limits: "
                              f"Losses: {bot_status.get('consecutive_losses', 0)}, "
                              f"Daily Loss: {bot_status.get('daily_loss', 0)}")
                
            consecutive_errors = 0  # Reset error counter on successful cycle
            
            # Set next signal time before sleeping
            bot_status['next_signal_time'] = get_cairo_time() + timedelta(seconds=scan_interval)
            print(f"Next signal expected at: {format_cairo_time(bot_status['next_signal_time'])}")
            
            time.sleep(scan_interval)  # Use scan interval instead of 1 hour
        
        except KeyboardInterrupt:
            print("\n=== Keyboard Interrupt ===")
            bot_status['running'] = False
            break
            
        except Exception as e:
            consecutive_errors += 1
            error_msg = f"Trading loop error (attempt {consecutive_errors}/{max_consecutive_errors}): {e}"
            print(error_msg)
            
            # Log error to CSV
            log_error_to_csv(str(e), "TRADING_LOOP_ERROR", "trading_loop", "ERROR")
            
            # Update bot status
            bot_status['errors'].append(error_msg)
            bot_status['last_error'] = error_msg
            bot_status['last_update'] = format_cairo_time()
            
            if consecutive_errors >= max_consecutive_errors:
                print(f"Maximum consecutive errors reached ({max_consecutive_errors}). Stopping bot.")
                bot_status['running'] = False
                bot_status['status'] = 'stopped_due_to_errors'
                break
            
            # Exponential backoff for errors
            sleep_time = min(error_sleep_time * (2 ** (consecutive_errors - 1)), 3600)  # Max 1 hour
            print(f"Sleeping for {sleep_time} seconds before retry...")
            time.sleep(sleep_time)
    
    print("\n=== Trading Loop Stopped ===")
    bot_status['running'] = False
    bot_status['status'] = 'stopped'

def smart_portfolio_manager():
    """Advanced portfolio management with dynamic risk allocation"""
    try:
        if not client:
            return {"error": "API not connected"}
        
        account = client.get_account()
        balances = {b['asset']: float(b['free']) for b in account['balances'] if float(b['free']) > 0}
        
        # Calculate total portfolio value in USDT
        total_usdt_value = balances.get('USDT', 0)
        for asset, amount in balances.items():
            if asset != 'USDT' and amount > 0:
                try:
                    ticker = client.get_ticker(symbol=f"{asset}USDT")
                    price = float(ticker['price'])
                    total_usdt_value += amount * price
                except:
                    continue
        
        # Smart position sizing based on portfolio value and risk
        max_position_size = total_usdt_value * (config.RISK_PERCENTAGE / 100)
        
        # Adjust for volatility and consecutive losses
        volatility_adjustment = 1.0
        loss_adjustment = 1.0
        
        consecutive_losses = bot_status.get('consecutive_losses', 0)
        if consecutive_losses > 0:
            loss_adjustment = max(0.1, 1.0 - (consecutive_losses * 0.2))  # Reduce size by 20% per loss
        
        adjusted_position_size = max_position_size * volatility_adjustment * loss_adjustment
        
        portfolio_info = {
            'total_value_usdt': total_usdt_value,
            'max_position_size': max_position_size,
            'adjusted_position_size': adjusted_position_size,
            'risk_percentage': config.RISK_PERCENTAGE,
            'consecutive_losses': consecutive_losses,
            'loss_adjustment': loss_adjustment,
            'balances': balances,
            'portfolio_allocation': {}
        }
        
        # Calculate portfolio allocation percentages
        for asset, amount in balances.items():
            if asset == 'USDT':
                portfolio_info['portfolio_allocation'][asset] = (amount / total_usdt_value) * 100
            else:
                try:
                    ticker = client.get_ticker(symbol=f"{asset}USDT")
                    price = float(ticker['price'])
                    asset_value = amount * price
                    portfolio_info['portfolio_allocation'][asset] = (asset_value / total_usdt_value) * 100
                except:
                    portfolio_info['portfolio_allocation'][asset] = 0
        
        return portfolio_info
        
    except Exception as e:
        return {"error": f"Portfolio management error: {e}"}

# Flask Routes and Dashboard Functions
    bot_status['running'] = False
    bot_status['next_signal_time'] = None  # Clear next signal time when stopped
    bot_status['last_stop_reason'] = 'normal'  # Track stop reason for auto-restart logic

def auto_start_bot():
    """Automatically start the bot if auto-start is enabled and conditions are met"""
    try:
        if not bot_status.get('auto_start', True):
            print("Auto-start is disabled")
            return False
            
        if bot_status.get('running', False):
            print("Bot is already running")
            return True
            
        print("Auto-starting trading bot...")
        if initialize_client():
            # Start trading loop in a separate thread
            trading_thread = threading.Thread(target=trading_loop, daemon=True)
            trading_thread.start()
            print("✅ Bot auto-started successfully")
            return True
        else:
            print("❌ Auto-start failed: Could not initialize API client")
            return False
            
    except Exception as e:
        error_msg = f"Auto-start failed: {str(e)}"
        print(error_msg)
        log_error_to_csv(error_msg, "AUTO_START_ERROR", "auto_start_bot", "ERROR")
        return False

def start_trading_bot():
    """Start the trading bot in a separate thread"""
    try:
        if not bot_status['running']:
            # Start trading loop in background thread
            trading_thread = threading.Thread(target=trading_loop, daemon=True)
            trading_thread.start()
            bot_status['running'] = True
            bot_status['status'] = 'running'
            print("✅ Trading bot started successfully")
        else:
            print("⚠️ Trading bot is already running")
    except Exception as e:
        print(f"❌ Failed to start trading bot: {e}")
        log_error_to_csv(str(e), "START_ERROR", "start_trading_bot", "ERROR")

def start_auto_restart_monitor():
    """Monitor bot status and auto-restart if needed"""
    def monitor():
        while True:
            try:
                time.sleep(60)  # Check every minute
                
                if not bot_status.get('auto_restart', True):
                    continue
                    
                # Check if bot should be running but isn't
                # Don't restart if it was manually stopped
                last_stop_reason = bot_status.get('last_stop_reason', 'unknown')
                if (bot_status.get('auto_start', True) and 
                    not bot_status.get('running', False) and 
                    bot_status.get('api_connected', False) and
                    last_stop_reason != 'manual'):
                    
                    print("🔄 Bot appears to have stopped unexpectedly, attempting auto-restart...")
                    log_error_to_csv("Bot stopped unexpectedly - attempting auto-restart", 
                                    "AUTO_RESTART", "start_auto_restart_monitor", "WARNING")
                    
                    # Wait a moment before restart
                    time.sleep(5)
                    
                    if auto_start_bot():
                        print("✅ Bot successfully auto-restarted")
                        bot_status['last_stop_reason'] = 'restarted'
                    else:
                        print("❌ Auto-restart failed")
                        
            except Exception as e:
                error_msg = f"Auto-restart monitor error: {str(e)}"
                print(error_msg)
                log_error_to_csv(error_msg, "AUTO_RESTART_ERROR", "start_auto_restart_monitor", "ERROR")
                time.sleep(30)  # Wait longer on error
    
    # Start monitor in background thread
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    print("🔍 Auto-restart monitor started")

@app.route('/download_logs')
def download_logs():
    """Create a zip file containing all CSV log files and send it to the user"""
    try:
        # Create an in-memory zip file
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Get all CSV files from logs directory
            logs_dir = Path('logs')
            if not logs_dir.exists():
                return jsonify({'error': 'No log files found'}), 404
                
            for csv_file in logs_dir.glob('*.csv'):
                if csv_file.exists():
                    # Add file to zip with relative path
                    zf.write(csv_file, csv_file.name)
        
        # Prepare the zip file for sending
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name='trading_bot_logs.zip'
        )
    except Exception as e:
        print(f"Error creating log zip file: {e}")
        return jsonify({'error': 'Failed to create zip file'}), 500

@app.route('/')
def home():
    # Get current strategy for display
    current_strategy = bot_status.get('trading_strategy', 'STRICT')
    strategy_descriptions = {
        'STRICT': '🎯 Conservative strategy with strict rules to minimize risk',
        'MODERATE': '⚖️ Balanced strategy for more frequent trading opportunities',
        'ADAPTIVE': '🧠 Smart strategy that adapts to market conditions'
    }
    strategy_desc = strategy_descriptions.get(current_strategy, '')
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CRYPTIX AI Trading Bot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        .strategy-section {
            padding: 20px;
            text-align: center;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            margin: 20px 0;
        }
        
        .strategy-buttons {
            display: flex;
            justify-content: center;
            gap: 15px;
            margin: 20px 0;
        }
        
        .strategy-btn {
            padding: 12px 25px;
            border: none;
            border-radius: 25px;
            color: white;
            text-decoration: none;
            font-weight: bold;
            transition: all 0.3s ease;
            background: rgba(255, 255, 255, 0.2);
        }
        
        .strategy-btn:hover {
            transform: translateY(-2px);
            background: rgba(255, 255, 255, 0.3);
        }
        
        .strategy-btn.active {
            background: #28a745;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 15px;
        }
        
        .robot-icon {
            font-size: 2rem;
        }
        
        .subtitle {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        
        .status-section {
            padding: 30px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .status-cards {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .status-card {
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            font-weight: 600;
        }
        
        .status-running {
            background: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
        }
        
        .status-stopped {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
        }
        
        .status-connected {
            background: #d1ecf1;
            color: #0c5460;
            border: 2px solid #bee5eb;
        }
        
        .status-disconnected {
            background: #fff3cd;
            color: #856404;
            border: 2px solid #ffeaa7;
        }
        
        .stats-section {
            padding: 30px;
        }
        
        .tabs {
            display: flex;
            justify-content: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #e9ecef;
        }
        
        .tab {
            padding: 15px 30px;
            background: none;
            border: none;
            font-size: 1.1rem;
            font-weight: 600;
            color: #666;
            cursor: pointer;
            transition: all 0.3s ease;
            border-bottom: 3px solid transparent;
        }
        
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
        }
        
        .tab:hover {
            color: #667eea;
            background: rgba(102, 126, 234, 0.1);
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .stats-title {
            font-size: 1.8rem;
            color: #333;
            margin-bottom: 25px;
            text-align: center;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 15px;
        }
        
        .stat-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }
        
        .stat-label {
            font-weight: 600;
            color: #555;
        }
        
        .stat-value {
            font-weight: 700;
            color: #333;
            font-size: 1.1rem;
        }
        
        .signal-buy, .signal-bullish {
            color: #28a745;
        }
        
        .signal-sell, .signal-bearish {
            color: #dc3545;
        }
        
        .signal-hold, .signal-neutral {
            color: #ffc107;
        }
        
        .rsi-oversold {
            color: #28a745;
            font-weight: bold;
        }
        
        .rsi-overbought {
            color: #dc3545;
            font-weight: bold;
        }
        
        .rsi-neutral {
            color: #6c757d;
        }
        
        .sentiment-bullish {
            color: #28a745;
        }
        
        .sentiment-bearish {
            color: #dc3545;
        }
        
        .sentiment-neutral {
            color: #6c757d;
        }
        
        .revenue-positive {
            color: #28a745;
            font-weight: bold;
        }
        
        .revenue-negative {
            color: #dc3545;
            font-weight: bold;
        }
        
        .revenue-neutral {
            color: #6c757d;
        }
        
        .countdown-timer {
            color: #667eea !important;
            font-weight: bold !important;
            font-family: 'Courier New', monospace;
            background: rgba(102, 126, 234, 0.1);
            padding: 4px 8px;
            border-radius: 5px;
            border: 1px solid rgba(102, 126, 234, 0.3);
        }
        
        .trades-container {
            max-height: 300px;
            overflow-y: auto;
            border: 1px solid #e9ecef;
            border-radius: 10px;
            background: #f8f9fa;
        }
        
        .trade-item {
            padding: 15px;
            border-bottom: 1px solid #e9ecef;
            background: white;
            margin-bottom: 1px;
        }
        
        .trade-item:last-child {
            border-bottom: none;
        }
        
        .trade-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .trade-signal {
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 5px;
            font-size: 0.9rem;
        }
        
        .trade-time {
            color: #6c757d;
            font-size: 0.8rem;
        }
        
        .trade-details {
            display: flex;
            gap: 15px;
            align-items: center;
            font-size: 0.9rem;
        }
        
        .trade-value {
            font-weight: bold;
            color: #333;
        }
        
        .trade-status-badge {
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: bold;
            text-transform: uppercase;
        }
        
        .status-success {
            background: #d4edda;
            color: #155724;
        }
        
        .status-failed, .status-api-error {
            background: #f8d7da;
            color: #721c24;
        }
        
        .status-insufficient-funds {
            background: #fff3cd;
            color: #856404;
        }
        
        .no-trades {
            padding: 30px;
            text-align: center;
            color: #6c757d;
            font-style: italic;
        }
        
        .controls {
            padding: 30px;
            text-align: center;
            background: #f8f9fa;
        }
        
        .btn {
            padding: 12px 30px;
            border: none;
            border-radius: 25px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin: 0 10px;
            transition: all 0.3s ease;
        }
        
        .btn-start {
            background: #28a745;
            color: white;
        }
        
        .btn-start:hover {
            background: #218838;
            transform: translateY(-2px);
        }
        
        .btn-stop {
            background: #dc3545;
            color: white;
        }
        
        .btn-stop:hover {
            background: #c82333;
            transform: translateY(-2px);
        }
        
        .footer {
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 0.9rem;
        }
        
        .refresh-link {
            color: #667eea;
            text-decoration: none;
        }
        
        .refresh-link:hover {
            text-decoration: underline;
        }
        
        @media (max-width: 600px) {
            .status-cards {
                grid-template-columns: 1fr;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .container {
                margin: 10px;
            }
            
            .tabs {
                flex-direction: column;
                align-items: center;
            }
            
            .tab {
                width: 100%;
                max-width: 300px;
                margin-bottom: 5px;
                text-align: center;
            }
        }
    </style>
    <script>
        // Auto-refresh every 30 seconds
        setTimeout(function() {
            window.location.reload();
        }, 30000);
        
        function refreshNow() {
            window.location.reload();
        }
        
        // Tab functionality
        function showTab(tabName) {
            // Hide all tab contents
            var tabContents = document.querySelectorAll('.tab-content');
            tabContents.forEach(function(tab) {
                tab.classList.remove('active');
            });
            
            // Remove active class from all tabs
            var tabs = document.querySelectorAll('.tab');
            tabs.forEach(function(tab) {
                tab.classList.remove('active');
            });
            
            // Show selected tab content
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked tab
            event.target.classList.add('active');
        }
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>
                <span class="robot-icon">🤖</span>
                CRYPTIX AI Trading Bot
            </h1>
        </div>
        
        <div class="status-section">
            <div class="status-cards">
                <div class="status-card {{ 'status-running' if status.running else 'status-stopped' }}">
                    <div style="font-size: 1.1rem;">Bot Status</div>
                    <div style="font-size: 1.3rem; margin-top: 5px;">
                        {{ 'Running' if status.running else 'Stopped' }}
                    </div>
                </div>
                <div class="status-card {{ 'status-connected' if status.api_connected else 'status-disconnected' }}">
                    <div style="font-size: 1.1rem;">API Status</div>
                    <div style="font-size: 1.3rem; margin-top: 5px;">
                        {{ 'Connected (Testnet)' if status.api_connected else 'Disconnected' }}
                    </div>
                </div>
                <div class="status-card {{ 'status-running' if status.auto_start else 'status-stopped' }}">
                    <div style="font-size: 1.1rem;">Auto-Start</div>
                    <div style="font-size: 1.3rem; margin-top: 5px;">
                        {{ 'Enabled' if status.auto_start else 'Disabled' }}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="stats-section">
            <div class="tabs">
                <button class="tab" onclick="showTab('strategy')">🎯 Trading Strategy</button>
                <button class="tab active" onclick="showTab('statistics')">📊 Trading Statistics</button>
                <button class="tab" onclick="showTab('performance')">📈 Trading Performance</button>
            </div>
            
            <!-- Trading Statistics Tab -->
            <div id="statistics" class="tab-content active">
                <h2 class="stats-title">Current Trading Data</h2>
                <div class="stats-grid">
                    <div class="stat-item">
                        <span class="stat-label">Last Signal:</span>
                        <span class="stat-value signal-{{ status.last_signal.lower() }}">
                            {{ status.last_signal }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Current Symbol:</span>
                        <span class="stat-value">
                            {{ status.current_symbol }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Current Price:</span>
                        <span class="stat-value">
                            ${{ "{:,.2f}".format(status.last_price) if status.last_price else 'N/A' }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Last Update:</span>
                        <span class="stat-value">
                            {{ status.last_update or 'Never' }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Total Trades:</span>
                        <span class="stat-value">{{ status.total_trades }}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Time for next Signal:</span>
                        <span class="stat-value countdown-timer">
                            {{ time_remaining }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Uptime:</span>
                        <span class="stat-value">
                            {{ "{:.1f}".format(status.uptime.total_seconds() / 3600) if status.uptime else '0' }}h
                        </span>
                    </div>
                </div>
            </div>
            
            <!-- Trading Strategy Tab -->
            <div id="strategy" class="tab-content">
                <h2 class="stats-title">Trading Strategy Configuration</h2>
                <div class="strategy-container" style="padding: 20px; background: rgba(255, 255, 255, 0.1); border-radius: 10px; margin-bottom: 30px;">
                    <div style="text-align: center; margin-bottom: 25px;">
                        <p style="color: #666; margin: 0; font-size: 1rem; line-height: 1.5;">{{ strategy_desc }}</p>
                    </div>
                    <div class="strategy-buttons" style="display: flex; justify-content: center; gap: 15px; flex-wrap: wrap;">
                        <a href="/strategy/strict" class="strategy-btn" style="flex: 1; min-width: 150px; max-width: 250px; padding: 15px 25px; background: {{ '#28a745' if status.trading_strategy == 'STRICT' else '#6c757d' }}; color: white; text-decoration: none; border-radius: 25px; transition: all 0.3s ease; text-align: center; font-size: 1rem; display: flex; align-items: center; justify-content: center; margin: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <span style="margin-right: 8px; font-size: 1.2rem;">🎯</span> 
                            <div style="text-align: left;">
                                <div style="font-weight: bold;">Strict</div>
                                <div style="font-size: 0.8rem; opacity: 0.9">Conservative Trading</div>
                            </div>
                        </a>
                        <a href="/strategy/moderate" class="strategy-btn" style="flex: 1; min-width: 150px; max-width: 250px; padding: 15px 25px; background: {{ '#28a745' if status.trading_strategy == 'MODERATE' else '#6c757d' }}; color: white; text-decoration: none; border-radius: 25px; transition: all 0.3s ease; text-align: center; font-size: 1rem; display: flex; align-items: center; justify-content: center; margin: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <span style="margin-right: 8px; font-size: 1.2rem;">⚖️</span>
                            <div style="text-align: left;">
                                <div style="font-weight: bold;">Moderate</div>
                                <div style="font-size: 0.8rem; opacity: 0.9">Balanced Approach</div>
                            </div>
                        </a>
                        <a href="/strategy/adaptive" class="strategy-btn" style="flex: 1; min-width: 150px; max-width: 250px; padding: 15px 25px; background: {{ '#28a745' if status.trading_strategy == 'ADAPTIVE' else '#6c757d' }}; color: white; text-decoration: none; border-radius: 25px; transition: all 0.3s ease; text-align: center; font-size: 1rem; display: flex; align-items: center; justify-content: center; margin: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <span style="margin-right: 8px; font-size: 1.2rem;">🧠</span>
                            <div style="text-align: left;">
                                <div style="font-weight: bold;">Adaptive</div>
                                <div style="font-size: 0.8rem; opacity: 0.9">Smart & Dynamic</div>
                            </div>
                        </a>
                    </div>
                </div>
            </div>
            
            <!-- Trading Performance Tab -->
            <div id="performance" class="tab-content">
                <h2 class="stats-title">Revenue & Performance Metrics</h2>
                <div class="stats-grid">
                    <div class="stat-item">
                        <span class="stat-label">Total Revenue:</span>
                        <span class="stat-value revenue-{{ 'positive' if status.trading_summary.total_revenue > 0 else 'negative' if status.trading_summary.total_revenue < 0 else 'neutral' }}">
                            ${{ "{:,.2f}".format(status.trading_summary.total_revenue) }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Win Rate:</span>
                        <span class="stat-value">
                            {{ "{:.1f}".format(status.trading_summary.win_rate) }}%
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Successful Trades:</span>
                        <span class="stat-value">{{ status.trading_summary.successful_trades }}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Failed Trades:</span>
                        <span class="stat-value">{{ status.trading_summary.failed_trades }}</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Total Buy Volume:</span>
                        <span class="stat-value">
                            ${{ "{:,.2f}".format(status.trading_summary.total_buy_volume) }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Total Sell Volume:</span>
                        <span class="stat-value">
                            ${{ "{:,.2f}".format(status.trading_summary.total_sell_volume) }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Average Trade Size:</span>
                        <span class="stat-value">
                            ${{ "{:,.2f}".format(status.trading_summary.average_trade_size) }}
                        </span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">Profit Factor:</span>
                        <span class="stat-value revenue-{{ 'positive' if status.trading_summary.total_revenue > 0 else 'negative' if status.trading_summary.total_revenue < 0 else 'neutral' }}">
                            {% if status.trading_summary.total_buy_volume > 0 %}
                                {{ "{:.2f}".format((status.trading_summary.total_buy_volume + status.trading_summary.total_revenue) / status.trading_summary.total_buy_volume) }}
                            {% else %}
                                1.00
                            {% endif %}
                        </span>
                    </div>
                </div>
                
                <!-- Recent Trades History -->
                <div style="margin-top: 30px;">
                    <h3 style="color: #333; margin-bottom: 15px;">📋 Recent Trades</h3>
                    <div class="trades-container">
                        {% if status.trading_summary.trades_history %}
                            {% for trade in status.trading_summary.trades_history[:5] %}
                            <div class="trade-item trade-{{ trade.status }}">
                                <div class="trade-header">
                                    <span class="trade-signal signal-{{ trade.signal.lower() }}">{{ trade.signal }}</span>
                                    <span class="trade-time">{{ trade.timestamp }}</span>
                                </div>
                                <div class="trade-details">
                                    <span>{{ trade.quantity }} {{ trade.symbol[:3] }}</span>
                                    {% if trade.price > 0 %}
                                        <span>@ ${{ "{:,.2f}".format(trade.price) }}</span>
                                        <span class="trade-value">${{ "{:,.2f}".format(trade.value) }}</span>
                                    {% endif %}
                                    <span class="trade-status-badge status-{{ trade.status }}">{{ trade.status.replace('_', ' ').title() }}</span>
                                </div>
                            </div>
                            {% endfor %}
                        {% else %}
                            <div class="no-trades">
                                <p>No trades executed yet. Start the bot to begin trading!</p>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
        
        <div class="controls">
            <a href="/start" class="btn btn-start">Start Bot</a>
            <a href="/stop" class="btn btn-stop">Stop Bot</a>
            <a href="/logs" class="btn" style="background: #17a2b8; color: white;">📋 View Logs</a>
            <div style="margin-top: 15px;">
                {% if status.auto_start %}
                    <a href="/autostart/disable" class="btn" style="background: #ffc107; color: #212529;">🔄 Disable Auto-Start</a>
                {% else %}
                    <a href="/autostart/enable" class="btn" style="background: #28a745; color: white;">🔄 Enable Auto-Start</a>
                {% endif %}
            </div>
        </div>
        
        <div class="footer">
            <div style="margin-bottom: 10px;">
                <strong>Current Cairo Time: {{ current_time }}</strong>
            </div>
            Page auto-refreshes every 30 seconds • 
            <a href="javascript:refreshNow()" class="refresh-link">Manual Refresh</a>
        </div>
    </div>
</body>
</html>
    """, status=bot_status, current_time=format_cairo_time(), time_remaining=get_time_remaining_for_next_signal(), strategy_desc=strategy_desc)

@app.route('/start')
def start():
    """Manual start route - uses auto-start function"""
    if not bot_status['running']:
        if auto_start_bot():
            return redirect('/')
        else:
            bot_status['errors'].append("Failed to start bot - check API connection")
            return redirect('/')
    return redirect('/')

@app.route('/stop')
def stop():
    """Manual stop route"""
    bot_status['running'] = False
    bot_status['next_signal_time'] = None  # Clear next signal time when manually stopped
    bot_status['last_stop_reason'] = 'manual'  # Mark as manual stop
    # Note: Auto-restart monitor will not restart if manually stopped via web interface
    print("Bot manually stopped via web interface")
    return redirect('/')

@app.route('/strategy/<name>')
def set_strategy(name):
    """Switch trading strategy"""
    try:
        if name.upper() in ['STRICT', 'MODERATE', 'ADAPTIVE']:
            previous_strategy = bot_status.get('trading_strategy', 'STRICT')
            new_strategy = name.upper()
            
            # Update bot status
            bot_status['trading_strategy'] = new_strategy
            
            # Log the strategy change
            log_error_to_csv(
                f"Strategy changed from {previous_strategy} to {new_strategy}",
                "STRATEGY_CHANGE",
                "set_strategy",
                "INFO"
            )
            
            # Print debug info
            print(f"Strategy changed: {previous_strategy} -> {new_strategy}")
            print(f"Current bot status: {bot_status}")
            
            return redirect('/')
        else:
            log_error_to_csv(
                f"Invalid strategy name: {name}",
                "STRATEGY_ERROR",
                "set_strategy",
                "ERROR"
            )
            return "Invalid strategy name", 400
    except Exception as e:
        error_msg = f"Error changing strategy: {str(e)}"
        log_error_to_csv(error_msg, "STRATEGY_ERROR", "set_strategy", "ERROR")
        print(error_msg)
        return error_msg, 500

@app.route('/autostart/<action>')
def toggle_autostart(action):
    """Enable/disable auto-start functionality"""
    try:
        if action.lower() == 'enable':
            bot_status['auto_start'] = True
            bot_status['auto_restart'] = True
            message = "Auto-start and auto-restart enabled"
            print(message)
            log_error_to_csv(message, "CONFIG_CHANGE", "toggle_autostart", "INFO")
        elif action.lower() == 'disable':
            bot_status['auto_start'] = False
            bot_status['auto_restart'] = False
            message = "Auto-start and auto-restart disabled"
            print(message)
            log_error_to_csv(message, "CONFIG_CHANGE", "toggle_autostart", "INFO")
        else:
            return "Invalid action. Use 'enable' or 'disable'", 400
            
        return redirect('/')
    except Exception as e:
        error_msg = f"Error toggling auto-start: {str(e)}"
        log_error_to_csv(error_msg, "CONFIG_ERROR", "toggle_autostart", "ERROR")
        return error_msg, 500

@app.route('/api/status')
def api_status():
    """JSON API endpoint for bot status"""
    return jsonify(bot_status)

@app.route('/logs')
def view_logs():
    """View CSV logs interface"""
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Logs</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            background: #f5f5f5; 
            padding: 10px;
        }
        .container { 
            max-width: 1200px; 
            margin: 0 auto; 
            background: white; 
            padding: 15px; 
            border-radius: 10px;
            overflow-x: hidden;
        }
        .header { 
            text-align: center; 
            margin-bottom: 20px; 
        }
        .header h1 {
            font-size: 1.8rem;
            margin-bottom: 15px;
        }
        .log-section { 
            margin-bottom: 25px;
            overflow-x: auto;
        }
        .log-title { 
            font-size: 1.3rem; 
            color: #333; 
            margin-bottom: 15px; 
            border-bottom: 2px solid #667eea; 
            padding-bottom: 5px; 
        }
        .log-links { 
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 20px; 
        }
        .log-links a { 
            padding: 10px 15px; 
            background: #667eea; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
            flex: 1 1 auto;
            text-align: center;
            min-width: 140px;
            font-size: 0.9rem;
        }
        .log-links a:hover { 
            background: #5a6fd8; 
        }
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin: 0 -15px;
            padding: 0 15px;
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 15px;
            min-width: 600px;
        }
        th, td { 
            padding: 10px 12px; 
            border: 1px solid #ddd; 
            text-align: left; 
            font-size: 0.9rem;
            white-space: nowrap;
        }
        th { 
            background: #f8f9fa; 
            font-weight: bold;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        tr:nth-child(even) { 
            background: #f9f9f9; 
        }
        .back-link { 
            display: inline-block; 
            margin-bottom: 20px; 
            padding: 12px 20px; 
            background: #28a745; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
            font-size: 0.9rem;
            text-align: center;
        }
        .back-link:hover { 
            background: #218838; 
        }
        
        @media (max-width: 768px) {
            body {
                padding: 5px;
            }
            .container {
                padding: 10px;
            }
            .header h1 {
                font-size: 1.5rem;
            }
            .log-links {
                flex-direction: column;
            }
            .log-links a {
                width: 100%;
                min-width: unset;
            }
            th, td {
                padding: 8px 10px;
                font-size: 0.85rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 Trading Bot Logs</h1>
            <a href="/" class="back-link">← Back to Dashboard</a>
        </div>
        
        <div class="log-section">
            <h2 class="log-title">Available Log Files</h2>
            <div class="log-links">
                <a href="/logs/trades">📊 Trade History</a>
                <a href="/logs/signals">📈 Signal History</a>
                <a href="/logs/performance">📉 Daily Performance</a>
                <a href="/logs/errors">❌ Error Log</a>
                <a href="/download_logs">💾 Download All CSV Files</a>
            </div>
        </div>
        
        <div class="log-section">
            <h2 class="log-title">Quick Stats</h2>
            <p><strong>Total Trades Logged:</strong> {{ total_trades }}</p>
            <p><strong>CSV Files Location:</strong> /logs/</p>
            <p><strong>Last Updated:</strong> {{ current_time }}</p>
        </div>
    </div>
</body>
</html>
    """, total_trades=len(get_csv_trade_history()), current_time=format_cairo_time())

@app.route('/logs/trades')
def view_trade_logs():
    """View trade history CSV"""
    trades = get_csv_trade_history(30)  # Last 30 days
    
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trade History</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            background: #f5f5f5;
            padding: 10px;
        }
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            background: white; 
            padding: 15px; 
            border-radius: 10px;
            overflow-x: hidden;
        }
        .table-wrapper {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            margin: 0 -15px;
            padding: 0 15px;
        }
        table { 
            width: 100%; 
            border-collapse: collapse; 
            margin-top: 15px; 
            font-size: 0.85rem;
            min-width: 800px;
        }
        th, td { 
            padding: 10px 12px; 
            border: 1px solid #ddd; 
            text-align: left;
            white-space: nowrap;
        }
        th { 
            background: #f8f9fa; 
            font-weight: bold; 
            position: sticky; 
            top: 0;
            z-index: 1;
        }
        tr:nth-child(even) { background: #f9f9f9; }
        .back-link { 
            display: inline-block; 
            margin-bottom: 20px; 
            padding: 12px 20px; 
            background: #28a745; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
            font-size: 0.9rem;
        }
        .back-link:hover {
            background: #218838;
        }
        h1 {
            font-size: 1.8rem;
            margin: 15px 0;
        }
        .status-success { background: #d4edda; }
        .status-simulated { background: #d1ecf1; }
        .status-error { background: #f8d7da; }
        .signal-buy { color: #28a745; font-weight: bold; }
        .signal-sell { color: #dc3545; font-weight: bold; }
        .signal-hold { color: #ffc107; font-weight: bold; }
        
        @media (max-width: 768px) {
            body {
                padding: 5px;
            }
            .container {
                padding: 10px;
            }
            h1 {
                font-size: 1.5rem;
                margin: 10px 0;
            }
            table {
                font-size: 0.8rem;
            }
            th, td {
                padding: 8px 10px;
            }
            .back-link {
                width: 100%;
                text-align: center;
                box-sizing: border-box;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/logs" class="back-link">← Back to Logs</a>
        <h1>📊 Trade History (Last 30 Days)</h1>
        
        {% if trades %}
        <table>
            <thead>
                <tr>
                    <th>Time (Cairo)</th>
                    <th>Signal</th>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Value</th>
                    <th>Fee</th>
                    <th>Status</th>
                    <th>RSI</th>
                    <th>MACD</th>
                    <th>Sentiment</th>
                    <th>P&L</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in trades %}
                <tr class="status-{{ trade.status }}">
                    <td>{{ trade.cairo_time }}</td>
                    <td class="signal-{{ trade.signal.lower() }}">{{ trade.signal }}</td>
                    <td>{{ trade.symbol }}</td>
                    <td>{{ "%.6f"|format(trade.quantity) }}</td>
                    <td>${{ "%.2f"|format(trade.price) }}</td>
                    <td>${{ "%.2f"|format(trade.value) }}</td>
                    <td>${{ "%.4f"|format(trade.fee) }}</td>
                    <td>{{ trade.status }}</td>
                    <td>{{ "%.1f"|format(trade.rsi) }}</td>
                    <td>{{ trade.macd_trend }}</td>
                    <td>{{ trade.sentiment }}</td>
                    <td>${{ "%.2f"|format(trade.profit_loss) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>No trades found in the last 30 days.</p>
        {% endif %}
    </div>
</body>
</html>
    """, trades=trades)

@app.route('/logs/signals')
def view_signal_logs():
    """View signal history CSV"""
    try:
        csv_files = setup_csv_logging()
        
        if not csv_files['signals'].exists():
            signals = []
        else:
            df = pd.read_csv(csv_files['signals'])
            # Get last 100 signals
            signals = df.tail(100).to_dict('records')
        
        return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Signal History</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.8rem; }
        th, td { padding: 6px 8px; border: 1px solid #ddd; text-align: left; }
        th { background: #f8f9fa; font-weight: bold; position: sticky; top: 0; }
        tr:nth-child(even) { background: #f9f9f9; }
        .back-link { display: inline-block; margin-bottom: 20px; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; }
        .signal-buy { color: #28a745; font-weight: bold; }
        .signal-sell { color: #dc3545; font-weight: bold; }
        .signal-hold { color: #ffc107; font-weight: bold; }
        .sentiment-bullish { color: #28a745; }
        .sentiment-bearish { color: #dc3545; }
        .sentiment-neutral { color: #6c757d; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/logs" class="back-link">← Back to Logs</a>
        <h1>📈 Signal History (Last 100 Signals)</h1>
        
        {% if signals %}
        <table>
            <thead>
                <tr>
                    <th>Time (Cairo)</th>
                    <th>Signal</th>
                    <th>Symbol</th>
                    <th>Price</th>
                    <th>RSI</th>
                    <th>MACD</th>
                    <th>MACD Trend</th>
                    <th>Sentiment</th>
                    <th>SMA5</th>
                    <th>SMA20</th>
                    <th>Reason</th>
                </tr>
            </thead>
            <tbody>
                {% for signal in signals %}
                <tr>
                    <td>{{ signal.cairo_time }}</td>
                    <td class="signal-{{ signal.signal.lower() }}">{{ signal.signal }}</td>
                    <td>{{ signal.symbol }}</td>
                    <td>${{ "%.2f"|format(signal.price) }}</td>
                    <td>{{ "%.1f"|format(signal.rsi) }}</td>
                    <td>{{ "%.6f"|format(signal.macd) }}</td>
                    <td>{{ signal.macd_trend }}</td>
                    <td class="sentiment-{{ signal.sentiment }}">{{ signal.sentiment }}</td>
                    <td>${{ "%.2f"|format(signal.sma5) }}</td>
                    <td>${{ "%.2f"|format(signal.sma20) }}</td>
                    <td style="font-size: 0.7rem;">{{ signal.reason[:100] }}...</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>No signals found.</p>
        {% endif %}
    </div>
</body>
</html>
        """, signals=signals)
        
    except Exception as e:
        return f"Error loading signal logs: {e}"

@app.route('/logs/performance')
def view_performance_logs():
    """View daily performance CSV with enhanced UI"""
    try:
        csv_files = setup_csv_logging()
        performance_history = []
        
        if csv_files['performance'].exists():
            df = pd.read_csv(csv_files['performance'])
            for _, row in df.iterrows():
                performance_history.append({
                    'date': row.get('date', 'Unknown'),
                    'total_trades': row.get('total_trades', 0),
                    'successful_trades': row.get('successful_trades', 0),
                    'failed_trades': row.get('failed_trades', 0),
                    'win_rate': row.get('win_rate', 0),
                    'total_revenue': row.get('total_revenue', 0),
                    'daily_pnl': row.get('daily_pnl', 0),
                    'total_volume': row.get('total_volume', 0)
                })
        
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Performance History - CRYPTIX AI Trading Bot</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="30">
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    min-height: 100vh;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 15px;
                    padding: 30px;
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                }}
                h1 {{
                    text-align: center;
                    margin-bottom: 30px;
                    font-size: 2.5em;
                    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
                }}
                .nav-buttons {{
                    display: flex;
                    justify-content: center;
                    gap: 15px;
                    margin-bottom: 30px;
                    flex-wrap: wrap;
                }}
                .nav-btn {{
                    padding: 12px 25px;
                    background: rgba(255, 255, 255, 0.2);
                    border: none;
                    border-radius: 25px;
                    color: white;
                    text-decoration: none;
                    font-weight: bold;
                    transition: all 0.3s ease;
                    backdrop-filter: blur(5px);
                }}
                .nav-btn:hover {{
                    background: rgba(255, 255, 255, 0.3);
                    transform: translateY(-2px);
                }}
                .stats-summary {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .stat-card {{
                    background: rgba(255, 255, 255, 0.15);
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    backdrop-filter: blur(5px);
                }}
                .stat-value {{
                    font-size: 1.8em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .stat-label {{
                    opacity: 0.8;
                    font-size: 0.9em;
                }}
                .table-container {{
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    overflow: hidden;
                    overflow-x: auto;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    min-width: 800px;
                }}
                th, td {{
                    padding: 15px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }}
                th {{
                    background: rgba(255, 255, 255, 0.2);
                    font-weight: bold;
                    position: sticky;
                    top: 0;
                    z-index: 10;
                }}
                tr:hover {{
                    background: rgba(255, 255, 255, 0.1);
                }}
                .positive {{
                    color: #4CAF50;
                    font-weight: bold;
                }}
                .negative {{
                    color: #f44336;
                    font-weight: bold;
                }}
                .neutral {{
                    color: #FFA726;
                    font-weight: bold;
                }}
                .empty-state {{
                    text-align: center;
                    padding: 60px 20px;
                    opacity: 0.7;
                }}
                .empty-state h3 {{
                    margin-bottom: 10px;
                }}
                @media (max-width: 768px) {{
                    .container {{
                        padding: 15px;
                        margin: 10px;
                    }}
                    h1 {{
                        font-size: 2em;
                    }}
                    .nav-buttons {{
                        justify-content: center;
                    }}
                    .nav-btn {{
                        padding: 10px 20px;
                        font-size: 0.9em;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Performance History</h1>
                
                <div class="nav-buttons">
                    <a href="/" class="nav-btn">🏠 Dashboard</a>
                    <a href="/logs" class="nav-btn">📋 All Logs</a>
                    <a href="/logs/trades" class="nav-btn">💰 Trades</a>
                    <a href="/logs/signals" class="nav-btn">📡 Signals</a>
                    <a href="/logs/performance" class="nav-btn" style="background: rgba(255, 255, 255, 0.3);">📊 Performance</a>
                    <a href="/logs/errors" class="nav-btn">⚠️ Errors</a>
                </div>
                
                <div class="stats-summary">
                    <div class="stat-card">
                        <div class="stat-value">{len(performance_history)}</div>
                        <div class="stat-label">Total Records</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{format_cairo_time()}</div>
                        <div class="stat-label">Last Updated (Cairo)</div>
                    </div>
                </div>
                
                <div class="table-container">
        """
        
        if performance_history:
            html_template += """
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Total Trades</th>
                                <th>Successful</th>
                                <th>Failed</th>
                                <th>Win Rate %</th>
                                <th>Total Revenue</th>
                                <th>Daily P&L</th>
                                <th>Total Volume</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for record in performance_history:
                win_rate = float(record['win_rate'])
                total_revenue = float(record['total_revenue'])
                daily_pnl = float(record['daily_pnl'])
                
                win_rate_class = "positive" if win_rate >= 60 else "negative" if win_rate < 40 else "neutral"
                revenue_class = "positive" if total_revenue > 0 else "negative" if total_revenue < 0 else "neutral"
                pnl_class = "positive" if daily_pnl > 0 else "negative" if daily_pnl < 0 else "neutral"
                
                html_template += f"""
                            <tr>
                                <td>{record['date']}</td>
                                <td>{record['total_trades']}</td>
                                <td>{record['successful_trades']}</td>
                                <td>{record['failed_trades']}</td>
                                <td class="{win_rate_class}">{win_rate:.1f}%</td>
                                <td class="{revenue_class}">${total_revenue:.2f}</td>
                                <td class="{pnl_class}">${daily_pnl:.2f}</td>
                                <td>${record['total_volume']:.2f}</td>
                            </tr>
                """
            
            html_template += """
                        </tbody>
                    </table>
            """
        else:
            html_template += """
                    <div class="empty-state">
                        <h3>📊 No Performance Data Available</h3>
                        <p>Performance metrics will appear here once the bot starts trading and generating reports.</p>
                        <p>Performance data is logged periodically to track trading efficiency and profitability.</p>
                    </div>
            """
        
        html_template += """
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_template
        
    except Exception as e:
        return f"<h1>Error loading performance logs: {str(e)}</h1>"

@app.route('/logs/errors')
def view_error_logs():
    """View error log CSV"""
    try:
        csv_files = setup_csv_logging()
        
        if not csv_files['errors'].exists():
            errors = []
        else:
            df = pd.read_csv(csv_files['errors'])
            # Get last 50 errors
            errors = df.tail(50).to_dict('records')
        
        return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error Log</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.8rem; }
        th, td { padding: 6px 8px; border: 1px solid #ddd; text-align: left; }
        th { background: #f8f9fa; font-weight: bold; position: sticky; top: 0; }
        tr:nth-child(even) { background: #f9f9f9; }
        .back-link { display: inline-block; margin-bottom: 20px; padding: 10px 20px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; }
        .error { background: #f8d7da; }
        .warning { background: #fff3cd; }
        .critical { background: #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <a href="/logs" class="back-link">← Back to Logs</a>
        <h1>❌ Error Log (Last 50 Errors)</h1>
        
        {% if errors %}
        <table>
            <thead>
                <tr>
                    <th>Time (Cairo)</th>
                    <th>Severity</th>
                    <th>Error Type</th>
                    <th>Function</th>
                    <th>Error Message</th>
                    <th>Bot Status</th>
                </tr>
            </thead>
            <tbody>
                {% for error in errors %}
                <tr class="{{ error.severity.lower() }}">
                    <td>{{ error.cairo_time }}</td>
                    <td>{{ error.severity }}</td>
                    <td>{{ error.error_type }}</td>
                    <td>{{ error.function_name }}</td>
                    <td style="max-width: 300px; word-wrap: break-word;">{{ error.error_message }}</td>
                    <td>{{ error.bot_status }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p>No errors found.</p>
        {% endif %}
    </div>
</body>
</html>
        """, errors=errors)
        
    except Exception as e:
        return f"Error loading error logs: {e}"

@app.route('/ping')
def ping():
    """Simple ping endpoint for uptime monitoring"""
    return {"status": "alive", "timestamp": format_cairo_time()}, 200

@app.route('/health')
def health():
    """Comprehensive health check with system and bot status"""
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': format_cairo_time(),
            'bot_running': bot_status.get('running', False),
            'api_connected': bot_status.get('api_connected', False),
            'last_update': bot_status.get('last_update', 'Never'),
            'error_count': len(bot_status.get('errors', [])),
            'consecutive_errors': bot_status.get('consecutive_errors', 0),
            'uptime_seconds': (get_cairo_time() - bot_status.get('start_time', get_cairo_time())).total_seconds()
        }
        
        # Try to get memory info if psutil is available
        try:
            import psutil  # Optional dependency for system metrics
            process = psutil.Process()
            health_data['memory_usage_mb'] = round(process.memory_info().rss / 1024 / 1024, 2)
            health_data['cpu_percent'] = round(process.cpu_percent(), 2)
        except ImportError:
            health_data['memory_usage_mb'] = 'unknown'
            health_data['cpu_percent'] = 'unknown'
        
        # Determine overall health status
        if not bot_status.get('api_connected', False):
            health_data['status'] = 'degraded'
        elif bot_status.get('consecutive_errors', 0) >= 3:
            health_data['status'] = 'warning'
        elif not bot_status.get('running', False):
            health_data['status'] = 'stopped'
            
        return jsonify(health_data)
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': format_cairo_time()
        }), 500

if __name__ == '__main__':
    print("\n🚀 Starting CRYPTIX AI Trading Bot...")
    print("=" * 50)
    
    # Initialize auto-start and monitoring systems
    try:
        # Start the auto-restart monitor
        start_auto_restart_monitor()
        
        # Auto-start the bot if enabled
        if bot_status.get('auto_start', True):
            print("Auto-starting trading bot...")
            start_trading_bot()
        
        # Configure Flask for production
        flask_env = os.getenv('FLASK_ENV', 'development')
        flask_host = os.getenv('FLASK_HOST', '0.0.0.0')
        flask_port = int(os.getenv('FLASK_PORT', 10000))
        
        if flask_env == 'production':
            print(f"🌐 Starting Flask server in PRODUCTION mode on {flask_host}:{flask_port}")
            app.run(host=flask_host, port=flask_port, debug=False)
        else:
            print(f"🌐 Starting Flask server in DEVELOPMENT mode on {flask_host}:{flask_port}")
            app.run(host=flask_host, port=flask_port, debug=True)
    except Exception as e:
        print(f"Failed to start application: {e}")
        log_error_to_csv(str(e), "STARTUP_ERROR", "main", "CRITICAL")
        
