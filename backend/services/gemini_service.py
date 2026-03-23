"""
services/gemini_service.py
--------------------------
Pipeline analisis prospektus IPO:
  Step 1 — LLM ekstrak data mentah keuangan (angka per tahun)
  Step 2 — LLM hitung KPI + Financial Highlights langsung (prompt Gemini Pro)
  Step 3 — LLM analisis kualitatif (summary, risiko, benefit, use of funds) EN/ID
  Step 4 — Ticker search fallback
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
# 3. JSON UTILITIES
# ══════════════════════════════════════════════════════════════════════

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


def _chunk_text(text: str, max_len: int = 60000) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks, i = [], 0
    overlap = 2000
    while i < len(text):
        chunks.append(text[i: i + max_len])
        i += max_len - overlap
    return chunks


_FIN_KEYWORDS = [
    "ikhtisar data keuangan", "ringkasan data keuangan", "data keuangan penting",
    "laporan laba rugi", "posisi keuangan", "neraca konsolidasian",
    "laba kotor", "laba usaha", "laba bersih", "pendapatan usaha",
    "pendapatan bersih", "penjualan bersih", "31 desember",
    "rasio keuangan", "rasio penting",
    "gross profit", "net revenue", "operating profit", "net income",
    "profit or loss", "statement of profit", "balance sheet",
    "selected financial", "financial highlights",
]


# ══════════════════════════════════════════════════════════════════════
# 4. STEP 1 — LLM EKSTRAK DATA MENTAH (angka per tahun + saham + harga)
# ══════════════════════════════════════════════════════════════════════

_RAW_SYSTEM = """Kamu adalah akuntan senior Indonesia. Ekstrak data keuangan mentah dari teks prospektus IPO.

CARI di bagian:
- "IKHTISAR DATA KEUANGAN PENTING" / "RINGKASAN DATA KEUANGAN" / "DATA KEUANGAN PENTING"
- "LAPORAN LABA RUGI" / "CONSOLIDATED STATEMENTS OF PROFIT OR LOSS"
- "LAPORAN POSISI KEUANGAN" / "NERACA KONSOLIDASIAN" / "BALANCE SHEET"
- "SELECTED FINANCIAL DATA" / "FINANCIAL HIGHLIGHTS"
- Tabel yang menampilkan data per 31 Desember XXXX

ATURAN:
- Baca header kolom tabel → itulah tahun-tahun yang tersedia
- Ambil data tahun buku PENUH (31 Desember) saja, abaikan interim
- Tulis angka PERSIS dari dokumen, jangan ubah satuan
- Angka dalam kurung (1.234) = negatif → tulis -1234
- satuan: "jutaan" / "ribuan" / "miliar" / "full" (lihat header tabel)
- total_ekuitas, total_liabilitas, total_aset: dari tahun TERAKHIR di neraca
- total_saham_beredar: jumlah saham SETELAH IPO (halaman depan/ringkasan)
- harga_penawaran: harga per saham tanpa "Rp" (halaman ringkasan penawaran)

OUTPUT JSON MURNI:
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


def llm_extract_raw(text: str) -> Dict[str, Any]:
    """Step 1: Ekstrak angka mentah dari prospektus."""
    empty: Dict[str, Any] = {
        "satuan": None, "mata_uang": None, "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas": None, "total_liabilitas": None, "total_aset": None,
        "total_saham_beredar": None, "harga_penawaran": None,
    }

    def _call(chunk: str) -> dict:
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.0, max_tokens=4000,
                messages=[
                    {"role": "system", "content": _RAW_SYSTEM},
                    {"role": "user", "content": f"DOKUMEN:\n{chunk}"},
                ],
            )
            return _safe_json(resp.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"LLM raw extract error: {e}")
            return {}

    def _has_data(r: dict) -> bool:
        for yr in r.get("data_per_tahun", []):
            for k in ("pendapatan", "laba_kotor", "laba_usaha", "laba_bersih"):
                if yr.get(k) is not None:
                    return True
        return (r.get("total_saham_beredar") is not None and
                r.get("harga_penawaran") is not None)

    def _merge(base: dict, part: dict) -> dict:
        for k in ("satuan", "mata_uang"):
            if not base[k] and part.get(k):
                base[k] = part[k]
        if part.get("tahun_tersedia"):
            base["tahun_tersedia"] = sorted(
                set(base["tahun_tersedia"]) | set(str(y) for y in part["tahun_tersedia"])
            )
        if part.get("data_per_tahun"):
            m_dict = {str(d.get("tahun", "")).strip(): d for d in base["data_per_tahun"]}
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
            base["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]
        for k in ("total_ekuitas", "total_liabilitas", "total_aset",
                  "total_saham_beredar", "harga_penawaran"):
            v = part.get(k)
            if base.get(k) is None and v is not None and str(v).strip() not in ("null", ""):
                base[k] = v
        return base

    merged = dict(empty)

    # Fase 1: Halaman depan (saham + harga biasanya di sini)
    front = _call(text[:6000])
    merged = _merge(merged, front)

    # Fase 2: Chunk scan prioritas keyword keuangan
    all_chunks = _chunk_text(text, max_len=60000)
    priority = []
    for c in all_chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman") > 5:
            continue
        if any(k in cl for k in _FIN_KEYWORDS):
            priority.append(c)
    for idx in [0, len(all_chunks)//4, len(all_chunks)//2, -1]:
        try:
            c = all_chunks[idx]
            if c not in priority:
                priority.append(c)
        except IndexError:
            pass

    for chunk in priority[:8]:
        part = _call(chunk)
        merged = _merge(merged, part)
        if _has_data(merged):
            break

    logger.info(f"[RAW] tahun={merged.get('tahun_tersedia')}, "
                f"saham={merged.get('total_saham_beredar')}, "
                f"harga={merged.get('harga_penawaran')}, "
                f"ekuitas={merged.get('total_ekuitas')}")
    return merged


# ══════════════════════════════════════════════════════════════════════
# 5. STEP 2 — LLM HITUNG KPI + FINANCIAL HIGHLIGHTS (Gemini Pro prompt)
# ══════════════════════════════════════════════════════════════════════

_KPI_SYSTEM = """Anda adalah seorang analis keuangan senior dan spesialis pembacaan dokumen prospektus IPO.
Tugas Anda adalah mengekstrak data keuangan historis tahunan (per 31 Desember) dari teks prospektus
dan menghitung metrik KPI serta Financial Highlights.

ATURAN EKSTRAKSI & PERHITUNGAN:

1. DETEKSI PERIODE DINAMIS: Identifikasi semua tahun buku penuh (31 Desember) yang tersedia.
   Abaikan data interim (31 Mei, 30 September, dll).

2. PRIORITAS: Cari bagian "Rasio Keuangan" atau "Rasio Penting" terlebih dahulu.
   Jika metrik sudah dihitung oleh penerbit, GUNAKAN angka tersebut langsung.

3. KALKULASI (jika tidak tersedia di dokumen, hitung dengan rumus ini):
   - ROE (%) = (Laba Tahun Berjalan / Total Ekuitas) × 100
   - D/E Ratio = Total Liabilitas / Total Ekuitas
   - Revenue Growth (%) = ((Pendapatan T - Pendapatan T-1) / Pendapatan T-1) × 100
   - Gross Margin (%) = (Laba Kotor / Pendapatan) × 100
   - Operating Margin (%) = (Laba Usaha / Pendapatan) × 100
     → Jika tidak ada Laba Usaha, pakai Laba Sebelum Pajak sebagai proksi
   - EBITDA Margin (%) = ((Laba Usaha + Depresiasi & Amortisasi) / Pendapatan) × 100
   - EPS = Laba Bersih Tahun Terakhir / Total Saham Beredar Setelah IPO
   - P/E Ratio = Harga Penawaran IPO / EPS
   - P/B Ratio = Harga Penawaran IPO / (Total Ekuitas / Total Saham Beredar)

4. DATA TIDAK TERSEDIA: Kembalikan "N/A" (string) jika komponen tidak ditemukan.

5. FORMAT:
   - Key JSON menggunakan tahun aktual: "2022", "2023", "2024"
   - Nilai numerik: angka desimal, titik sebagai pemisah, maksimal 2 desimal
   - JANGAN sertakan simbol "%" atau "x" pada value numerik
   - pe_ratio, pb_ratio, eps: nilai untuk tahun TERAKHIR saja (bukan per tahun)

OUTPUT: JSON murni tanpa markdown, tanpa teks penjelasan."""

_KPI_SCHEMA = """{
  "kpi": {
    "pe_ratio": "N/A",
    "pb_ratio": "N/A",
    "eps": "N/A",
    "roe_percent": {"YYYY": 0.00},
    "de_ratio": {"YYYY": 0.00}
  },
  "financial_highlights": {
    "revenue_growth_percent": {"YYYY": 0.00},
    "gross_margin_percent": {"YYYY": 0.00},
    "operating_margin_percent": {"YYYY": 0.00},
    "ebitda_margin_percent": {"YYYY": 0.00},
    "net_profit_margin_percent": {"YYYY": 0.00}
  }
}"""


def llm_compute_kpi(text: str, raw: Dict[str, Any]) -> Tuple[Dict, Dict]:
    """
    Step 2: LLM hitung KPI dan Financial Highlights dari teks prospektus.
    raw digunakan sebagai context tambahan.
    """
    # Beri konteks data yang sudah diekstrak ke LLM
    context = f"""DATA YANG SUDAH DIEKSTRAK SISTEM:
Satuan: {raw.get('satuan', 'full')}
Mata Uang: {raw.get('mata_uang', 'IDR')}
Total Saham Beredar (post-IPO): {raw.get('total_saham_beredar')}
Harga Penawaran: {raw.get('harga_penawaran')}
Total Ekuitas (tahun terakhir): {raw.get('total_ekuitas')}
Total Liabilitas (tahun terakhir): {raw.get('total_liabilitas')}

Data Per Tahun:
{json.dumps(raw.get('data_per_tahun', []), ensure_ascii=False)}

Gunakan data di atas sebagai panduan, tapi VERIFIKASI dan LENGKAPI dengan membaca langsung dari dokumen prospektus di bawah."""

    system_msg = _KPI_SYSTEM + f"\n\nFORMAT OUTPUT WAJIB:\n{_KPI_SCHEMA}"

    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0.0, max_tokens=3000,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"{context}\n\nDOKUMEN PROSPEKTUS:\n{text[:350000]}"},
            ],
        )
        result = _safe_json(resp.choices[0].message.content)
        if not result:
            raise ValueError("Empty response")
    except Exception as e:
        logger.warning(f"LLM KPI compute error: {e}")
        result = {}

    kpi_raw  = result.get("kpi", {})
    fin_raw  = result.get("financial_highlights", {})
    currency = (raw.get("mata_uang") or "IDR").upper()
    unit     = (raw.get("satuan") or "full").lower()

    # ── Format KPI untuk frontend ──
    def _apply_unit(val):
        v = parse_num(val)
        if v is None:
            return None
        multipliers = {"jutaan": 1_000_000, "ribuan": 1_000,
                       "miliar": 1_000_000_000, "triliun": 1_000_000_000_000}
        return v * multipliers.get(unit, 1)

    def _fmt_kpi_val(val, suffix="") -> str:
        if val is None or str(val).upper() == "N/A":
            return "N/A"
        v = parse_num(val)
        if v is None:
            return "N/A"
        return f"{v:.2f}{suffix}"

    # EPS — format dengan currency
    eps_raw = kpi_raw.get("eps")
    if eps_raw and str(eps_raw).upper() != "N/A":
        eps_v = parse_num(eps_raw)
        if eps_v is not None:
            eps_v_real = _apply_unit(eps_v) if unit != "full" else eps_v
            eps_str = f"Rp {eps_v_real:,.2f}".replace(",", ".") if currency == "IDR" else f"{currency} {eps_v_real:.4f}"
        else:
            eps_str = "N/A"
    else:
        eps_str = "N/A"

    # Market cap dari raw data
    market_cap_str = "N/A"
    saham = parse_num(raw.get("total_saham_beredar"))
    harga = parse_num(raw.get("harga_penawaran"))
    if saham and harga and saham > 0 and harga > 0:
        mc = saham * harga
        market_cap_str = fmt_idr(mc)

    kpi = {
        "pe":         _fmt_kpi_val(kpi_raw.get("pe_ratio"), "x"),
        "pb":         _fmt_kpi_val(kpi_raw.get("pb_ratio"), "x"),
        "roe":        _fmt_kpi_val(_last_val(kpi_raw.get("roe_percent")), "%"),
        "der":        _fmt_kpi_val(_last_val(kpi_raw.get("de_ratio")), "x"),
        "eps":        eps_str,
        "market_cap": market_cap_str,
    }

    # ── Format Financial Highlights untuk chart ──
    def _to_series(d: Any) -> Optional[List[Dict]]:
        """Convert dict {year: val} ke [{year, value}] untuk Recharts."""
        if not d or not isinstance(d, dict):
            return None
        series = []
        for yr, val in sorted(d.items()):
            v = parse_num(val)
            series.append({"year": str(yr), "value": v})
        return series if series else None

    financial = {
        "currency":          currency,
        "years":             sorted(list(fin_raw.get("revenue_growth_percent", {}).keys())),
        "revenue_growth":    _to_series(fin_raw.get("revenue_growth_percent")),
        "gross_margin":      _to_series(fin_raw.get("gross_margin_percent")),
        "operating_margin":  _to_series(fin_raw.get("operating_margin_percent")),
        "ebitda_margin":     _to_series(fin_raw.get("ebitda_margin_percent")),
        "net_profit_margin": _to_series(fin_raw.get("net_profit_margin_percent")),
        # Simpan raw juga untuk absolute data
        "absolute_data":     raw.get("data_per_tahun", []),
    }

    logger.info(f"[KPI] {kpi}")
    logger.info(f"[FIN] years={financial['years']}")
    return financial, kpi


def _last_val(d: Any) -> Optional[float]:
    """Ambil nilai tahun terakhir dari dict {year: val}."""
    if not d or not isinstance(d, dict):
        return None
    last_key = sorted(d.keys())[-1] if d else None
    return parse_num(d[last_key]) if last_key else None


# ══════════════════════════════════════════════════════════════════════
# 6. STEP 3 — LLM ANALISIS KUALITATIF (EN/ID)
# ══════════════════════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str = "ID") -> Dict:
    is_en    = lang.upper() == "EN"
    currency = financial.get("currency", "IDR")
    years    = financial.get("years", [])

    # Semua string bergantung bahasa di-evaluate di Python dulu
    if is_en:
        lang_rule        = "CRITICAL: ALL output text fields MUST be in ENGLISH ONLY. No Bahasa Indonesia."
        sector_hint      = "Specific business sector in English (e.g. Coffee & F&B, Gold Mining, Banking)"
        summary_hint     = "3 PARAGRAPHS IN ENGLISH separated by \\n\\n. P1: Company profile with numbers. P2: IPO details. P3: Financial condition and outlook."
        category_hint    = "Category name in English"
        desc_hint        = f"Specific description with project names and values in {currency}"
        reputation_hint  = "2-3 sentences analyzing underwriter track record in English"
        risk_reason_hint = "2-3 sentences in English explaining this risk level"
        risk_title_hint  = "Risk title in English"
        risk_desc_hint   = "1-2 sentences specific risk description in English with facts"
        benefit_title_h  = "Competitive advantage title in English"
        benefit_desc_h   = "1-2 sentences specific description in English with data"
        rule_uof  = 'Find "Use of Proceeds" section. Fill 2-6 items. allocation = NUMBER totaling 100.'
        rule_risk = 'Fill 4-5 specific risks from "Risk Factors". level = "High", "Medium", or "Low".'
        rule_ben  = 'Fill 4-6 specific competitive advantages. Find in "Competitive Advantages" or front page.'
    else:
        lang_rule        = "WAJIB: SEMUA field teks output dalam BAHASA INDONESIA. Tidak boleh ada kata Inggris kecuali istilah teknis."
        sector_hint      = "Sektor bisnis spesifik (misal: Kopi & F&B, Pertambangan Emas, Perbankan)"
        summary_hint     = "3 PARAGRAF BAHASA INDONESIA dipisah \\n\\n. P1: Profil perusahaan dengan angka. P2: Detail IPO. P3: Kondisi keuangan dan prospek."
        category_hint    = "Nama kategori dalam Bahasa Indonesia"
        desc_hint        = f"Deskripsi spesifik dengan nama proyek dan nilai dalam {currency}"
        reputation_hint  = "2-3 kalimat analisis track record penjamin emisi dalam Bahasa Indonesia"
        risk_reason_hint = "2-3 kalimat Bahasa Indonesia menjelaskan alasan level risiko"
        risk_title_hint  = "Judul risiko dalam Bahasa Indonesia"
        risk_desc_hint   = "1-2 kalimat deskripsi risiko spesifik dengan fakta konkret"
        benefit_title_h  = "Judul keunggulan dalam Bahasa Indonesia"
        benefit_desc_h   = "1-2 kalimat deskripsi spesifik dengan data dan angka"
        rule_uof  = 'Cari "Rencana Penggunaan Dana". Isi 2-6 item. allocation = NUMBER total 100.'
        rule_risk = 'Isi 4-5 risiko spesifik dari bab "Faktor Risiko". level = "High", "Medium", atau "Low".'
        rule_ben  = 'Isi 4-6 keunggulan dari bab "Keunggulan Kompetitif" atau halaman depan. JANGAN kosong.'

    system_prompt = f"""Kamu adalah analis IPO senior Indonesia berpengalaman 20 tahun.

{lang_rule}
Gunakan mata uang {currency} untuk semua nilai moneter.

DATA KPI SUDAH DIHITUNG — SALIN PERSIS, JANGAN HITUNG ULANG:
{json.dumps(kpi, ensure_ascii=False)}
Tahun data: {years}

OUTPUT JSON:
{{
  "company_name": "Nama lengkap Tbk dari dokumen",
  "ticker": "Kode IDX 2-6 huruf. Cari: Kode Saham/Efek/Stock Code. Kosong jika tidak ada",
  "sector": "{sector_hint}",
  "ipo_date": "Tanggal pencatatan BEI",
  "share_price": "Harga penawaran final",
  "total_shares": "Total saham beredar setelah IPO",
  "market_cap": "SALIN dari DATA KPI di atas",
  "summary": "{summary_hint}",
  "use_of_funds": [
    {{"category": "{category_hint}", "description": "{desc_hint}", "allocation": 60}},
    {{"category": "{category_hint}", "description": "{desc_hint}", "allocation": 40}}
  ],
  "underwriter": {{
    "lead": "Nama penjamin pelaksana emisi dari dokumen",
    "others": ["Nama penjamin lain"],
    "type": "Full Commitment atau Best Efforts",
    "reputation": "{reputation_hint}"
  }},
  "overall_risk_level": "High atau Medium atau Low",
  "overall_risk_reason": "{risk_reason_hint}",
  "risks": [
    {{"level": "High/Medium/Low", "title": "{risk_title_hint}", "desc": "{risk_desc_hint}"}}
  ],
  "benefits": [
    {{"title": "{benefit_title_h}", "desc": "{benefit_desc_h}"}}
  ]
}}

ATURAN:
1. use_of_funds: {rule_uof}
2. risks: {rule_risk}
3. benefits: {rule_ben}
4. summary: 3 paragraf penuh masing-masing min 3 kalimat
5. Output HANYA JSON murni"""

    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0.1, max_tokens=8000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"DOKUMEN PROSPEKTUS:\n{text[:380000]}"},
            ],
        )
        raw    = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result:
            return result
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        s, e  = fixed.find("{"), fixed.rfind("}") + 1
        if s != -1 and e > s:
            for end in range(e, s, -200):
                try:
                    return json.loads(fixed[s:end])
                except Exception:
                    pass
        raise ValueError(f"JSON parse failed: {raw[:200]}")
    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Gagal analisis kualitatif: {e}")


# ══════════════════════════════════════════════════════════════════════
# 7. TICKER SEARCH FALLBACK
# ══════════════════════════════════════════════════════════════════════

def search_ticker_by_name(company_name: str) -> str:
    import requests
    HEADERS = {"User-Agent": "Mozilla/5.0 AppleWebKit/537.36", "Accept": "application/json"}
    TIMEOUT = 10
    EXCLUDE = {"PT", "TBK", "IDX", "BEI", "OJK", "IDR", "USD", "IPO",
               "ROE", "ROA", "DER", "EPS", "CEO", "CFO", "GDP", "EBITDA"}

    def clean(name: str) -> str:
        name = re.sub(r"\bPT\.?\s*", "", name, flags=re.I)
        name = re.sub(r"\bTbk\.?\b", "", name, flags=re.I)
        return re.sub(r"\s+", " ", name).strip()

    cleaned = clean(company_name)
    if not cleaned:
        return ""

    # Yahoo Finance
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": cleaned, "lang": "id", "region": "ID", "quotesCount": 10, "newsCount": 0},
            headers=HEADERS, timeout=TIMEOUT,
        )
        for q in resp.json().get("quotes", []):
            sym  = q.get("symbol", "")
            exch = q.get("exchange", "")
            if sym.endswith(".JK") or exch in ["JKT", "IDX", "Jakarta"]:
                t = sym.replace(".JK", "").upper()
                if t not in EXCLUDE and 2 <= len(t) <= 6:
                    logger.info(f"Ticker Yahoo: {t}")
                    return t
    except Exception as e:
        logger.warning(f"Yahoo: {e}")

    # IDX API
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
                logger.info(f"Ticker IDX: {t}")
                return t
    except Exception as e:
        logger.warning(f"IDX: {e}")

    # Stooq
    try:
        q    = cleaned.lower().replace(" ", "+")
        resp = requests.get(f"https://stooq.com/q/?s={q}.jk", headers=HEADERS, timeout=TIMEOUT)
        m = re.search(r'Symbol["\s:]+([A-Z]{2,6})\.JK', resp.text)
        if m and m.group(1) not in EXCLUDE:
            logger.info(f"Ticker Stooq: {m.group(1)}")
            return m.group(1)
    except Exception as e:
        logger.warning(f"Stooq: {e}")

    return ""


# ══════════════════════════════════════════════════════════════════════
# 8. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def analyze_prospectus(text: str, lang: str = "ID") -> dict:
    """
    Analisis penuh prospektus IPO.
    lang: "ID" → Bahasa Indonesia | "EN" → English
    """
    lang = (lang or "ID").upper()

    # Step 1: Ekstrak data mentah
    raw = llm_extract_raw(text)
    if not raw.get("satuan"):
        raw["satuan"] = detect_unit(text)
    if not raw.get("mata_uang"):
        raw["mata_uang"] = detect_currency(text)

    # Step 2: Hitung KPI & Financial Highlights via LLM (Gemini Pro approach)
    fx_rate = detect_fx_rate(text)
    financial, kpi = llm_compute_kpi(text, raw)

    # Step 3: Analisis kualitatif (bahasa sesuai lang)
    result = llm_qualitative(text, kpi, financial, lang=lang)
    result["financial"] = financial
    result["kpi"]       = kpi

    # Step 4: Validasi ticker
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$", ticker):
        company_name = result.get("company_name", "")
        if company_name:
            ticker = search_ticker_by_name(company_name)
        result["ticker"] = ticker
    else:
        result["ticker"] = ticker

    # Step 5: Validasi use_of_funds
    uof = result.get("use_of_funds", [])
    if uof:
        total_alloc = sum(float(x.get("allocation") or 0) for x in uof)
        if total_alloc > 150:
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0) / total_alloc * 100, 1)

    return result