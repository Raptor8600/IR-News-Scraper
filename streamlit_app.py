
import streamlit as st
import scout
from datetime import datetime
import pandas as pd
import requests

# Page Config
st.set_page_config(page_title="IR News Scraper", page_icon="🦅", layout="wide")

# Custom CSS for "The Raptor" branding
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #e2e8f0; }
    .stButton>button { background-color: #3b82f6; color: white; width: 100%; border-radius: 8px; font-weight: bold; }
    .stTextInput>div>div>input { background-color: #1e293b; color: white; }
    .footer { text-align: center; padding: 20px; color: #64748b; font-size: 0.8rem; }
    .raptor { color: #60a5fa; font-weight: bold; }
    .source-badge { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; background: #334155; color: #94a3b8; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# Header
st.title("IR News Scraper 🦅")
st.subheader("Discover Investor Relations news without the noise. Created by Raptor.")

# Sidebar Controls
with st.sidebar:
    st.header("🦅 Raptor Controls")
    tickers_input = st.text_input("🎯 Target Tickers", placeholder="NVDA, AMD, GOOG", help="Max 5 tickers.")
    filter_keywords = st.text_input("🔍 Search Keywords", placeholder="e.g. earnings, merger, layoff", help="Catch variations using fuzzy matching.")
    
    timeframe_options = {
        1: "Last 24 Hours", 3: "Last 3 Days", 7: "Last Week",
        30: "Last Month", 60: "Last 2 Months", 90: "Last Quarter",
        120: "Last 4 Months", 150: "Last 5 Months", 180: "Last 6 Months",
        270: "Last 9 Months", 365: "Last Year"
    }
    
    timeframe = st.selectbox("Time Range",
                           options=list(timeframe_options.keys()),
                           format_func=lambda x: timeframe_options.get(x),
                           index=2)
    
    source_filters = st.multiselect("Source Filter", 
                                  options=["Official IR", "Yahoo/Aggregate", "Reddit/WSB"],
                                  default=["Official IR", "Yahoo/Aggregate", "Reddit/WSB"])
    
    scan_clicked = st.button("🚀 Launch Scan", use_container_width=True)

    st.divider()
    st.subheader("🔐 Access EDGAR SEC Filings via API Keys")
    edgar_api_key = st.text_input("SEC-API.io Key", type="password", help="Get a free key at https://sec-api.io to unlock EDGAR filings.")
    if edgar_api_key:
        edgar_api_key = edgar_api_key.strip()  # Clean the key after input
    
    with st.expander("❓ How to get a Key"):
        st.markdown("""
        1. Go to **[sec-api.io](https://sec-api.io)**
        2. Sign up for a **Free Plan** (no credit card).
        3. Copy your API Key from the dashboard.
        4. Paste it above to see filing links!
        """)
    
    if edgar_api_key:
        if st.button("🔌 Test API Connection"):
            with st.spinner("Testing key..."):
                try:
                    test_url = f"https://api.sec-api.io?token={edgar_api_key}"
                    test_payload = {
                        "query": { "query_string": { "query": "ticker:AAPL" } },
                        "from": "0", "size": "1"
                    }
                    r = requests.post(test_url, json=test_payload, timeout=5)
                    if r.status_code == 200:
                        data = r.json()
                        total = data.get('total', {}).get('value', 0) if isinstance(data.get('total'), dict) else data.get('total', 0)
                        st.success(f"✅ Connected! Found {total} AAPL filings.")
                    else:
                        st.error(f"❌ API Error {r.status_code}: {r.text[:200]}")
                except Exception as e:
                    st.error(f"❌ Connection Failed: {e}")
    
    # SEC Filing Type Filter
    if edgar_api_key:
        st.divider()
        st.subheader("📋 SEC Filing Filters")
        filing_types = st.multiselect(
            "Form Types to Show",
            options=["10-K", "10-Q", "8-K", "4", "S-1", "S-3", "13F", "DEF 14A", "424B5", "All"],
            default=["All"],
            help="Filter SEC filings by form type. Select 'All' to show everything."
        )
        # Convert "All" to empty list (show all)
        if "All" in filing_types or not filing_types:
            filing_types = []

    st.divider()
    st.subheader("⚙️ Settings")
    match_threshold = st.slider("Match Sensitivity", 0, 100, 75, help="Higher = stricter matches.")

# Logic
if scan_clicked:
    if not tickers_input:
        st.error("Please enter at least one ticker.")
    else:
        tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()][:5]
        
        # Master Data Storage
        all_results = {"news": [], "filings": []}
        summary_container = st.empty()
        
        # Create columns for tickers
        cols = st.columns(len(tickers_list))
        
        for idx, ticker in enumerate(tickers_list):
            with cols[idx]:
                st.markdown(f"### 📊 {ticker}")
                # Data containers
                news = []
                filings = []
                
                # --- PHASE 1: Data Gathering (Status Bar) ---
                with st.status(f"Hunting {ticker}...", expanded=True) as status:
                    # 1. Find IR Page
                    st.write("🔎 Locating Official IR Page...")
                    url = scout.find_ir_page(ticker)
                    
                    if not url:
                        st.error("Discovery Failed")
                        status.update(label=f"❌ {ticker} Failed", state="error")
                        continue
                    
                    # 2. Fetch News
                    st.write(f"🦅 Scanning sources for news ({timeframe} days)...")
                    raw_news = scout.get_news(url, ticker, days_lookback=timeframe)
                    
                    # 3. Filter News
                    filtered_news = [n for n in raw_news if n.get('source') in source_filters]
                    
                    if filter_keywords and filtered_news:
                        from rapidfuzz import process, fuzz
                        keywords = [k.strip().lower() for k in filter_keywords.split(",") if k.strip()]
                        
                        final_filtered = []
                        for item in filtered_news:
                            headline = item['headline'].lower()
                            is_match = False
                            for kw in keywords:
                                if fuzz.partial_ratio(kw, headline) >= match_threshold:
                                    is_match = True
                                    break
                            if is_match:
                                final_filtered.append(item)
                        news = final_filtered
                    else:
                        news = filtered_news

                    if edgar_api_key:
                        st.write("🏛️ Fetching Official SEC Filings...")
                        filings = scout.search_edgar_filings(ticker, edgar_api_key)
                    
                    # Store for master summary
                    all_results["news"].extend(news)
                    all_results["filings"].extend(filings)

                    status.update(label=f"✅ {ticker}: Ready", state="complete", expanded=False)

                # --- PHASE 2: Display Results ---
                ticker_summary = scout.generate_summary(news, filings)
                if ticker_summary:
                    st.info(f"⚖️ **{ticker} Glance:** {ticker_summary.replace('**', '')}")
                
                # SECTION: OFFICIAL FILINGS (High Priority)
                if edgar_api_key:
                    st.subheader("🏛️ SEC Filings", divider="blue")
                    if filings:
                        # Apply filing type filter
                        filtered_filings = filings
                        if filing_types:  # If specific types selected (not "All")
                            filtered_filings = [f for f in filings if f['type'] in filing_types]
                        
                        if filtered_filings:
                            for f in filtered_filings:
                                st.markdown(f"""
                                **{f['date']}** • `{f['type']}`  
                                [{f['description']}]({f['link']})
                                """)
                        else:
                            st.caption(f"No filings found matching selected types: {', '.join(filing_types)}")
                    else:
                        st.caption("No recent filings found.")

                # SECTION: NEWS
                st.subheader("📰 Latest News", divider="gray")
                if not news:
                    st.warning("No matches found.")
                else:
                    for item in news:
                        with st.container(border=True):
                            st.caption(f"{item['date']} • {item['source']}")
                            st.markdown(f"**[{item['headline']}]({item['link']})**")

        # --- PHASE 3: Master Summary ---
        if len(tickers_list) > 1:
            master_summary = scout.generate_summary(all_results["news"], all_results["filings"])
            if master_summary:
                summary_container.markdown(f"""
                <div style="background-color: #1e293b; padding: 15px; border-radius: 10px; border-left: 5px solid #3b82f6; margin-bottom: 25px;">
                    <h3 style="margin-top: 0; color: #60a5fa;">🦅 Market Glance (All Tickers)</h3>
                    <p style="font-size: 1.1rem; margin-bottom: 0;">{master_summary.replace('**', '')}</p>
                </div>
                """, unsafe_allow_html=True)

# Footer
st.markdown("""
    <div class="footer">
        Powered by <span class="raptor">The Raptor</span> 🦅
    </div>
""", unsafe_allow_html=True)
