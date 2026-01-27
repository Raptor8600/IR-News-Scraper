
import streamlit as st
import scout
from datetime import datetime
import pandas as pd

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
    tickers_input = st.text_input("🎯 Target Tickers", placeholder="NVDA, AMD, PETV", help="Max 5 tickers.")
    filter_keywords = st.text_input("🔍 Search Keywords", placeholder="e.g. earnings, merger, layoff", help="Catch variations using fuzzy matching.")
    
    timeframe = st.selectbox("Time Range", 
                           options=[1, 3, 7, 30, 60, 90, 120, 150, 180], 
                           format_func=lambda x: {
                               1: "Last 24 Hours", 3: "Last 3 Days", 7: "Last Week",
                               30: "Last Month", 60: "Last 2 Months", 90: "Last Quarter",
                               120: "Last 4 Months", 150: "Last 5 Months", 180: "Last 6 Months"
                           }.get(x),
                           index=2)
    
    source_filters = st.multiselect("Source Filter", 
                                  options=["Official IR", "Yahoo/Aggregate", "Reddit/WSB"],
                                  default=["Official IR", "Yahoo/Aggregate", "Reddit/WSB"])
    
    scan_clicked = st.button("🚀 Launch Scan", use_container_width=True)

    st.divider()
    st.subheader("⚙️ Settings")
    match_threshold = st.slider("Match Sensitivity", 0, 100, 75, help="Higher = stricter matches.")

# Logic
if scan_clicked:
    if not tickers_input:
        st.error("Please enter at least one ticker.")
    else:
        tickers_list = [t.strip().upper() for t in tickers_input.split(",") if t.strip()][:5]
        
        # Create columns for tickers
        cols = st.columns(len(tickers_list))
        
        for idx, ticker in enumerate(tickers_list):
            with cols[idx]:
                st.markdown(f"### 📊 {ticker}")
                with st.status(f"Hunting {ticker}...", expanded=False) as status:
                    url = scout.find_ir_page(ticker)
                    if not url:
                        st.error(f"Discovery Failed")
                        status.update(label=f"❌ {ticker} Failed", state="error")
                        continue
                    
                    news = scout.get_news(url, ticker, days_lookback=timeframe)
                    
                    # Apply Source Filter
                    filtered_news = [n for n in news if n.get('source') in source_filters]
                    
                    # Apply Keyword Fuzzy Filter
                    if filter_keywords and filtered_news:
                        from rapidfuzz import process, fuzz
                        keywords = [k.strip().lower() for k in filter_keywords.split(",") if k.strip()]
                        
                        final_filtered = []
                        for item in filtered_news:
                            headline = item['headline'].lower()
                            # Check each keyword against the headline
                            is_match = False
                            for kw in keywords:
                                # Simple ratio check for typo tolerance
                                score = fuzz.partial_ratio(kw, headline)
                                if score >= match_threshold:
                                    is_match = True
                                    break
                            if is_match:
                                final_filtered.append(item)
                        filtered_news = final_filtered
                    
                    if not filtered_news:
                        st.warning("No matches found.")
                        status.update(label=f"⚠️ {ticker}: No news", state="complete")
                    else:
                        for item in filtered_news:
                            with st.container(border=True):
                                st.caption(f"{item['date']} • {item['source']}")
                                st.markdown(f"**[{item['headline']}]({item['link']})**")
                        
                        status.update(label=f"✅ {ticker}: Found {len(filtered_news)}", state="complete")

# Footer
st.markdown("""
    <div class="footer">
        Powered by <span class="raptor">The Raptor</span> 🦅
    </div>
""", unsafe_allow_html=True)
