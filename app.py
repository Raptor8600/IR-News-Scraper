
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import scout
import logging

app = Flask(__name__)
CORS(app) # Enable CORS for all routes (allows file:// access)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebApp")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "Server is running!"})

@app.route('/api/scan', methods=['POST'])
def scan():
    data = request.json
    tickers = data.get('tickers', [])
    days = int(data.get('days', 7))
    
    logger.info(f"Scanning {tickers} for last {days} days")
    
    all_news = []
    
    for ticker in tickers:
        try:
            ticker = ticker.strip().upper()
            if not ticker: continue
            
            # 1. Find URL
            url = scout.find_ir_page(ticker)
            if not url:
                all_news.append({
                    'ticker': ticker,
                    'error': 'Could not find Investor Relations page.'
                })
                continue
                
            # 2. Get News
            news = scout.get_news(url, ticker, days_lookback=days)
            if not news:
                all_news.append({
                    'ticker': ticker,
                    'error': 'No recent news found in this timeframe.'
                })
            else:
                all_news.extend(news)
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
            all_news.append({
                'ticker': ticker,
                'error': f"Internal Error: {str(e)}"
            })
            
    return jsonify(all_news)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
