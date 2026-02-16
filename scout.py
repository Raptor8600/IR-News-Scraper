
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import dateparser
import re
from datetime import datetime, timedelta, timezone
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRScraper")

LAST_GOOGLE_SEARCH = 0

import json
import os
from bs4 import XMLParsedAsHTMLWarning
import urllib3

# Suppress annoying console warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=UserWarning, module='bs4')

CACHE_FILE = "ticker_cache.json"

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=4)
    except: pass

# Global cache loaded in memory
TICKER_CACHE = load_cache()

def _check_url(url):
    """Helper to check if a URL is reachable."""
    try:
        headers = {'User-Agent': USER_AGENT}
        if requests.get(url, headers=headers, timeout=5, verify=False).status_code < 400:
            return url
    except:
        pass
    return None

def find_ir_page(ticker):
    """
    Robustly finds the Investor Relations page for any given ticker, with Caching and Parallel Lookups.
    """
    ticker = ticker.upper()
    
    # 1. Check Memory Cache first
    if ticker in TICKER_CACHE:
        return TICKER_CACHE[ticker]

    ticker_map = {
        "NVDA": "https://nvidianews.nvidia.com/",
        "TSLA": "https://ir.tesla.com",
        "AAPL": "https://www.apple.com/newsroom/",
        "AMZN": "https://ir.aboutamazon.com",
        "MSFT": "https://www.microsoft.com/en-us/investor",
        "META": "https://investor.fb.com",
        "GOOG": "https://abc.xyz/investor",
        "GOOGL": "https://abc.xyz/investor",
        "AMD": "https://ir.amd.com",
        "GME": "https://news.gamestop.com/",
        "PETV": "https://www.petv.com/investors/",
        "PLTR": "https://investors.palantir.com",
        "SOFI": "https://investors.sofi.com",
        "RKLB": "https://investors.rocketlabusa.com"
    }
    
    if ticker in ticker_map:
        url = ticker_map[ticker]
        TICKER_CACHE[ticker] = url
        save_cache(TICKER_CACHE)
        return url

    logger.info(f"Looking up official domain for {ticker} via Parallel Discovery...")
    found_url = None

    # Parallel Phase 1: Try Yahoo lookup AND common domain guesses
    domain = ticker.lower() + ".com"
    potential_urls = [
        f"https://investor.{domain}", 
        f"https://ir.{domain}", 
        f"https://investors.{domain}"
    ]
    
    # Add Yahoo Profile as a source for the base URL
    base_url_from_yahoo = None
    try:
        y_url = f"https://finance.yahoo.com/quote/{ticker}/profile"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(y_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if 'http' in href and not any(x in href for x in ['yahoo.com', 'google.com', 'twitter.com']):
                    base_url_from_yahoo = href.rstrip('/')
                    potential_urls.append(base_url_from_yahoo)
                    # Add common IR paths for the Yahoo discovered domain
                    ir_paths = ["/investors", "/ir", "/investor-relations", "/newsroom"]
                    for path in ir_paths:
                        potential_urls.append(base_url_from_yahoo + path)
                    break
    except Exception as e:
        logger.error(f"Yahoo domain lookup failed for {ticker}: {e}")

    # Test all potential URLs in parallel, but LIMITED to 3 workers to avoid VPN crash
    # Also added a small delay logic implicitly by limiting concurrency
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(_check_url, potential_urls))
        # Filter None and prioritize longer URLs (usually more specific like /investors)
        valid_urls = [r for r in results if r]
        if valid_urls:
            # Sort by length descending to pick the most specific IR page found
            valid_urls.sort(key=len, reverse=True)
            found_url = valid_urls[0]

    # Parallel Phase 2: Google Search Fallback (Only if Phase 1 failed)
    if not found_url:
        try:
            global LAST_GOOGLE_SEARCH
            elapsed = time.time() - LAST_GOOGLE_SEARCH
            if elapsed < 12: # Increased delay slightly
                sleep_time = 12 - elapsed + random.uniform(2, 5)
                logger.warning(f"⏳ Throttling Google Search for {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            
            LAST_GOOGLE_SEARCH = time.time()
            logger.warning(f"⚠️ Performing Google Search for {ticker} IR page (Rate Limit Risk)")
            
            query = f"{ticker} investor relations news"
            # Updated to match current googlesearch-python API
            search_results = search(query, num_results=3)
            for result in search_results:
                url_str = result.url if hasattr(result, 'url') else result
                if url_str and "google.com" not in url_str: 
                    found_url = url_str
                    break
        except Exception as e:
            logger.error(f"Google Search failed: {e}")
    
    # Absolute Fallback
    if not found_url:
        found_url = f"https://www.google.com/search?q={ticker}+investor+relations+news"

    # Save to Cache
    TICKER_CACHE[ticker] = found_url
    save_cache(TICKER_CACHE)
    logger.info(f"✅ Cached IR URL for {ticker}: {found_url}")

    return found_url

def _fetch_yahoo(ticker, cutoff_date):
    results = []
    try:
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker.upper()}&region=US&lang=en-US"
        headers = {'User-Agent': USER_AGENT}
        resp = requests.get(rss_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            items = soup.find_all("item")
            for item in items:
                title_tag = item.find('title')
                link_tag = item.find('link')
                date_tag = item.find('pubdate') or item.find('pubDate')
                title = title_tag.text if title_tag else ""
                link = link_tag.next_sibling.strip() if link_tag and not link_tag.text else (link_tag.text if link_tag else "")
                pub_date = date_tag.text if date_tag else ""
                if not title or not link: continue
                dt = dateparser.parse(pub_date)
                if not dt: continue
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff_date:
                    results.append({
                        'ticker': ticker, 'date': dt.strftime("%Y-%m-%d"),
                        'headline': title[:150], 'link': link, 'source': 'Yahoo/Aggregate'
                    })
    except: pass
    return results

def _fetch_reddit(ticker, cutoff_date):
    results = []
    try:
        reddit_url = f"https://www.reddit.com/r/wallstreetbets/search.rss?q={ticker}&sort=new&restrict_sr=on"
        headers = {'User-Agent': USER_AGENT}
        resp = requests.get(reddit_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            entries = soup.find_all("entry")
            for entry in entries:
                title_tag = entry.find('title')
                link_tag = entry.find('link')
                pub_date_tag = entry.find('updated')
                title = title_tag.text if title_tag else ""
                link = link_tag.get('href') if link_tag else ""
                pub_date = pub_date_tag.text if pub_date_tag else ""
                if not link or not title: continue
                dt = dateparser.parse(pub_date)
                if not dt: continue
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff_date:
                    results.append({
                        'ticker': ticker, 'date': dt.strftime("%Y-%m-%d"),
                        'headline': title[:150], 'link': link, 'source': 'Reddit/WSB'
                    })
    except: pass
    return results

def _fetch_ir(url, ticker, cutoff_date):
    results = []
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        soup = BeautifulSoup(response.text, 'html.parser')
        date_regex = re.compile(r'\d{1,2},?\s+\d{4}|\b\d{4}-\d{2}-\d{2}\b', re.I)
        for element in soup.find_all(['div', 'p', 'li', 'span', 'td', 'a']):
            text = element.get_text(separator=" ").strip()
            if len(text) < 5 or not date_regex.search(text): continue
            months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            if not any(m in text.lower() for m in months) and '-' not in text: continue
            dt = dateparser.parse(text, settings={'STRICT_PARSING': False})
            if dt:
                if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff_date:
                    link, headline = None, None
                    curr = element
                    for _ in range(6):
                        if not curr: break
                        a_tags = curr.find_all('a')
                        for a in a_tags:
                            h = a.get_text().strip()
                            href = a.get('href', '')
                            if href and len(h) > 12: link, headline = href, h; break
                        if link: break
                        curr = curr.parent
                    if link and headline:
                        if link.startswith('/'):
                            from urllib.parse import urljoin
                            link = urljoin(url, link)
                        results.append({
                            'ticker': ticker, 'date': dt.strftime("%Y-%m-%d"),
                            'headline': headline.replace('\n', ' ').strip()[:150],
                            'link': link, 'source': 'Official IR'
                        })
    except: pass
    return results

def get_news(url, ticker, days_lookback=7, recursive=True):
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=days_lookback)
    logger.info(f"Speed-Scouting {ticker} across all sources...")
    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(_fetch_yahoo, ticker, cutoff_date)
        f2 = executor.submit(_fetch_reddit, ticker, cutoff_date)
        f3 = executor.submit(_fetch_ir, url, ticker, cutoff_date)
        results = f1.result() + f2.result() + f3.result()

    unique_results = []
    seen_links = set()
    for item in results:
        if item['link'] not in seen_links:
            unique_results.append(item)
            seen_links.add(item['link'])

    unique_results.sort(key=lambda x: x['date'], reverse=True)
    return unique_results[:100]

def search_edgar_filings(ticker, api_key, limit=5):
    """
    Fetches recent EDGAR filings for a ticker using sec-api.io.
    Requires a valid API key.
    """
    if not api_key:
        return []
    
    # Clean ticker input
    ticker = ticker.strip().upper()
    
    # Handle explicit mapping for known separators
    search_ticker = ticker.replace(".", "-")
    
    url = f"https://api.sec-api.io?token={api_key}"

    # Try 1: Specific Ticker Search (e.g. "ticker:AAPL")
    query = f"ticker:{search_ticker}"
    
    payload = {
        "query": { "query_string": { "query": query } },
        "from": "0",
        "size": str(limit),
        "sort": [{ "filedAt": { "order": "desc" } }]
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        
        # If the first search yields nothing (e.g. user searched GOOG but needed GOOGL and map didn't catch it), try fallback
        if response.status_code == 200:
            data = response.json()
            total = data.get('total', {}).get('value', 0) if isinstance(data.get('total'), dict) else data.get('total', 0)
            
            # If 0 results, maybe we need to try adding "L" for Alphabet or just generally handle 0 results gracefully
            if total == 0 and "GOOG" in ticker and not ticker.endswith("L"):
                 query = "ticker:GOOGL"
                 payload["query"]["query_string"]["query"] = query
                 response = requests.post(url, json=payload, timeout=5)
                 data = response.json()
                 total = data.get('total', {}).get('value', 0) if isinstance(data.get('total'), dict) else data.get('total', 0)

            filings = []
            for f in data.get('filings', []):
                filed_at = f.get('filedAt', '')
                try:
                    # Extract just YYYY-MM-DD
                    date_str = filed_at[:10]
                except:
                    date_str = filed_at
                
                filings.append({
                    'date': date_str,
                    'type': f.get('formType', 'Unknown'),
                    'description': f.get('description', ''),
                    'link': f.get('linkToFilingDetails', '')
                })
            return filings
        else:
            logger.error(f"SEC-API.io Error {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"Failed to fetch EDGAR filings for {ticker}: {e}")
    
    return []

def generate_summary(news_items, filing_items=[]):
    """
    Generates a concise, rule-based summary of news and filings based on title keywords.
    """
    categories = {
        "Financials": ["earnings", "quarterly", "result", "revenue", "eps", "fiscal", "profit", "loss", "income"],
        "Dividends": ["dividend", "yield", "distribution", "payout"],
        "Strategic": ["merger", "acquisition", "m&a", "purchase", "divestiture", "partnership", "alliance", "deal", "agreement"],
        "Operations": ["expansion", "hiring", "layoff", "facility", "manufacturing", "launch", "product"],
        "Regulatory": ["sec", "filing", "10-k", "10-q", "8-k", "litigation", "settlement", "audit", "non-compliance", "edgar"],
        "Equity": ["buyback", "offering", "share", "stock", "split", "warrants", "capital", "shelf"]
    }
    
    counts = {cat: 0 for cat in categories}
    total_items = len(news_items) + len(filing_items)
    
    if total_items == 0:
        return ""

    # Process News
    for item in news_items:
        text = item.get('headline', '').lower()
        for cat, keywords in categories.items():
            if any(kw in text for kw in keywords):
                counts[cat] += 1
                break 
    
    # Process Filings
    for f in filing_items:
        text = (f.get('type', '') + " " + f.get('description', '')).lower()
        for cat, keywords in categories.items():
            if any(kw in text for kw in keywords):
                counts[cat] += 1
                break
                
    # Build summary string
    active_cats = [f"{count} {cat}" for cat, count in counts.items() if count > 0]
    
    if not active_cats:
        return f"{total_items} News Updates"
        
    summary = " | ".join(active_cats)
    return summary
