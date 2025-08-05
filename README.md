# Binance AI Crypto Trading Bot (Web Dashboard)

## 🔥 Features
- Automated trading on Binance Testnet
- RSI + MACD strategy (lightweight custom implementation)
- Twitter sentiment analysis with TextBlob (memory-optimized)
- **Beautiful web dashboard with responsive design**
- Real-time status monitoring and trading statistics
- Start/Stop control from UI with immediate feedback
- Uptime monitoring via `/ping` route
- Memory usage monitoring via `/health` route
- JSON API endpoint at `/api/status` for developers

## 🛠 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Hatem-shaban/CRYPTIX-AI-BOT.git
cd binance-ai-bot
```

### 2. Create Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Set the following environment variables:
- `API_KEY` - Your Binance API key
- `API_SECRET` - Your Binance API secret

### 5. Run the Bot
```bash
python web_bot.py
```

## 🚀 Deployment Tips

### Render.com Deployment (Optimized for Free Tier)
This bot has been optimized to run within Render's 512MB memory limit:

1. **Memory Optimizations Applied:**
   - Replaced heavy PyTorch/Transformers with lightweight TextBlob
   - Custom RSI/MACD calculations instead of heavy TA libraries
   - Removed unnecessary dependencies

2. **Deploy Steps:**
   - Connect your GitHub repository to Render
   - Use the following environment variables in Render:
     - `API_KEY` = your Binance API key
     - `API_SECRET` = your Binance API secret
   - The app will automatically start on the port provided by Render

3. **Monitoring:**
   - Use `/ping` endpoint for uptime monitoring
   - Use `/health` endpoint to check memory usage
   - Set up [UptimeRobot](https://uptimerobot.com) to ping `/ping` every 30 minutes

## 📊 Strategy
- Buy: RSI < 30, MACD positive, bullish sentiment, SMA5 > SMA20
- Sell: RSI > 70, MACD negative, bearish sentiment, SMA5 < SMA20

## 📡 API Endpoints
- `/` - Beautiful web dashboard with real-time status
- `/api/status` - JSON API for bot status and metrics
- `/start` - Start the trading bot (redirects to dashboard)
- `/stop` - Stop the trading bot (redirects to dashboard)
- `/ping` - Simple alive check for uptime monitoring
- `/health` - Detailed health check with memory usage

## 📌 Important Notes
- This runs on Binance Testnet, no real money involved.
- You must provide your own Twitter scraping keys if you want real tweet data. `snscrape` is used here.
- The `venv/` folder is not included in this repository to keep it lightweight.
- Optimized for low-memory environments (under 512MB).

## 🔧 Troubleshooting

### Memory Issues on Render
If you still encounter memory issues:
1. Check the `/health` endpoint to monitor memory usage
2. Consider reducing the data fetch limit in `fetch_data()` function
3. Ensure you're using the latest optimized version without PyTorch/Transformers

### Git Large Files
If you encounter issues with large files when pushing to GitHub:
1. Make sure `venv/` is in your `.gitignore`
2. Use `git rm --cached` to remove any accidentally committed large files
3. Consider using Git LFS for large model files if needed

Enjoy & trade smart! 🚀