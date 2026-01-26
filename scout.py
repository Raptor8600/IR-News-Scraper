
import requests
from bs4 import BeautifulSoup
from googlesearch import search
import dateparser
import re
from datetime import datetime, timedelta, timezone
import logging
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("IRScraper")

def find_ir_page(ticker):
    """
    Robustly finds the Investor Relations page for any given ticker.
    """
    ticker = ticker.upper()
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
        "PETV": "https://www.petv.com/investors/"
    }
    
    if ticker in ticker_map:
        return ticker_map[ticker]

    logger.info(f"Looking up official domain for {ticker} via Yahoo...")
    try:
        y_url = f"https://finance.yahoo.com/quote/{ticker}/profile"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(y_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if 'http' in href and not any(x in href for x in ['yahoo.com', 'google.com', 'twitter.com']):
                    base_url = href.rstrip('/')
                    ir_paths = ["/investors", "/ir", "/investor-relations", "/newsroom"]
                    for path in ir_paths:
                        test_url = base_url + path
                        try:
                            if requests.get(test_url, timeout=3, verify=False).status_code < 400:
                                return test_url
                        except: continue
                    return base_url
    except Exception as e:
        logger.error(f"Yahoo domain lookup failed for {ticker}: {e}")

    domain = ticker.lower() + ".com"
    guesses = [f"https://investor.{domain}", f"https://ir.{domain}", f"https://investors.{domain}"]
    for url in guesses:
        try:
            if requests.get(url, timeout=3, verify=False).status_code < 400: return url
        except: continue

    try:
        query = f"{ticker} investor relations news"
        for result in search(query):
            url_str = result.url if hasattr(result, 'url') else result
            if url_str: return url_str
            break
    except: pass

    return f"https://www.google.com/search?q={ticker}+investor+relations+news"

def _fetch_yahoo(ticker, cutoff_date):
    results = []
    try:
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker.upper()}&region=US&lang=en-US"
        resp = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
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
        headers = {"User-Agent": "RaptorScraper/1.0 by TheRaptor"}
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
        headers = {"User-Agent": "Mozilla/5.0"}
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
