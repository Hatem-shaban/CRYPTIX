# AI Agent Instructions for Binance AI Trading Bot

## Project Overview
This is a Flask-based cryptocurrency trading bot that uses AI/ML techniques and technical analysis to automate trading on Binance. Key components:

- `web_bot.py`: Main application file containing trading logic, web server, and dashboard
- `/logs`: Directory for CSV trade history and error logs
- Environment variables: `API_KEY` and `API_SECRET` for Binance API authentication

## Architecture Patterns

### Trading Engine
- Uses a stateful `bot_status` dictionary for real-time metrics and trading state
- Core trading loop in `trading_loop()` runs analysis every hour
- Trading decisions use a statistical scoring system combining:
  - Technical indicators (RSI, MACD, SMAs)
  - Market sentiment analysis
  - Volume and volatility metrics
  - Risk management rules

### Data Processing
- Custom implementations of technical indicators (RSI, MACD) to optimize memory usage
- Example from `calculate_rsi()`:
```python
def calculate_rsi(prices, period=14):
    """Calculate RSI using proper Wilder's smoothing method"""
    try:
        # Implementation optimized for memory usage
        # Returns RSI value between 0-100
```

### Risk Management
- Position sizing based on account balance (2% risk per trade)
- Statistical stop-loss using 95% Value at Risk (VaR)
- Drawdown monitoring with 15% maximum limit
- Dynamic quantity calculation based on symbol-specific rules

## Common Operations

### Adding New Technical Indicators
1. Implement calculation function (see `calculate_rsi()` as template)
2. Add to `fetch_data()` for data preparation
3. Integrate into signal generation logic in `signal_generator()`

### Modifying Trading Strategy
Core logic is in `signal_generator()`:
- Buy signals: Statistically significant oversold conditions
- Sell signals: Overbought conditions or stop-loss triggers
- Risk metrics: Incorporated into final decision

### Error Handling Pattern
Use `log_error_to_csv()` for all errors with consistent categorization:
```python
log_error_to_csv(str(e), "CATEGORY", "function_name", "SEVERITY")
```

## Testing & Debugging
- Use Binance Testnet for development
- Monitor `/health` endpoint for memory usage
- Check `/logs` directory for CSV trade history and errors
- Web dashboard auto-refreshes every 30 seconds

## Performance Considerations
- Optimized for low memory (512MB) environments
- Avoid loading entire price history - use rolling windows
- Implement statistical calculations incrementally where possible
- Cache API responses when appropriate

## Common Pitfalls
- Don't modify `bot_status` without proper synchronization
- Always validate symbol info before trading
- Handle API rate limits in data fetching
- Consider timezone differences (bot uses Cairo time)

## Integration Points
- Binance API: Primary interface for market data and trading
- Twitter sentiment analysis via TextBlob
- Flask web server for dashboard and controls
- CSV logging system for trade history

## Development Workflow
1. Activate virtual environment
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables for API access
4. Run locally: `python web_bot.py`
5. Monitor via web dashboard at `/`
