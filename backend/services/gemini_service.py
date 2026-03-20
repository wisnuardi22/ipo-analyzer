from __future__ import annotations
from openai import OpenAI
import json, re, os, math
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)
MODEL = "gemini/gemini-2.5-flash"

# ══════════════════════════════════════════════════════
# UTILITIES (dari ipo_kpi_analyzer v2)
# ══════════════════════════════════════════════════════

def parse_numeric_id_style(raw: Optional[str], force_thousands: bool = False) -> Optional[float]:
    if raw is None: return None
    s = raw.strip()
    if not s: return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True; s = s[1:-1]
    s2 = re.sub(r'[^0-9,\.\-]', '', s)
    if '.' in s2 and ',' in s2:
        s2 = s2.replace('.', '').replace(',', '.')
    elif ',' in s2 and '.' not in s2:
        s2 = s2.replace(',', '')
    elif '.' in s2 and ',' not in s2:
        if force_thousands or re.match(r'^\d{1,3}(\.\d{3})+$', s2):
            s2 = s2.replace('.', '')
    try:
        val = float(s2)
        return -val if neg else val
    except: return None

def parse_money_idr(raw: Optional[str]) -> Optional[float]:
    return parse_numeric_id_style(raw, force_thousands=True)

def pct(val) -> Optional[float]:
    if val is None: return None
    try:
        v = float(val)
        return round(v * 100.0, 2) if not math.isnan(v) else None
    except: return None

def safe_div(a, b) -> Optional[float]:
    try:
        if a is None or b is None or float(b) == 0: return None
        return float(a) / float(b)
    except: return None

def calc_growth(cur, prev) -> Optional[float]:
    try:
        if cur is None or prev is None or float(prev) == 0: return None
        return round(((float(cur) - float(prev)) / abs(float(prev))) * 100, 2)
    except: return None

def apply_unit(val, unit: str) -> Optional[float]:
    if val is None: return None
    try:
        v = float(val)
        if unit == "jutaan": return v * 1_000_000.0
        if unit == "ribuan": return v * 1_000.0
        return v
    except: return None

def detect_currency_and_unit(text: str) -> Tuple[str, str]:
    t = text.lower()
    currency = "USD" if ("us$" in t or "usd" in t or "dolar amerika" in t) else "IDR"
    unit = "full"
    if re.search(r'dalam\s+jutaan', t): unit = "jutaan"
    elif re.search(r'dalam\s+ribuan', t): unit = "ribuan"
    return currency, unit

def detect_fx_rate(text: str) -> Optional[float]:
    m = re.search(r'kurs.*?rp\s*([0-9\.\,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)', text, flags=re.I)
    if m:
        val = parse_money_idr(m.group(1))
        if val and val > 0: return float(val)
    return None

def chunk_text(s: str, max_len: int = 12000, overlap: int = 400) -> List[str]:
    if not s or len(s) <= max_len: return [s or ""]
    chunks = []
    i = 0
    while i < len(s):
        chunks.append(s[i:i + max_len])
        i += max(1, max_len - overlap)
    return chunks

# ══════════════════════════════════════════════════════
# REGEX FALLBACK EXTRACTOR (v2)
# ══════════════════════════════════════════════════════

ROW_ALIASES = {
    "pendapatan": ["pendapatan bersih", "total pendapatan", "pendapatan", "revenue", "net revenue"],
    "laba_kotor": ["laba kotor", "gross profit"],
    "laba_usaha": ["laba usaha", "laba (rugi) usaha", "rugi usaha", "operating profit", "operating loss", "laba operasi"],
    "laba_bersih": ["laba (rugi) bersih", "laba bersih", "laba periode", "rugi periode",
                    "laba tahun berjalan", "rugi tahun berjalan", "net profit", "net income",
                    "laba (rugi) yang dapat diatribusikan kepada pemilik entitas induk"],
    "depresiasi": ["depresiasi", "penyusutan", "amortisasi", "depreciation", "amortization"],
}

BALANCE_ALIASES = {
    "total_ekuitas": ["jumlah ekuitas", "total ekuitas", "jumlah ekuitas yang dapat diatribusikan", "equity"],
    "total_liabilitas": ["jumlah liabilitas", "total liabilitas", "liabilities"],
}

def regex_extract_financials(text: str) -> Dict[str, Any]:
    # Cari blok laporan laba rugi
    m1 = re.search(
        r'(laporan laba rugi|ikhtisar data keuangan).*?(?=rasio keuangan|informasi nilai kurs|penggunaan dana|\Z)',
        text, flags=re.I | re.S
    )
    laba_rugi = m1.group(0) if m1 else text

    years = sorted(set(re.findall(r'(20[12][0-9])', text)))

    def pick_row(block: str, aliases: List[str]) -> List[Optional[float]]:
        bl = block.lower()
        for alias in aliases:
            m = re.search(rf'(?:^|\n)\s*{re.escape(alias)}\b.*$', bl, flags=re.M | re.I)
            if not m:
                m = re.search(rf'{re.escape(alias)}.*', bl, flags=re.I)
            if m:
                raw_line = block[m.start():m.end()]
                nums = re.findall(r'[\(\)0-9\.\,\-]+', raw_line)
                parsed = [parse_numeric_id_style(x, force_thousands=True) for x in nums]
                return [x for x in parsed if x is not None and abs(x) > 0]
        return []

    row_vals = {k: pick_row(laba_rugi, v) for k, v in ROW_ALIASES.items()}
    valid_cols = min([len(v) for v in row_vals.values() if v], default=0)

    def build_years(vals, reverse: bool):
        y_sorted = sorted([int(y) for y in years if y.isdigit()])[-5:]
        if reverse: y_sorted = list(reversed(y_sorted))
        out = []
        for i, y in enumerate(y_sorted[:valid_cols]):
            out.append({
                "tahun": str(y),
                "pendapatan": vals["pendapatan"][i] if i < len(vals.get("pendapatan", [])) else None,
                "laba_kotor": vals["laba_kotor"][i] if i < len(vals.get("laba_kotor", [])) else None,
                "laba_usaha": vals["laba_usaha"][i] if i < len(vals.get("laba_usaha", [])) else None,
                "laba_bersih": vals["laba_bersih"][i] if i < len(vals.get("laba_bersih", [])) else None,
                "depresiasi": vals["depresiasi"][i] if i < len(vals.get("depresiasi", [])) else None,
            })
        return out

    def score(records):
        s = 0
        for r in records:
            rev, gp = r.get("pendapatan"), r.get("laba_kotor")
            if rev and gp and rev != 0:
                gm = gp / rev
                if 0 <= gm <= 1.5: s += 1
        return s

    c1, c2 = build_years(row_vals, False), build_years(row_vals, True)
    data_per_tahun = c1 if score(c1) >= score(c2) else c2

    # Neraca
    m2 = re.search(r'laporan posisi keuangan.*?(?=laporan laba rugi|rasio keuangan|\Z)', text, flags=re.I | re.S)
    posisi = m2.group(0) if m2 else text

    def find_balance(block, aliases):
        bl = block.lower()
        for alias in aliases:
            m = re.search(rf'{re.escape(alias)}.*?([\(\)0-9\.\,]+)\s*$', bl, flags=re.M)
            if not m:
                m = re.search(rf'{re.escape(alias)}.*?([\(\)0-9\.\,]+)', bl)
            if m:
                return parse_numeric_id_style(m.group(1), force_thousands=True)
        return None

    total_ekuitas    = find_balance(posisi, BALANCE_ALIASES["total_ekuitas"])
    total_liabilitas = find_balance(posisi, BALANCE_ALIASES["total_liabilitas"])

    # Harga penawaran
    harga = None
    for pat in [r'harga penawaran.*?rp\s*([\d\.\,]+)', r'harga saham.*?rp\s*([\d\.\,]+)', r'offering price.*?rp\s*([\d\.\,]+)']:
        m = re.search(pat, text, flags=re.I)
        if m:
            harga = parse_money_idr(m.group(1))
            break

    # Total saham
    saham_candidates = []
    for alias in ["jumlah saham yang akan dicatatkan","jumlah saham yang dicatatkan","jumlah saham"]:
        for m in re.finditer(rf'{alias}.*?([\d\.\,]+)', text, flags=re.I):
            v = parse_numeric_id_style(m.group(1), force_thousands=True)
            if v and v >= 1_000_000:
                saham_candidates.append(v)
    total_saham = max(saham_candidates) if saham_candidates else None

    currency, unit = detect_currency_and_unit(text)
    return {
        "satuan": unit, "mata_uang": currency,
        "tahun_tersedia": [r["tahun"] for r in data_per_tahun],
        "data_per_tahun": data_per_tahun,
        "total_ekuitas_terakhir": total_ekuitas,
        "total_liabilitas_terakhir": total_liabilitas,
        "total_saham_beredar": total_saham,
        "harga_penawaran_angka": harga,
    }

# ══════════════════════════════════════════════════════
# LLM EXTRACTOR (multi-chunk, merge results)
# ══════════════════════════════════════════════════════

def llm_extract_financials(text: str) -> Dict[str, Any]:
    merged = {
        "satuan": None, "mata_uang": None,
        "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas_terakhir": None, "total_liabilitas_terakhir": None,
        "total_saham_beredar": None, "harga_penawaran_angka": None
    }

    sys_prompt = """Kamu adalah akuntan Indonesia. Ekstrak angka mentah dari potongan prospektus.
Output HANYA JSON murni:
{
  "satuan": "full|jutaan|ribuan",
  "mata_uang": "IDR|USD",
  "tahun_tersedia": ["2023","2024"],
  "data_per_tahun": [{"tahun":"2023","pendapatan":75765791,"laba_kotor":6378346,"laba_usaha":8234,"laba_bersih":234567,"depresiasi":null}],
  "total_ekuitas_terakhir": 1234567890,
  "total_liabilitas_terakhir": 987654321,
  "total_saham_beredar": 5000000000,
  "harga_penawaran_angka": 500
}
PENTING:
- Catat angka PERSIS dari tabel (sesuai satuan yang tertulis di header tabel)
- Cari: "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN KONSOLIDASIAN", "Ikhtisar Data Keuangan Penting"
- Null jika tidak ada"""

    # Pilih chunk yang relevan
    all_chunks = chunk_text(text, max_len=12000, overlap=400)
    kw = ["laporan laba rugi", "ikhtisar data keuangan", "pendapatan bersih", "laba kotor", "gross profit",
          "laporan posisi keuangan", "jumlah ekuitas", "harga penawaran"]
    priority = [c for c in all_chunks if any(k in c.lower() for k in kw)]
    if all_chunks and all_chunks[0] not in priority: priority.insert(0, all_chunks[0])
    if len(all_chunks) > 1 and all_chunks[-1] not in priority: priority.append(all_chunks[-1])
    selected = priority[:6]

    def safe_json(s: str) -> Optional[dict]:
        s = s.strip()
        if "```" in s:
            for p in s.split("```"):
                p = p.strip().lstrip("json").strip()
                if p.startswith("{"): s = p; break
        si, ei = s.find("{"), s.rfind("}")
        if si != -1 and ei > si:
            try: return json.loads(s[si:ei+1])
            except:
                try: return json.loads(re.sub(r',\s*([}\]])', r'\1', s[si:ei+1]))
                except: return None
        return None

    for chunk in selected:
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=0.05, max_tokens=3000,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"DOKUMEN:\n{chunk}"}
                ]
            )
            part = safe_json(resp.choices[0].message.content) or {}
        except: part = {}

        if not merged["satuan"] and part.get("satuan"): merged["satuan"] = part["satuan"]
        if not merged["mata_uang"] and part.get("mata_uang"): merged["mata_uang"] = part["mata_uang"]
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(set(merged["tahun_tersedia"]) | set(part["tahun_tersedia"]))
        if part.get("data_per_tahun"):
            m_dict = {d["tahun"]: d for d in merged["data_per_tahun"] if d.get("tahun")}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun","")).strip()
                if not y: continue
                if y in m_dict:
                    for k in ["pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"]:
                        if m_dict[y].get(k) is None and d.get(k) is not None:
                            m_dict[y][k] = d[k]
                else: m_dict[y] = d
            merged["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]
        for k in ["total_ekuitas_terakhir","total_liabilitas_terakhir","total_saham_beredar","harga_penawaran_angka"]:
            if merged.get(k) is None and part.get(k) is not None: merged[k] = part[k]

    return merged

# ══════════════════════════════════════════════════════
# MERGE LLM + REGEX, NORMALIZE, COMPUTE
# ══════════════════════════════════════════════════════

def merge_fin(llm: Dict, regex: Dict) -> Dict:
    def pick(a, b): return a if a not in [None, [], ""] else b
    return {
        "satuan":                    pick(llm.get("satuan"), regex.get("satuan")),
        "mata_uang":                 pick(llm.get("mata_uang"), regex.get("mata_uang")),
        "tahun_tersedia":            pick(llm.get("tahun_tersedia"), regex.get("tahun_tersedia")),
        "data_per_tahun":            pick(llm.get("data_per_tahun"), regex.get("data_per_tahun")),
        "total_ekuitas_terakhir":    pick(llm.get("total_ekuitas_terakhir"), regex.get("total_ekuitas_terakhir")),
        "total_liabilitas_terakhir": pick(llm.get("total_liabilitas_terakhir"), regex.get("total_liabilitas_terakhir")),
        "total_saham_beredar":       pick(llm.get("total_saham_beredar"), regex.get("total_saham_beredar")),
        "harga_penawaran_angka":     pick(llm.get("harga_penawaran_angka"), regex.get("harga_penawaran_angka")),
    }

def normalize_and_compute(fin_raw: Dict, fx_rate: Optional[float]) -> Tuple[Dict, Dict]:
    unit     = (fin_raw.get("satuan") or "full").lower()
    currency = (fin_raw.get("mata_uang") or "IDR").upper()

    # Normalisasi ke angka penuh
    years_data = []
    for d in fin_raw.get("data_per_tahun", []):
        nd = dict(d)
        for k in ["pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"]:
            nd[k] = apply_unit(nd.get(k), unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data = sorted(years_data, key=lambda x: x.get("tahun",""))

    ekuitas    = apply_unit(fin_raw.get("total_ekuitas_terakhir"), unit)
    liabilitas = apply_unit(fin_raw.get("total_liabilitas_terakhir"), unit)
    saham      = fin_raw.get("total_saham_beredar")
    harga      = fin_raw.get("harga_penawaran_angka")

    # Hitung tren
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

    # Hitung KPI
    kpi = {"pe": "N/A", "pb": "N/A", "roe": "N/A", "der": "N/A", "eps": "N/A"}
    laba_bersih = years_data[-1].get("laba_bersih") if years_data else None

    try:
        if saham and laba_bersih and float(saham) > 0:
            eps_val = float(laba_bersih) / float(saham)
            kpi["eps"] = f"Rp {eps_val:,.2f}".replace(",",".") if currency=="IDR" else f"USD {eps_val:.6f}"
            if harga and eps_val != 0:
                price_ccy = float(harga) / (fx_rate or 1) if currency == "USD" else float(harga)
                pe = price_ccy / eps_val
                kpi["pe"] = f"{pe:.1f}x" if pe > 0 else "N/A (Rugi)"
    except: pass

    try:
        if ekuitas and saham and float(saham) > 0 and harga:
            bvps = float(ekuitas) / float(saham)
            if bvps > 0:
                price_ccy = float(harga) / (fx_rate or 1) if currency == "USD" else float(harga)
                kpi["pb"] = f"{price_ccy/bvps:.2f}x"
    except: pass

    try:
        if ekuitas and laba_bersih and float(ekuitas) > 0:
            kpi["roe"] = f"{(float(laba_bersih)/float(ekuitas))*100:.1f}%"
    except: pass

    try:
        if ekuitas and liabilitas and float(ekuitas) > 0:
            kpi["der"] = f"{float(liabilitas)/float(ekuitas):.2f}x"
    except: pass

    financial = {
        "currency":          currency,
        "years":             [d.get("tahun","") for d in years_data],
        "revenue_growth":    revenue_growth or None,
        "gross_margin":      gross_margin   or None,
        "operating_margin":  op_margin      or None,
        "ebitda_margin":     ebitda_margin  or None,
        "net_profit_margin": net_margin     or None,
    }
    return financial, kpi

# ══════════════════════════════════════════════════════
# ANALISIS KUALITATIF
# ══════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict) -> Dict:
    prompt = f"""Kamu adalah analis IPO Indonesia senior (CFA Level 3). Analisis prospektus berikut.

DATA KPI SUDAH DIHITUNG: {json.dumps(kpi, ensure_ascii=False)}
TAHUN DATA: {financial.get('years', [])}

TUGAS — hasilkan JSON analisis lengkap:

1. IDENTITAS: company_name, ticker (dari pengetahuanmu - kosong jika tidak tahu), sector (spesifik), ipo_date, share_price (dengan "Rp"), total_shares, market_cap

2. SUMMARY: 3 paragraf Bahasa Indonesia awam, pisahkan \\n\\n, spesifik dengan angka

3. PENGGUNAAN DANA IPO — WAJIB minimal 2 item:
   Cari: "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum"
   allocation total = 100, description SPESIFIK

4. PENJAMIN EMISI: lead, others[], type, reputation

5. RISIKO: overall_risk_level, overall_risk_reason, risks (3-5 item)

6. BENEFIT: 4-6 item spesifik dengan angka

Output JSON murni, tidak ada teks lain.

DOKUMEN:
{text[:400000]}

OUTPUT:
{{"company_name":"...","ticker":"","sector":"...","ipo_date":"...","share_price":"...","total_shares":"...","market_cap":"...","summary":"...","use_of_funds":[{{"category":"...","description":"...","allocation":60}}],"underwriter":{{"lead":"...","others":[],"type":"...","reputation":"..."}},"overall_risk_level":"Medium","overall_risk_reason":"...","risks":[{{"level":"Medium","title":"...","desc":"..."}}],"benefits":[{{"title":"...","desc":"..."}}]}}"""

    resp = client.chat.completions.create(
        model=MODEL, temperature=0.1, max_tokens=12000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.choices[0].message.content.strip()
    if "```" in raw:
        for p in raw.split("```"):
            p = p.strip().lstrip("json").strip()
            if p.startswith("{"): raw = p; break
    s, e = raw.find("{"), raw.rfind("}") + 1
    if s != -1 and e > s: raw = raw[s:e]
    try: return json.loads(raw)
    except:
        fixed = re.sub(r',\s*([}\]])', r'\1', raw)
        try: return json.loads(fixed)
        except:
            for i in range(len(fixed), 0, -100):
                try: return json.loads(fixed[:i])
                except: continue
            raise ValueError(f"JSON error: {raw[:300]}")

# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

def analyze_prospectus(text: str) -> dict:
    # 1. Deteksi kurs FX
    fx_rate = detect_fx_rate(text)

    # 2. Ekstrak angka — LLM + regex fallback, lalu merge
    fin_llm   = llm_extract_financials(text)
    fin_regex = regex_extract_financials(text)
    fin_raw   = merge_fin(fin_llm, fin_regex)

    # 3. Normalisasi & hitung metrik (Python, bukan LLM)
    financial, kpi = normalize_and_compute(fin_raw, fx_rate)

    # 4. Analisis kualitatif (LLM)
    result = llm_qualitative(text, kpi, financial)

    # 5. Gabungkan
    result["financial"] = financial
    result["kpi"]       = kpi
    return result