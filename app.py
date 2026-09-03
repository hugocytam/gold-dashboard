"""
Physical vs Paper Gold — Daily Benchmark Dashboard
===================================================
SGE Gold 99.99 (physical, RMB/gram) vs COMEX GC futures (paper, USD/troy oz)

DEPLOYMENT — Streamlit Community Cloud (free)
─────────────────────────────────────────────
1. Push app.py + requirements.txt to a public GitHub repo
2. Go to share.streamlit.io → New app → select repo → Main file: app.py → Deploy

DATA SOURCES (all free, no API key needed)
──────────────────────────────────────────
• COMEX gold price        → Yahoo Finance / yfinance  (ticker: GC=F)
• USD/CNY live rate       → Yahoo Finance / yfinance  (ticker: USDCNY=X, 5-min cache)
• USD/CNY history         → FRED St. Louis            (series: DEXCHUS, 24h cache)
• SGE Gold 99.99 live     → en.sge.com.cn             (Jan 2024+, 1h cache)
• SGE actual Dec 2016+    → sge.com.cn/graph/Dailyhq  (JSON API, 24h cache)
• SGE pre-2017 est.       → COMEX price × FRED USD/CNY ÷ 31.1035 (labelled estimated)

NOTE: SGE's graph API (/graph/Dailyhq) returns all Au99.99 data from Dec 2016 onwards.
Pre-2017 prices are estimated from COMEX converted to RMB/gram via FRED exchange rates.
"""

import time
import re
import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

# ── Constants ──────────────────────────────────────────────────────────────────
TROY = 31.1035
FRED_DEXCHUS   = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXCHUS"
FRED_GOLD_LBMA = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GOLDPMGBD228NLBM"

SGE_FALLBACK_HISTORY = pd.DataFrame([
    {"date": pd.Timestamp("2024-01-02"), "price": 476.36},
    {"date": pd.Timestamp("2024-06-28"), "price": 543.90},
    {"date": pd.Timestamp("2024-12-31"), "price": 620.14},
    {"date": pd.Timestamp("2026-07-21"), "price": 886.95},
    {"date": pd.Timestamp("2026-07-28"), "price": 883.28},
])
SGE_FALLBACK = {
    "date": "2026-07-28", "close": 883.28, "high": 896.00, "low": 879.50,
    "chg": -10.69, "pct": -1.20,
}

SGE_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://en.sge.com.cn/data_BenchmarkPrice",
}

SGE_GRAPH_HEADERS = {
    "User-Agent":        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
    "Accept":            "text/html, */*; q=0.01",
    "Accept-Language":   "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type":      "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin":            "https://www.sge.com.cn",
    "Referer":           "https://www.sge.com.cn/sjzx/mrhq",
    "X-Requested-With":  "XMLHttpRequest",
}

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Physical vs Paper Gold | SGE vs COMEX",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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


def _parse_sge_html(html: str) -> list[dict]:
    """Parse SGE daily report HTML. Tracks date across rowspan cells."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    current_date = None
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        cells = [td.get_text(strip=True) for td in tds]
        for cell in cells:
            if re.match(r"^\d{4}-\d{2}-\d{2}$", cell):
                current_date = cell
                break
        if "Au99.99" not in cells:
            continue
        idx = cells.index("Au99.99")
        row_date = None
        if idx > 0 and re.match(r"^\d{4}-\d{2}-\d{2}$", cells[idx - 1]):
            row_date = cells[idx - 1]
        elif current_date:
            row_date = current_date
        if not row_date or idx + 4 >= len(cells):
            continue
        try:
            rows.append({
                "date":  pd.Timestamp(row_date),
                "open":  float(cells[idx + 1].replace(",", "")),
                "high":  float(cells[idx + 2].replace(",", "")),
                "low":   float(cells[idx + 3].replace(",", "")),
                "close": float(cells[idx + 4].replace(",", "")),
                "chg":   float(cells[idx + 5].replace(",", "")) if idx + 5 < len(cells) else 0.0,
                "pct":   float(cells[idx + 6].replace("%", "").replace(",", "")) if idx + 6 < len(cells) else 0.0,
            })
        except (ValueError, IndexError):
            continue
    return rows


# ── SGE latest snapshot (cached 1h) ───────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_sge_latest():
    end   = datetime.now()
    start = end - timedelta(days=30)
    url   = (
        "https://en.sge.com.cn/data/data_daily_international_new"
        f"?start_date={start.strftime('%Y-%m-%d')}"
        f"&end_date={end.strftime('%Y-%m-%d')}"
    )
    try:
        r = requests.get(url, headers=SGE_HEADERS, timeout=12)
        r.raise_for_status()
        rows = _parse_sge_html(r.text)
        if not rows:
            return SGE_FALLBACK, True
        df = pd.DataFrame(rows).sort_values("date").drop_duplicates("date")
        latest = df.iloc[-1]
        return {
            "date":  latest["date"].strftime("%Y-%m-%d"),
            "close": float(latest["close"]),
            "high":  float(latest["high"]),
            "low":   float(latest["low"]),
            "chg":   float(latest["chg"]),
            "pct":   float(latest["pct"]),
        }, False
    except Exception:
        return SGE_FALLBACK, True


# ── SGE actual history Jan 2024+ (cached 24h) ─────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_sge_history_actual():
    """
    Actual SGE Au99.99 daily closes (Jan 2024+).
    Primary: bundled sge_history_2024_2026.csv (full daily history, reliable).
    Extended: SGE English API for any trading days after the CSV's last entry.

    The old approach (one API call per year) only retrieved page 1 = ~2 days
    per year due to server-side pagination. The CSV fixes that entirely.
    """
    import os

    # 1. Load bundled CSV -------------------------------------------------------
    csv_path = os.path.join(os.path.dirname(__file__), "sge_history_2024_2026.csv")
    try:
        df_csv = pd.read_csv(csv_path, parse_dates=["date"])
        df_csv = df_csv.rename(columns={"close_rmb_g": "price"})
        df_csv["date"] = pd.to_datetime(df_csv["date"]).dt.normalize()
    except Exception:
        df_csv = pd.DataFrame(columns=["date", "price"])

    csv_end = df_csv["date"].max() if not df_csv.empty else pd.Timestamp("2023-12-31")

    # 2. Extend with live SGE API for dates after the CSV ----------------------
    start_live = (csv_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    end_live   = datetime.now().strftime("%Y-%m-%d")
    live_rows  = []
    if start_live <= end_live:
        url = (
            "https://en.sge.com.cn/data/data_daily_international_new"
            f"?start_date={start_live}&end_date={end_live}"
        )
        try:
            r = requests.get(url, headers=SGE_HEADERS, timeout=15)
            r.raise_for_status()
            live_rows = _parse_sge_html(r.text)
        except Exception:
            pass

    if live_rows:
        df_live = (pd.DataFrame(live_rows)
                     [["date", "close"]]
                     .rename(columns={"close": "price"}))
        df_live["date"] = pd.to_datetime(df_live["date"]).dt.normalize()
    else:
        df_live = pd.DataFrame(columns=["date", "price"])

    return (pd.concat([df_csv, df_live], ignore_index=True)
              .sort_values("date")
              .drop_duplicates("date")
              .reset_index(drop=True))


# ── SGE actual history Dec 2016+ via graph API (cached 24h) ──────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_sge_history_graph_api():
    """
    Fetch actual SGE Au99.99 data from the Chinese SGE graph API.
    Endpoint: https://www.sge.com.cn/graph/Dailyhq
    Returns all historical data from 2016-12-19 onwards in one call.
    """
    url = "https://www.sge.com.cn/graph/Dailyhq"
    try:
        r = requests.post(url, data={"instid": "Au99.99"},
                          headers=SGE_GRAPH_HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = data.get("time", [])
        if not rows:
            return pd.DataFrame(columns=["date", "price"])
        df = pd.DataFrame(rows, columns=["date", "open", "close", "low", "high"])
        df["date"]  = pd.to_datetime(df["date"], errors="coerce")
        df["price"] = pd.to_numeric(df["close"], errors="coerce")
        df = df.dropna(subset=["date", "price"])
        return df[["date", "price"]].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "price"])


# ── FRED DEXCHUS — historical USD/CNY (cached 24h) ────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_fx_history_fred():
    """
    Historical daily USD/CNY from FRED St. Louis (series DEXCHUS).
    FRED lags ~2 months for the most recent data; Yahoo Finance fills the gap.
    """
    try:
        df = pd.read_csv(FRED_DEXCHUS, parse_dates=["DATE"])
        df.columns = ["date", "fx"]
        df = df[df["fx"] != "."].copy()
        df["fx"] = pd.to_numeric(df["fx"], errors="coerce")
        df = df.dropna(subset=["fx"]).sort_values("date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "fx"])


# ── LBMA/COMEX gold history from FRED (cached 24h) ───────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_gold_history_fred():
    """
    LBMA PM gold price from FRED (GOLDPMGBD228NLBM) — USD/troy oz, daily from 1968.
    Used for the chart history and as fallback for live COMEX price.
    LBMA PM and COMEX GC settle within ~$1 of each other on any given day.
    """
    try:
        df = pd.read_csv(FRED_GOLD_LBMA, parse_dates=["DATE"])
        df.columns = ["date", "price"]
        df = df[df["price"] != "."].copy()
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna(subset=["price"]).sort_values("date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return pd.DataFrame(columns=["date", "price"])


# ── Full COMEX history from yfinance (cached 24h) — primary source ────────────
@st.cache_data(ttl=86400, show_spinner=False)
def get_gold_history_recent():
    """
    Full GC=F history from yfinance (period='max' — goes back to ~1975).
    This is the primary COMEX source; FRED LBMA fills any gaps on recent dates
    where yfinance may lag. Cached 24h since history rarely changes intraday.
    """
    try:
        ticker = yf.Ticker("GC=F")
        hist   = ticker.history(period="max", interval="1d")
        hist   = hist[hist["Close"] > 0].dropna(subset=["Close"])
        if hist.empty:
            raise ValueError("empty")
        idx = hist.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        df = pd.DataFrame({"date": idx, "price": hist["Close"].values})
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df[["date", "price"]].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "price"])


# ── Recent FX history from yfinance (cached 1h) — bridges FRED DEXCHUS lag ────
@st.cache_data(ttl=3600, show_spinner=False)
def get_fx_history_recent():
    """
    Recent 6-month USDCNY=X history from yfinance to fill any FRED DEXCHUS lag.
    Falls back gracefully — FRED DEXCHUS typically lags < 1 week.
    """
    try:
        ticker = yf.Ticker("USDCNY=X")
        hist   = ticker.history(period="6mo", interval="1d")
        hist   = hist[hist["Close"] > 0].dropna(subset=["Close"])
        if hist.empty:
            raise ValueError("empty")
        idx = hist.index
        if hasattr(idx, "tz") and idx.tz is not None:
            idx = idx.tz_localize(None)
        df = pd.DataFrame({"date": idx, "fx": hist["Close"].values})
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df[["date", "fx"]].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    except Exception:
        return pd.DataFrame(columns=["date", "fx"])


# ── COMEX live price (cached 5m) — yfinance with FRED fallback ────────────────
@st.cache_data(ttl=300, show_spinner=False)
def get_comex_live():
    """
    Live COMEX GC=F price from yfinance.
    Falls back to FRED LBMA latest if Yahoo Finance rate-limits or errors.
    """
    try:
        ticker = yf.Ticker("GC=F")
        hist   = ticker.history(period="5d", interval="1d")
        hist   = hist[hist["Close"] > 0].dropna(subset=["Close"])
        if hist.empty:
            raise ValueError("No data returned")
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
        chg  = last - prev
        pct  = chg / prev * 100
        return {"price": round(last, 2), "chg": round(chg, 2), "pct": round(pct, 2), "stale": False}
    except Exception:
        gold = get_gold_history_fred()
        if gold.empty:
            return {"price": 3300.0, "chg": 0.0, "pct": 0.0, "stale": True}
        last = float(gold["price"].iloc[-1])
        prev = float(gold["price"].iloc[-2]) if len(gold) > 1 else last
        chg  = last - prev
        pct  = chg / prev * 100
        return {"price": round(last, 2), "chg": round(chg, 2), "pct": round(pct, 2), "stale": True}


# ── FX live rate (cached 5m) — yfinance with FRED fallback ───────────────────
@st.cache_data(ttl=300, show_spinner=False)
def get_fx_live():
    """
    Live USD/CNY from yfinance (USDCNY=X).
    Falls back to FRED DEXCHUS latest if Yahoo Finance rate-limits or errors.
    """
    try:
        ticker = yf.Ticker("USDCNY=X")
        hist   = ticker.history(period="5d", interval="1d")
        hist   = hist[hist["Close"] > 0].dropna(subset=["Close"])
        if hist.empty:
            raise ValueError("No data returned")
        return round(float(hist["Close"].iloc[-1]), 4), False
    except Exception:
        fx_hist = get_fx_history_fred()
        if fx_hist.empty:
            return 7.25, True
        return round(float(fx_hist["fx"].iloc[-1]), 4), True


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="gold-header">
  <h1>🥇 Physical vs Paper Gold — Daily Benchmark</h1>
  <p>SGE Gold 99.99 (Shanghai · Physical · RMB/gram) &nbsp;vs&nbsp;
     COMEX GC Futures (New York · Paper · USD/troy oz)</p>
</div>
""", unsafe_allow_html=True)

# ── Controls ───────────────────────────────────────────────────────────────────
c_unit, c_dark, c_refresh, c_ts = st.columns([3.5, 1.2, 0.7, 4])
with c_unit:
    unit = st.radio("unit", ["¥ RMB / gram", "$ USD / troy oz"],
                    horizontal=True, label_visibility="collapsed")
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
    st.caption(f"SGE 1h · History 24h · COMEX/FX 5m (FRED fallback if rate-limited) · "
               f"Last loaded {datetime.now().strftime('%b %d, %H:%M')}")

st.divider()

# ── Fetch ──────────────────────────────────────────────────────────────────────
with st.spinner("Fetching live prices…"):
    comex          = get_comex_live()
    fx, fx_stale   = get_fx_live()
    sge, sge_stale = get_sge_latest()

_ph = st.empty()
_ph.caption("⏳ Loading historical data… (first load only, cached 24h after)")
sge_graph       = get_sge_history_graph_api()   # Dec 2016 – present (actual, Chinese API)
sge_actual      = get_sge_history_actual()       # Jan 2024 – present (actual, English API)
fx_hist_fred    = get_fx_history_fred()          # FRED DEXCHUS long history
fx_hist_recent  = get_fx_history_recent()        # yfinance bridge for FRED lag
gold_hist_fred  = get_gold_history_fred()        # FRED LBMA long history
gold_hist_recent = get_gold_history_recent()     # yfinance bridge for FRED lag
_ph.empty()

# Merge FRED + yfinance to get continuous COMEX and FX history up to today
def _merge_history(base, recent, val_col):
    if base.empty and recent.empty:
        return pd.DataFrame(columns=["date", val_col])
    if base.empty:
        return recent
    if recent.empty:
        return base
    fred_end  = base["date"].max()
    bridge    = recent[recent["date"] > fred_end]
    merged    = pd.concat([base, bridge], ignore_index=True)
    return merged.sort_values("date").drop_duplicates("date").reset_index(drop=True)

gold_history = _merge_history(gold_hist_recent, gold_hist_fred, "price")  # yfinance full history base, FRED fills any gap
fx_hist      = _merge_history(fx_hist_fred,  fx_hist_recent,  "fx")

# Merge: graph API covers Dec 2016 – Dec 2023; English API covers Jan 2024+
# Combined → full actual SGE series from Dec 2016 onwards
if not sge_graph.empty:
    sge_graph_pre2024 = sge_graph[sge_graph["date"] < pd.Timestamp("2024-01-01")]
else:
    sge_graph_pre2024 = pd.DataFrame(columns=["date", "price"])
sge_actual_combined = (pd.concat([sge_graph_pre2024, sge_actual], ignore_index=True)
                         .sort_values("date").drop_duplicates("date").reset_index(drop=True))
# Threshold for estimation: everything before the earliest actual SGE date gets estimated.
# If graph API worked → Dec 2016. If graph API failed → Jan 2024. Never leaves a gap.
SGE_ACTUAL_START = (sge_actual_combined["date"].min()
                    if not sge_actual_combined.empty
                    else pd.Timestamp("2024-01-01"))

use_usd = "USD" in unit

# ── Derived prices ─────────────────────────────────────────────────────────────
sge_cny = sge["close"]
sge_usd = cny_to_usd(sge_cny, fx)
cx_usd  = comex["price"]
cx_cny  = usd_to_cny(cx_usd, fx)

if use_usd:
    sge_main, cx_main = sge_usd, cx_usd
    sge_conv, cx_conv = sge_cny, cx_cny
    main_fmt  = lambda v: f"${v:,.2f}"
    conv_fmt  = lambda v: f"¥{v:,.2f}"
    conv_lbl  = "RMB / gram"
    sge_delta = cny_to_usd(sge["chg"], fx)
    cx_delta  = comex["chg"]
else:
    sge_main, cx_main = sge_cny, cx_cny
    sge_conv, cx_conv = sge_usd, cx_usd
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
    st.metric("SGE Close", main_fmt(sge_main),
              delta=f"{sge_delta:+.2f}  ({sge['pct']:+.2f}%)")
    st.caption(f"≈ {conv_fmt(sge_conv)} {conv_lbl}  ·  "
               f"Hi ¥{sge['high']:.2f}  Lo ¥{sge['low']:.2f}  ·  {sge['date']}")
    if sge_stale:
        st.warning("Using cached SGE data — live scrape unavailable", icon="⚠️")

with c2:
    st.markdown("##### 📜 COMEX — Paper Gold")
    src_label = "FRED LBMA PM (prev. day)" if comex["stale"] else "Yahoo Finance GC=F"
    st.caption(f"GC Front Month · CME Group · USD/troy oz native · Source: {src_label}")
    st.metric("COMEX Last", main_fmt(cx_main),
              delta=f"{cx_delta:+.2f}  ({comex['pct']:+.2f}%)")
    st.caption(f"≈ {conv_fmt(cx_conv)} {conv_lbl}")
    if comex["stale"]:
        st.warning("Yahoo Finance rate-limited — showing FRED LBMA PM (prev. business day)", icon="⚠️")

with c3:
    st.markdown("##### 📊 Spread  (COMEX − SGE)")
    st.caption("Converted to a common unit for like-for-like comparison")
    st.metric(f"Absolute ({spread_unit})", f"{spread_abs:+.2f}",
              delta=f"{spread_pct:+.2f}%  COMEX {'premium' if spread_pct >= 0 else 'discount'}",
              delta_color="off")
    abs_pct = abs(spread_pct)
    if abs_pct < 0.5:
        msg, icon = "Spread within normal range — prices broadly aligned.", "✅"
    elif spread_pct >= 0:
        msg, icon = f"COMEX at {abs_pct:.2f}% premium. Futures optimism or limits on physical arbitrage.", "📈"
    else:
        msg, icon = f"SGE at {abs_pct:.2f}% premium. Strong physical demand in China or FX effects.", "📉"
    st.info(f"{icon}  {msg}")
    fx_src = "FRED DEXCHUS (prev. day)" if fx_stale else "live"
    st.caption(f"USD/CNY: **{fx}** ({fx_src})  ·  1 troy oz = 31.1035 g")

st.divider()

# ── Price history chart ────────────────────────────────────────────────────────
ch_head, ch_period = st.columns([2, 5])
with ch_head:
    st.subheader("Price History")
with ch_period:
    period = st.radio("period", ["1M", "6M", "YTD", "1Y", "5Y", "All"],
                      horizontal=True, index=3, label_visibility="collapsed")

today  = pd.Timestamp.now().normalize()
cutoff = {
    "1M":  today - pd.DateOffset(months=1),
    "6M":  today - pd.DateOffset(months=6),
    "YTD": pd.Timestamp(f"{today.year}-01-01"),
    "1Y":  today - pd.DateOffset(years=1),
    "5Y":  today - pd.DateOffset(years=5),
    "All": pd.Timestamp("2006-10-30"),
}[period]

# ── Build SGE estimated history ─────────────────────────────────────────────────
# Estimated = COMEX/LBMA × FRED DEXCHUS ÷ 31.1035 for all dates where actual
# SGE data is unavailable. Actual SGE data (where fetched) takes priority.
cx_all = gold_history.copy()
cx_all["date"] = pd.to_datetime(cx_all["date"]).dt.normalize()

SGE_INCEPTION = pd.Timestamp("2006-10-30")

if not fx_hist.empty:
    fx_daily = fx_hist.copy()
    fx_daily["date"] = pd.to_datetime(fx_daily["date"]).dt.normalize()
    # Forward-fill weekends/holidays in FX (sources are business days only)
    full_idx = pd.date_range(fx_daily["date"].min(), fx_daily["date"].max(), freq="D")
    fx_daily = fx_daily.set_index("date").reindex(full_idx).ffill().reset_index()
    fx_daily.columns = ["date", "fx"]
    sge_est = cx_all.merge(fx_daily, on="date", how="inner")
    sge_est["price"] = sge_est["price"] * sge_est["fx"] / TROY
    sge_est = sge_est[["date", "price"]]
    # Apply SGE inception filter (exchange opened Oct 30, 2006)
    sge_est = sge_est[sge_est["date"] >= SGE_INCEPTION]
    # Remove dates that are covered by actual SGE data (no double-counting)
    if not sge_actual_combined.empty:
        actual_dates = set(sge_actual_combined["date"].dt.normalize())
        sge_est = sge_est[~sge_est["date"].isin(actual_dates)]
else:
    sge_est = pd.DataFrame(columns=["date", "price"])

# ── Filter all series to selected period ──────────────────────────────────────
sge_est_plot    = sge_est[sge_est["date"] >= cutoff].copy()
sge_actual_plot = sge_actual_combined[sge_actual_combined["date"] >= cutoff].copy()
cx_plot         = cx_all[cx_all["date"] >= cutoff].copy()

if use_usd:
    sge_est_plot["price"]    = sge_est_plot["price"].apply(lambda p: cny_to_usd(p, fx))
    sge_actual_plot["price"] = sge_actual_plot["price"].apply(lambda p: cny_to_usd(p, fx))
    y_title, hover_fmt = "USD / troy oz", "$%{y:,.2f}"
else:
    cx_plot["price"] = cx_plot["price"].apply(lambda p: usd_to_cny(p, fx))
    y_title, hover_fmt = "RMB / gram", "¥%{y:,.2f}"

# ── Theme colours ──────────────────────────────────────────────────────────────
if dark:
    bg   = "#0e1117"; grid = "#2a2a3a"; txt = "#cccccc"
    gold = "#f0cc60"; blue = "#60b8f0"
else:
    bg   = "white";   grid = "#f0ece2"; txt = "#555"
    gold = "#c9a227"; blue = "#3a8fc0"

fig = go.Figure()

# Trace 1: SGE estimated (pre-Dec 2016) — dashed gold
if not sge_est_plot.empty:
    fig.add_trace(go.Scatter(
        x=sge_est_plot["date"], y=sge_est_plot["price"],
        name="SGE Estimated (COMEX × FRED FX, where actual unavailable)",
        line=dict(color=gold, width=1.5, dash="dot"),
        mode="lines",
        opacity=0.65,
        hovertemplate=f"SGE est.: {hover_fmt}<extra></extra>",
    ))

# Trace 2: SGE actual (Dec 2016+) — solid gold
if not sge_actual_plot.empty:
    fig.add_trace(go.Scatter(
        x=sge_actual_plot["date"], y=sge_actual_plot["price"],
        name="SGE Gold 99.99 (Actual, Dec 2016+)",
        line=dict(color=gold, width=2.5),
        mode="lines",
        hovertemplate=f"SGE actual: {hover_fmt}<extra></extra>",
    ))

# Trace 3: COMEX/LBMA — blue
fig.add_trace(go.Scatter(
    x=cx_plot["date"], y=cx_plot["price"],
    name="COMEX/LBMA Paper Gold (USD/oz)",
    line=dict(color=blue, width=2),
    mode="lines",
    hovertemplate=f"COMEX/LBMA: {hover_fmt}<extra></extra>",
))

fig.update_layout(
    height=420,
    margin=dict(l=0, r=10, t=10, b=0),
    plot_bgcolor=bg, paper_bgcolor=bg,
    font=dict(color=txt, size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(size=11, color=txt), bgcolor="rgba(0,0,0,0)"),
    yaxis=dict(title=y_title, title_font=dict(color=txt), tickfont=dict(color=txt),
               gridcolor=grid, tickformat=",.0f", linecolor=grid, autorange=True),
    xaxis=dict(tickfont=dict(color=txt), gridcolor=grid, linecolor=grid, type="date"),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#1c1c12" if dark else "#fff8e6",
                    font_color="#f0cc60" if dark else "#333", bordercolor=gold),
)

st.plotly_chart(fig, use_container_width=True)

if not sge_est_plot.empty:
    if not sge_actual_combined.empty:
        a_start = sge_actual_combined["date"].min().strftime("%b %Y")
        a_end   = sge_actual_combined["date"].max().strftime("%b %Y")
        est_note = f"Solid gold = actual SGE Au99.99 ({a_start} – {a_end})."
    else:
        est_note = "Actual SGE data unavailable — full series is estimated."
    st.caption(
        f"⚠️ Dotted gold = SGE estimated (COMEX/LBMA × FRED DEXCHUS USD/CNY ÷ 31.1035) "
        f"for all dates without actual SGE data. {est_note}"
    )

st.divider()

# ── History table ──────────────────────────────────────────────────────────────
with st.expander("📋 SGE Gold 99.99 Daily Close Table (Actual, Dec 2016+)"):
    df_tbl = sge_actual_combined.copy().sort_values("date", ascending=False)
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
and the world's largest physical gold market by volume. All gold requires mandatory physical
delivery into SGE-certified vaults — a true physical benchmark.<br><br>
The <strong>Shanghai Gold Benchmark Price (SHAU)</strong> is set via a twice-daily electronic
auction: AM (~10:15 Beijing) and PM (~14:30 Beijing). This dashboard uses the
<strong>Gold 99.99 spot contract</strong> — 99.99% fine gold, priced in <strong>RMB per gram</strong>.<br><br>
<strong>Data availability:</strong> Actual SGE Au99.99 data sourced from
<a href="https://www.sge.com.cn/sjzx/mrhq" target="_blank">sge.com.cn/graph/Dailyhq</a>
from <strong>Dec 19, 2016</strong> onwards. Jan 2024+ data is additionally cross-checked via the
<a href="https://en.sge.com.cn/data_BenchmarkPrice" target="_blank">English SGE API</a>.
Pre-2017 data (dotted line) is estimated — see methodology below.<br><br>
<strong>Market hours (Beijing / UTC+8):</strong> Night 20:00–02:30 · Day 09:00–15:30.
Closed weekends and Chinese public holidays.<br><br>
<a href="https://en.sge.com.cn/data_BenchmarkPrice" target="_blank">→ SGE Benchmark Price</a>
</div>""", unsafe_allow_html=True)

    with m2:
        st.markdown("**📜 COMEX — Gold Futures (Paper Gold)**")
        st.markdown("""<div class="meth">
<strong>COMEX</strong> (CME Group) is the world's primary gold futures market. The front-month
GC contract — 100 troy oz, priced in <strong>USD per troy oz</strong> — is the global reference
used in ETF valuations, central bank reserve pricing, and international contracts.<br><br>
Over 95% of COMEX contracts are cash-settled or rolled. COMEX reflects <em>financial market
expectations and hedging flows</em>, not immediate physical supply/demand.<br><br>
<strong>Market hours (US Eastern):</strong> Sunday 6 PM – Friday 5 PM, 60-min daily break.<br><br>
Price sourced via <strong>Yahoo Finance</strong> (ticker: GC=F, ~15-min delay on free tier).
</div>""", unsafe_allow_html=True)

    st.markdown("---")
    fc1, fc2 = st.columns(2)

    with fc1:
        st.markdown("**🔄 Conversion Formula & FX Sources**")
        st.markdown("""<div class="meth">
<strong>RMB/gram → USD/troy oz:</strong><br>
Price (USD/oz) = Price (RMB/g) × 31.1035 ÷ USD/CNY<br><br>
<strong>USD/troy oz → RMB/gram:</strong><br>
Price (RMB/g) = Price (USD/oz) × USD/CNY ÷ 31.1035<br><br>
<strong>FX sources:</strong><br>
• <strong>Live rate:</strong> Yahoo Finance (USDCNY=X), refreshed every 5 min<br>
• <strong>Historical rate:</strong> FRED St. Louis Federal Reserve, series
  <a href="https://fred.stlouisfed.org/series/DEXCHUS" target="_blank">DEXCHUS</a>
  (China / U.S. Foreign Exchange Rate, business days, refreshed 24h). FRED lags
  ~2 months behind the present date — Yahoo Finance fills the recent gap.<br><br>
Real cross-market arbitrage additionally involves ~13% Chinese VAT on gold, transport,
insurance, and settlement lag.
</div>""", unsafe_allow_html=True)

    with fc2:
        st.markdown("**⚠️ Estimated Series Methodology**")
        st.markdown("""<div class="meth">
Actual SGE Au99.99 data is available from <strong>Dec 19, 2016</strong> via SGE's graph API
(<code>sge.com.cn/graph/Dailyhq</code>). For <strong>Oct 2006 – Dec 2016</strong>, prices are estimated:<br>
<em>SGE est. (RMB/g) = LBMA PM (USD/oz) × FRED DEXCHUS ÷ 31.1035</em><br><br>
If the graph API is unreachable (Chinese server, US-hosted app), the estimation
automatically extends to cover the gap up to Jan 2024, so the chart never shows a blank
stretch. The estimated dotted line and solid actual line meet seamlessly at whatever
date actual data begins.<br><br>
LBMA PM and COMEX GC settle within ~$1 of each other daily. The COMEX/LBMA price
closely tracks SGE Au99.99 with a typical spread under 1%, so the long-run trend is
representative. Spreads may widen during periods of strong Chinese physical demand.<br><br>
Historical LBMA PM price sourced from <a href="https://fred.stlouisfed.org/series/GOLDPMGBD228NLBM"
target="_blank">FRED GOLDPMGBD228NLBM</a>. Verify before any financial decision.
</div>""", unsafe_allow_html=True)

# ── Data verification & export ─────────────────────────────────────────────────
with st.expander("🔬 Data Verification & Export (SGE vs COMEX matched)"):
    if not sge_actual_combined.empty and not cx_all.empty and not fx_hist.empty:
        # Build matched dataset
        _sge = sge_actual_combined.copy()
        _sge["date"] = pd.to_datetime(_sge["date"]).dt.normalize()
        _cx  = cx_all.copy()
        _cx["date"] = pd.to_datetime(_cx["date"]).dt.normalize()
        _fx  = fx_hist.copy()
        _fx["date"] = pd.to_datetime(_fx["date"]).dt.normalize()
        # Fill FX forward so weekends don't drop
        full_idx = pd.date_range(_fx["date"].min(), _fx["date"].max(), freq="D")
        _fx = _fx.set_index("date").reindex(full_idx).ffill().reset_index()
        _fx.columns = ["date", "fx"]

        merged = (_sge
                  .rename(columns={"price": "sge_cny_g"})
                  .merge(_cx.rename(columns={"price": "comex_usd_oz"}), on="date", how="inner")
                  .merge(_fx, on="date", how="left")
                  .dropna())
        merged["comex_cny_g"] = merged["comex_usd_oz"] * merged["fx"] / TROY
        merged["spread_cny"]  = merged["sge_cny_g"] - merged["comex_cny_g"]
        merged["spread_pct"]  = merged["spread_cny"] / merged["comex_cny_g"] * 100
        merged = merged.sort_values("date").reset_index(drop=True)

        # Summary stats
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Matched rows", f"{len(merged):,}")
        sc2.metric("Avg SGE premium", f"{merged['spread_pct'].mean():+.2f}%")
        sc3.metric("Median spread", f"{merged['spread_pct'].median():+.2f}%")
        outliers = merged[merged["spread_pct"].abs() > 15]
        sc4.metric("Outliers >15%", len(outliers), delta="⚠️ check" if len(outliers) else "✓ clean", delta_color="inverse" if len(outliers) else "off")

        st.caption(f"Date range: {merged['date'].min().date()} → {merged['date'].max().date()}")

        # Yearly avg spread
        yr = merged.groupby(merged["date"].dt.year)["spread_pct"].mean().reset_index()
        yr.columns = ["Year", "Avg SGE premium (%)"]
        yr["Avg SGE premium (%)"] = yr["Avg SGE premium (%)"].round(2)
        st.dataframe(yr, use_container_width=False, hide_index=True)

        if not outliers.empty:
            st.warning(f"⚠️ {len(outliers)} rows with >15% spread — may indicate data errors:")
            st.dataframe(outliers[["date","sge_cny_g","comex_cny_g","spread_pct"]].assign(date=outliers["date"].dt.date), hide_index=True)

        # Download button
        csv_bytes = merged.assign(date=merged["date"].dt.strftime("%Y-%m-%d")).to_csv(index=False).encode()
        st.download_button(
            label="⬇️ Download matched CSV (SGE + COMEX + FX)",
            data=csv_bytes,
            file_name="sge_comex_matched.csv",
            mime="text/csv",
        )
    else:
        st.info("Historical data not fully loaded — refresh the page and try again.")
