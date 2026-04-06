"""
gemini_service.py - IPO Analyzer
Pipeline:
  1. Detect metadata (currency, unit, fx_rate)
  2. LLM financial extraction (multi-chunk, baca semua halaman keuangan)
  3. Python KPI computation
  4. LLM qualitative (Basic: ringkas | Pro: detail penuh)
"""
from __future__ import annotations
import json, logging, math, os, re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.environ.get("SUMOPOD_API_KEY"),
    base_url="https://ai.sumopod.com/v1",
)
MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = "gemini/gemini-2.5-pro"
MODEL       = MODEL_FLASH  # backward compat

# ══════════════════════════════════════════════════════════════════════
# 1. NUMBER UTILITIES
# ══════════════════════════════════════════════════════════════════════

def parse_num(raw: Any) -> Optional[float]:
    if raw is None: return None
    if isinstance(raw, (int, float)): return float(raw)
    s = str(raw).strip()
    if not s or s.lower() in ("null","n/a","-",""): return None
    neg = False
    if s.startswith("(") and s.endswith(")"): neg, s = True, s[1:-1]
    elif s.startswith("-"): neg, s = True, s[1:]
    s = re.sub(r"[^0-9.,]","",s)
    if not s: return None
    if "." in s and "," in s:
        s = s.replace(".","").replace(",",".") if s.rfind(",")>s.rfind(".") else s.replace(",","")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",",".") if len(parts)==2 and len(parts[1])<=2 else s.replace(",","")
    elif "." in s:
        parts = s.split(".")
        if not (len(parts)==2 and len(parts[1])<=2): s = s.replace(".","")
    try:
        v = float(s); return -v if neg else v
    except: return None

def apply_unit(val: Any, unit: str) -> Optional[float]:
    v = parse_num(val)
    if v is None: return None
    return v * {"jutaan":1_000_000,"ribuan":1_000,"miliar":1_000_000_000,"triliun":1_000_000_000_000}.get((unit or "").lower(),1)

def safe_div(a: Any, b: Any) -> Optional[float]:
    try:
        af, bf = parse_num(a), parse_num(b)
        return af/bf if af is not None and bf else None
    except: return None

def to_pct(val: Any) -> Optional[float]:
    v = parse_num(val)
    return round(v*100,2) if v is not None and not math.isnan(v) else None

def calc_growth(cur: Any, prev: Any) -> Optional[float]:
    c, p = parse_num(cur), parse_num(prev)
    if c is None or p is None or p==0: return None
    return round((c-p)/abs(p)*100,2)

def fmt_idr(value: float) -> str:
    if value>=1_000_000_000_000: return f"Rp {value/1_000_000_000_000:.2f} Triliun"
    if value>=1_000_000_000: return f"Rp {value/1_000_000_000:.2f} Miliar"
    return f"Rp {value:,.0f}".replace(",",".")

# ══════════════════════════════════════════════════════════════════════
# 2. METADATA DETECTION
# ══════════════════════════════════════════════════════════════════════

def detect_currency(text: str) -> str:
    t = text[:5000].lower()
    return "USD" if ("us$" in t or " usd" in t or "dolar amerika" in t) else "IDR"

def detect_unit(text: str) -> str:
    t = text[:10000].lower()
    if re.search(r"dalam\s+jutaan",t): return "jutaan"
    if re.search(r"dalam\s+ribuan",t): return "ribuan"
    if re.search(r"dalam\s+miliar",t): return "miliar"
    return "full"

def detect_fx_rate(text: str) -> Optional[float]:
    for pat in [r"kurs.*?rp\s*([\d.,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)", r"rp\s*([\d.,]+)\s*/\s*us\$"]:
        m = re.search(pat, text[:20000], re.I)
        if m:
            v = parse_num(m.group(1))
            if v and v>1000: return float(v)
    return None

# ══════════════════════════════════════════════════════════════════════
# 3. LLM FINANCIAL EXTRACTION (MULTI-CHUNK)
# ══════════════════════════════════════════════════════════════════════

_FIN_KEYWORDS = [
    "laporan laba rugi","ikhtisar data keuangan","data keuangan penting",
    "ringkasan keuangan","informasi keuangan","laba kotor","laba usaha",
    "laba bersih","pendapatan usaha","pendapatan bersih","penjualan bersih",
    "posisi keuangan","neraca","ekuitas","liabilitas","31 desember",
    "rasio keuangan","rasio penting","rasio keuangan penting","konsolidasian","consolidated",
    "gross profit","net revenue","operating profit","net income","profit or loss",
    "statement of profit","balance sheet","selected financial","financial highlights",
    "total aset","total assets","return on equity","return on asset",
    "debt to equity","earnings per share","laba per saham","imbal hasil",
]

_FIN_SYSTEM = """Kamu adalah akuntan senior Indonesia. Tugasmu: ekstrak data keuangan LENGKAP dari potongan prospektus IPO.
Output HANYA JSON murni tanpa teks lain, tanpa markdown.

LANGKAH EKSTRAKSI:

STEP 1 - LAPORAN LABA RUGI / INCOME STATEMENT
Cari tabel dengan judul:
- "LAPORAN LABA RUGI (RUGI)" / "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN"
- "IKHTISAR DATA KEUANGAN PENTING" / "DATA KEUANGAN PENTING"
- "SELECTED FINANCIAL DATA" / "RINGKASAN KEUANGAN"
Baca header kolom = tahun-tahun yang tersedia.
Untuk SETIAP tahun ekstrak (tulis angka PERSIS dari dokumen):
  pendapatan  = Total Pendapatan / Net Revenue / Penjualan Bersih
  laba_kotor  = Laba Kotor / Gross Profit
  laba_usaha  = Laba/Rugi Usaha / Operating Profit (bisa negatif)
  laba_bersih = Laba/Rugi Bersih / Net Profit (bisa negatif)
  depresiasi  = Depresiasi & Amortisasi (null jika tidak ada)

STEP 2 - TABEL RASIO KEUANGAN PENTING (WAJIB DIBACA)
Cari tabel dengan judul:
- "RASIO KEUANGAN PENTING" / "RASIO KEUANGAN" / "KEY FINANCIAL RATIOS"
- "RASIO-RASIO PENTING" / "INFORMASI KEUANGAN LAINNYA"
Tabel ini biasanya ada SETELAH tabel laporan laba rugi.
Untuk SETIAP tahun yang ada di kolom header tabel ini, ekstrak PERSIS angka yang tertulis:
  roe           = ROE / Imbal Hasil Ekuitas / Return on Equity (%)
  roa           = ROA / Imbal Hasil Aset / Return on Asset (%)
  der           = DER / Rasio Utang thd Ekuitas / Debt to Equity Ratio (x)
  npm           = NPM / Margin Laba Bersih / Net Profit Margin (%)
  gpm           = GPM / Margin Laba Kotor / Gross Profit Margin (%)
  eps           = EPS / Laba per Saham / Earnings per Share (Rp atau angka)
  current_ratio = Rasio Lancar / Current Ratio (x)
PENTING: SALIN angka PERSIS dari tabel. JANGAN hitung sendiri!

STEP 3 - NERACA / BALANCE SHEET
Dari tabel posisi keuangan, ambil data tahun TERAKHIR:
  total_ekuitas    = Total Ekuitas / Total Equity
  total_liabilitas = Total Liabilitas / Total Liabilities
  total_aset       = Total Aset / Total Assets

STEP 4 - INFO IPO
  total_saham_beredar = Total saham beredar SETELAH IPO (dari halaman depan)
  harga_penawaran     = Harga per saham (angka saja, null jika DRHP/belum final)

ATURAN:
- satuan: "jutaan" / "ribuan" / "miliar" / "full" (baca dari header tabel)
- Angka negatif dalam kurung (1.234.567) → tulis -1234567
- Jika tidak ada data di potongan ini → kembalikan struktur kosong

OUTPUT JSON WAJIB:
{
  "satuan": "jutaan",
  "mata_uang": "IDR",
  "tahun_tersedia": ["2022","2023","2024","2025 (9M)"],
  "data_per_tahun": [
    {"tahun":"2022","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}
  ],
  "rasio_per_tahun": [
    {"tahun":"2022","roe":null,"roa":null,"der":null,"npm":null,"gpm":null,"eps":null,"current_ratio":null}
  ],
  "total_ekuitas": null,
  "total_liabilitas": null,
  "total_aset": null,
  "total_saham_beredar": null,
  "harga_penawaran": null
}"""

def _chunk_text(text: str, max_len: int=18000, overlap: int=800) -> List[str]:
    if len(text)<=max_len: return [text]
    chunks, i = [], 0
    while i<len(text):
        chunks.append(text[i:i+max_len])
        i += max_len-overlap
    return chunks

def _safe_json(raw: str) -> Optional[dict]:
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"): raw = part; break
    s, e = raw.find("{"), raw.rfind("}")
    if s==-1 or e<=s: return None
    snippet = raw[s:e+1]
    for attempt in [snippet, re.sub(r",\s*([}\]])",r"\1",snippet)]:
        try: return json.loads(attempt)
        except: pass
    return None

def llm_extract_financials(text: str, model: str=None) -> Dict[str, Any]:
    _m = model or MODEL_FLASH
    merged: Dict[str, Any] = {
        "satuan":None,"mata_uang":None,
        "tahun_tersedia":[],"data_per_tahun":[],
        "rasio_per_tahun":[],
        "total_ekuitas":None,"total_liabilitas":None,"total_aset":None,
        "total_saham_beredar":None,"harga_penawaran":None,
    }
    all_chunks = _chunk_text(text, max_len=18000, overlap=800)

    # Pilih chunk prioritas - yang mengandung kata kunci keuangan
    priority, others = [], []
    for c in all_chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman")>5: continue
        if any(k in cl for k in _FIN_KEYWORDS): priority.append(c)
        else: others.append(c)

    # Ambil chunk strategis: priority + tengah + awal + akhir
    mid = len(all_chunks)//2
    selected = list(priority[:8])
    for idx in [0, mid-1, mid, mid+1, len(all_chunks)-1]:
        try:
            c = all_chunks[idx]
            if c not in selected: selected.append(c)
        except: pass
    selected = selected[:12]

    for chunk in selected:
        try:
            resp = client.chat.completions.create(
                model=_m, temperature=0.0, max_tokens=5000,
                messages=[
                    {"role":"system","content":_FIN_SYSTEM},
                    {"role":"user","content":f"EKSTRAK DATA KEUANGAN dari potongan ini:\n\n{chunk}"},
                ],
            )
            part = _safe_json(resp.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"FIN chunk error: {e}"); part = {}

        # Merge metadata
        for k in ("satuan","mata_uang"):
            if not merged[k] and part.get(k): merged[k] = part[k]

        # Merge tahun
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(set(merged["tahun_tersedia"])|{str(y) for y in part["tahun_tersedia"]})

        # Merge data_per_tahun
        if part.get("data_per_tahun"):
            m = {str(d.get("tahun","")).strip():d for d in merged["data_per_tahun"]}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun","")).strip()
                if not y: continue
                if y in m:
                    for k in ("pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"):
                        v = d.get(k)
                        if m[y].get(k) is None and v is not None and str(v).strip() not in ("null",""):
                            m[y][k] = v
                else: m[y] = d
            merged["data_per_tahun"] = [m[k] for k in sorted(m.keys())]

        # Merge rasio_per_tahun
        if part.get("rasio_per_tahun"):
            r = {str(x.get("tahun","")).strip():x for x in merged["rasio_per_tahun"]}
            for x in part["rasio_per_tahun"]:
                y = str(x.get("tahun","")).strip()
                if not y: continue
                if y in r:
                    for k in ("roe","roa","der","npm","gpm","eps","current_ratio"):
                        v = x.get(k)
                        if r[y].get(k) is None and v is not None and str(v).strip() not in ("null",""):
                            r[y][k] = v
                else: r[y] = x
            merged["rasio_per_tahun"] = [r[k] for k in sorted(r.keys())]

        # Merge scalar
        for k in ("total_ekuitas","total_liabilitas","total_aset","total_saham_beredar","harga_penawaran"):
            v = part.get(k)
            if merged.get(k) is None and v is not None and str(v).strip() not in ("null",""):
                merged[k] = v

    logger.info(f"[FIN] tahun={merged.get('tahun_tersedia')} saham={merged.get('total_saham_beredar')} harga={merged.get('harga_penawaran')} ekuitas={merged.get('total_ekuitas')} rasio={len(merged.get('rasio_per_tahun',[]))}")
    return merged

# ══════════════════════════════════════════════════════════════════════
# 4. NORMALIZE + COMPUTE KPI
# ══════════════════════════════════════════════════════════════════════

def normalize_and_compute(fin_raw: Dict, fx_rate: Optional[float]) -> Tuple[Dict, Dict]:
    unit     = (fin_raw.get("satuan") or "full").lower()
    currency = (fin_raw.get("mata_uang") or "IDR").upper()

    years_data = []
    for d in fin_raw.get("data_per_tahun",[]):
        nd = dict(d)
        for k in ("pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"):
            nd[k] = apply_unit(nd.get(k),unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data.sort(key=lambda x: str(x.get("tahun","")))

    ekuitas    = apply_unit(fin_raw.get("total_ekuitas"),unit)
    liabilitas = apply_unit(fin_raw.get("total_liabilitas"),unit)
    saham      = parse_num(fin_raw.get("total_saham_beredar"))
    harga      = parse_num(fin_raw.get("harga_penawaran"))
    harga_idr  = harga*fx_rate if (harga and currency=="USD" and fx_rate) else harga

    revenue_growth, gross_margin, op_margin, ebitda_margin, net_margin = [],[],[],[],[]
    prev_rev = None
    for yr in years_data:
        y   = str(yr.get("tahun",""))
        rev = yr.get("pendapatan")
        gp  = yr.get("laba_kotor")
        op  = yr.get("laba_usaha")
        net = yr.get("laba_bersih")
        dep = yr.get("depresiasi")
        revenue_growth.append({"year":y,"value":0.0 if prev_rev is None else calc_growth(rev,prev_rev)})
        prev_rev = rev
        gross_margin.append({"year":y,"value":to_pct(safe_div(gp,rev))})
        op_margin.append({"year":y,"value":to_pct(safe_div(op,rev))})
        ebitda_margin.append({
            "year":y,
            "value":to_pct(safe_div(float(op)+float(dep),rev)) if (dep is not None and op is not None and rev) else None
        })
        net_margin.append({"year":y,"value":to_pct(safe_div(net,rev))})

    kpi: Dict = {"pe":"N/A","pb":"N/A","roe":"N/A","der":"N/A","eps":"N/A","market_cap":"N/A",
                 "roe_by_year":{},"der_by_year":{},"eps_by_year":{}}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    # PRIORITAS: baca dari tabel Rasio Keuangan Penting
    rasio_list = fin_raw.get("rasio_per_tahun",[])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, key in [("roe","roe_by_year"),("der","der_by_year"),("eps","eps_by_year")]:
                v = parse_num(r.get(field))
                if v is not None: kpi[key][y] = v
        # Ambil tahun terakhir dari rasio
        last_r = rasio_list[-1] if rasio_list else {}
        roe_v = parse_num(last_r.get("roe"))
        der_v = parse_num(last_r.get("der"))
        eps_v = parse_num(last_r.get("eps"))
        if roe_v is not None: kpi["roe"] = f"{roe_v:.2f}%"
        if der_v is not None: kpi["der"] = f"{der_v:.2f}x"
        if eps_v is not None:
            kpi["eps"] = f"Rp {eps_v:,.2f}".replace(",",".") if currency=="IDR" else f"{eps_v:.2f}"

    # Fallback hitung HANYA jika tidak ada tabel rasio
    try:
        if saham and laba_last and saham>0 and kpi["eps"]=="N/A":
            eps_val = laba_last/saham
            kpi["eps"] = f"Rp {eps_val:,.2f}".replace(",",".") if currency=="IDR" else f"{currency} {eps_val:.4f}"
            if harga_idr and eps_val>0: kpi["pe"] = f"{harga_idr/eps_val:.1f}x"
            elif harga_idr and eps_val<0: kpi["pe"] = "N/A (Rugi)"
    except: pass
    try:
        if ekuitas and saham and saham>0 and harga_idr and ekuitas>0:
            bvps = ekuitas/saham
            if bvps>0: kpi["pb"] = f"{harga_idr/bvps:.2f}x"
    except: pass
    try:
        if not has_rasio and ekuitas and laba_last and ekuitas>0 and kpi["roe"]=="N/A":
            kpi["roe"] = f"{laba_last/ekuitas*100:.2f}%"
    except: pass
    try:
        if not has_rasio and ekuitas and liabilitas and ekuitas>0 and kpi["der"]=="N/A":
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
    except: pass
    try:
        if saham and harga and saham>0 and harga>0:
            mc = saham*(harga_idr if harga_idr else harga)
            kpi["market_cap"] = fmt_idr(mc)
    except: pass

    financial = {
        "currency":          currency,
        "years":             [str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun":   rasio_list,
        "absolute_data":     years_data,
        "revenue_growth":    revenue_growth or None,
        "gross_margin":      gross_margin or None,
        "operating_margin":  op_margin or None,
        "ebitda_margin":     ebitda_margin or None,
        "net_profit_margin": net_margin or None,
    }
    return financial, kpi

# ══════════════════════════════════════════════════════════════════════
# 5. LLM QUALITATIVE - BEDA BASIC VS PRO
# ══════════════════════════════════════════════════════════════════════

def _build_basic_prompt(text: str, kpi: Dict, financial: Dict, lang: str) -> str:
    """Basic prompt: ringkas, hanya info utama."""
    is_en = lang=="EN"
    currency = financial.get("currency","IDR")
    years    = financial.get("years",[])

    if is_en:
        return f"""You are an IPO analyst. Analyze this Indonesian IPO prospectus. Output ONLY JSON.

KPI DATA (copy exactly): {json.dumps(kpi, ensure_ascii=False)}
Financial years: {years}

Extract:
A. company_name, ticker (find "Kode Saham:"), sector, ipo_date, share_price, total_shares, market_cap (copy from KPI)
B. summary: 2 paragraphs in English. P1: company profile. P2: IPO details.
C. use_of_funds: Find "Use of Proceeds" section. Extract ALL items with EXACT percentages from document. Each item: category (exact name), description (specific with amounts), allocation (number). Total must = 100.
D. underwriter: lead, others (array), type, reputation (2 sentences)
E. risks: Find "Risk Factors" chapter. Extract 4-6 specific risks. Each: level (High/Medium/Low), title, desc (1-2 sentences with specific facts)
F. overall_risk_level: High/Medium/Low, overall_risk_reason: 2 sentences
G. benefits: 3-4 main competitive strengths with specific data

DOCUMENT:
{text[:200000]}

OUTPUT JSON:
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"","summary":"","use_of_funds":[{{"category":"","description":"","allocation":60}}],"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},"overall_risk_level":"Medium","overall_risk_reason":"","risks":[{{"level":"High","title":"","desc":""}}],"benefits":[{{"title":"","desc":""}}]}}"""
    else:
        return f"""Kamu adalah analis IPO. Analisis prospektus IPO Indonesia ini. Output HANYA JSON.

DATA KPI (salin persis): {json.dumps(kpi, ensure_ascii=False)}
Tahun keuangan: {years}

Ekstrak:
A. company_name, ticker (cari "Kode Saham:"), sector, ipo_date, share_price, total_shares, market_cap (salin dari KPI)
B. summary: 2 paragraf Bahasa Indonesia. P1: profil perusahaan. P2: detail IPO.
C. use_of_funds: Cari bagian "Rencana Penggunaan Dana". Ekstrak SEMUA item dengan persentase PERSIS dari dokumen. Setiap item: category (nama persis), description (spesifik dengan nilai nominal), allocation (angka). Total harus = 100.
D. underwriter: lead, others (array), type, reputation (2 kalimat)
E. risks: Cari bab "Faktor Risiko". Ekstrak 4-6 risiko spesifik. Setiap: level (High/Medium/Low), title, desc (1-2 kalimat dengan fakta spesifik)
F. overall_risk_level: High/Medium/Low, overall_risk_reason: 2 kalimat
G. benefits: 3-4 keunggulan utama dengan data spesifik

DOKUMEN:
{text[:200000]}

OUTPUT JSON:
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"","summary":"","use_of_funds":[{{"category":"","description":"","allocation":60}}],"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},"overall_risk_level":"Medium","overall_risk_reason":"","risks":[{{"level":"High","title":"","desc":""}}],"benefits":[{{"title":"","desc":""}}]}}"""


def _build_pro_prompt(text: str, kpi: Dict, financial: Dict, lang: str) -> str:
    """Pro prompt: detail lengkap, analisis mendalam."""
    is_en = lang=="EN"
    currency = financial.get("currency","IDR")
    years    = financial.get("years",[])
    rasio    = financial.get("rasio_per_tahun",[])

    if is_en:
        return f"""You are a senior IPO analyst with 20 years experience at top Indonesian investment banks.
Provide COMPREHENSIVE and ACCURATE analysis of this IPO prospectus. Output ONLY JSON.

KPI DATA (copy exactly, do not recalculate): {json.dumps(kpi, ensure_ascii=False)}
Financial years available: {years}
Ratio table data: {json.dumps(rasio, ensure_ascii=False)}

ANALYSIS REQUIREMENTS:

A. COMPANY IDENTITY
   company_name: full name including Tbk
   ticker: find "Kode Saham:" / "Kode Efek:" / "Stock Code:" in document. Leave empty if not found.
   sector: specific industry sector
   ipo_date: listing date on IDX
   share_price: offering price (exact from document)
   total_shares: total shares after IPO
   market_cap: COPY from KPI data above

B. SUMMARY (3 full paragraphs in English, separated by \\n\\n)
   P1: Detailed company profile - founding year, business activities, geographic presence, key operational metrics
   P2: IPO structure - number of shares offered, % dilution, price range, total proceeds, use breakdown
   P3: Financial performance highlights with specific numbers, growth rates, key ratios, business outlook

C. USE OF PROCEEDS (CRITICAL - must be accurate)
   Find section "Use of Proceeds" / "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum"
   Read CAREFULLY and extract EVERY allocation item:
   - category: EXACT name from document
   - description: DETAILED description including specific amounts (e.g., "Acquisition of 191,250 shares = 99.99% of PT XYZ for IDR 215 billion"), project names, subsidiary names
   - allocation: EXACT percentage from document (must sum to 100.0)
   If document shows nominal amounts only: calculate percentages proportionally.
   Minimum 2 items. Do NOT use generic descriptions.

D. UNDERWRITER
   lead: lead underwriter name(s) from document
   others: array of co-underwriters from document (can be empty [])
   type: "Full Commitment" or "Best Efforts"
   reputation: 3 sentences analyzing track record and market standing

E. RISK ANALYSIS (4-6 risks from Risk Factors chapter)
   For each risk:
   level: "High" (material/concentration/regulatory), "Medium" (operational/market), "Low" (minor)
   title: exact risk name from document
   desc: 2-3 sentences with SPECIFIC data - percentages, customer names, amounts, regulatory details from document
   overall_risk_level: "High" / "Medium" / "Low"
   overall_risk_reason: 3 sentences explaining the overall risk assessment with specific facts

F. INVESTMENT BENEFITS (5-7 specific benefits)
   Find "Competitive Strengths" / "Keunggulan Kompetitif" / "Business Prospects"
   For each: title (exact from document), desc (2-3 sentences with specific data, market share %, growth rates, capacity numbers)

DOCUMENT:
{text[:380000]}

OUTPUT JSON:
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"","summary":"P1...\\n\\nP2...\\n\\nP3...","use_of_funds":[{{"category":"","description":"","allocation":70.26}},{{"category":"","description":"","allocation":29.74}}],"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},"overall_risk_level":"High","overall_risk_reason":"","risks":[{{"level":"High","title":"","desc":""}},{{"level":"Medium","title":"","desc":""}}],"benefits":[{{"title":"","desc":""}}]}}"""
    else:
        return f"""Kamu adalah analis IPO senior dengan pengalaman 20 tahun di bank investasi terkemuka Indonesia.
Berikan analisis KOMPREHENSIF dan AKURAT dari prospektus IPO ini. Output HANYA JSON.

DATA KPI (salin persis, jangan hitung ulang): {json.dumps(kpi, ensure_ascii=False)}
Tahun keuangan tersedia: {years}
Data tabel rasio: {json.dumps(rasio, ensure_ascii=False)}

PERSYARATAN ANALISIS:

A. IDENTITAS PERUSAHAAN
   company_name: nama lengkap termasuk Tbk
   ticker: cari "Kode Saham:" / "Kode Efek:" di dokumen. Kosongkan jika tidak ada.
   sector: sektor industri spesifik
   ipo_date: tanggal pencatatan di BEI
   share_price: harga penawaran (persis dari dokumen)
   total_shares: total saham beredar setelah IPO
   market_cap: SALIN dari data KPI di atas

B. RINGKASAN (3 paragraf penuh Bahasa Indonesia, pisah dengan \\n\\n)
   P1: Profil perusahaan detail - tahun berdiri, kegiatan usaha, kehadiran geografis, metrik operasional kunci
   P2: Struktur IPO - jumlah saham ditawarkan, % dilusi, rentang harga, total dana, rincian penggunaan
   P3: Sorotan kinerja keuangan dengan angka spesifik, tingkat pertumbuhan, rasio kunci, prospek usaha

C. PENGGUNAAN DANA (KRITIS - harus akurat)
   Cari bagian "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum" / "Use of Proceeds"
   Baca TELITI dan ekstrak SETIAP item alokasi:
   - category: nama PERSIS dari dokumen
   - description: deskripsi DETAIL termasuk nilai nominal spesifik (mis: "Akuisisi 191.250 saham = 99,99% PT XYZ senilai Rp215 miliar"), nama proyek, nama anak perusahaan
   - allocation: persentase PERSIS dari dokumen (total harus = 100,0)
   Jika dokumen hanya menunjukkan nilai nominal: hitung persentase secara proporsional.
   Minimal 2 item. JANGAN gunakan deskripsi generik.

D. PENJAMIN EMISI
   lead: nama penjamin pelaksana utama dari dokumen
   others: array penjamin lain dari dokumen (bisa [] jika tidak ada)
   type: "Full Commitment" atau "Best Efforts"
   reputation: 3 kalimat menganalisis rekam jejak dan posisi pasar

E. ANALISIS RISIKO (4-6 risiko dari bab Faktor Risiko)
   Untuk setiap risiko:
   level: "High" (material/konsentrasi/regulasi), "Medium" (operasional/pasar), "Low" (minor)
   title: nama risiko persis dari dokumen
   desc: 2-3 kalimat dengan data SPESIFIK - persentase, nama pelanggan, nilai, detail regulasi dari dokumen
   overall_risk_level: "High" / "Medium" / "Low"
   overall_risk_reason: 3 kalimat menjelaskan penilaian risiko keseluruhan dengan fakta spesifik

F. KEUNGGULAN INVESTASI (5-7 keunggulan spesifik)
   Cari "Keunggulan Kompetitif" / "Prospek Usaha" / "Kekuatan Bisnis"
   Untuk setiap: title (persis dari dokumen), desc (2-3 kalimat dengan data spesifik, pangsa pasar %, tingkat pertumbuhan, angka kapasitas)

DOKUMEN:
{text[:380000]}

OUTPUT JSON:
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"","summary":"P1...\\n\\nP2...\\n\\nP3...","use_of_funds":[{{"category":"","description":"","allocation":70.26}},{{"category":"","description":"","allocation":29.74}}],"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},"overall_risk_level":"High","overall_risk_reason":"","risks":[{{"level":"High","title":"","desc":""}},{{"level":"Medium","title":"","desc":""}}],"benefits":[{{"title":"","desc":""}}]}}"""


def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str="ID", model: str=None) -> Dict:
    _m = model or MODEL_FLASH
    is_pro = _m == MODEL_PRO

    if is_pro:
        prompt = _build_pro_prompt(text, kpi, financial, lang)
    else:
        prompt = _build_basic_prompt(text, kpi, financial, lang)

    logger.info(f"[QUAL] model={_m} is_pro={is_pro} lang={lang}")

    try:
        resp = client.chat.completions.create(
            model=_m, temperature=0.1, max_tokens=16000,
            messages=[{"role":"user","content":prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result: return result

        # Repair JSON terpotong
        fixed = re.sub(r",\s*([}\]])",r"\1",raw)
        s = fixed.find("{")
        if s != -1:
            snippet = fixed[s:]
            ob = snippet.count("{") - snippet.count("}")
            ol = snippet.count("[") - snippet.count("]")
            closed = snippet + ("]" * max(0,ol)) + ("}" * max(0,ob))
            result = _safe_json(closed)
            if result: return result
            for end in range(len(fixed), s, -100):
                try: return json.loads(fixed[s:end])
                except: pass

        raise ValueError(f"JSON parse failed: {raw[:300]}")
    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Gagal analisis kualitatif: {e}")

# ══════════════════════════════════════════════════════════════════════
# 6. TICKER SEARCH FALLBACK
# ══════════════════════════════════════════════════════════════════════

def search_ticker_by_name(company_name: str) -> str:
    import requests
    HEADERS = {"User-Agent":"Mozilla/5.0 AppleWebKit/537.36","Accept":"application/json"}
    EXCLUDE = {"PT","TBK","IDX","BEI","OJK","IDR","USD","IPO","ROE","ROA","DER","EPS","CEO","CFO","GDP","EBITDA"}
    def clean(n: str) -> str:
        n = re.sub(r"\bPT\.?\s*","",n,flags=re.I)
        n = re.sub(r"\bTbk\.?\b","",n,flags=re.I)
        return re.sub(r"\s+"," ",n).strip()
    cleaned = clean(company_name)
    if not cleaned: return ""
    try:
        resp = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":cleaned,"lang":"id","region":"ID","quotesCount":10,"newsCount":0},
            headers=HEADERS, timeout=10)
        for q in resp.json().get("quotes",[]):
            sym = q.get("symbol",""); exch = q.get("exchange","")
            if sym.endswith(".JK") or exch in ["JKT","IDX","Jakarta"]:
                t = sym.replace(".JK","").upper()
                if t not in EXCLUDE and 2<=len(t)<=6:
                    logger.info(f"Ticker Yahoo: {t}"); return t
    except Exception as e: logger.warning(f"Yahoo: {e}")
    return ""

# ══════════════════════════════════════════════════════════════════════
# 7. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

def analyze_prospectus(text: str, lang: str="ID", model: str=None) -> dict:
    lang   = (lang or "ID").upper()
    _model = model or MODEL_FLASH

    logger.info(f"[START] analyze_prospectus lang={lang} model={_model} text_len={len(text)}")

    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    fin_raw = llm_extract_financials(text, model=_model)
    if not fin_raw.get("satuan"):   fin_raw["satuan"]   = unit
    if not fin_raw.get("mata_uang"): fin_raw["mata_uang"] = currency

    financial, kpi = normalize_and_compute(fin_raw, fx_rate)
    logger.info(f"[KPI] {json.dumps(kpi, ensure_ascii=False)}")

    result = llm_qualitative(text, kpi, financial, lang=lang, model=_model)
    result["financial"] = financial
    result["kpi"]       = kpi

    # Ticker
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$",ticker):
        company = result.get("company_name","")
        if company: ticker = search_ticker_by_name(company)
        result["ticker"] = ticker
    else:
        result["ticker"] = ticker

    # Validasi use_of_funds
    uof = result.get("use_of_funds",[])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            logger.warning(f"UoF total={total:.1f}, normalisasi ke 100")
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total*100,2)

    return result