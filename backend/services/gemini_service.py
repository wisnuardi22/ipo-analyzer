from openai import OpenAI
import json, re, os, math
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)

MODEL = "gemini/gemini-2.5-flash"

# ══════════════════════════════════════════════════════════════════
# UTIL UMUM
# ══════════════════════════════════════════════════════════════════

def parse_number(raw: Optional[Any]) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s.lower() in ("null", "n/a", "-"):
        return None
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    elif s.startswith('-'):
        neg = True
        s = s[1:]
    s = re.sub(r'[^0-9\.,]', '', s)
    if not s:
        return None
    if '.' in s and ',' in s:
        last_dot   = s.rfind('.')
        last_comma = s.rfind(',')
        if last_comma > last_dot:
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            s = s.replace(',', '.')
        else:
            s = s.replace(',', '')
    elif '.' in s:
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) <= 2:
            pass
        else:
            s = s.replace('.', '')
    try:
        val = float(s)
        return -val if neg else val
    except Exception:
        return None

def to_decimal(s: Optional[str]) -> Optional[Decimal]:
    if not s:
        return None
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError):
        return None

def safe_div(a, b) -> Optional[float]:
    try:
        a_f, b_f = parse_number(a), parse_number(b)
        if a_f is None or b_f is None or b_f == 0:
            return None
        return a_f / b_f
    except:
        return None

def pct(val) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
        return round(v * 100.0, 2) if not math.isnan(v) else None
    except:
        return None

def calc_growth(cur, prev) -> Optional[float]:
    try:
        c, p = parse_number(cur), parse_number(prev)
        if c is None or p is None or p == 0:
            return None
        return round(((c - p) / abs(p)) * 100, 2)
    except:
        return None

def apply_unit(val, unit: str) -> Optional[float]:
    v = parse_number(val)
    if v is None:
        return None
    if unit == "jutaan":
        return v * 1_000_000
    if unit == "ribuan":
        return v * 1_000
    return v

def detect_currency_and_unit(text: str) -> Tuple[str, str]:
    t = text.lower()
    currency = "IDR"
    if "us$" in t or "usd" in t or "dolar amerika" in t:
        currency = "USD"
    unit = "full"
    if re.search(r'dalam\s+jutaan', t):
        unit = "jutaan"
    elif re.search(r'dalam\s+ribuan', t):
        unit = "ribuan"
    return currency, unit

def detect_fx_rate(text: str) -> Optional[float]:
    m = re.search(r'kurs.*?rp\s*([0-9\.\,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)', text, flags=re.I)
    if m:
        val = parse_number(m.group(1))
        if val and val > 0:
            return float(val)
    return None

def chunk_text(s: str, max_len: int = 15000, overlap: int = 500) -> List[str]:
    if not s or len(s) <= max_len:
        return [s or ""]
    chunks = []
    i = 0
    while i < len(s):
        chunks.append(s[i:i + max_len])
        i += max(1, max_len - overlap)
    return chunks

# ══════════════════════════════════════════════════════════════════
# REGEX FALLBACK — dari ipo_from_prospectus_general.py
# ══════════════════════════════════════════════════════════════════

def _grab_first_number(line: str) -> Optional[Decimal]:
    m = re.search(r"[-]?\d[\d\.\,]*", line)
    if not m:
        return None
    token = m.group(0).strip().replace("−", "-")
    token = re.sub(r"[^0-9\.\-]", "", token.replace(",", "."))
    try:
        return Decimal(token)
    except:
        return None

def regex_extract_financials(text: str) -> Dict[str, Any]:
    """
    Fallback: ekstrak data keuangan via regex dari teks prospektus.
    Mengembalikan format yang kompatibel dengan normalize_and_compute().
    """
    rev_by_year: Dict[str, Optional[float]] = {}
    gp_by_year:  Dict[str, Optional[float]] = {}
    op_by_year:  Dict[str, Optional[float]] = {}
    ni_by_year:  Dict[str, Optional[float]] = {}
    eq_by_year:  Dict[str, Optional[float]] = {}
    lb_by_year:  Dict[str, Optional[float]] = {}

    lines = text.splitlines()
    for ln in lines:
        l = ln.lower()
        yr_m = re.search(r"(20\d{2})", ln)
        yr = yr_m.group(1) if yr_m else None
        val = _grab_first_number(ln)
        if val is None:
            continue
        fval = float(val)

        if "pendapatan" in l or "revenue" in l or "penjualan" in l:
            if yr and yr not in rev_by_year:
                rev_by_year[yr] = fval
        if "laba kotor" in l or "gross profit" in l:
            if yr and yr not in gp_by_year:
                gp_by_year[yr] = fval
        if ("laba usaha" in l or "rugi usaha" in l or
                "operating profit" in l or "operating income" in l):
            if yr and yr not in op_by_year:
                op_by_year[yr] = fval
        if ("laba bersih" in l or "rugi bersih" in l or
                "laba periode" in l or "rugi periode" in l or
                "net profit" in l or "net income" in l or
                "loss for the period" in l):
            if yr and yr not in ni_by_year:
                ni_by_year[yr] = fval
        if "jumlah ekuitas" in l or "total equity" in l:
            if yr and yr not in eq_by_year:
                eq_by_year[yr] = fval
        if "jumlah liabilitas" in l or "total liabilit" in l:
            if yr and yr not in lb_by_year:
                lb_by_year[yr] = fval

    # Ambil semua tahun yang ditemukan
    all_years = sorted(set(
        list(rev_by_year.keys()) + list(gp_by_year.keys()) +
        list(op_by_year.keys())  + list(ni_by_year.keys())
    ))

    if not all_years:
        return {}

    data_per_tahun = []
    for y in all_years:
        data_per_tahun.append({
            "tahun":       y,
            "pendapatan":  rev_by_year.get(y),
            "laba_kotor":  gp_by_year.get(y),
            "laba_usaha":  op_by_year.get(y),
            "laba_bersih": ni_by_year.get(y),
            "depresiasi":  None,
        })

    # Ekuitas & liabilitas tahun terakhir
    last_eq = eq_by_year.get(all_years[-1]) if eq_by_year else None
    last_lb = lb_by_year.get(all_years[-1]) if lb_by_year else None

    # Saham & harga via regex
    saham = None
    for pat in [
        r"jumlah\s+saham\s+(?:yang\s+)?(?:akan\s+)?dicatatkan.*?(\d{1,3}(?:\.\d{3})+)",
        r"jumlah\s+saham\s+beredar\s+setelah\s+IPO.*?(\d{1,3}(?:\.\d{3})+)",
        r"(\d{1,3}(?:\.\d{3}){3,})\s*saham.*?dicatatkan",
    ]:
        m = re.search(pat, text, re.I | re.S)
        if m:
            s = re.sub(r"[^\d]", "", m.group(1))
            try:
                saham = int(s)
                break
            except:
                pass

    harga = None
    for pat in [
        r"Harga\s+Penawaran\s*:?\s*Rp\s*([\d\.]+)",
        r"Offering\s+Price\s*:?\s*Rp\s*([\d\.]+)",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            h = re.sub(r"[^\d]", "", m.group(1))
            try:
                harga = int(h)
                break
            except:
                pass

    currency, unit = detect_currency_and_unit(text)

    return {
        "satuan":                   unit,
        "mata_uang":                currency,
        "tahun_tersedia":           all_years,
        "data_per_tahun":           data_per_tahun,
        "total_ekuitas_terakhir":   last_eq,
        "total_liabilitas_terakhir":last_lb,
        "total_saham_beredar":      saham,
        "harga_penawaran_angka":    harga,
    }

# ══════════════════════════════════════════════════════════════════
# LLM EXTRACT FINANCIALS
# ══════════════════════════════════════════════════════════════════

def llm_extract_financials(text: str) -> Dict[str, Any]:
    sys_prompt = """Kamu adalah akuntan Indonesia. Tugasmu: ekstrak angka keuangan mentah dari potongan prospektus IPO.
Output HANYA JSON murni — tidak ada teks penjelasan, tidak ada markdown.

LANGKAH EKSTRAKSI:
1. Temukan tabel laporan keuangan. Judulnya bisa:
   - "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN KONSOLIDASIAN"
   - "DATA KEUANGAN PENTING" / "IKHTISAR DATA KEUANGAN PENTING"
   - "Ringkasan Keuangan" / "Informasi Keuangan Ringkas"
   - "CONSOLIDATED STATEMENTS OF PROFIT OR LOSS"
   - "SELECTED FINANCIAL DATA"

2. Baca header kolom tabel → itulah daftar tahun yang tersedia (misal: 2021, 2022, 2023, 2024).
   Masukkan SEMUA tahun ke "tahun_tersedia" dan buat satu entry per tahun di "data_per_tahun".

3. Untuk setiap tahun, catat:
   - pendapatan   : Total Pendapatan / Revenue / Net Revenue
   - laba_kotor   : Laba Kotor / Gross Profit
   - laba_usaha   : Laba Usaha / Operating Profit (bisa negatif)
   - laba_bersih  : Laba Bersih / Net Profit (bisa negatif)
   - depresiasi   : Depresiasi & Amortisasi (isi null jika tidak ada)

4. Catat satuan dari header tabel:
   - "dalam jutaan Rupiah" → satuan = "jutaan"
   - "dalam ribuan" → satuan = "ribuan"
   - tidak ada keterangan → satuan = "full"

5. Tulis angka PERSIS seperti di dokumen — JANGAN konversi ke satuan lain.
   Angka dalam kurung misal (1.234) artinya negatif → tulis -1234.

6. Dari Laporan Posisi Keuangan / Neraca, ambil data tahun TERAKHIR:
   - total_ekuitas_terakhir
   - total_liabilitas_terakhir

7. Cari juga:
   - total_saham_beredar: jumlah saham beredar SETELAH IPO
   - harga_penawaran_angka: harga per saham (angka saja, tanpa "Rp")

8. Jika potongan ini tidak mengandung data keuangan → isi null atau [].

OUTPUT JSON:
{
  "satuan": "jutaan",
  "mata_uang": "IDR",
  "tahun_tersedia": ["2022", "2023", "2024"],
  "data_per_tahun": [
    {"tahun": "2022", "pendapatan": null, "laba_kotor": null, "laba_usaha": null, "laba_bersih": null, "depresiasi": null},
    {"tahun": "2023", "pendapatan": null, "laba_kotor": null, "laba_usaha": null, "laba_bersih": null, "depresiasi": null},
    {"tahun": "2024", "pendapatan": null, "laba_kotor": null, "laba_usaha": null, "laba_bersih": null, "depresiasi": null}
  ],
  "total_ekuitas_terakhir": null,
  "total_liabilitas_terakhir": null,
  "total_saham_beredar": null,
  "harga_penawaran_angka": null
}"""

    merged = {
        "satuan": None, "mata_uang": None,
        "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas_terakhir": None, "total_liabilitas_terakhir": None,
        "total_saham_beredar": None, "harga_penawaran_angka": None
    }

    chunks = chunk_text(text, max_len=15000, overlap=500)
    priority_chunks = []
    keywords = [
        "laporan laba rugi", "ikhtisar data keuangan", "data keuangan penting",
        "ringkasan keuangan", "pendapatan bersih", "laba kotor", "laba usaha",
        "laba bersih", "pendapatan usaha", "penjualan bersih",
        "gross profit", "net revenue", "operating profit", "net income",
        "profit or loss", "statement of profit",
    ]
    for c in chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman") > 5:
            continue
        if any(k in cl for k in keywords):
            priority_chunks.append(c)
    if chunks and chunks[0] not in priority_chunks:
        priority_chunks.insert(0, chunks[0])
    if len(chunks) > 1 and chunks[-1] not in priority_chunks:
        priority_chunks.append(chunks[-1])
    selected_chunks = priority_chunks[:8]

    def safe_json(s: str) -> Optional[dict]:
        s = s.strip()
        if "```" in s:
            for p in s.split("```"):
                p = p.strip().lstrip("json").strip()
                if p.startswith("{"):
                    s = p
                    break
        si = s.find("{")
        ei = s.rfind("}")
        if si != -1 and ei > si:
            try:
                return json.loads(s[si:ei+1])
            except:
                fixed = re.sub(r',\s*([}\]])', r'\1', s[si:ei+1])
                try:
                    return json.loads(fixed)
                except:
                    return None
        return None

    for chunk in selected_chunks:
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                temperature=0.01,
                max_tokens=3000,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user",   "content": f"DOKUMEN:\n{chunk}"}
                ]
            )
            part = safe_json(resp.choices[0].message.content) or {}
        except Exception:
            part = {}

        if not merged["satuan"] and part.get("satuan"):
            merged["satuan"] = part["satuan"]
        if not merged["mata_uang"] and part.get("mata_uang"):
            merged["mata_uang"] = part["mata_uang"]
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(list(set(merged["tahun_tersedia"]) | set(part["tahun_tersedia"])))
        if part.get("data_per_tahun"):
            m_dict = {str(d.get("tahun","")).strip(): d for d in merged["data_per_tahun"] if str(d.get("tahun","")).strip()}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun","")).strip()
                if not y:
                    continue
                if y in m_dict:
                    for k in ["pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"]:
                        val = d.get(k)
                        if m_dict[y].get(k) is None and val is not None and str(val).strip() not in ("null",""):
                            m_dict[y][k] = val
                else:
                    m_dict[y] = d
            merged["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]
        for k in ["total_ekuitas_terakhir","total_liabilitas_terakhir","total_saham_beredar","harga_penawaran_angka"]:
            val = part.get(k)
            if merged.get(k) is None and val is not None and str(val).strip() not in ("null",""):
                merged[k] = val

    return merged

# ══════════════════════════════════════════════════════════════════
# MERGE LLM + REGEX (LLM prioritas, regex sebagai fallback)
# ══════════════════════════════════════════════════════════════════

def _has_financial_data(fin_raw: Dict) -> bool:
    """Cek apakah hasil LLM punya data keuangan yang bermakna."""
    years = fin_raw.get("data_per_tahun", [])
    if not years:
        return False
    for yr in years:
        for k in ["pendapatan", "laba_kotor", "laba_usaha", "laba_bersih"]:
            if yr.get(k) is not None:
                return True
    return False

def extract_financials_with_fallback(text: str) -> Dict[str, Any]:
    """
    1. Coba LLM dulu (lebih akurat untuk tabel kompleks)
    2. Jika LLM tidak dapat data → pakai regex fallback
    3. Merge: field yang masih null di LLM diisi dari regex
    """
    llm_result = llm_extract_financials(text)
    regex_result = regex_extract_financials(text)

    if not regex_result:
        return llm_result

    if not _has_financial_data(llm_result):
        # LLM gagal total → pakai regex sepenuhnya
        return regex_result

    # Merge: isi field yang masih null di LLM dengan regex
    # Saham & harga
    for k in ["total_saham_beredar", "harga_penawaran_angka",
              "total_ekuitas_terakhir", "total_liabilitas_terakhir"]:
        if llm_result.get(k) is None and regex_result.get(k) is not None:
            llm_result[k] = regex_result[k]

    # Isi nilai null per tahun dari regex
    regex_by_year = {str(d.get("tahun","")): d for d in regex_result.get("data_per_tahun", [])}
    for yr_data in llm_result.get("data_per_tahun", []):
        y = str(yr_data.get("tahun", ""))
        if y in regex_by_year:
            for k in ["pendapatan", "laba_kotor", "laba_usaha", "laba_bersih"]:
                if yr_data.get(k) is None and regex_by_year[y].get(k) is not None:
                    yr_data[k] = regex_by_year[y][k]

    return llm_result

# ══════════════════════════════════════════════════════════════════
# NORMALIZE & COMPUTE KPI
# ══════════════════════════════════════════════════════════════════

def normalize_and_compute(fin_raw: Dict, fx_rate: Optional[float]) -> Tuple[Dict, Dict]:
    unit     = (fin_raw.get("satuan") or "full").lower()
    currency = (fin_raw.get("mata_uang") or "IDR").upper()

    years_data = []
    for d in fin_raw.get("data_per_tahun", []):
        nd = dict(d)
        for k in ["pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"]:
            nd[k] = apply_unit(nd.get(k), unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data = sorted(years_data, key=lambda x: x.get("tahun",""))

    ekuitas    = apply_unit(fin_raw.get("total_ekuitas_terakhir"), unit)
    liabilitas = apply_unit(fin_raw.get("total_liabilitas_terakhir"), unit)
    saham      = parse_number(fin_raw.get("total_saham_beredar"))
    harga      = parse_number(fin_raw.get("harga_penawaran_angka"))

    revenue_growth, gross_margin, op_margin, ebitda_margin, net_margin = [], [], [], [], []
    prev_rev = None
    for yr in years_data:
        y   = str(yr.get("tahun",""))
        rev = yr.get("pendapatan")
        gp  = yr.get("laba_kotor")
        op  = yr.get("laba_usaha")
        net = yr.get("laba_bersih")
        dep = yr.get("depresiasi")

        revenue_growth.append({"year": y, "value": 0.0 if prev_rev is None else calc_growth(rev, prev_rev)})
        prev_rev = rev
        gross_margin.append({"year": y, "value": pct(safe_div(gp, rev))})
        op_margin.append({"year": y, "value": pct(safe_div(op, rev))})
        if dep is not None and op is not None and rev:
            ebitda_margin.append({"year": y, "value": pct(safe_div(float(op)+float(dep), rev))})
        else:
            ebitda_margin.append({"year": y, "value": None})
        net_margin.append({"year": y, "value": pct(safe_div(net, rev))})

    kpi = {"pe": "N/A", "pb": "N/A", "roe": "N/A", "der": "N/A", "eps": "N/A"}
    laba_bersih = years_data[-1].get("laba_bersih") if years_data else None

    try:
        if saham and laba_bersih and saham > 0:
            eps_val = laba_bersih / saham
            kpi["eps"] = f"Rp {eps_val:,.2f}".replace(",",".") if currency=="IDR" else f"USD {eps_val:.6f}"
            if harga and eps_val != 0:
                price_ccy = harga / fx_rate if (currency == "USD" and fx_rate and fx_rate > 0) else harga
                pe = price_ccy / eps_val
                kpi["pe"] = f"{pe:.1f}x" if pe > 0 else "N/A (Rugi)"
    except:
        pass

    try:
        if ekuitas and saham and saham > 0 and harga:
            bvps = ekuitas / saham
            if bvps > 0:
                price_ccy = harga / (fx_rate or 1) if currency=="USD" else harga
                kpi["pb"] = f"{price_ccy/bvps:.2f}x"
    except:
        pass

    try:
        if ekuitas and laba_bersih and ekuitas > 0:
            kpi["roe"] = f"{(laba_bersih/ekuitas)*100:.1f}%"
    except:
        pass

    try:
        if ekuitas and liabilitas and ekuitas > 0:
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
    except:
        pass

    kpi["market_cap"] = "N/A"
    try:
        if saham and harga and saham > 0 and harga > 0:
            mc = saham * harga
            if currency == "IDR":
                if mc >= 1_000_000_000_000:
                    kpi["market_cap"] = f"Rp {mc/1_000_000_000_000:.2f} Triliun"
                else:
                    kpi["market_cap"] = f"Rp {mc/1_000_000_000:.2f} Miliar"
            else:
                kpi["market_cap"] = f"USD {mc:,.0f}"
    except:
        pass

    financial = {
        "currency":          currency,
        "years":             [str(d.get("tahun","")) for d in years_data],
        "absolute_data":     years_data,
        "revenue_growth":    revenue_growth or None,
        "gross_margin":      gross_margin   or None,
        "operating_margin":  op_margin      or None,
        "ebitda_margin":     ebitda_margin  or None,
        "net_profit_margin": net_margin     or None,
    }
    return financial, kpi

# ══════════════════════════════════════════════════════════════════
# LLM QUALITATIVE
# ══════════════════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str = "ID") -> Dict:
    is_en    = lang.upper() == "EN"
    currency = financial.get("currency", "IDR")

    lang_instruction = (
        "LANGUAGE: Write ALL output in ENGLISH. Only company_name, ticker, ipo_date stay as-is."
    ) if is_en else (
        "BAHASA: Tulis SEMUA output dalam Bahasa Indonesia. Hanya company_name, ticker, ipo_date dari dokumen."
    )

    currency_note = f"Gunakan mata uang {currency} sesuai prospektus untuk semua nilai uang."

    prompt = f"""Kamu adalah analis IPO senior. Analisis prospektus berikut.

{lang_instruction}
{currency_note}

DATA REFERENSI SUDAH DIHITUNG SISTEM (jangan hitung ulang, salin langsung):
- Market Cap  : {kpi.get('market_cap', 'N/A')}
- KPI Lengkap : {json.dumps(kpi, ensure_ascii=False)}
- Tahun data  : {financial.get('years', [])}

TUGAS — Hasilkan JSON analisis lengkap:

1. IDENTITAS: company_name, ticker (2-6 huruf kapital IDX), sector, ipo_date, share_price, total_shares, market_cap (SALIN PERSIS dari DATA REFERENSI)

2. SUMMARY: 3 paragraf {'in English' if is_en else 'Bahasa Indonesia'} spesifik dengan angka. Pisahkan dengan \\n\\n.

3. PENGGUNAAN DANA IPO:
   Cari: "Rencana Penggunaan Dana" / "Use of Proceeds"
   - Minimal 2 item, maksimal 6 item
   - allocation: persentase PERSIS dari dokumen, total = 100
   - DILARANG membuat allocation 50/50 atau angka bulat yang tidak ada di dokumen

4. PENJAMIN EMISI: lead, others (array), type, reputation

5. RISIKO: overall_risk_level (High/Medium/Low), overall_risk_reason, risks (3-5 item)

6. BENEFIT: 4-6 keunggulan spesifik dengan angka konkret

ATURAN: Output JSON murni tanpa markdown.

DOKUMEN:
{text[:400000]}

OUTPUT JSON:
{{
  "company_name": "...", "ticker": "", "sector": "...", "ipo_date": "...",
  "share_price": "...", "total_shares": "...", "market_cap": "...",
  "summary": "...",
  "use_of_funds": [{{"category": "...", "description": "...", "allocation": 60}}],
  "underwriter": {{"lead": "...", "others": [], "type": "...", "reputation": "..."}},
  "overall_risk_level": "Medium", "overall_risk_reason": "...",
  "risks": [{{"level": "Medium", "title": "...", "desc": "..."}}],
  "benefits": [{{"title": "...", "desc": "..."}}]
}}"""

    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.1,
        max_tokens=12000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        for p in raw.split("```"):
            p = p.strip().lstrip("json").strip()
            if p.startswith("{"):
                raw = p
                break

    s = raw.find("{")
    e = raw.rfind("}") + 1
    if s != -1 and e > s:
        raw = raw[s:e]

    try:
        return json.loads(raw)
    except:
        fixed = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            return json.loads(fixed)
        except:
            for i in range(len(fixed), 0, -100):
                try:
                    return json.loads(fixed[:i])
                except:
                    continue
            raise ValueError(f"Tidak bisa parse JSON: {raw[:300]}")

# ══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════

def analyze_prospectus(text: str, lang: str = "ID") -> dict:
    fx_rate          = detect_fx_rate(text)
    fin_raw          = extract_financials_with_fallback(text)  # LLM + regex fallback
    financial, kpi   = normalize_and_compute(fin_raw, fx_rate)
    result           = llm_qualitative(text, kpi, financial, lang=lang)
    result["financial"] = financial
    result["kpi"]       = kpi
    return result