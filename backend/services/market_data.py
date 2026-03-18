"""
services/market_data.py
Cari ticker & harga live via Yahoo Finance (lebih reliable dari scraping Google)
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


# ── 1. Cari ticker via Yahoo Finance Search ───────────────────────────────────

def get_ticker_from_google(company_name: str, ticker_hint: str = "") -> str:
    """
    Cari ticker saham IDX via Yahoo Finance Search API.
    Return ticker 4 huruf tanpa .JK (contoh: "MGRO")
    """
    # ── Coba ticker_hint dulu via Yahoo Finance ──
    if ticker_hint and re.match(r"^[A-Z]{2,6}$", ticker_hint.strip().upper()):
        candidate = ticker_hint.strip().upper()
        if _verify_ticker_yahoo(candidate + ".JK"):
            logger.info(f"Ticker hint terverifikasi: {candidate}")
            return candidate

    # ── Search via Yahoo Finance ──
    try:
        # Bersihkan nama perusahaan untuk search
        clean_name = company_name.replace("PT ", "").replace(" Tbk", "").strip()
        url = f"https://query2.finance.yahoo.com/v1/finance/search"
        params = {
            "q": clean_name,
            "lang": "id",
            "region": "ID",
            "quotesCount": 5,
            "newsCount": 0,
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        quotes = data.get("quotes", [])
        for q in quotes:
            symbol = q.get("symbol", "")
            exchange = q.get("exchange", "")
            # Cari yang di IDX (Jakarta Stock Exchange)
            if symbol.endswith(".JK") or exchange in ["JKT", "IDX", "Jakarta"]:
                ticker = symbol.replace(".JK", "").upper()
                logger.info(f"Ticker ditemukan via Yahoo: {ticker}")
                return ticker

        # Fallback: coba dengan nama lengkap
        if ticker_hint:
            logger.info(f"Fallback ke ticker dari prospektus: {ticker_hint}")
            return ticker_hint.upper()

        logger.warning(f"Ticker tidak ditemukan untuk: {company_name}")
        return ticker_hint or ""

    except Exception as e:
        logger.error(f"Error cari ticker '{company_name}': {e}")
        return ticker_hint or ""


def _verify_ticker_yahoo(ticker_jk: str) -> bool:
    """Verifikasi ticker di Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_jk}"
        params = {"interval": "1d", "range": "1d"}
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        result = data.get("chart", {}).get("result")
        return bool(result)
    except Exception:
        return False


# ── 2. Ambil harga live via Yahoo Finance ─────────────────────────────────────

def get_market_data(ticker: str) -> dict:
    """
    Ambil data harga live dari Yahoo Finance.
    Return: {current_price, market_cap, shares_outstanding, currency}
    """
    if not ticker:
        return {}

    # Format ticker untuk Yahoo Finance
    ticker_clean = ticker.replace(".JK", "").upper()
    ticker_yf = ticker_clean + ".JK"

    for attempt in range(3):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_yf}"
            params = {
                "interval": "1d",
                "range":    "1d",
                "includePrePost": False,
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            result = data.get("chart", {}).get("result", [])
            if not result:
                logger.warning(f"Tidak ada data untuk {ticker_yf}")
                return {}

            meta = result[0].get("meta", {})

            # Harga
            price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
            currency = meta.get("currency", "IDR")

            # Format harga
            price_str = _format_price(price, currency)

            # Market cap & shares dari summary detail
            market_cap_str = ""
            shares_str = ""

            try:
                url2 = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker_yf}"
                params2 = {"modules": "summaryDetail,defaultKeyStatistics"}
                resp2 = requests.get(url2, params=params2, headers=HEADERS, timeout=TIMEOUT)
                data2 = resp2.json()
                summary = data2.get("quoteSummary", {}).get("result", [{}])[0]

                sd = summary.get("summaryDetail", {})
                ks = summary.get("defaultKeyStatistics", {})

                mkt_cap = sd.get("marketCap", {}).get("raw") or ks.get("marketCap", {}).get("raw")
                shares  = ks.get("sharesOutstanding", {}).get("raw")

                if mkt_cap:
                    market_cap_str = _format_market_cap(mkt_cap, currency)
                if shares:
                    shares_str = _format_shares(shares)

            except Exception as e:
                logger.warning(f"Gagal ambil summary detail: {e}")

            return {
                "current_price":      price_str,
                "market_cap":         market_cap_str,
                "shares_outstanding": shares_str,
                "currency":           currency,
            }

        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt+1} gagal ({ticker_yf}): {e}")
            if attempt < 2:
                time.sleep(2)

    logger.error(f"Semua attempt gagal: {ticker}")
    return {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_price(price, currency: str) -> str:
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


def _format_market_cap(value, currency: str) -> str:
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


def _format_shares(value) -> str:
    if not value:
        return ""
    try:
        num = float(value)
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.2f} M lembar"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.2f} juta lembar"
        else:
            return f"{num:,.0f} lembar"
    except Exception:
        return str(value)


def get_underwriter_track_record(underwriters: list) -> str:
    """Placeholder - track record sudah dianalisis oleh Gemini langsung."""
    return ""