"""
services/market_data.py

Dua fungsi utama:
  - get_ticker_from_google(company_name, ticker_hint)
      → verifikasi / cari ticker saham via Google Search
  - get_market_data(ticker)
      → scrape data live dari Google Finance
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
}
TIMEOUT = 10


# ── 1. Cari / verifikasi ticker via Google Search ─────────────────────────────

def get_ticker_from_google(company_name: str, ticker_hint: str = "") -> str | None:
    """
    Cari kode saham via Google Search.

    Strategi:
    1. Jika ticker_hint tersedia, coba verifikasi langsung ke Google Finance
    2. Jika tidak valid, lakukan Google Search untuk cari ticker yang benar
    3. Return ticker dalam format 4 huruf IDX, e.g. "SUPA"
    """
    # ── Coba verifikasi ticker_hint dulu ──
    if ticker_hint and re.match(r"^[A-Z]{2,6}$", ticker_hint.strip().upper()):
        candidate = ticker_hint.strip().upper()
        if _verify_ticker_on_google_finance(candidate + ".JK"):
            logger.info(f"Ticker hint terverifikasi: {candidate}")
            return candidate  # Return tanpa .JK untuk display

    # ── Fallback: Google Search ──
    query = f"{company_name} kode saham IDX BEI"
    url   = f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=id"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        full_text = soup.get_text(separator=" ")

        patterns = [
            r"IDX\s*[:\-]\s*([A-Z]{2,6})",
            r"BEI\s*[:\-]\s*([A-Z]{2,6})",
            r"kode\s+saham\s*[:\-]?\s*([A-Z]{2,6})",
            r"ticker\s*[:\-]?\s*([A-Z]{2,6})",
            r"\b([A-Z]{2,6})\.JK\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                found = match.group(1).upper()
                # Hapus .JK jika ada
                ticker = found.replace(".JK", "")
                logger.info(f"Ticker ditemukan via Google Search: {ticker}")
                return ticker

        logger.warning(f"Ticker tidak ditemukan untuk: {company_name}")
        return None

    except requests.RequestException as e:
        logger.error(f"Error cari ticker '{company_name}': {e}")
        return None


def _verify_ticker_on_google_finance(ticker: str) -> bool:
    """Cek apakah ticker valid dengan hit Google Finance."""
    exchange, symbol = _parse_ticker(ticker)
    url = f"https://www.google.com/finance/quote/{symbol}:{exchange}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        return resp.status_code == 200 and "data-last-price" in resp.text
    except Exception:
        return False


# ── 2. Scrape data live dari Google Finance ───────────────────────────────────

def get_market_data(ticker: str) -> dict:
    """
    Scrape data pasar terkini dari Google Finance.

    Return:
    {
      "current_price":      "Rp 860",
      "market_cap":         "Rp 29,07 T",
      "shares_outstanding": "33,89 M",
      "currency":           "IDR",
      "exchange":           "IDX",
    }
    Jika gagal, return dict kosong {}.
    """
    # Pastikan format ticker untuk Google Finance: tambah .JK jika belum ada
    if not ticker.endswith(".JK") and "." not in ticker:
        ticker_gf = ticker + ".JK"
    else:
        ticker_gf = ticker

    exchange, symbol = _parse_ticker(ticker_gf)
    url = f"https://www.google.com/finance/quote/{symbol}:{exchange}"

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return _parse_page(resp.text, exchange)
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt+1} gagal ({ticker}): {e}")
            if attempt < 2:
                time.sleep(2)

    logger.error(f"Semua attempt gagal: {ticker}")
    return {}


def _parse_page(html: str, exchange: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # ── Harga ──
    price = ""
    price_tag = soup.find(attrs={"data-last-price": True})
    if price_tag:
        price = price_tag["data-last-price"]

    # ── Currency ──
    currency_tag = soup.find(attrs={"data-currency-code": True})
    currency = currency_tag["data-currency-code"] if currency_tag else _exchange_to_currency(exchange)

    # ── Key stats ──
    stats = {}
    for row in soup.find_all("div", class_=re.compile(r"gyFHrc")):
        try:
            label_el = row.find("div", class_=re.compile(r"mfs7Fc"))
            value_el = row.find("div", class_=re.compile(r"P6K39c"))
            if label_el and value_el:
                stats[label_el.get_text(strip=True).lower()] = value_el.get_text(strip=True)
        except Exception:
            continue

    # Fallback scrape
    if not stats:
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                if key:
                    stats[key] = val

    symbol_map = {"IDR": "Rp", "USD": "$", "SGD": "S$", "MYR": "RM"}
    sym = symbol_map.get(currency, currency)

    def fmt_price(val: str) -> str:
        if not val:
            return ""
        try:
            # Format harga dengan titik ribuan untuk IDR
            if currency == "IDR":
                num = float(val)
                return f"Rp {num:,.0f}".replace(",", ".")
            return f"{sym} {val}"
        except Exception:
            return f"{sym} {val}"

    mkt_cap = _find_stat(stats, ["market cap", "kapitalisasi", "mkt cap"])
    shares  = _find_stat(stats, ["shares outstanding", "saham beredar"])

    return {
        "current_price":      fmt_price(price),
        "currency":           currency,
        "exchange":           exchange,
        "market_cap":         mkt_cap,
        "shares_outstanding": shares,
    }


def _find_stat(stats: dict, keys: list) -> str:
    for key in keys:
        for k, v in stats.items():
            if key in k:
                return v
    return ""


def _parse_ticker(ticker: str) -> tuple[str, str]:
    """
    "SUPA.JK" → ("IDX", "SUPA")
    "AAPL"    → ("NASDAQ", "AAPL")
    """
    suffix_map = {
        "JK": "IDX", "BK": "SET", "KL": "KLSE",
        "SI": "SGX", "HK": "HKEX", "T": "TYO",
    }
    if "." in ticker:
        symbol, suffix = ticker.rsplit(".", 1)
        exchange = suffix_map.get(suffix.upper(), suffix.upper())
    else:
        symbol   = ticker.upper()
        exchange = "NASDAQ"
    return exchange, symbol.upper()


def _exchange_to_currency(exchange: str) -> str:
    return {
        "IDX": "IDR", "NASDAQ": "USD", "NYSE": "USD",
        "SET": "THB", "KLSE": "MYR", "SGX": "SGD",
    }.get(exchange.upper(), "USD")