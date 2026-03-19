"""
services/market_data.py

Strategi:
1. Cari ticker via IDX API (paling akurat untuk saham Indonesia)
2. Fallback ke Yahoo Finance Search jika IDX tidak ketemu
3. Ambil harga live + financial data via Yahoo Finance
"""

import re
import time
import logging
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = 10


# ── 1. Cari Ticker ────────────────────────────────────────────────────────────

def get_ticker_from_google(company_name: str, ticker_hint: str = "") -> str:
    """
    Cari ticker saham IDX.
    Strategi: IDX API → Yahoo Finance Search → ticker_hint
    """
    # ── Step 1: Coba ticker_hint via IDX API ──
    if ticker_hint and re.match(r"^[A-Z]{2,6}$", ticker_hint.strip().upper()):
        candidate = ticker_hint.strip().upper()
        if _verify_ticker_idx(candidate):
            logger.info(f"Ticker hint terverifikasi via IDX: {candidate}")
            return candidate

    # ── Step 2: Search via IDX API ──
    ticker = _search_ticker_idx(company_name)
    if ticker:
        return ticker

    # ── Step 3: Fallback Yahoo Finance ──
    ticker = _search_ticker_yahoo(company_name)
    if ticker:
        return ticker

    # ── Step 4: Gunakan ticker_hint ──
    if ticker_hint:
        logger.info(f"Fallback ke ticker dari prospektus: {ticker_hint}")
        return ticker_hint.upper()

    return ""


def _verify_ticker_idx(ticker: str) -> bool:
    """Verifikasi ticker via IDX API."""
    try:
        url = f"https://idx.co.id/umum/GetStockSummary/?stockCode={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            # IDX API return data jika ticker valid
            return bool(data.get("stockCode") or data.get("StockCode") or
                       (isinstance(data, list) and len(data) > 0))
        return False
    except Exception as e:
        logger.warning(f"IDX verify error: {e}")
        return False


def _search_ticker_idx(company_name: str) -> str:
    """Cari ticker via IDX search."""
    try:
        # Bersihkan nama perusahaan
        clean = company_name.replace("PT ", "").replace(" Tbk", "").replace(" Tbk.", "").strip()
        
        # IDX search endpoint
        url = "https://idx.co.id/umum/GetStockList/"
        params = {"language": "id", "querySearch": clean}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        
        if resp.status_code == 200:
            data = resp.json()
            results = data if isinstance(data, list) else data.get("data", [])
            
            if results and len(results) > 0:
                # Ambil hasil pertama yang paling relevan
                first = results[0]
                ticker = (first.get("stockCode") or 
                         first.get("StockCode") or 
                         first.get("code", ""))
                if ticker and re.match(r"^[A-Z]{2,6}$", ticker.upper()):
                    logger.info(f"Ticker ditemukan via IDX Search: {ticker}")
                    return ticker.upper()
        return ""
    except Exception as e:
        logger.warning(f"IDX search error: {e}")
        return ""


def _search_ticker_yahoo(company_name: str) -> str:
    """Fallback: cari ticker via Yahoo Finance Search."""
    try:
        clean = company_name.replace("PT ", "").replace(" Tbk", "").strip()
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q": clean + " IDX",
            "lang": "id",
            "region": "ID",
            "quotesCount": 5,
            "newsCount": 0,
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        for q in data.get("quotes", []):
            symbol = q.get("symbol", "")
            exchange = q.get("exchange", "")
            if symbol.endswith(".JK") or exchange in ["JKT", "IDX", "Jakarta"]:
                ticker = symbol.replace(".JK", "").upper()
                logger.info(f"Ticker ditemukan via Yahoo: {ticker}")
                return ticker
        return ""
    except Exception as e:
        logger.warning(f"Yahoo search error: {e}")
        return ""


# ── 2. Ambil Data Live ────────────────────────────────────────────────────────

def get_market_data(ticker: str) -> dict:
    """
    Ambil harga live + financial data.
    Prioritas: IDX API untuk validasi → Yahoo Finance untuk data lengkap
    """
    if not ticker:
        return {}

    ticker_clean = ticker.replace(".JK", "").upper()

    # Coba ambil data dari Yahoo Finance
    result = _get_yahoo_data(ticker_clean)
    
    # Jika Yahoo gagal, coba IDX API untuk harga
    if not result.get("current_price"):
        idx_price = _get_idx_price(ticker_clean)
        if idx_price:
            result["current_price"] = idx_price

    return result


def _get_yahoo_data(ticker: str) -> dict:
    """Ambil data dari Yahoo Finance."""
    ticker_yf = ticker + ".JK"
    
    for attempt in range(3):
        try:
            # ── Chart data (harga) ──
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}"
            params = {"interval": "1d", "range": "1d"}
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return {}

            meta     = result[0].get("meta", {})
            price    = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            currency = meta.get("currency", "IDR")
            price_str = _fmt_price(price, currency)

            # ── Summary detail (market cap, shares) ──
            mkt_cap_str = ""
            shares_str  = ""

            try:
                url2   = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_yf}"
                params2 = {"modules": "summaryDetail,defaultKeyStatistics,financialData"}
                resp2  = requests.get(url2, params=params2, headers=HEADERS, timeout=TIMEOUT)
                data2  = resp2.json()
                summary = data2.get("quoteSummary", {}).get("result", [{}])[0]

                sd = summary.get("summaryDetail", {})
                ks = summary.get("defaultKeyStatistics", {})

                mkt_cap = (sd.get("marketCap", {}).get("raw") or
                          ks.get("marketCap", {}).get("raw"))
                shares  = ks.get("sharesOutstanding", {}).get("raw")

                if mkt_cap:
                    mkt_cap_str = _fmt_market_cap(mkt_cap, currency)
                if shares:
                    shares_str = _fmt_shares(shares)

            except Exception as e:
                logger.warning(f"Yahoo summary error: {e}")

            return {
                "current_price":      price_str,
                "market_cap":         mkt_cap_str,
                "shares_outstanding": shares_str,
                "currency":           currency,
            }

        except requests.RequestException as e:
            logger.warning(f"Yahoo attempt {attempt+1} gagal ({ticker_yf}): {e}")
            if attempt < 2:
                time.sleep(2)

    return {}


def _get_idx_price(ticker: str) -> str:
    """Ambil harga dari IDX API sebagai fallback."""
    try:
        url = f"https://idx.co.id/umum/GetStockSummary/?stockCode={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            # Coba berbagai field nama harga di IDX API
            price = (data.get("LastPrice") or 
                    data.get("lastPrice") or
                    data.get("Close") or
                    data.get("close"))
            if price:
                return _fmt_price(float(price), "IDR")
    except Exception as e:
        logger.warning(f"IDX price error: {e}")
    return ""


def get_underwriter_track_record(underwriters: list) -> str:
    """Placeholder — track record dianalisis Gemini langsung."""
    return ""


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_price(price, currency: str) -> str:
    if not price:
        return ""
    try:
        num = float(price)
        if currency == "IDR":
            return f"Rp {num:,.0f}".replace(",", ".")
        elif currency == "USD":
            return f"$ {num:,.2f}"
        else:
            return f"{currency} {num:,.2f}"
    except Exception:
        return str(price)


def _fmt_market_cap(value, currency: str) -> str:
    if not value:
        return ""
    try:
        num = float(value)
        if currency == "IDR":
            if num >= 1_000_000_000_000:
                return f"Rp {num/1_000_000_000_000:.2f} T"
            elif num >= 1_000_000_000:
                return f"Rp {num/1_000_000_000:.2f} M"
            else:
                return f"Rp {num:,.0f}"
        else:
            if num >= 1_000_000_000:
                return f"${num/1_000_000_000:.2f}B"
            else:
                return f"${num/1_000_000:.2f}M"
    except Exception:
        return str(value)


def _fmt_shares(value) -> str:
    if not value:
        return ""
    try:
        num = float(value)
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.2f} miliar lembar"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.0f} juta lembar"
        else:
            return f"{num:,.0f} lembar"
    except Exception:
        return str(value)