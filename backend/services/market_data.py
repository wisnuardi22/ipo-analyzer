"""
services/market_data.py

Fungsi utama:
  - get_ticker_from_google(company_name)        → cari ticker via Google Search
  - get_market_data(ticker)                     → scrape harga live Google Finance
  - get_underwriter_track_record(underwriters)  → cari track record penjamin efek
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


# ── 1. Cari ticker via Google Search ─────────────────────────────────────────

def get_ticker_from_google(company_name: str) -> str | None:
    """
    Cari kode saham IDX via Google Search.
    Return: ticker 4 huruf kapital, e.g. "MGRO"
    Tidak pakai ticker_hint dari prospektus — langsung Google.
    """
    # Bersihkan nama: hapus "PT", "Tbk", dll untuk query lebih bersih
    clean_name = re.sub(r'\b(PT|Tbk|tbk)\b', '', company_name, flags=re.IGNORECASE).strip()

    queries = [
        f"{clean_name} kode saham IDX BEI",
        f"{clean_name} stock ticker IDX",
        f"site:idx.co.id {clean_name}",
    ]

    for query in queries:
        url = f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=id"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            full_text = soup.get_text(separator=" ")

            patterns = [
                r"IDX\s*[:\-]\s*([A-Z]{4})\b",
                r"BEI\s*[:\-]\s*([A-Z]{4})\b",
                r"kode\s+saham\s*[:\-]?\s*([A-Z]{4})\b",
                r"ticker\s*[:\-]?\s*([A-Z]{4})\b",
                r"\b([A-Z]{4})\.JK\b",
                r"saham\s+([A-Z]{4})\b",
            ]
            for pattern in patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    found = match.group(1).upper()
                    # Verifikasi ticker valid di Google Finance
                    if _verify_ticker(found):
                        logger.info(f"Ticker ditemukan: {found} untuk {company_name}")
                        return found
        except requests.RequestException as e:
            logger.warning(f"Error Google Search ticker: {e}")
            continue
        time.sleep(1)

    logger.warning(f"Ticker tidak ditemukan untuk: {company_name}")
    return None


def _verify_ticker(ticker: str) -> bool:
    """Verifikasi ticker valid di Google Finance IDX."""
    url = f"https://www.google.com/finance/quote/{ticker}:IDX"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        return resp.status_code == 200 and (
            "data-last-price" in resp.text or
            ticker in resp.text
        )
    except Exception:
        return False


# ── 2. Scrape harga live dari Google Finance ──────────────────────────────────

def get_market_data(ticker: str) -> dict:
    """
    Scrape data pasar terkini dari Google Finance IDX.
    Return dict dengan current_price, market_cap, dll.
    """
    if not ticker:
        return {}

    url = f"https://www.google.com/finance/quote/{ticker.upper()}:IDX"

    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            return _parse_price_page(resp.text)
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt+1} gagal ({ticker}): {e}")
            if attempt < 2:
                time.sleep(2)

    logger.error(f"Semua attempt gagal: {ticker}")
    return {}


def _parse_price_page(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # ── Harga ──
    price = ""
    price_tag = soup.find(attrs={"data-last-price": True})
    if price_tag:
        try:
            num = float(price_tag["data-last-price"])
            price = f"Rp {num:,.0f}".replace(",", ".")
        except Exception:
            price = price_tag["data-last-price"]

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

    # Fallback
    if not stats:
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                val = cells[1].get_text(strip=True)
                if key:
                    stats[key] = val

    return {
        "current_price":      price,
        "market_cap":         _find_stat(stats, ["market cap", "kapitalisasi", "mkt cap"]),
        "shares_outstanding": _find_stat(stats, ["shares outstanding", "saham beredar"]),
        "pe_ratio":           _find_stat(stats, ["p/e ratio", "rasio p/e"]),
        "52w_high":           _find_stat(stats, ["52-week high", "tertinggi 52"]),
        "52w_low":            _find_stat(stats, ["52-week low", "terendah 52"]),
    }


# ── 3. Cari track record penjamin efek ───────────────────────────────────────

def get_underwriter_track_record(underwriters: list[str]) -> list[dict]:
    """
    Cari track record penjamin emisi efek via Google Search.

    Input: list nama penjamin, e.g. ["PT BRI Danareksa Sekuritas", "PT Mirae Asset"]
    Output: list dict berisi nama, reputasi, jumlah IPO, rating
    """
    results = []

    for uw in underwriters[:3]:  # Maksimal 3 penjamin untuk hemat quota
        clean = re.sub(r'\b(PT|Tbk)\b', '', uw, flags=re.IGNORECASE).strip()
        query = f"{clean} sekuritas track record IPO BEI reputasi"
        url   = f"https://www.google.com/search?q={requests.utils.quote(query)}&hl=id"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            snippet = " ".join(soup.get_text(separator=" ").split()[:500])

            # Cari jumlah IPO yang pernah dijamin
            ipo_count = None
            match = re.search(r'(\d+)\s*(?:IPO|emiten|perusahaan)', snippet, re.IGNORECASE)
            if match:
                ipo_count = int(match.group(1))

            # Tentukan reputasi berdasarkan nama
            reputation = _assess_underwriter_reputation(clean)

            results.append({
                "name":       uw,
                "reputation": reputation["level"],
                "desc":       reputation["desc"],
                "ipo_count":  ipo_count,
                "snippet":    snippet[:300],
            })

        except requests.RequestException as e:
            logger.warning(f"Error cari track record {uw}: {e}")
            results.append({
                "name":       uw,
                "reputation": "Medium",
                "desc":       "Data track record tidak tersedia",
                "ipo_count":  None,
                "snippet":    "",
            })
        time.sleep(1)

    return results


def _assess_underwriter_reputation(name: str) -> dict:
    """
    Nilai reputasi penjamin berdasarkan nama perusahaan.
    Tier 1: Sekuritas besar milik BUMN atau bank besar
    Tier 2: Sekuritas menengah
    Tier 3: Sekuritas kecil/baru
    """
    name_upper = name.upper()

    tier1 = [
        "MANDIRI", "BRI", "BCA", "BNI", "DANAREKSA",
        "CIMB", "TRIMEGAH", "MIRAE", "INDO PREMIER",
        "BAHANA", "SUCOR", "SAMUEL"
    ]
    tier2 = [
        "SINARMAS", "PANIN", "MANULIFE", "HENAN",
        "ERDIKHA", "MNC", "PHINTRACO", "VICTORIA"
    ]

    for t in tier1:
        if t in name_upper:
            return {
                "level": "Tinggi",
                "desc": f"Sekuritas Tier 1 dengan reputasi kuat dan berpengalaman dalam puluhan IPO besar di BEI"
            }
    for t in tier2:
        if t in name_upper:
            return {
                "level": "Menengah",
                "desc": f"Sekuritas menengah dengan pengalaman cukup dalam proses IPO di BEI"
            }

    return {
        "level": "Perlu Diverifikasi",
        "desc": "Sekuritas belum banyak dikenal — investor perlu verifikasi track record lebih lanjut"
    }


# ── Helper ────────────────────────────────────────────────────────────────────

def _find_stat(stats: dict, keys: list) -> str:
    for key in keys:
        for k, v in stats.items():
            if key in k:
                return v
    return ""