"""
Physical vs Paper Gold — Daily Benchmark Dashboard
===================================================
SGE Au99.99 (physical, CNY/gram) vs COMEX GC futures (paper, USD/troy oz)

DEPLOYMENT — Streamlit Community Cloud (free)
─────────────────────────────────────────────
1. Push app.py + requirements.txt to a public GitHub repo
2. Go to share.streamlit.io → New app → select repo → Main file: app.py → Deploy

DATA SOURCES (all free, no API key needed)
──────────────────────────────────────────
• COMEX gold price  → Yahoo Finance via yfinance (ticker: GC=F, 15-min delay)
• USD/CNY FX rate   → Yahoo Finance via yfinance (ticker: USDCNY=X)
• SGE Au99.99 price → scraped from en.sge.com.cn (daily benchmark, cached 1h)
"""

import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

# ── Constants ──────────────────────────────────────────────────────────────────
TROY = 31.1035

SGE_FALLBACK_HISTORY = pd.DataFrame([
    {"date": pd.Timestamp("2026-07-21"), "price": 886.95},
    {"date": pd.Timestamp("2026-07-22"), "price": 899.00},
    {"date": pd.Timestamp("2026-07-23"), "price": 895.67},
    {"date": pd.Timestamp("2026-07-24"), "price": 883.66},
    {"date": pd.Timestamp("2026-07-27"), "price": 893.97},
    {"date": pd.Timestamp("2026-07-28"), "price": 883.28},
])
SGE_FALLBACK = {
    "date": "2026-07-28", "close": 883.28, "high": 896.00, "low": 879.50,
    "chg": -10.69, "pct": -1.20, "history": SGE_FALLBACK_HISTORY,
}

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Physical vs Paper Gold | SGE vs COMEX",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Session state defaults ─────────────────────────────────────────────────────
if "dark" not in st.session_state:
    st.session_state.dark = False

dark = st.session_state.dark

# ── Theme CSS ──────────────────────────────────────────────────────────────────
LIGHT_CSS = """
<style>
.block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }
[data-testid="stMetricValue"] { font-size: 1.85rem !important; font-weight: 700; }
[data-testid="stMetricDelta"] { font-size: 0.85rem; }
.gold-header {
    background: linear-gradient(135deg, #1c1c12 0%, #2a2a16 100%);
    color: white; padding: 1rem 1.4rem; border-radius: 8px;
    border-left: 4px solid #c9a227; margin-bottom: 0.6rem;
}
.gold-header h1 { color: #f0cc60; font-size: 1.3rem; margin: 0; }
.gold-header p  { color: #b0a880; font-size: 0.76rem; margin: 0.25rem 0 0; }
.meth { font-size: 0.81rem; color: #444; line-height: 1.75; }
.meth a { color: #c9a227; text-decoration: none; }
.meth a:hover { text-decoration: underline; }
</style>
"""

DARK_CSS = """
<style>
.block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
[data-testid="stBottom"] { background-color: #0e1117 !important; }
[data-testid="stMetricValue"] { font-size: 1.85rem !important; font-weight: 700; color: #f0cc60 !important; }
[data-testid="stMetricDelta"] { font-size: 0.85rem; }
[data-testid="stMetricLabel"] > div { color: #aaa !important; }
p, li, .stMarkdown, label { color: #d0d0d0 !important; }
h1, h2, h3, h4, h5 { color: #f5f5f5 !important; }
[data-testid="stExpander"] { background-color: #161b22 !important; border-color: #30363d !important; }
[data-testid="stExpanderDetails"] { background-color: #161b22 !important; }
hr { border-color: #30363d !important; }
[data-testid="stAlert"] { background-color: #1e2a1e !important; }
[data-testid="stInfoAlertContent"] { color: #b0c8b0 !important; }
[data-testid="stDataFrame"] { background-color: #161b22 !important; }
.gold-header {
    background: linear-gradient(135deg, #1c1c12 0%, #2a2a16 100%);
    color: white; padding: 1rem 1.4rem; border-radius: 8px;
    border-left: 4px solid #c9a227; margin-bottom: 0.6rem;
}
.gold-header h1 { color: #f0cc60; font-size: 1.3rem; margin: 0; }
.gold-header p  { color: #b0a880; font-size: 0.76rem; margin: 0.25rem 0 0; }
.meth { font-size: 0.81rem; color: #999; line-height: 1.75; }
.meth a { color: #f0cc60; text-decoration: none; }
.meth a:hover { text-decoration: underline; }
</style>
"""

st.markdown(DARK_CSS if dark else LIGHT_CSS, unsafe_allow_html=True)

# ── Helpers ────────────────────────────────────────────────────────────────────
def cny_to_usd(p, fx): return p * TROY / fx
def usd_to_cny(p, fx): return p * fx / TROY

# ── Data fetching ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_comex():
    ticker = yf.Ticker("GC=F")
    hist = ticker.history(period="45d", interval="1d")
    hist = hist[hist["Close"] > 0].dropna(subset=["Close"])
    last = float(hist["Close"].iloc[-1])
    prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
    chg  = last - prev
    pct  = chg / prev * 100
    df = hist["Close"].reset_index()[["Date", "Close"]].rename(
        columns={"Date": "date", "Close": "price"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return {"price": round(last, 2), "chg": round(chg, 2), "pct": round(pct, 2), "history": df}

@st.cache_data(ttl=300, show_spinner=False)
def get_fx():
    ticker = yf.Ticker("USDCNY=X")
    hist = ticker.history(period="5d", interval="1d")
    hist = hist[hist["Close"] > 0].dropna(subset=["Close"])
    return round(float(hist["Close"].iloc[-1]), 4)

@st.cache_data(ttl=3600, show_spinner=False)
def get_sge():
    end   = datetime.now()
    start = end - timedelta(days=45)
    url   = (
        "https://en.sge.com.cn/data/data_daily_international_new"
        f"?start_date={start.strftime('%Y-%m-%d')}"
        f"&end_date={end.strftime('%Y-%m-%d')}"
    )
    headers = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://en.sge.com.cn/data_BenchmarkPrice",
    }
    try:
        r = requests.get(url, headers=headers, timeout=12)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for tr in soup.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if "Au99.99" not in cells:
                continue
            idx = cells.index("Au99.99")
            if idx < 1 or idx + 6 >= len(cells):
                continue
            try:
                rows.append({
                    "date":  pd.Timestamp(cells[idx - 1]),
                    "open":  float(cells[idx + 1]),
                    "high":  float(cells[idx + 2]),
                    "low":   float(cells[idx + 3]),
                    "close": float(cells[idx + 4]),
                    "chg":   float(cells[idx + 5]),
                    "pct":   float(cells[idx + 6].replace("%", "").strip()),
                })
            except (ValueError, IndexError):
                continue
        if not rows:
            return SGE_FALLBACK, True
        df = pd.DataFrame(rows).sort_values("date").drop_duplicates("date")
        latest  = df.iloc[-1]
        history = df[["date", "close"]].rename(columns={"close": "price"})
        return {
            "date":    latest["date"].strftime("%Y-%m-%d"),
            "close":   float(latest["close"]),
            "high":    float(latest["high"]),
            "low":     float(latest["low"]),
            "chg":     float(latest["chg"]),
            "pct":     float(latest["pct"]),
            "history": history,
        }, False
    except Exception:
        return SGE_FALLBACK, True

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="gold-header">
  <h1>🥇 Physical vs Paper Gold — Daily Benchmark</h1>
  <p>SGE Gold 99.99 (Shanghai · Physical · CNY/gram) &nbsp;vs&nbsp;
     COMEX GC Futures (New York · Paper · USD/troy oz)</p>
</div>
""", unsafe_allow_html=True)

# ── Controls row ───────────────────────────────────────────────────────────────
c_unit, c_dark, c_refresh, c_ts = st.columns([3.5, 1, 0.7, 4])

with c_unit:
    unit = st.radio(
        "unit", ["¥ RMB / gram", "$ USD / troy oz"],
        horizontal=True, label_visibility="collapsed",
    )

with c_dark:
    toggled = st.toggle("🌙 Dark", value=dark, key="dark_toggle")
    if toggled != dark:
        st.session_state.dark = toggled
        st.rerun()

with c_refresh:
    if st.button("🔄", help="Refresh all data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with c_ts:
    st.caption(
        f"SGE cached 1h · COMEX + FX cached 5m · "
        f"Last loaded {datetime.now().strftime('%b %d, %H:%M')}"
    )

st.divider()

# ── Fetch ──────────────────────────────────────────────────────────────────────
with st.spinner("Fetching live prices…"):
    comex          = get_comex()
    fx             = get_fx()
    sge, sge_stale = get_sge()

use_usd = "USD" in unit

# Derived prices
sge_cny = sge["close"]
sge_usd = cny_to_usd(sge_cny, fx)
cx_usd  = comex["price"]
cx_cny  = usd_to_cny(cx_usd, fx)

if use_usd:
    sge_main, cx_main = sge_usd,  cx_usd
    sge_conv, cx_conv = sge_cny,  cx_cny
    main_fmt  = lambda v: f"${v:,.2f}"
    conv_fmt  = lambda v: f"¥{v:,.2f}"
    conv_lbl  = "RMB / gram"
    sge_delta = cny_to_usd(sge["chg"], fx)
    cx_delta  = comex["chg"]
else:
    sge_main, cx_main = sge_cny,  cx_cny
    sge_conv, cx_conv = sge_usd,  cx_usd
    main_fmt  = lambda v: f"¥{v:,.2f}"
    conv_fmt  = lambda v: f"${v:,.2f}"
    conv_lbl  = "USD / troy oz"
    sge_delta = sge["chg"]
    cx_delta  = usd_to_cny(comex["chg"], fx)

spread_cny  = cx_cny - sge_cny
spread_pct  = spread_cny / sge_cny * 100
spread_abs  = (cx_usd - sge_usd) if use_usd else spread_cny
spread_unit = "USD/oz" if use_usd else "RMB/g"

# ── Price cards ────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("##### 🏦 SGE — Physical Gold")
    st.caption("Gold 99.99 Spot · Shanghai Gold Exchange · RMB/gram native")
    st.metric(
        label="SGE Close",
        value=main_fmt(sge_main),
        delta=f"{sge_delta:+.2f}  ({sge['pct']:+.2f}%)",
    )
    st.caption(
        f"≈ {conv_fmt(sge_conv)} {conv_lbl}"
        f"  ·  Hi ¥{sge['high']:.2f}  Lo ¥{sge['low']:.2f}"
        f"  ·  {sge['date']}"
    )
    if sge_stale:
        st.warning("Using cached SGE data — live scrape unavailable", icon="⚠️")

with c2:
    st.markdown("##### 📜 COMEX — Paper Gold")
    st.caption("GC Front Month · CME Group · USD/troy oz native · 15-min delay")
    st.metric(
        label="COMEX Last",
        value=main_fmt(cx_main),
        delta=f"{cx_delta:+.2f}  ({comex['pct']:+.2f}%)",
    )
    st.caption(f"≈ {conv_fmt(cx_conv)} {conv_lbl}  ·  Source: Yahoo Finance (GC=F)")

with c3:
    st.markdown("##### 📊 Spread  (COMEX − SGE)")
    st.caption("Converted to a common unit for like-for-like comparison")
    st.metric(
        label=f"Absolute ({spread_unit})",
        value=f"{spread_abs:+.2f}",
        delta=f"{spread_pct:+.2f}%  COMEX {'premium' if spread_pct >= 0 else 'discount'}",
        delta_color="off",
    )
    abs_pct = abs(spread_pct)
    if abs_pct < 0.5:
        msg, icon = "Spread within normal range — prices broadly aligned.", "✅"
    elif spread_pct >= 0:
        msg, icon = f"COMEX at {abs_pct:.2f}% premium. Futures optimism or limits on physical arbitrage.", "📈"
    else:
        msg, icon = f"SGE at {abs_pct:.2f}% premium. Strong physical demand in China or FX effects.", "📉"
    st.info(f"{icon}  {msg}")
    st.caption(f"USD/CNY: **{fx}**  ·  1 troy oz = 31.1035 g")

st.divider()

# ── Price history chart ────────────────────────────────────────────────────────
st.subheader("Price History")

sge_hist = sge["history"].copy()
cx_hist  = comex["history"].copy()

if use_usd:
    sge_hist["price"] = sge_hist["price"].apply(lambda p: cny_to_usd(p, fx))
    y_title, hover_fmt = "USD / troy oz", "$%{y:,.2f}"
else:
    cx_hist["price"] = cx_hist["price"].apply(lambda p: usd_to_cny(p, fx))
    y_title, hover_fmt = "RMB / gram", "¥%{y:,.2f}"

# Theme-aware chart colors
if dark:
    bg_color    = "#0e1117"
    grid_color  = "#2a2a3a"
    text_color  = "#cccccc"
    gold_line   = "#f0cc60"
    blue_line   = "#60b8f0"
else:
    bg_color    = "white"
    grid_color  = "#f0ece2"
    text_color  = "#555555"
    gold_line   = "#c9a227"
    blue_line   = "#3a8fc0"

fig = go.Figure()

fig.add_trace(go.Scatter(
    x=sge_hist["date"], y=sge_hist["price"],
    name="SGE Gold 99.99 (Physical)",
    line=dict(color=gold_line, width=2.5),
    mode="lines+markers",
    marker=dict(size=5, color=gold_line),
    hovertemplate=f"SGE: {hover_fmt}<extra></extra>",
))

fig.add_trace(go.Scatter(
    x=cx_hist["date"], y=cx_hist["price"],
    name="COMEX GC (Paper)",
    line=dict(color=blue_line, width=2.5),
    mode="lines",
    hovertemplate=f"COMEX: {hover_fmt}<extra></extra>",
))

fig.update_layout(
    height=340,
    margin=dict(l=0, r=10, t=10, b=0),
    plot_bgcolor=bg_color,
    paper_bgcolor=bg_color,
    font=dict(color=text_color, size=12),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
        font=dict(size=12, color=text_color),
        bgcolor="rgba(0,0,0,0)",
    ),
    yaxis=dict(
        title=y_title,
        title_font=dict(color=text_color),
        tickfont=dict(color=text_color),
        gridcolor=grid_color,
        tickformat=",.0f",
        linecolor=grid_color,
    ),
    xaxis=dict(
        tickfont=dict(color=text_color),
        gridcolor=grid_color,
        linecolor=grid_color,
    ),
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="#1c1c12" if dark else "#fff8e6",
        font_color="#f0cc60" if dark else "#333",
        bordercolor=gold_line,
    ),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── History table ──────────────────────────────────────────────────────────────
with st.expander("📋 SGE Gold 99.99 Daily Close Table"):
    df_tbl = sge["history"].copy().sort_values("date", ascending=False)
    df_tbl["USD / troy oz"] = df_tbl["price"].apply(lambda p: round(cny_to_usd(p, fx), 2))
    df_tbl["date"] = df_tbl["date"].dt.strftime("%Y-%m-%d")
    df_tbl = df_tbl.rename(columns={"date": "Date", "price": "SGE Close (RMB/g)"})
    st.dataframe(df_tbl, use_container_width=True, hide_index=True)

# ── Methodology ────────────────────────────────────────────────────────────────
with st.expander("📚 Sources, Methodology & Market Hours"):
    m1, m2 = st.columns(2)

    with m1:
        st.markdown("**🏦 SGE — Shanghai Gold Exchange (Physical Gold)**")
        st.markdown("""<div class="meth">
The <strong>Shanghai Gold Exchange (SGE)</strong> is China's state-supervised gold exchange
and the world's largest physical gold market by volume. All gold traded on the SGE requires
mandatory physical delivery into SGE-certified vaults — making it a true physical benchmark.<br><br>
The <strong>Shanghai Gold Benchmark Price (SHAU)</strong> is set via a twice-daily electronic
auction: AM session (~10:15 Beijing) and PM session (~14:30 Beijing). This dashboard uses
the <strong>Gold 99.99 spot contract</strong> — 99.99% fine gold, denominated in
<strong>RMB per gram</strong>.<br><br>
<strong>Market hours (Beijing / UTC+8):</strong> Night 20:00–02:30 · Day 09:00–15:30.
Closed weekends and Chinese public holidays.<br><br>
<a href="https://en.sge.com.cn/data_BenchmarkPrice" target="_blank">
→ SGE Benchmark Price (en.sge.com.cn)</a>
</div>""", unsafe_allow_html=True)

    with m2:
        st.markdown("**📜 COMEX — Gold Futures (Paper Gold)**")
        st.markdown("""<div class="meth">
<strong>COMEX</strong> (a CME Group division) is the world's primary gold futures market.
The front-month GC contract — 100 troy oz, priced in <strong>USD per troy oz</strong> — is
the global reference used in ETF valuations, central bank reserve pricing, and nearly all
international contracts.<br><br>
While physical delivery is technically available, over 95% of COMEX contracts are
cash-settled or rolled forward. COMEX reflects <em>financial market expectations and hedging
flows</em>, not immediate physical supply/demand.<br><br>
<strong>Market hours (US Eastern):</strong> Sunday 6 PM – Friday 5 PM with a 60-min daily
break. Near-continuous 5-day coverage.<br><br>
Price sourced via <strong>Yahoo Finance</strong> (ticker: GC=F, ~15-min delay).
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    fc1, fc2 = st.columns(2)

    with fc1:
        st.markdown("**🔄 Conversion Formula**")
        st.markdown("""<div class="meth">
<strong>RMB/gram → USD/troy oz:</strong><br>
Price (USD/oz) = Price (RMB/g) × 31.1035 ÷ USD/CNY<br><br>
<strong>USD/troy oz → RMB/gram:</strong><br>
Price (RMB/g) = Price (USD/oz) × USD/CNY ÷ 31.1035<br><br>
FX rate is the live USD/CNY spot sourced from Yahoo Finance (USDCNY=X), refreshed every
5 minutes. Real cross-market arbitrage additionally involves ~13% Chinese VAT, transport,
insurance, and settlement lag.
</div>""", unsafe_allow_html=True)

    with fc2:
        st.markdown("**⚠️ Disclaimer**")
        st.markdown("""<div class="meth">
For <strong>informational and educational purposes only</strong> — not financial,
investment, or trading advice. Prices carry a delay and are sourced from third-party
aggregators (Yahoo Finance, en.sge.com.cn).<br><br>
Verify with official sources
(<a href="https://en.sge.com.cn" target="_blank">en.sge.com.cn</a>,
<a href="https://www.cmegroup.com/markets/metals/precious/gold.html" target="_blank">cmegroup.com</a>)
before any financial decision.
</div>""", unsafe_allow_html=True)
