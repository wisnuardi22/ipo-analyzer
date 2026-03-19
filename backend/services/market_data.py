"""
services/market_data.py

Strategi multi-layer untuk data saham IDX Indonesia:
1. Yahoo Finance (yfinance library) — paling reliable, support IDX .JK
2. IDX Official API — fallback untuk harga
3. Stooq — alternatif untuk historical data
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
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}
TIMEOUT = 15


# ═══════════════════════════════════════════════════════
# 1. CARI TICKER
# ═══════════════════════════════════════════════════════

def get_ticker_from_google(company_name: str, ticker_hint: str = "") -> str:
    """
    Cari ticker IDX via multi-source.
    Priority: ticker_hint (dari Gemini) → Yahoo search → IDX search → Stooq
    """
    # Step 1: Gunakan ticker dari Gemini jika ada
    if ticker_hint and re.match(r"^[A-Z]{2,6}$", ticker_hint.strip().upper()):
        t = ticker_hint.strip().upper()
        if _verify_yahoo(t):
            logger.info(f"✅ Ticker Gemini terverifikasi: {t}")
            return t
        logger.warning(f"⚠️ Ticker Gemini {t} tidak valid di Yahoo, coba search")

    # Step 2: Yahoo Finance Search
    t = _yahoo_search(company_name)
    if t:
        return t

    # Step 3: IDX Official API
    t = _idx_search(company_name)
    if t:
        return t

    # Step 4: Stooq search
    t = _stooq_search(company_name)
    if t:
        return t

    # Step 5: Fallback ke ticker_hint meski tidak terverifikasi
    if ticker_hint:
        logger.warning(f"⚠️ Fallback ke ticker hint: {ticker_hint}")
        return ticker_hint.strip().upper()

    logger.error(f"❌ Ticker tidak ditemukan untuk: {company_name}")
    return ""


def _verify_yahoo(ticker: str) -> bool:
    """Verifikasi ticker di Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.JK"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        result = data.get("chart", {}).get("result")
        return bool(result)
    except Exception:
        return False


def _yahoo_search(company_name: str) -> str:
    """Search ticker via Yahoo Finance API."""
    try:
        clean = _clean_name(company_name)
        url   = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q":           clean,
            "lang":        "id",
            "region":      "ID",
            "quotesCount": 8,
            "newsCount":   0,
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        quotes = resp.json().get("quotes", [])

        for q in quotes:
            sym  = q.get("symbol", "")
            exch = q.get("exchange", "")
            if sym.endswith(".JK") or exch in ["JKT", "IDX", "Jakarta"]:
                ticker = sym.replace(".JK", "").upper()
                logger.info(f"✅ Ticker Yahoo: {ticker} untuk '{company_name}'")
                return ticker
        return ""
    except Exception as e:
        logger.warning(f"Yahoo search error: {e}")
        return ""


def _idx_search(company_name: str) -> str:
    """Search ticker via IDX official API."""
    try:
        clean = _clean_name(company_name)
        url   = "https://idx.co.id/umum/GetStockList/"
        params = {"language": "id", "querySearch": clean}
        resp  = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)

        if resp.status_code == 200:
            data    = resp.json()
            results = data if isinstance(data, list) else data.get("data", [])
            if results:
                first  = results[0]
                ticker = (first.get("stockCode") or
                         first.get("StockCode") or
                         first.get("code", ""))
                if ticker and re.match(r"^[A-Z]{2,6}$", ticker.upper()):
                    logger.info(f"✅ Ticker IDX: {ticker}")
                    return ticker.upper()
        return ""
    except Exception as e:
        logger.warning(f"IDX search error: {e}")
        return ""


def _stooq_search(company_name: str) -> str:
    """Search ticker via Stooq (alternatif untuk IDX)."""
    try:
        clean = _clean_name(company_name).lower().replace(" ", "+")
        url   = f"https://stooq.com/q/?s={clean}.jk"
        resp  = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        # Cari ticker di response
        if resp.status_code == 200:
            match = re.search(r'Symbol["\s:]+([A-Z]{2,6})\.JK', resp.text)
            if match:
                ticker = match.group(1)
                logger.info(f"✅ Ticker Stooq: {ticker}")
                return ticker
        return ""
    except Exception as e:
        logger.warning(f"Stooq error: {e}")
        return ""


def _clean_name(name: str) -> str:
    """Bersihkan nama perusahaan untuk search."""
    name = name.replace("PT ", "").replace(" Tbk", "").replace(" Tbk.", "")
    name = name.replace(",", "").strip()
    return name


# ═══════════════════════════════════════════════════════
# 2. AMBIL HARGA & DATA PASAR
# ═══════════════════════════════════════════════════════

def get_market_data(ticker: str) -> dict:
    """
    Ambil data pasar terkini via multi-source.
    Priority: Yahoo Finance chart API → Yahoo Finance quoteSummary → IDX
    """
    if not ticker:
        return {}

    ticker_clean = ticker.replace(".JK", "").upper()
    ticker_yf    = ticker_clean + ".JK"

    # Coba Yahoo Finance
    result = _yahoo_chart(ticker_yf)
    if result.get("current_price"):
        # Tambahkan data detail
        detail = _yahoo_summary(ticker_yf)
        result.update(detail)
        return result

    # Fallback IDX
    idx_data = _idx_price(ticker_clean)
    if idx_data:
        return idx_data

    # Fallback Stooq
    stooq_data = _stooq_price(ticker_clean)
    if stooq_data:
        return stooq_data

    return {}


def _yahoo_chart(ticker_yf: str) -> dict:
    """Ambil harga dari Yahoo Finance chart API."""
    for attempt in range(3):
        try:
            url    = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}"
            params = {"interval": "1d", "range": "1d"}
            resp   = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data   = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                return {}

            meta     = result[0].get("meta", {})
            price    = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            currency = meta.get("currency", "IDR")

            if not price:
                return {}

            return {
                "current_price": _fmt_price(float(price), currency),
                "currency":      currency,
            }
        except requests.RequestException as e:
            if attempt < 2:
                time.sleep(2)
    return {}


def _yahoo_summary(ticker_yf: str) -> dict:
    """Ambil market cap & shares dari Yahoo Finance quoteSummary."""
    try:
        url    = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_yf}"
        params = {"modules": "summaryDetail,defaultKeyStatistics"}
        resp   = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        data   = resp.json()
        res    = data.get("quoteSummary", {}).get("result", [{}])[0]

        sd      = res.get("summaryDetail", {})
        ks      = res.get("defaultKeyStatistics", {})
        currency = sd.get("currency", "IDR")

        mkt_cap = (sd.get("marketCap", {}).get("raw") or
                  ks.get("marketCap", {}).get("raw"))
        shares  = ks.get("sharesOutstanding", {}).get("raw")

        result = {}
        if mkt_cap:
            result["market_cap"] = _fmt_mktcap(float(mkt_cap), currency)
        if shares:
            result["shares_outstanding"] = _fmt_shares(float(shares))
        return result
    except Exception as e:
        logger.warning(f"Yahoo summary error: {e}")
        return {}


def _idx_price(ticker: str) -> dict:
    """Ambil harga dari IDX API."""
    try:
        url  = f"https://idx.co.id/umum/GetStockSummary/?stockCode={ticker}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            data  = resp.json()
            price = (data.get("LastPrice") or data.get("lastPrice") or
                    data.get("Close") or data.get("close"))
            if price:
                return {"current_price": _fmt_price(float(price), "IDR")}
    except Exception as e:
        logger.warning(f"IDX price error: {e}")
    return {}


def _stooq_price(ticker: str) -> dict:
    """Ambil harga dari Stooq sebagai last resort."""
    try:
        url  = f"https://stooq.com/q/l/?s={ticker.lower()}.jk&f=sd2t2ohlcvn"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split(",")
                if len(parts) > 4:
                    price = parts[4]  # Close price
                    if price and price != "N/D":
                        return {"current_price": _fmt_price(float(price), "IDR")}
    except Exception as e:
        logger.warning(f"Stooq price error: {e}")
    return {}


# ═══════════════════════════════════════════════════════
# 3. FORMATTERS
# ═══════════════════════════════════════════════════════

def _fmt_price(price: float, currency: str) -> str:
    if currency == "IDR":
        return f"Rp {price:,.0f}".replace(",", ".")
    elif currency == "USD":
        return f"$ {price:,.2f}"
    return f"{currency} {price:,.2f}"


def _fmt_mktcap(value: float, currency: str) -> str:
    if currency == "IDR":
        if value >= 1_000_000_000_000:
            return f"Rp {value/1_000_000_000_000:.2f} T"
        elif value >= 1_000_000_000:
            return f"Rp {value/1_000_000_000:.2f} M"
        return f"Rp {value:,.0f}"
    else:
        if value >= 1_000_000_000:
            return f"${value/1_000_000_000:.2f}B"
        return f"${value/1_000_000:.2f}M"


def _fmt_shares(value: float) -> str:
    if value >= 1_000_000_000:
        return f"{value/1_000_000_000:.2f} miliar lembar"
    elif value >= 1_000_000:
        return f"{value/1_000_000:.0f} juta lembar"
    return f"{value:,.0f} lembar"


def get_underwriter_track_record(underwriters: list) -> str:
    return ""