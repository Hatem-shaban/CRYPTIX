# CRYPTIX Trading Bot - Telegram Notifications Setup

## Overview
The CRYPTIX Trading Bot now includes comprehensive Telegram notification functionality to keep you informed about:
- 🚦 **Trading Signals** - Buy/Sell signal notifications with technical indicators
- 💰 **Trade Executions** - Real-time trade execution status and P&L
- ⚠️ **Error Alerts** - Critical error notifications for immediate attention
- 📊 **Daily Summaries** - End-of-day performance reports
- 🐺 **Bot Status** - Start/stop notifications and market regime updates

## Features
- **Smart Rate Limiting** - Prevents spam with intelligent message queuing
- **Rich Formatting** - Uses HTML formatting with emojis for clear, professional messages
- **Configurable Notifications** - Enable/disable specific notification types
- **Error Recovery** - Robust error handling with automatic retry mechanisms
- **Test Functions** - Easy testing of all notification types

## Setup Instructions

### Step 1: Create a Telegram Bot
1. Open Telegram and search for `@BotFather`
2. Start a chat and send `/newbot`
3. Follow the instructions to create your bot
4. Save the **Bot Token** (looks like: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyz`)

### Step 2: Get Your Chat ID
1. Search for `@userinfobot` on Telegram
2. Start a chat and send `/start`
3. The bot will reply with your **Chat ID** (looks like: `123456789`)

### Step 3: Configure Environment Variables
Add these environment variables to your system or `.env` file:

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### Step 4: Update config.py (Optional)
You can customize notification settings in `config.py`:

```python
TELEGRAM = {
    'enabled': True,  # Enable/disable Telegram notifications
    'bot_token': '',  # Your bot token (or use environment variable)
    'chat_id': '',    # Your chat ID (or use environment variable)
    'notifications': {
        'signals': True,           # Trading signal notifications
        'trades': True,            # Trade execution notifications
        'errors': True,            # Error notifications
        'daily_summary': True,     # Daily performance summary
        'bot_status': True         # Bot start/stop notifications
    },
    'message_format': {
        'include_emoji': True,     # Include emojis in messages
        'include_price': True,     # Include current price
        'include_indicators': True, # Include technical indicators
        'include_profit_loss': True # Include P&L information
    },
    'rate_limiting': {
        'max_messages_per_minute': 20,  # Rate limit
        'batch_notifications': True      # Batch similar notifications
    }
}
```

### Step 5: Test Your Setup
1. Start the bot
2. The bot will automatically send Telegram notifications for:
   - Trading signals when generated
   - Trade executions (success/failure)
   - Critical errors
   - Daily summaries (at end of trading day)
3. Monitor your Telegram chat for incoming notifications

## Notification Types

### 🚦 Trading Signals
Sent when the bot generates BUY or SELL signals:
```
🟢 TRADING SIGNAL 🟢

📊 Symbol: BTCUSDT
🚦 Signal: BUY
💰 Price: $45,000.00
📈 RSI: 28.5
🟢 MACD: BULLISH
😊 Sentiment: Bullish

💡 Reason: Strong buy signal with multiple confirmations
🕒 Time: 2025-08-12 14:30:00 EET
```

### 💰 Trade Executions
Sent when trades are executed successfully or fail:
```
✅ TRADE EXECUTED ✅

📊 Symbol: BTCUSDT
🚦 Action: BUY
📦 Quantity: 0.00100000
💰 Price: $45,000.00
💵 Value: $45.00
💸 Fee: $0.045
🆔 Order ID: 12345678
💰 P&L: $2.50
🕒 Time: 2025-08-12 14:30:15 EET
```

### 📊 Daily Summary
Sent at the end of each trading day:
```
📊 DAILY TRADING SUMMARY 📊

🔢 Total Trades: 8
✅ Successful: 6
❌ Failed: 2
🎯 Win Rate: 75.0%
💰 Total Revenue: $127.50

📈 Buy Volume: $450.00
📉 Sell Volume: $520.00
📊 Avg Trade Size: $121.25

🕒 Date: 2025-08-12
```

### 🐺 Wolf Status Updates
Periodic market regime and bot status updates:
```
🐺 WOLF STATUS UPDATE 🐺

🟠 Market Regime: VOLATILE
🐺 Hunting Mode: ACTIVE
⏰ Next Scan: 14:35:00 EET

📊 Market Metrics:
📈 Hourly Vol: 0.856
📊 Volume Surge: 2.34x

🕒 Time: 2025-08-12 14:30:00 EET
```

## Dashboard Integration

The Telegram notification system is fully integrated into the trading bot and works automatically in the background. Notifications are sent when:
- Trading signals are generated
- Trades are executed or fail  
- Critical errors occur
- Daily trading sessions end

The notifications appear directly in your Telegram chat without any manual intervention required.

## Production Usage

The Telegram notification system operates automatically once configured. You will receive:

- **Real-time trading signals** when the bot identifies buy/sell opportunities
- **Trade execution notifications** with order details and P&L information  
- **Error alerts** for any critical issues that require attention
- **Daily summaries** at the end of each trading session
- **Bot status updates** when the trading system starts or stops

All notifications are sent automatically based on trading activity - no manual intervention required.

## Troubleshooting

### Common Issues:

1. **"Telegram module not available"**
   - Check that `telegram_notify.py` exists
   - Verify no import errors in the console

2. **"Failed to send test message"**
   - Verify your bot token is correct
   - Ensure your chat ID is correct
   - Check that you've started a chat with your bot

3. **"Rate limit exceeded"**
   - The bot has hit Telegram's rate limits
   - Wait a few minutes and try again
   - Check the queue status in the dashboard

4. **Messages not received**
   - Make sure you've started a conversation with your bot
   - Check that the bot is not blocked
   - Verify the chat ID matches your actual Telegram user ID

### Debugging Steps:
1. Check the bot logs for Telegram-related errors
2. Use `/telegram/status` to view current configuration
3. Test with `/telegram/test` first before testing other types
4. Verify environment variables are loaded correctly

## Security Notes

- Keep your bot token secure and never share it publicly
- Use environment variables instead of hardcoding tokens
- The bot only sends messages to the configured chat ID
- All messages include timestamps for audit trails

## Advanced Configuration

### Custom Message Templates
You can modify the message templates in `telegram_notify.py` to customize the format and content of notifications.

### Rate Limiting
The system includes intelligent rate limiting to prevent hitting Telegram's limits:
- Maximum 20 messages per minute by default
- Automatic message queuing when limits are reached
- Smart batching of similar notifications

### Error Recovery
The notification system includes robust error handling:
- Automatic retry on transient failures
- Graceful degradation when Telegram is unavailable
- Detailed error logging for troubleshooting

## Support

For issues or questions:
1. Check the bot logs in the `/logs` section
2. Use the test functions to verify configuration
3. Review this documentation for common solutions
4. Check the console output for detailed error messages

---

**Note**: Telegram notifications are optional and the bot will continue to function normally even if Telegram is not configured or unavailable.
