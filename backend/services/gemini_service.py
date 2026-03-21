"""
services/gemini_service.py
--------------------------
Analisis prospektus IPO Indonesia secara komprehensif.
Pipeline:
  1. Detect metadata dokumen (currency, unit, fx rate)
  2. LLM multi-chunk — ekstrak data keuangan mentah
  3. Python — normalisasi + hitung semua KPI
  4. LLM — analisis kualitatif (summary, risiko, benefit, use of funds)
  5. Fallback ticker search jika tidak ada di dokumen

Output mendukung lang="ID" (Bahasa Indonesia) dan lang="EN" (English).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.environ.get("SUMOPOD_API_KEY"),
    base_url="https://ai.sumopod.com/v1",
)
MODEL = "gemini/gemini-2.5-flash"


# ══════════════════════════════════════════════════════════════════════
# 1. NUMBER UTILITIES
# ══════════════════════════════════════════════════════════════════════

def parse_num(raw: Any) -> Optional[float]:
    """Parse angka format Indonesia/Inggris, termasuk (xxx) = negatif."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s.lower() in ("null", "n/a", "-", ""):
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    elif s.startswith("-"):
        neg, s = True, s[1:]
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts) == 2 and len(parts[1]) <= 2 else s.replace(",", "")
    elif "." in s:
        parts = s.split(".")
        if not (len(parts) == 2 and len(parts[1]) <= 2):
            s = s.replace(".", "")
    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return None


def apply_unit(val: Any, unit: str) -> Optional[float]:
    v = parse_num(val)
    if v is None:
        return None
    return v * {"jutaan": 1_000_000, "ribuan": 1_000,
                "miliar": 1_000_000_000, "triliun": 1_000_000_000_000}.get(unit.lower(), 1)


def safe_div(a: Any, b: Any) -> Optional[float]:
    try:
        af, bf = parse_num(a), parse_num(b)
        return af / bf if af is not None and bf else None
    except Exception:
        return None


def to_pct(val: Any) -> Optional[float]:
    v = parse_num(val)
    return round(v * 100, 2) if v is not None and not math.isnan(v) else None


def calc_growth(cur: Any, prev: Any) -> Optional[float]:
    c, p = parse_num(cur), parse_num(prev)
    if c is None or p is None or p == 0:
        return None
    return round((c - p) / abs(p) * 100, 2)


def fmt_idr(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"Rp {value/1_000_000_000_000:.2f} Triliun"
    if value >= 1_000_000_000:
        return f"Rp {value/1_000_000_000:.2f} Miliar"
    return f"Rp {value:,.0f}".replace(",", ".")


# ══════════════════════════════════════════════════════════════════════
# 2. DOCUMENT METADATA DETECTION
# ══════════════════════════════════════════════════════════════════════

def detect_currency(text: str) -> str:
    t = text[:5000].lower()
    return "USD" if ("us$" in t or " usd" in t or "dolar amerika" in t) else "IDR"


def detect_unit(text: str) -> str:
    t = text[:10000].lower()
    if re.search(r"dalam\s+jutaan", t):
        return "jutaan"
    if re.search(r"dalam\s+ribuan", t):
        return "ribuan"
    if re.search(r"dalam\s+miliar", t):
        return "miliar"
    return "full"


def detect_fx_rate(text: str) -> Optional[float]:
    for pat in [
        r"kurs.*?rp\s*([\d.,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)",
        r"rp\s*([\d.,]+)\s*/\s*us\$",
        r"exchange\s+rate.*?rp\s*([\d.,]+)",
    ]:
        m = re.search(pat, text[:20000], re.I)
        if m:
            v = parse_num(m.group(1))
            if v and v > 1000:
                return float(v)
    return None


# ══════════════════════════════════════════════════════════════════════
# 3. LLM FINANCIAL EXTRACTION (MULTI-CHUNK)
# ══════════════════════════════════════════════════════════════════════

def _chunk_text(text: str, max_len: int = 18000, overlap: int = 800) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i: i + max_len])
        i += max_len - overlap
    return chunks


def _safe_json(raw: str) -> Optional[dict]:
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                raw = part
                break
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e <= s:
        return None
    snippet = raw[s: e + 1]
    for attempt in [snippet, re.sub(r",\s*([}\]])", r"\1", snippet)]:
        try:
            return json.loads(attempt)
        except Exception:
            pass
    return None


_FIN_KEYWORDS = [
    "laporan laba rugi", "ikhtisar data keuangan", "data keuangan penting",
    "ringkasan keuangan", "informasi keuangan", "laba kotor", "laba usaha",
    "laba bersih", "pendapatan usaha", "pendapatan bersih", "penjualan bersih",
    "posisi keuangan", "neraca", "ekuitas", "liabilitas",
    "gross profit", "net revenue", "operating profit", "net income",
    "profit or loss", "statement of profit", "balance sheet",
    "selected financial", "financial highlights",
]

_FIN_SYSTEM = """Kamu adalah akuntan senior Indonesia. Ekstrak data keuangan dari potongan prospektus IPO.
Output HANYA JSON murni — tanpa teks lain, tanpa markdown.

INSTRUKSI EKSTRAKSI:
1. Cari tabel laporan keuangan dengan judul seperti:
   "LAPORAN LABA RUGI", "DATA KEUANGAN PENTING", "IKHTISAR DATA KEUANGAN",
   "SELECTED FINANCIAL DATA", "CONSOLIDATED STATEMENTS OF PROFIT OR LOSS",
   "RINGKASAN KEUANGAN", "INFORMASI KEUANGAN RINGKAS"

2. Baca header kolom tabel — itulah tahun-tahun tersedia (contoh: 2021, 2022, 2023, 2024).
   Masukkan SEMUA tahun ke "tahun_tersedia" dan buat entry per tahun di "data_per_tahun".

3. Untuk setiap tahun, ekstrak:
   - pendapatan   : Total Pendapatan / Revenue / Penjualan Bersih / Net Revenue
   - laba_kotor   : Laba Kotor / Gross Profit
   - laba_usaha   : Laba / Rugi Usaha / Operating Profit/Loss (bisa negatif)
   - laba_bersih  : Laba / Rugi Bersih / Net Profit/Loss (bisa negatif)
   - depresiasi   : Depresiasi & Amortisasi (null jika tidak ada)

4. Catat satuan dari header tabel:
   "dalam jutaan Rupiah" → satuan="jutaan"
   "dalam ribuan" → satuan="ribuan"
   "dalam miliar" → satuan="miliar"
   Tidak ada keterangan → satuan="full"

5. Tulis angka PERSIS seperti di dokumen — JANGAN konversi satuan.
   Angka negatif dalam kurung (1.234) → tulis -1234.

6. Dari neraca/posisi keuangan, ambil tahun TERAKHIR:
   - total_ekuitas, total_liabilitas, total_aset

7. Cari:
   - total_saham_beredar: jumlah saham beredar SETELAH IPO
   - harga_penawaran: harga per saham (angka saja, tanpa "Rp")

8. Jika potongan ini tidak ada data keuangan → isi null/[]

OUTPUT JSON WAJIB PERSIS FORMAT INI:
{
  "satuan": "jutaan",
  "mata_uang": "IDR",
  "tahun_tersedia": ["2022","2023","2024"],
  "data_per_tahun": [
    {"tahun":"2022","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null},
    {"tahun":"2023","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null},
    {"tahun":"2024","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}
  ],
  "total_ekuitas": null,
  "total_liabilitas": null,
  "total_aset": null,
  "total_saham_beredar": null,
  "harga_penawaran": null
}"""


def llm_extract_financials(text: str) -> Dict[str, Any]:
    """Multi-chunk LLM extraction untuk data keuangan."""
    merged: Dict[str, Any] = {
        "satuan": None, "mata_uang": None,
        "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas": None, "total_liabilitas": None, "total_aset": None,
        "total_saham_beredar": None, "harga_penawaran": None,
    }

    all_chunks = _chunk_text(text, max_len=18000, overlap=800)

    # Pilih chunk prioritas berdasarkan keywords keuangan
    priority, others = [], []
    for c in all_chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman") > 5:
            continue
        if any(k in cl for k in _FIN_KEYWORDS):
            priority.append(c)
        else:
            others.append(c)

    # Sertakan chunk tengah dokumen (sering berisi tabel keuangan)
    mid = len(others) // 2
    selected = list(priority[:8])
    for c in others[max(0, mid - 1): mid + 2]:
        if c not in selected:
            selected.append(c)
    # Selalu sertakan chunk pertama & terakhir
    if all_chunks and all_chunks[0] not in selected:
        selected.insert(0, all_chunks[0])
    if len(all_chunks) > 1 and all_chunks[-1] not in selected:
        selected.append(all_chunks[-1])

    selected = selected[:10]

    for chunk in selected:
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.01, max_tokens=4000,
                messages=[
                    {"role": "system", "content": _FIN_SYSTEM},
                    {"role": "user", "content": f"DOKUMEN:\n{chunk}"},
                ],
            )
            part = _safe_json(resp.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"LLM financial chunk error: {e}")
            part = {}

        # Merge metadata
        for k in ("satuan", "mata_uang"):
            if not merged[k] and part.get(k):
                merged[k] = part[k]

        # Merge tahun
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(
                set(merged["tahun_tersedia"]) | set(str(y) for y in part["tahun_tersedia"])
            )

        # Merge data per tahun
        if part.get("data_per_tahun"):
            m_dict = {str(d.get("tahun", "")).strip(): d for d in merged["data_per_tahun"]}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun", "")).strip()
                if not y:
                    continue
                if y in m_dict:
                    for k in ("pendapatan", "laba_kotor", "laba_usaha", "laba_bersih", "depresiasi"):
                        v = d.get(k)
                        if m_dict[y].get(k) is None and v is not None and str(v).strip() not in ("null", ""):
                            m_dict[y][k] = v
                else:
                    m_dict[y] = d
            merged["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]

        # Merge scalar fields
        for k in ("total_ekuitas", "total_liabilitas", "total_aset",
                  "total_saham_beredar", "harga_penawaran"):
            v = part.get(k)
            if merged.get(k) is None and v is not None and str(v).strip() not in ("null", ""):
                merged[k] = v

    return merged


# ══════════════════════════════════════════════════════════════════════
# 4. NORMALIZE + COMPUTE ALL KPIs
# ══════════════════════════════════════════════════════════════════════

def normalize_and_compute(fin_raw: Dict, fx_rate: Optional[float]) -> Tuple[Dict, Dict]:
    unit     = (fin_raw.get("satuan") or "full").lower()
    currency = (fin_raw.get("mata_uang") or "IDR").upper()

    years_data = []
    for d in fin_raw.get("data_per_tahun", []):
        nd = dict(d)
        for k in ("pendapatan", "laba_kotor", "laba_usaha", "laba_bersih", "depresiasi"):
            nd[k] = apply_unit(nd.get(k), unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data.sort(key=lambda x: str(x.get("tahun", "")))

    ekuitas    = apply_unit(fin_raw.get("total_ekuitas"), unit)
    liabilitas = apply_unit(fin_raw.get("total_liabilitas"), unit)
    saham      = parse_num(fin_raw.get("total_saham_beredar"))
    harga      = parse_num(fin_raw.get("harga_penawaran"))
    harga_idr  = harga * fx_rate if (harga and currency == "USD" and fx_rate) else harga

    # Chart series
    revenue_growth, gross_margin, op_margin, ebitda_margin, net_margin = [], [], [], [], []
    prev_rev = None
    for yr in years_data:
        y   = str(yr.get("tahun", ""))
        rev = yr.get("pendapatan")
        gp  = yr.get("laba_kotor")
        op  = yr.get("laba_usaha")
        net = yr.get("laba_bersih")
        dep = yr.get("depresiasi")

        revenue_growth.append({"year": y, "value": 0.0 if prev_rev is None else calc_growth(rev, prev_rev)})
        prev_rev = rev
        gross_margin.append({"year": y, "value": to_pct(safe_div(gp, rev))})
        op_margin.append({"year": y, "value": to_pct(safe_div(op, rev))})
        ebitda_margin.append({
            "year": y,
            "value": to_pct(safe_div(float(op) + float(dep), rev))
            if (dep is not None and op is not None and rev) else None
        })
        net_margin.append({"year": y, "value": to_pct(safe_div(net, rev))})

    # KPI
    kpi = {"pe": "N/A", "pb": "N/A", "roe": "N/A", "der": "N/A", "eps": "N/A", "market_cap": "N/A"}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    try:
        if saham and laba_last and saham > 0:
            eps_val = laba_last / saham
            kpi["eps"] = f"Rp {eps_val:,.2f}".replace(",", ".") if currency == "IDR" else f"{currency} {eps_val:.4f}"
            if harga_idr and eps_val > 0:
                kpi["pe"] = f"{harga_idr / eps_val:.1f}x"
            elif harga_idr and eps_val < 0:
                kpi["pe"] = "N/A (Rugi)"
    except Exception:
        pass

    try:
        if ekuitas and saham and saham > 0 and harga_idr and ekuitas > 0:
            bvps = ekuitas / saham
            if bvps > 0:
                kpi["pb"] = f"{harga_idr / bvps:.2f}x"
    except Exception:
        pass

    try:
        if ekuitas and laba_last and ekuitas > 0:
            kpi["roe"] = f"{laba_last / ekuitas * 100:.1f}%"
    except Exception:
        pass

    try:
        if ekuitas and liabilitas and ekuitas > 0:
            kpi["der"] = f"{liabilitas / ekuitas:.2f}x"
    except Exception:
        pass

    try:
        if saham and harga and saham > 0 and harga > 0:
            mc = saham * (harga_idr if harga_idr else harga)
            kpi["market_cap"] = fmt_idr(mc)
    except Exception:
        pass

    financial = {
        "currency":          currency,
        "years":             [str(d.get("tahun", "")) for d in years_data],
        "absolute_data":     years_data,
        "revenue_growth":    revenue_growth or None,
        "gross_margin":      gross_margin or None,
        "operating_margin":  op_margin or None,
        "ebitda_margin":     ebitda_margin or None,
        "net_profit_margin": net_margin or None,
    }
    return financial, kpi


# ══════════════════════════════════════════════════════════════════════
# 5. LLM QUALITATIVE ANALYSIS
# ══════════════════════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str = "ID") -> Dict:
    is_en    = lang.upper() == "EN"
    currency = financial.get("currency", "IDR")
    years    = financial.get("years", [])

    lang_rule = (
        "OUTPUT LANGUAGE: Write ALL text fields in ENGLISH. "
        "company_name stays as original from document."
    ) if is_en else (
        "BAHASA OUTPUT: Tulis SEMUA field teks dalam Bahasa Indonesia. "
        "company_name tetap asli dari dokumen."
    )

    prompt = f"""Kamu adalah analis IPO senior Indonesia. Analisis prospektus IPO berikut secara mendalam dan akurat.

{lang_rule}
Gunakan mata uang {currency} untuk semua nilai uang.

DATA KPI SUDAH DIHITUNG SISTEM — SALIN PERSIS, JANGAN HITUNG ULANG:
{json.dumps(kpi, ensure_ascii=False)}
Tahun data keuangan tersedia: {years}

════ INSTRUKSI ANALISIS ════

A. IDENTITAS PERUSAHAAN
   company_name : nama lengkap perusahaan termasuk "Tbk"
   ticker       : kode saham IDX. Cari di dokumen dengan pola PERSIS:
                  "Kode Saham:", "Kode Efek:", "Stock Code:", "kode saham adalah",
                  "akan dicatatkan dengan kode", "kode perdagangan"
                  → Jika ada di dokumen, WAJIB diisi. Jika tidak ada → kosongkan ""
   sector       : sektor bisnis spesifik (misal: "Pertambangan Emas", "Perbankan", "Teknologi")
   ipo_date     : tanggal PENCATATAN di BEI (bukan tanggal penawaran)
   share_price  : harga penawaran final
   total_shares : total saham beredar setelah IPO
   market_cap   : SALIN PERSIS dari DATA KPI di atas

B. RINGKASAN (summary) — 3 paragraf spesifik {'in English' if is_en else 'Bahasa Indonesia'}:
   Paragraf 1: Profil perusahaan, bisnis utama, skala operasi, lokasi, jumlah karyawan/aset
   Paragraf 2: Detail IPO — jumlah saham ditawarkan, persentase dari modal, harga, total dana IPO
   Paragraf 3: Kondisi keuangan terkini, pertumbuhan revenue, profitabilitas, prospek ke depan
   Pisahkan paragraf dengan \\n\\n

C. PENGGUNAAN DANA (use_of_funds)
   Cari bagian: "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum" / "Use of Proceeds"
   - Ekstrak SEMUA item alokasi (2-6 item sesuai dokumen)
   - allocation: angka persentase PERSIS dari dokumen. Total HARUS = 100.
   - DILARANG mengarang persentase. Jika tidak ada % eksplisit, hitung dari nominal.
   - DILARANG membuat allocation semua 0 jika ada data di dokumen
   - description: spesifik dengan nama proyek, lokasi, nilai nominal

D. PENJAMIN EMISI (underwriter)
   lead       : nama penjamin pelaksana emisi efek utama
   others     : array nama penjamin lain (bisa kosong [])
   type       : "Full Commitment" atau "Best Efforts"
   reputation : analisis singkat track record penjamin 2-3 kalimat {'in English' if is_en else 'Bahasa Indonesia'}

E. ANALISIS RISIKO
   overall_risk_level  : "High", "Medium", atau "Low" berdasarkan kondisi nyata perusahaan
   overall_risk_reason : 2-3 kalimat alasan utama
   risks               : 4-5 risiko SPESIFIK dari bab Faktor Risiko di dokumen
     - level: "High", "Medium", atau "Low"
     - title: judul singkat risiko
     - desc: penjelasan 1-2 kalimat dengan angka/fakta konkret

F. KEUNGGULAN INVESTASI (benefits)
   4-6 keunggulan kompetitif SPESIFIK dari dokumen, dengan data/angka konkret
   - title: judul singkat
   - desc: penjelasan 1-2 kalimat dengan fakta konkret

ATURAN PENTING:
- Output HANYA JSON murni, TANPA markdown, TANPA teks lain
- Semua string field wajib diisi (gunakan "" jika tidak ada, BUKAN null)
- risks[].level dan overall_risk_level HARUS salah satu dari: "High", "Medium", "Low"
- use_of_funds[].allocation adalah NUMBER (angka), BUKAN string

DOKUMEN PROSPEKTUS:
{text[:380000]}

OUTPUT JSON:
{{
  "company_name": "PT ... Tbk",
  "ticker": "",
  "sector": "...",
  "ipo_date": "...",
  "share_price": "...",
  "total_shares": "...",
  "market_cap": "...",
  "summary": "...",
  "use_of_funds": [
    {{"category": "...", "description": "...", "allocation": 60}},
    {{"category": "...", "description": "...", "allocation": 40}}
  ],
  "underwriter": {{
    "lead": "...",
    "others": [],
    "type": "Full Commitment",
    "reputation": "..."
  }},
  "overall_risk_level": "Medium",
  "overall_risk_reason": "...",
  "risks": [
    {{"level": "High", "title": "...", "desc": "..."}},
    {{"level": "Medium", "title": "...", "desc": "..."}}
  ],
  "benefits": [
    {{"title": "...", "desc": "..."}},
    {{"title": "...", "desc": "..."}}
  ]
}}"""

    resp = client.chat.completions.create(
        model=MODEL, temperature=0.1, max_tokens=12000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw    = resp.choices[0].message.content.strip()
    result = _safe_json(raw)
    if result:
        return result

    # JSON repair
    fixed = re.sub(r",\s*([}\]])", r"\1", raw)
    s, e  = fixed.find("{"), fixed.rfind("}") + 1
    if s != -1 and e > s:
        for end in range(e, s, -100):
            try:
                return json.loads(fixed[s:end])
            except Exception:
                pass

    raise ValueError(f"LLM qualitative parse failed: {raw[:300]}")


# ══════════════════════════════════════════════════════════════════════
# 6. TICKER SEARCH FALLBACK (jika tidak ada di dokumen)
# ══════════════════════════════════════════════════════════════════════

def search_ticker_by_name(company_name: str) -> str:
    """
    Cari ticker IDX menggunakan nama perusahaan lengkap.
    Dipakai sebagai fallback jika ticker tidak ditemukan di dokumen.
    Priority: Yahoo Finance → IDX API → Stooq
    """
    import requests

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    TIMEOUT = 10
    EXCLUDE = {
        "PT", "TBK", "IDX", "BEI", "OJK", "IDR", "USD", "IPO",
        "ROE", "ROA", "DER", "EPS", "CEO", "CFO", "GDP", "EBITDA",
    }

    def clean(name: str) -> str:
        name = re.sub(r"\bPT\.?\s*", "", name, flags=re.I)
        name = re.sub(r"\bTbk\.?\b", "", name, flags=re.I)
        return re.sub(r"\s+", " ", name).strip()

    cleaned = clean(company_name)
    if not cleaned:
        return ""

    # 1. Yahoo Finance Search
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": cleaned, "lang": "id", "region": "ID",
                    "quotesCount": 10, "newsCount": 0},
            headers=HEADERS, timeout=TIMEOUT,
        )
        for q in resp.json().get("quotes", []):
            sym  = q.get("symbol", "")
            exch = q.get("exchange", "")
            if sym.endswith(".JK") or exch in ["JKT", "IDX", "Jakarta"]:
                t = sym.replace(".JK", "").upper()
                if t not in EXCLUDE and 2 <= len(t) <= 6:
                    logger.info(f"Ticker Yahoo: {t} untuk '{company_name}'")
                    return t
    except Exception as e:
        logger.warning(f"Yahoo ticker search: {e}")

    # 2. IDX Official API
    try:
        resp = requests.get(
            "https://idx.co.id/umum/GetStockList/",
            params={"language": "id", "querySearch": cleaned},
            headers=HEADERS, timeout=TIMEOUT,
        )
        data    = resp.json()
        results = data if isinstance(data, list) else data.get("data", [])
        if results:
            t = (results[0].get("stockCode") or results[0].get("StockCode") or "").upper()
            if t and re.match(r"^[A-Z]{2,6}$", t) and t not in EXCLUDE:
                logger.info(f"Ticker IDX: {t} untuk '{company_name}'")
                return t
    except Exception as e:
        logger.warning(f"IDX ticker search: {e}")

    # 3. Stooq
    try:
        q    = cleaned.lower().replace(" ", "+")
        resp = requests.get(f"https://stooq.com/q/?s={q}.jk",
                            headers=HEADERS, timeout=TIMEOUT)
        m = re.search(r'Symbol["\s:]+([A-Z]{2,6})\.JK', resp.text)
        if m and m.group(1) not in EXCLUDE:
            logger.info(f"Ticker Stooq: {m.group(1)}")
            return m.group(1)
    except Exception as e:
        logger.warning(f"Stooq ticker search: {e}")

    return ""


# ══════════════════════════════════════════════════════════════════════
# 7. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def analyze_prospectus(text: str, lang: str = "ID") -> dict:
    """
    Analisis penuh prospektus IPO.

    Args:
        text : teks prospektus (sudah diekstrak dari PDF)
        lang : "ID" → output Bahasa Indonesia | "EN" → output English

    Returns:
        dict lengkap berisi semua hasil analisis
    """
    lang = (lang or "ID").upper()

    # Step 1: Deteksi metadata dokumen
    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    # Step 2: Ekstrak data keuangan via LLM multi-chunk
    fin_raw = llm_extract_financials(text)
    if not fin_raw.get("satuan"):
        fin_raw["satuan"] = unit
    if not fin_raw.get("mata_uang"):
        fin_raw["mata_uang"] = currency

    # Step 3: Normalisasi + hitung KPI di Python
    financial, kpi = normalize_and_compute(fin_raw, fx_rate)

    # Step 4: Analisis kualitatif via LLM
    result = llm_qualitative(text, kpi, financial, lang=lang)

    # Attach data
    result["financial"] = financial
    result["kpi"]       = kpi

    # Step 5: Validasi & cari ticker
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$", ticker):
        company_name = result.get("company_name", "")
        if company_name:
            logger.info(f"Ticker tidak ada di dokumen, search by name: {company_name}")
            ticker = search_ticker_by_name(company_name)
        result["ticker"] = ticker
    else:
        result["ticker"] = ticker

    # Step 6: Validasi use_of_funds
    uof = result.get("use_of_funds", [])
    if uof:
        total_alloc = sum(float(x.get("allocation") or 0) for x in uof)
        # Jika total sangat jauh dari 100, kemungkinan LLM mengarang — set ke 0
        if total_alloc > 150 or (total_alloc > 0 and total_alloc < 50):
            logger.warning(f"use_of_funds total={total_alloc}, mungkin tidak akurat")

    return result