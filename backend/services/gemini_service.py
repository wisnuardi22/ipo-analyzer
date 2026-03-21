"""
services/gemini_service.py
--------------------------
Analisis prospektus IPO Indonesia — versi final.

Pipeline:
  1. Detect metadata dokumen (currency, unit, fx rate)
  2. LLM single-pass — ekstrak data keuangan (response_format JSON)
  3. Python — normalisasi + hitung semua KPI
  4. LLM — analisis kualitatif lengkap (EN/ID) dengan response_format JSON
  5. Ticker search fallback via Yahoo / IDX / Stooq
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
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
# 3. LLM FINANCIAL EXTRACTION — SINGLE PASS + JSON MODE
# ══════════════════════════════════════════════════════════════════════

_FIN_SYSTEM = """Kamu adalah akuntan senior Indonesia. Tugasmu: ekstrak data keuangan dari teks prospektus IPO.

LANGKAH 1 — CARI DATA DI BAGIAN-BAGIAN INI:
1. "IKHTISAR DATA KEUANGAN PENTING" / "DATA KEUANGAN PENTING" / "RINGKASAN KEUANGAN"
2. "RINGKASAN DATA KEUANGAN" — tabel yang menampilkan data per 31 Desember XXXX
   (biasanya berisi kolom tahun: 31 Des 2021, 31 Des 2022, 31 Des 2023, dst.)
3. "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF KONSOLIDASIAN"
4. "LAPORAN POSISI KEUANGAN KONSOLIDASIAN" / "NERACA KONSOLIDASIAN"
5. "SELECTED FINANCIAL DATA" / "FINANCIAL HIGHLIGHTS" / "FINANCIAL SUMMARY"
6. Tabel ringkasan di halaman depan prospektus

LANGKAH 2 — ATURAN EKSTRAKSI:
- Baca header kolom tabel → itulah daftar tahun yang tersedia
- Tulis angka PERSIS seperti di dokumen, JANGAN ubah satuan
- Angka negatif dalam kurung (1.234) atau dengan tanda minus → tulis -1234
- total_ekuitas, total_liabilitas, total_aset → ambil dari tahun TERAKHIR di neraca
- total_saham_beredar → jumlah saham beredar SETELAH IPO (ada di halaman depan/ringkasan)
- harga_penawaran → harga per saham tanpa simbol "Rp" (ada di halaman ringkasan penawaran)
- Satuan: "jutaan" / "ribuan" / "miliar" / "full" (lihat keterangan di header tabel)

LANGKAH 3 — NILAI UNTUK PERHITUNGAN KPI (sistem akan hitung, kamu cukup ekstrak):
Sistem butuh nilai-nilai ini untuk menghitung:
  EPS  = laba_bersih_tahun_terakhir / total_saham_beredar
  P/E  = harga_penawaran / EPS
  P/B  = harga_penawaran / (total_ekuitas / total_saham_beredar)
  ROE  = (laba_bersih / total_ekuitas) × 100%
  D/E  = total_liabilitas / total_ekuitas
  MarketCap = harga_penawaran × total_saham_beredar

Pastikan kamu mengekstrak SEMUA nilai ini dari dokumen agar KPI dapat dihitung.

KEMBALIKAN JSON DENGAN STRUKTUR PERSIS INI (isi dengan data nyata atau null):"""

_FIN_SCHEMA = {
    "satuan": "jutaan",
    "mata_uang": "IDR",
    "tahun_tersedia": ["2022", "2023", "2024"],
    "data_per_tahun": [
        {"tahun": "2022", "pendapatan": None, "laba_kotor": None,
         "laba_usaha": None, "laba_bersih": None, "depresiasi": None},
    ],
    "total_ekuitas": None,
    "total_liabilitas": None,
    "total_aset": None,
    "total_saham_beredar": None,
    "harga_penawaran": None,
}

# Keywords untuk memilih chunk yang relevan secara keuangan
_FIN_KEYWORDS = [
    "ikhtisar data keuangan", "data keuangan penting", "laporan laba rugi",
    "ringkasan data keuangan", "ringkasan keuangan", "31 desember",
    "posisi keuangan", "neraca konsolidasian", "laba kotor", "laba usaha",
    "laba bersih", "pendapatan usaha", "pendapatan bersih", "penjualan bersih",
    "gross profit", "net revenue", "operating profit", "net income",
    "profit or loss", "statement of profit", "balance sheet",
    "selected financial", "financial highlights", "financial summary",
]


def _chunk_text(text: str, max_len: int = 120000) -> List[str]:
    """Bagi teks menjadi chunk besar — untuk prospektus panjang."""
    if len(text) <= max_len:
        return [text]
    chunks, i = [], 0
    overlap = 2000
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


def llm_extract_financials(text: str) -> Dict[str, Any]:
    """
    Ekstrak data keuangan dengan pendekatan dua fase:
    1. Single-pass dengan teks penuh (ideal untuk prospektus pendek/sedang)
    2. Jika hasilnya kosong, scan chunk-chunk yang mengandung keyword keuangan
    """
    empty_result = {
        "satuan": None, "mata_uang": None, "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas": None, "total_liabilitas": None, "total_aset": None,
        "total_saham_beredar": None, "harga_penawaran": None,
    }

    system_msg = _FIN_SYSTEM + "\n" + json.dumps(_FIN_SCHEMA, ensure_ascii=False, indent=2)

    def _has_fin_data(r: dict) -> bool:
        """Cek apakah hasil ekstraksi punya data laporan keuangan bermakna."""
        for yr in r.get("data_per_tahun", []):
            for k in ("pendapatan", "laba_kotor", "laba_usaha", "laba_bersih"):
                if yr.get(k) is not None:
                    return True
        return False

    def _has_kpi_data(r: dict) -> bool:
        """Cek apakah ada nilai untuk hitung KPI (saham + harga + ekuitas)."""
        return (r.get("total_saham_beredar") is not None and
                r.get("harga_penawaran") is not None)

    def _call_llm(chunk: str) -> dict:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0.0,
                max_tokens=4000,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": f"DOKUMEN PROSPEKTUS:\n\n{chunk}"},
                ],
            )
            raw = resp.choices[0].message.content
            result = _safe_json(raw)
            return result if result else empty_result.copy()
        except Exception as e:
            logger.warning(f"LLM financial extraction error: {e}")
            return empty_result.copy()

    def _merge(base: dict, part: dict) -> dict:
        """Merge hasil ekstraksi baru ke dalam base."""
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

    merged = empty_result.copy()

    # ── FASE 1: Halaman depan prospektus (5000 chars) ──
    # Harga penawaran & total saham hampir selalu ada di halaman 1-3
    front = _call_llm(text[:5000])
    merged = _merge(merged, front)
    logger.info(f"Fase 1 (front): saham={merged.get('total_saham_beredar')}, harga={merged.get('harga_penawaran')}")

    # ── FASE 2: Chunk scan untuk tabel keuangan ──
    all_chunks = _chunk_text(text, max_len=60000)

    # Prioritaskan chunk yang mengandung keyword keuangan
    priority_chunks = []
    for c in all_chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman") > 5:
            continue
        if any(k in cl for k in _FIN_KEYWORDS):
            priority_chunks.append(c)

    # Tambahkan chunk awal, tengah, akhir dokumen
    for idx in [0, len(all_chunks)//4, len(all_chunks)//2, -1]:
        try:
            c = all_chunks[idx]
            if c not in priority_chunks:
                priority_chunks.append(c)
        except IndexError:
            pass

    for chunk in priority_chunks[:8]:
        part = _call_llm(chunk)
        if not part:
            continue

        merged = _merge(merged, part)

        if _has_fin_data(merged):
            logger.info("Financial data ditemukan di fase 2 (chunk scan)")
            break

    logger.info(f"Final extraction: years={merged.get('tahun_tersedia')}, "
                f"saham={merged.get('total_saham_beredar')}, "
                f"harga={merged.get('harga_penawaran')}, "
                f"ekuitas={merged.get('total_ekuitas')}")
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
# 5. LLM QUALITATIVE ANALYSIS — DENGAN BAHASA EN/ID YANG BENAR
# ══════════════════════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str = "ID") -> Dict:
    is_en    = lang.upper() == "EN"
    currency = financial.get("currency", "IDR")
    years    = financial.get("years", [])

    # ── Semua string yang bergantung pada bahasa di-evaluate di Python dulu ──
    if is_en:
        lang_rule        = "CRITICAL: You MUST write ALL output text fields in ENGLISH ONLY. No Bahasa Indonesia at all."
        sector_hint      = "Specific business sector in English (e.g. Gold Mining, Banking, Technology)"
        summary_hint     = "3 PARAGRAPHS IN ENGLISH separated by \\n\\n. P1: Company profile with concrete numbers. P2: IPO details - shares, price, total proceeds. P3: Financial condition, growth, outlook."
        category_hint    = "Category name in English"
        desc_hint        = f"Specific description with project names and nominal values in {currency}"
        reputation_hint  = "2-3 sentences analyzing underwriter track record in English"
        risk_reason_hint = "2-3 sentences in English explaining why this risk level"
        risk_title_hint  = "Risk title in English"
        risk_desc_hint   = "1-2 sentences specific risk description in English with concrete facts"
        benefit_title_hint = "Benefit/strength title in English"
        benefit_desc_hint  = "1-2 sentences specific description in English with data and numbers"
        rule_uof  = 'Find section "Use of Proceeds" in document. Fill 2-6 items. allocation must be NUMBER totaling 100. If no explicit percentage, estimate from nominal amounts.'
        rule_risk = 'Fill 4-5 specific risks from the "Risk Factors" section. level must be "High", "Medium", or "Low".'
        rule_ben  = 'Fill 4-6 specific competitive advantages from "Competitive Advantages", "Business Prospects", or front page summary. DO NOT leave empty.'
        rule_sum  = "Write 3 full paragraphs, each at least 3 sentences."
    else:
        lang_rule        = "WAJIB: Tulis SEMUA field teks output dalam BAHASA INDONESIA. Tidak ada kata Inggris kecuali istilah teknis (IPO, ROE, dll)."
        sector_hint      = "Sektor bisnis spesifik (misal: Pertambangan Emas, Perbankan, Teknologi)"
        summary_hint     = "3 PARAGRAF BAHASA INDONESIA dipisah \\n\\n. P1: Profil perusahaan dengan angka konkret. P2: Detail IPO - jumlah saham, harga, total dana. P3: Kondisi keuangan, pertumbuhan, prospek."
        category_hint    = "Nama kategori dalam Bahasa Indonesia"
        desc_hint        = f"Deskripsi spesifik dengan nama proyek dan nilai nominal dalam {currency}"
        reputation_hint  = "2-3 kalimat analisis track record penjamin emisi dalam Bahasa Indonesia"
        risk_reason_hint = "2-3 kalimat Bahasa Indonesia menjelaskan alasan level risiko ini"
        risk_title_hint  = "Judul risiko dalam Bahasa Indonesia"
        risk_desc_hint   = "1-2 kalimat deskripsi risiko spesifik Bahasa Indonesia dengan fakta konkret"
        benefit_title_hint = "Judul keunggulan dalam Bahasa Indonesia"
        benefit_desc_hint  = "1-2 kalimat deskripsi spesifik Bahasa Indonesia dengan data dan angka"
        rule_uof  = 'Cari bagian "Rencana Penggunaan Dana" di dokumen. Isi 2-6 item. allocation harus NUMBER total 100. Jika tidak ada persentase eksplisit, estimasi dari nominal.'
        rule_risk = 'Isi 4-5 risiko spesifik dari bab "Faktor Risiko". level harus "High", "Medium", atau "Low".'
        rule_ben  = 'Isi 4-6 keunggulan spesifik dari bab "Keunggulan Kompetitif", "Prospek Usaha", atau halaman depan. JANGAN kosongkan.'
        rule_sum  = "Tulis 3 paragraf penuh, masing-masing minimal 3 kalimat."

    system_prompt = f"""Kamu adalah analis IPO senior Indonesia yang berpengalaman 20 tahun.
Tugasmu: analisis mendalam prospektus IPO dan hasilkan laporan lengkap.

{lang_rule}
Gunakan mata uang {currency} untuk semua nilai moneter.

DATA KPI SUDAH DIHITUNG SISTEM — SALIN PERSIS NILAI INI, JANGAN HITUNG ULANG:
{json.dumps(kpi, ensure_ascii=False)}
Tahun data tersedia: {years}

OUTPUT JSON dengan struktur persis berikut:
{{
  "company_name": "Nama lengkap perusahaan Tbk dari dokumen",
  "ticker": "Kode saham IDX 2-6 huruf KAPITAL. Cari: Kode Saham, Kode Efek, Stock Code. Jika tidak ada -> string kosong",
  "sector": "{sector_hint}",
  "ipo_date": "Tanggal pencatatan BEI dari dokumen",
  "share_price": "Harga penawaran final dari dokumen",
  "total_shares": "Total saham beredar setelah IPO dari dokumen",
  "market_cap": "SALIN PERSIS nilai market_cap dari DATA KPI di atas",
  "summary": "{summary_hint}",
  "use_of_funds": [
    {{
      "category": "{category_hint}",
      "description": "{desc_hint}",
      "allocation": 60
    }}
  ],
  "underwriter": {{
    "lead": "Nama penjamin pelaksana emisi efek dari dokumen",
    "others": ["Daftar penjamin lainnya dari dokumen"],
    "type": "Full Commitment atau Best Efforts",
    "reputation": "{reputation_hint}"
  }},
  "overall_risk_level": "High atau Medium atau Low",
  "overall_risk_reason": "{risk_reason_hint}",
  "risks": [
    {{
      "level": "High atau Medium atau Low",
      "title": "{risk_title_hint}",
      "desc": "{risk_desc_hint}"
    }}
  ],
  "benefits": [
    {{
      "title": "{benefit_title_hint}",
      "desc": "{benefit_desc_hint}"
    }}
  ]
}}

ATURAN:
1. use_of_funds: {rule_uof}
2. risks: {rule_risk}
3. benefits: {rule_ben}
4. summary: {rule_sum}
5. Output HANYA JSON murni — tidak ada teks lain di luar JSON."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"DOKUMEN PROSPEKTUS:\n\n{text[:380000]}"},
            ],
        )
        raw    = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result:
            return result

        # Repair JSON jika parse gagal
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        s, e  = fixed.find("{"), fixed.rfind("}") + 1
        if s != -1 and e > s:
            for end in range(e, s, -200):
                try:
                    return json.loads(fixed[s:end])
                except Exception:
                    pass

        raise ValueError(f"JSON parse failed: {raw[:300]}")

    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Gagal memproses analisis kualitatif: {e}")


# ══════════════════════════════════════════════════════════════════════
# 6. TICKER SEARCH — MULTI-SOURCE (Yahoo → IDX → Stooq)
# ══════════════════════════════════════════════════════════════════════

def search_ticker_by_name(company_name: str) -> str:
    """
    Cari ticker IDX menggunakan nama perusahaan lengkap.
    Fallback jika ticker tidak ada di dokumen.
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

    # 1. Yahoo Finance
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
        text : teks prospektus yang sudah diekstrak dari PDF
        lang : "ID" → output Bahasa Indonesia | "EN" → output English

    Returns:
        dict lengkap berisi semua hasil analisis
    """
    lang = (lang or "ID").upper()

    # Step 1: Deteksi metadata dokumen
    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)
    logger.info(f"Metadata: currency={currency}, unit={unit}, fx_rate={fx_rate}")

    # Step 2: Ekstrak data keuangan (fase 1: halaman depan, fase 2: chunk scan)
    fin_raw = llm_extract_financials(text)
    if not fin_raw.get("satuan"):
        fin_raw["satuan"] = unit
    if not fin_raw.get("mata_uang"):
        fin_raw["mata_uang"] = currency

    # DEBUG — log raw extraction result agar mudah troubleshoot
    logger.info(f"[FIN_RAW] satuan={fin_raw.get('satuan')}, mata_uang={fin_raw.get('mata_uang')}")
    logger.info(f"[FIN_RAW] tahun={fin_raw.get('tahun_tersedia')}")
    logger.info(f"[FIN_RAW] saham={fin_raw.get('total_saham_beredar')}, harga={fin_raw.get('harga_penawaran')}")
    logger.info(f"[FIN_RAW] ekuitas={fin_raw.get('total_ekuitas')}, liabilitas={fin_raw.get('total_liabilitas')}")
    for yr in fin_raw.get("data_per_tahun", []):
        logger.info(f"[FIN_RAW] {yr.get('tahun')}: rev={yr.get('pendapatan')}, gp={yr.get('laba_kotor')}, "
                    f"op={yr.get('laba_usaha')}, net={yr.get('laba_bersih')}")

    # Step 3: Normalisasi + hitung semua KPI di Python
    financial, kpi = normalize_and_compute(fin_raw, fx_rate)
    logger.info(f"[KPI] {kpi}")

    # Step 4: Analisis kualitatif dengan bahasa sesuai lang
    result = llm_qualitative(text, kpi, financial, lang=lang)

    # Step 5: Attach data keuangan & KPI
    result["financial"] = financial
    result["kpi"]       = kpi

    # Step 6: Validasi & cari ticker jika tidak ada di dokumen
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$", ticker):
        company_name = result.get("company_name", "")
        if company_name:
            logger.info(f"Ticker tidak ditemukan, search by name: '{company_name}'")
            ticker = search_ticker_by_name(company_name)
        result["ticker"] = ticker
    else:
        result["ticker"] = ticker

    # Step 7: Validasi use_of_funds
    uof = result.get("use_of_funds", [])
    if uof:
        total_alloc = sum(float(x.get("allocation") or 0) for x in uof)
        if total_alloc == 0:
            logger.warning("use_of_funds: semua allocation = 0, data mungkin tidak lengkap")
        elif total_alloc > 150:
            logger.warning(f"use_of_funds: total allocation={total_alloc:.0f}, normalisasi ke 100")
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0) / total_alloc * 100, 1)

    return result