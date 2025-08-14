"""
Telegram Notification Module for CRYPTIX Trading Bot
Handles all Telegram messaging functionality including signals, trades, and status updates
"""

import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import config
import os
from functools import wraps

class TelegramNotifier:
    def __init__(self):
        """Initialize Telegram notifier with configuration"""
        self.enabled = config.TELEGRAM.get('enabled', False)
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN') or config.TELEGRAM.get('bot_token', '')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID') or config.TELEGRAM.get('chat_id', '')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Rate limiting
        self.message_timestamps = []
        self.max_messages_per_minute = config.TELEGRAM.get('rate_limiting', {}).get('max_messages_per_minute', 20)
        
        # Notification settings
        self.notifications = config.TELEGRAM.get('notifications', {})
        self.message_format = config.TELEGRAM.get('message_format', {})
        
        # Message queuing for batch processing
        self.message_queue = []
        self.last_batch_time = datetime.now()
        
        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        self.last_error_time = None
        
        # Connection testing - use class-level flag to prevent multiple tests
        if not hasattr(TelegramNotifier, '_global_connection_tested'):
            TelegramNotifier._global_connection_tested = False
            TelegramNotifier._global_connection_working = False
        
        self.connection_tested = TelegramNotifier._global_connection_tested
        self.connection_working = TelegramNotifier._global_connection_working
        
        print(f"🤖 Telegram Notifier initialized - Enabled: {self.enabled}")
        # Connection test will be performed only once globally to avoid spam

    def _test_connection_silent(self) -> bool:
        """Test Telegram bot connection without sending test messages"""
        try:
            if not self.bot_token or not self.chat_id:
                print("⚠️ Telegram bot token or chat ID not configured")
                return False
                
            # Test if the bot is valid (doesn't send messages)
            response = requests.get(f"{self.base_url}/getMe", timeout=15)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    print(f"✅ Telegram bot is valid: @{bot_info['result']['username']}")
                    print(f"✅ Chat ID configured: {self.chat_id}")
                    return True
                else:
                    print(f"❌ Bot validation failed: {bot_info}")
                    return False
            else:
                print(f"❌ Bot connection failed: HTTP {response.status_code}")
                if response.status_code == 401:
                    print("   - This usually means the bot token is invalid")
                return False
                
        except requests.exceptions.ConnectTimeout:
            print("⚠️ Connection timeout to Telegram API")
            print("💡 This might be a local network issue - try testing on your deployed server")
            return False
        except requests.exceptions.ConnectionError:
            print("⚠️ Connection error to Telegram API")
            print("💡 Check internet connection or firewall settings")
            return False
        except Exception as e:
            print(f"❌ Telegram connection error: {e}")
            return False

    def test_connection_with_message(self) -> bool:
        """Test connection by sending an actual test message (use sparingly)"""
        return self._test_connection()

    def _test_connection(self) -> bool:
        """Test Telegram bot connection"""
        try:
            if not self.bot_token or not self.chat_id:
                print("⚠️ Telegram bot token or chat ID not configured")
                return False
                
            # First, test if the bot is valid
            response = requests.get(f"{self.base_url}/getMe", timeout=15)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    print(f"✅ Bot is valid: @{bot_info['result']['username']}")
                    
                    # Now test if we can send a message to the chat
                    test_payload = {
                        'chat_id': self.chat_id,
                        'text': '🤖 CRYPTIX Bot Connection Test - Please ignore this message',
                        'disable_notification': True
                    }
                    
                    test_response = requests.post(f"{self.base_url}/sendMessage", json=test_payload, timeout=15)
                    if test_response.status_code == 200:
                        print(f"✅ Chat connection successful for chat ID: {self.chat_id}")
                        return True
                    else:
                        error_data = test_response.json()
                        error_desc = error_data.get('description', 'Unknown error')
                        print(f"❌ Chat test failed: {error_desc}")
                        print(f"   - Chat ID used: {self.chat_id}")
                        print(f"   - Suggestion: Make sure you've sent /start to @{bot_info['result']['username']} first")
                        return False
                else:
                    print(f"❌ Bot validation failed: {bot_info}")
                    return False
            else:
                print(f"❌ Bot connection failed: HTTP {response.status_code}")
                if response.status_code == 401:
                    print("   - This usually means the bot token is invalid")
                return False
                
        except requests.exceptions.ConnectTimeout:
            print("⚠️ Connection timeout to Telegram API")
            print("💡 This might be a local network issue - try testing on your deployed server")
            return False
        except requests.exceptions.ConnectionError:
            print("⚠️ Connection error to Telegram API")
            print("💡 Check internet connection or firewall settings")
            return False
        except Exception as e:
            print(f"❌ Telegram connection error: {e}")
            return False

    def _rate_limit_check(self) -> bool:
        """Check if we're within rate limits"""
        now = datetime.now()
        # Remove timestamps older than 1 minute
        self.message_timestamps = [ts for ts in self.message_timestamps if now - ts < timedelta(minutes=1)]
        
        if len(self.message_timestamps) >= self.max_messages_per_minute:
            return False
        return True

    def _send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Send message to Telegram with error handling and rate limiting"""
        if not self.enabled or not self.bot_token or not self.chat_id:
            return False
            
        # Test connection only once globally when first message is sent
        if not TelegramNotifier._global_connection_tested:
            print("🔍 Testing Telegram connection (one-time test)...")
            TelegramNotifier._global_connection_working = self._test_connection_silent()
            TelegramNotifier._global_connection_tested = True
            self.connection_working = TelegramNotifier._global_connection_working
            self.connection_tested = True
            if not self.connection_working:
                print("❌ Telegram connection failed - messages will be skipped")
                return False
            
        if not self.connection_working:
            return False
            
        if not self._rate_limit_check():
            print("⚠️ Telegram rate limit exceeded - message queued")
            self.message_queue.append({'message': message, 'parse_mode': parse_mode})
            return False
            
        try:
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            response = requests.post(f"{self.base_url}/sendMessage", json=payload, timeout=15)
            
            if response.status_code == 200:
                self.message_timestamps.append(datetime.now())
                self.consecutive_errors = 0
                return True
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get('description', 'Unknown error')
                    
                    # Provide helpful error messages
                    if 'chat not found' in error_msg.lower():
                        print(f"❌ Telegram error: Chat not found")
                        print(f"💡 Solution: Send /start to your bot first")
                        print(f"   1. Open Telegram and search for your bot")
                        print(f"   2. Send /start to begin conversation")
                        print(f"   3. Verify your chat ID: {self.chat_id}")
                    elif 'bot was blocked' in error_msg.lower():
                        print(f"❌ Telegram error: Bot was blocked by user")
                        print(f"💡 Solution: Unblock the bot in Telegram")
                    else:
                        print(f"❌ Telegram send failed: {error_msg}")
                        
                except:
                    print(f"❌ Telegram send failed: HTTP {response.status_code}")
                    
                self.consecutive_errors += 1
                return False
                
        except requests.exceptions.ConnectTimeout:
            print("❌ Telegram connection timeout - network may be restricted")
            print("💡 This might work on your deployed server even if it fails locally")
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            return False
        except requests.exceptions.ConnectionError:
            print("❌ Telegram connection failed - check internet connection")
            print("💡 If running locally, this might work on your deployed server")
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            return False
        except Exception as e:
            print(f"❌ Telegram send error: {e}")
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            return False

    def _format_price(self, price: float, symbol: str = "USDT") -> str:
        """Format price with appropriate decimal places"""
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        else:
            return f"${price:.8f}"

    def _get_emoji(self, signal_type: str) -> str:
        """Get appropriate emoji for signal type"""
        if not self.message_format.get('include_emoji', True):
            return ""
            
        emoji_map = {
            'BUY': '🟢',
            'SELL': '🔴', 
            'HOLD': '🟡',
            'SUCCESS': '✅',
            'FAILED': '❌',
            'WARNING': '⚠️',
            'INFO': 'ℹ️',
            'PROFIT': '💰',
            'LOSS': '📉',
            'NEUTRAL': '🔵'
        }
        return emoji_map.get(signal_type.upper(), '🔔')

    def send_signal_notification(self, signal: str, symbol: str, price: float, 
                               indicators: Dict[str, Any], reason: str = "") -> bool:
        """Send trading signal notification"""
        if not self.notifications.get('signals', True):
            return False
            
        emoji = self._get_emoji(signal)
        price_str = self._format_price(price)
        
        message = f"""
{emoji} <b>TRADING SIGNAL</b> {emoji}

📊 <b>Symbol:</b> {symbol}
🚦 <b>Signal:</b> {signal}
💰 <b>Price:</b> {price_str}
"""

        if self.message_format.get('include_indicators', True) and indicators:
            if 'rsi' in indicators:
                rsi_emoji = '📈' if indicators['rsi'] < 30 else '📉' if indicators['rsi'] > 70 else '📊'
                message += f"{rsi_emoji} <b>RSI:</b> {indicators['rsi']:.1f}\n"
                
            if 'macd_trend' in indicators:
                macd_emoji = '🟢' if indicators['macd_trend'] == 'BULLISH' else '🔴' if indicators['macd_trend'] == 'BEARISH' else '🟡'
                message += f"{macd_emoji} <b>MACD:</b> {indicators['macd_trend']}\n"
                
            if 'sentiment' in indicators:
                sentiment_emoji = '😊' if indicators['sentiment'] == 'bullish' else '😞' if indicators['sentiment'] == 'bearish' else '😐'
                message += f"{sentiment_emoji} <b>Sentiment:</b> {indicators['sentiment'].title()}\n"

        if reason:
            message += f"\n💡 <b>Reason:</b> {reason}"
            
        message += f"\n🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())

    def send_trade_notification(self, trade_info: Dict[str, Any], is_executed: bool = True) -> bool:
        """Send trade execution notification"""
        if not self.notifications.get('trades', True):
            return False
            
        signal = trade_info.get('signal', 'UNKNOWN')
        symbol = trade_info.get('symbol', 'UNKNOWN')
        quantity = trade_info.get('quantity', 0)
        price = trade_info.get('price', 0)
        value = trade_info.get('value', 0)
        status = trade_info.get('status', 'unknown')
        
        if is_executed and status == 'success':
            emoji = self._get_emoji('SUCCESS')
            status_text = "EXECUTED"
        elif status == 'insufficient_funds':
            emoji = self._get_emoji('WARNING')
            status_text = "INSUFFICIENT FUNDS"
        else:
            emoji = self._get_emoji('FAILED')
            status_text = "FAILED"
            
        message = f"""
{emoji} <b>TRADE {status_text}</b> {emoji}

📊 <b>Symbol:</b> {symbol}
🚦 <b>Action:</b> {signal}
📦 <b>Quantity:</b> {quantity:.8f}
💰 <b>Price:</b> {self._format_price(price)}
💵 <b>Value:</b> {self._format_price(value)}
"""

        if 'fee' in trade_info and trade_info['fee'] > 0:
            message += f"💸 <b>Fee:</b> {self._format_price(trade_info['fee'])}\n"
            
        if 'order_id' in trade_info and trade_info['order_id']:
            message += f"🆔 <b>Order ID:</b> {trade_info['order_id']}\n"

        # Add profit/loss if available
        if self.message_format.get('include_profit_loss', True) and 'profit_loss' in trade_info:
            pnl = trade_info['profit_loss']
            if pnl != 0:
                pnl_emoji = self._get_emoji('PROFIT') if pnl > 0 else self._get_emoji('LOSS')
                message += f"{pnl_emoji} <b>P&L:</b> {self._format_price(pnl)}\n"
                
        message += f"🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())

    def send_error_notification(self, error_msg: str, error_type: str = "ERROR", 
                              function_name: str = "", severity: str = "ERROR") -> bool:
        """Send error notification"""
        if not self.notifications.get('errors', True):
            return False
            
        # Only send critical errors to avoid spam
        if severity not in ['ERROR', 'CRITICAL']:
            return False
            
        emoji = self._get_emoji('WARNING') if severity == 'WARNING' else self._get_emoji('FAILED')
        
        message = f"""
{emoji} <b>BOT {severity}</b> {emoji}

🔧 <b>Type:</b> {error_type}
📄 <b>Function:</b> {function_name}
📝 <b>Message:</b> {error_msg[:200]}{'...' if len(error_msg) > 200 else ''}
🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return self._send_message(message.strip())

    def send_bot_status_notification(self, status: str, additional_info: str = "") -> bool:
        """Send bot status change notification"""
        if not self.notifications.get('bot_status', True):
            return False
            
        # Prevent duplicate STARTED notifications using class-level tracking
        if not hasattr(TelegramNotifier, '_last_status_sent'):
            TelegramNotifier._last_status_sent = {}
        
        status_key = f"{status}:{additional_info}"
        current_time = datetime.now()
        
        # If same status was sent in last 30 seconds, skip it
        if (status_key in TelegramNotifier._last_status_sent and 
            (current_time - TelegramNotifier._last_status_sent[status_key]).total_seconds() < 30):
            print(f"⚠️ Skipping duplicate {status} notification (sent {(current_time - TelegramNotifier._last_status_sent[status_key]).total_seconds():.1f}s ago)")
            return False
        
        TelegramNotifier._last_status_sent[status_key] = current_time
            
        if status.upper() == 'STARTED':
            emoji = '🚀'
            message = f"{emoji} <b>CRYPTIX BOT STARTED</b> {emoji}\n\n"
        elif status.upper() == 'STOPPED':
            emoji = '🛑'
            message = f"{emoji} <b>CRYPTIX BOT STOPPED</b> {emoji}\n\n"
        else:
            emoji = 'ℹ️'
            message = f"{emoji} <b>BOT STATUS UPDATE</b> {emoji}\n\n"
            
        message += f"📊 <b>Status:</b> {status}\n"
        
        if additional_info:
            message += f"📝 <b>Info:</b> {additional_info}\n"
            
        message += f"🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())

    def send_daily_summary(self, trading_summary: Dict[str, Any]) -> bool:
        """Send daily trading summary"""
        if not self.notifications.get('daily_summary', True):
            return False
            
        total_trades = trading_summary.get('successful_trades', 0) + trading_summary.get('failed_trades', 0)
        win_rate = trading_summary.get('win_rate', 0)
        total_revenue = trading_summary.get('total_revenue', 0)
        
        revenue_emoji = self._get_emoji('PROFIT') if total_revenue > 0 else self._get_emoji('LOSS') if total_revenue < 0 else self._get_emoji('NEUTRAL')
        
        message = f"""
📊 <b>DAILY TRADING SUMMARY</b> 📊

🔢 <b>Total Trades:</b> {total_trades}
✅ <b>Successful:</b> {trading_summary.get('successful_trades', 0)}
❌ <b>Failed:</b> {trading_summary.get('failed_trades', 0)}
🎯 <b>Win Rate:</b> {win_rate:.1f}%
{revenue_emoji} <b>Total Revenue:</b> {self._format_price(total_revenue)}

📈 <b>Buy Volume:</b> {self._format_price(trading_summary.get('total_buy_volume', 0))}
📉 <b>Sell Volume:</b> {self._format_price(trading_summary.get('total_sell_volume', 0))}
📊 <b>Avg Trade Size:</b> {self._format_price(trading_summary.get('average_trade_size', 0))}

🕒 <b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}
"""
        
        return self._send_message(message.strip())

    def send_market_update(self, market_regime: str, hunting_mode: bool, 
                          next_scan_time: str, volatility_metrics: Dict[str, Any] = None) -> bool:
        """Send market regime and wolf status update"""
        if not self.notifications.get('bot_status', True):
            return False
            
        regime_emoji = {
            'EXTREME': '🔴',
            'VOLATILE': '🟠', 
            'NORMAL': '🟢',
            'QUIET': '🔵'
        }.get(market_regime, '🟡')
        
        hunting_emoji = '🐺' if hunting_mode else '😴'
        
        message = f"""
🐺 <b>WOLF STATUS UPDATE</b> 🐺

{regime_emoji} <b>Market Regime:</b> {market_regime}
{hunting_emoji} <b>Hunting Mode:</b> {'ACTIVE' if hunting_mode else 'PASSIVE'}
⏰ <b>Next Scan:</b> {next_scan_time}
"""

        if volatility_metrics:
            message += f"\n📊 <b>Market Metrics:</b>\n"
            if 'hourly_vol' in volatility_metrics:
                message += f"📈 Hourly Vol: {volatility_metrics['hourly_vol']:.3f}\n"
            if 'volume_surge' in volatility_metrics:
                message += f"📊 Volume Surge: {volatility_metrics['volume_surge']:.2f}x\n"
                
        message += f"\n🕒 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return self._send_message(message.strip())

    def process_queued_messages(self) -> None:
        """Process queued messages when rate limit allows"""
        if not self.message_queue:
            return
            
        # Process one message per call to avoid flooding
        if self._rate_limit_check() and self.message_queue:
            queued_message = self.message_queue.pop(0)
            self._send_message(queued_message['message'], queued_message['parse_mode'])

    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        return {
            'enabled': self.enabled,
            'configured': bool(self.bot_token and self.chat_id),
            'consecutive_errors': self.consecutive_errors,
            'queued_messages': len(self.message_queue),
            'messages_sent_last_minute': len(self.message_timestamps),
            'rate_limit_max': self.max_messages_per_minute,
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
            'bot_token_preview': f"{self.bot_token[:10]}...{self.bot_token[-10:]}" if self.bot_token else None,
            'chat_id': self.chat_id
        }

    def diagnose_connection(self) -> Dict[str, Any]:
        """Comprehensive connection diagnosis"""
        diagnosis = {
            'bot_token_configured': bool(self.bot_token),
            'chat_id_configured': bool(self.chat_id),
            'bot_valid': False,
            'chat_accessible': False,
            'bot_username': None,
            'errors': []
        }
        
        try:
            # Test bot validity
            if not self.bot_token:
                diagnosis['errors'].append("Bot token not configured")
                return diagnosis
                
            response = requests.get(f"{self.base_url}/getMe", timeout=10)
            if response.status_code == 200:
                bot_info = response.json()
                if bot_info.get('ok'):
                    diagnosis['bot_valid'] = True
                    diagnosis['bot_username'] = bot_info['result']['username']
                else:
                    diagnosis['errors'].append(f"Bot API error: {bot_info}")
            else:
                diagnosis['errors'].append(f"Bot connection failed: HTTP {response.status_code}")
                
            # Test chat accessibility
            if diagnosis['bot_valid'] and self.chat_id:
                test_payload = {
                    'chat_id': self.chat_id,
                    'text': '🔍 Connection Test - Please ignore',
                    'disable_notification': True
                }
                
                chat_response = requests.post(f"{self.base_url}/sendMessage", json=test_payload, timeout=10)
                if chat_response.status_code == 200:
                    diagnosis['chat_accessible'] = True
                else:
                    error_data = chat_response.json()
                    diagnosis['errors'].append(f"Chat error: {error_data.get('description', 'Unknown error')}")
                    
        except Exception as e:
            diagnosis['errors'].append(f"Connection test failed: {str(e)}")
            
        return diagnosis

# Global instance
telegram_notifier = TelegramNotifier()

# Convenience functions for easy integration
def notify_signal(signal: str, symbol: str, price: float, indicators: Dict[str, Any], reason: str = "") -> bool:
    """Send trading signal notification"""
    return telegram_notifier.send_signal_notification(signal, symbol, price, indicators, reason)

def notify_trade(trade_info: Dict[str, Any], is_executed: bool = True) -> bool:
    """Send trade execution notification"""
    return telegram_notifier.send_trade_notification(trade_info, is_executed)

def notify_error(error_msg: str, error_type: str = "ERROR", function_name: str = "", severity: str = "ERROR") -> bool:
    """Send error notification"""
    return telegram_notifier.send_error_notification(error_msg, error_type, function_name, severity)

def notify_bot_status(status: str, additional_info: str = "") -> bool:
    """Send bot status notification"""
    return telegram_notifier.send_bot_status_notification(status, additional_info)

def notify_daily_summary(trading_summary: Dict[str, Any]) -> bool:
    """Send daily summary notification"""
    return telegram_notifier.send_daily_summary(trading_summary)

def notify_market_update(market_regime: str, hunting_mode: bool, next_scan_time: str, volatility_metrics: Dict[str, Any] = None) -> bool:
    """Send market update notification"""
    return telegram_notifier.send_market_update(market_regime, hunting_mode, next_scan_time, volatility_metrics)

def process_queued_notifications() -> None:
    """Process any queued notifications"""
    telegram_notifier.process_queued_messages()

def get_telegram_stats() -> Dict[str, Any]:
    """Get Telegram notification statistics"""
    return telegram_notifier.get_stats()

def test_telegram_connection() -> bool:
    """Manually test Telegram connection (sends actual test message)"""
    return telegram_notifier.test_connection_with_message()
