"""
services/gemini_service.py - IPO Analyzer Backend
Pipeline:
  1. Detect metadata (currency, unit, fx rate)
  2. LLM multi-chunk - ekstrak data keuangan (termasuk holding company konsolidasi)
  3. Python - normalisasi + hitung KPI
  4. LLM - analisis kualitatif akurat (use_of_funds, risk, benefit)
  5. Ticker search fallback
"""
from __future__ import annotations
import json, logging, math, os, re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")
MODEL = "gemini/gemini-2.5-flash"

# ══════════════════════════════════════════════════════
# 1. NUMBER UTILITIES
# ══════════════════════════════════════════════════════

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
        val = float(s)
        return -val if neg else val
    except: return None

def apply_unit(val: Any, unit: str) -> Optional[float]:
    v = parse_num(val)
    if v is None: return None
    return v * {"jutaan":1_000_000,"ribuan":1_000,"miliar":1_000_000_000,"triliun":1_000_000_000_000}.get(unit.lower(),1)

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

# ══════════════════════════════════════════════════════
# 2. METADATA DETECTION
# ══════════════════════════════════════════════════════

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
    for pat in [r"kurs.*?rp\s*([\d.,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)",r"rp\s*([\d.,]+)\s*/\s*us\$"]:
        m = re.search(pat, text[:20000], re.I)
        if m:
            v = parse_num(m.group(1))
            if v and v>1000: return float(v)
    return None

# ══════════════════════════════════════════════════════
# 3. LLM FINANCIAL EXTRACTION - SUPPORT HOLDING COMPANY
# ══════════════════════════════════════════════════════

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

_FIN_KEYWORDS = [
    "laporan laba rugi","ikhtisar data keuangan","data keuangan penting",
    "ringkasan keuangan","informasi keuangan","laba kotor","laba usaha",
    "laba bersih","pendapatan usaha","pendapatan bersih","penjualan bersih",
    "posisi keuangan","neraca","ekuitas","liabilitas","31 desember",
    "rasio keuangan","rasio penting","rasio keuangan penting","konsolidasian","consolidated",
    "gross profit","net revenue","operating profit","net income",
    "profit or loss","statement of profit","balance sheet",
    "selected financial","financial highlights","total aset","total assets",
    "return on equity","return on asset","debt to equity","earnings per share",
]

_FIN_SYSTEM = """Kamu adalah akuntan senior Indonesia. Tugasmu: ekstrak data keuangan LENGKAP dari prospektus IPO.
Output HANYA JSON murni — tanpa teks lain, tanpa markdown.

INSTRUKSI UTAMA:

1. LAPORAN LABA RUGI — Cari tabel dengan judul:
   "LAPORAN LABA RUGI", "IKHTISAR DATA KEUANGAN", "DATA KEUANGAN PENTING",
   "SELECTED FINANCIAL DATA", "CONSOLIDATED STATEMENTS", "RINGKASAN KEUANGAN"
   → Ekstrak SEMUA tahun yang ada di kolom header tabel.
   → Untuk setiap tahun: pendapatan, laba_kotor, laba_usaha, laba_bersih, depresiasi

2. RASIO KEUANGAN PENTING — Cari tabel dengan judul:
   "RASIO KEUANGAN PENTING", "RASIO KEUANGAN", "KEY FINANCIAL RATIOS", "FINANCIAL RATIOS"
   → Ini berisi ROE, ROA, DER, NPM, GPM, EPS, Current Ratio, dll per tahun
   → Ekstrak ke "rasio_per_tahun" untuk setiap tahun yang ada
   → ROE bisa disebut: "Imbal Hasil Ekuitas", "Return on Equity", "ROE"
   → DER bisa disebut: "Debt to Equity Ratio", "Rasio Utang terhadap Ekuitas", "DER"
   → EPS bisa disebut: "Laba per Saham", "Earnings per Share", "EPS"
   → NPM: "Net Profit Margin", "Margin Laba Bersih"
   → GPM: "Gross Profit Margin", "Margin Laba Kotor"
   → Current Ratio: "Rasio Lancar"

3. NERACA/POSISI KEUANGAN — Tahun TERAKHIR:
   total_ekuitas, total_liabilitas, total_aset

4. IPO INFO:
   total_saham_beredar: total saham SETELAH IPO
   harga_penawaran: angka saja tanpa "Rp" (null jika DRHP/belum final)

5. Satuan: "jutaan"/"ribuan"/"miliar"/"full" dari header tabel
6. Angka negatif dalam kurung (1.234) → tulis -1234

OUTPUT JSON WAJIB:
{
  "satuan": "jutaan",
  "mata_uang": "IDR",
  "tahun_tersedia": ["2022","2023","2024"],
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

        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(set(merged["tahun_tersedia"])|set(str(y) for y in part["tahun_tersedia"]))

        if part.get("data_per_tahun"):
            m_dict = {str(d.get("tahun","")).strip():d for d in merged["data_per_tahun"]}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun","")).strip()
                if not y: continue
                if y in m_dict:
                    for k in ("pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"):
                        v = d.get(k)
                        if m_dict[y].get(k) is None and v is not None and str(v).strip() not in ("null",""):
                            m_dict[y][k] = v
                else: m_dict[y] = d
            merged["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]

        # Merge rasio keuangan penting
        if part.get("rasio_per_tahun"):
            r_dict = {str(r.get("tahun","")).strip():r for r in merged.get("rasio_per_tahun",[])}
            for r in part["rasio_per_tahun"]:
                y = str(r.get("tahun","")).strip()
                if not y: continue
                if y in r_dict:
                    for k in ("roe","roa","der","npm","gpm","eps","current_ratio"):
                        v = r.get(k)
                        if r_dict[y].get(k) is None and v is not None and str(v).strip() not in ("null",""):
                            r_dict[y][k] = v
                else: r_dict[y] = r
            merged["rasio_per_tahun"] = [r_dict[k] for k in sorted(r_dict.keys())]

        for k in ("total_ekuitas","total_liabilitas","total_aset","total_saham_beredar","harga_penawaran"):
            v = part.get(k)
            if merged.get(k) is None and v is not None and str(v).strip() not in ("null",""):
                merged[k] = v

    logger.info(f"[FIN] tahun={merged.get('tahun_tersedia')} saham={merged.get('total_saham_beredar')} harga={merged.get('harga_penawaran')} ekuitas={merged.get('total_ekuitas')}")
    return merged

# ══════════════════════════════════════════════════════
# 4. NORMALIZE + COMPUTE KPI
# ══════════════════════════════════════════════════════

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
        ebitda_margin.append({"year":y,"value":to_pct(safe_div(float(op)+float(dep),rev)) if (dep is not None and op is not None and rev) else None})
        net_margin.append({"year":y,"value":to_pct(safe_div(net,rev))})

    kpi = {"pe":"N/A","pb":"N/A","roe":"N/A","der":"N/A","eps":"N/A","market_cap":"N/A",
           "roe_by_year":{},"der_by_year":{},"eps_by_year":{},"npm_by_year":{},"gpm_by_year":{}}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    # Baca rasio langsung dari tabel "Rasio Keuangan Penting"
    rasio_list = fin_raw.get("rasio_per_tahun", [])
    if rasio_list:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, kpi_key in [("roe","roe_by_year"),("der","der_by_year"),
                                    ("eps","eps_by_year"),("npm","npm_by_year"),("gpm","gpm_by_year")]:
                v = parse_num(r.get(field))
                if v is not None:
                    kpi[kpi_key][y] = v

        # Ambil nilai tahun terakhir untuk display
        last_rasio = rasio_list[-1] if rasio_list else {}
        roe_v = parse_num(last_rasio.get("roe"))
        der_v = parse_num(last_rasio.get("der"))
        eps_v = parse_num(last_rasio.get("eps"))
        if roe_v is not None: kpi["roe"] = f"{roe_v:.1f}%"
        if der_v is not None: kpi["der"] = f"{der_v:.2f}x"
        if eps_v is not None:
            kpi["eps"] = f"Rp {eps_v:,.2f}".replace(",",".") if currency=="IDR" else f"{eps_v:.2f}"

    # Hitung dari laporan keuangan jika rasio tidak tersedia
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
        if ekuitas and laba_last and ekuitas>0 and kpi["roe"]=="N/A":
            kpi["roe"] = f"{laba_last/ekuitas*100:.1f}%"
    except: pass
    try:
        if ekuitas and liabilitas and ekuitas>0 and kpi["der"]=="N/A":
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
    except: pass
    try:
        if saham and harga and saham>0 and harga>0:
            mc = saham*(harga_idr if harga_idr else harga)
            kpi["market_cap"] = fmt_idr(mc)
    except: pass

    financial = {
        "currency": currency,
        "years": [str(d.get("tahun","")) for d in years_data],
        "absolute_data": years_data,
        "revenue_growth": revenue_growth or None,
        "gross_margin": gross_margin or None,
        "operating_margin": op_margin or None,
        "ebitda_margin": ebitda_margin or None,
        "net_profit_margin": net_margin or None,
    }
    return financial, kpi

# ══════════════════════════════════════════════════════
# 5. LLM QUALITATIVE - AKURAT USE_OF_FUNDS, RISK, BENEFIT
# ══════════════════════════════════════════════════════

def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str="ID") -> Dict:
    is_en    = lang.upper()=="EN"
    currency = financial.get("currency","IDR")
    years    = financial.get("years",[])

    if is_en:
        lang_rule = "CRITICAL: Write ALL text output fields in ENGLISH ONLY. No Bahasa Indonesia."
        uof_rule = """MANDATORY - Find the section titled exactly "Use of Proceeds" or "Rencana Penggunaan Dana".
Read the ACTUAL text and table in that section carefully.
- Extract EVERY item listed with its EXACT percentage or amount
- allocation = the EXACT percentage number written in the document
- Total MUST equal 100 (normalize if needed)
- category: use the EXACT category name from the document (e.g. "Working Capital", "Capital Expenditure", "Debt Repayment")
- description: copy specific details - project names, subsidiary names, nominal amounts from that section
- NEVER use generic descriptions - every prospectus has different use of proceeds
- At least 2 items, up to 6 items"""
        risk_rule = """MANDATORY - Find the chapter titled "Risk Factors".
Read ALL risks listed in that chapter carefully.
Extract 4-6 MOST SIGNIFICANT risks:
- level: "High" if explicitly stated as main/primary risk or involves customer concentration/regulatory/financial; "Medium" for operational risks; "Low" for minor risks
- title: exact risk name from document
- desc: 1-2 sentences with SPECIFIC facts: percentages, customer names, amounts mentioned in the document
DO NOT write generic descriptions - use actual data from the document."""
        benefit_rule = """MANDATORY - Find "Competitive Strengths", "Keunggulan Kompetitif", or company overview section.
Extract 4-6 SPECIFIC strengths actually stated in the document:
- title: exact strength name from document
- desc: specific supporting data/numbers/facts from the document
DO NOT invent or generalize - only use what is explicitly stated."""
        summary_hint = "3 PARAGRAPHS IN ENGLISH. P1: Company profile, business activities, key numbers. P2: IPO structure - shares offered, price, total proceeds, listing date. P3: Financial performance, growth trend, business outlook."
    else:
        lang_rule = "WAJIB: Tulis SEMUA field teks output dalam BAHASA INDONESIA."
        uof_rule = """WAJIB - Cari bagian yang judulnya "Rencana Penggunaan Dana" atau "Penggunaan Dana Hasil Penawaran Umum".
Baca teks dan tabel di bagian itu dengan teliti.
- Ekstrak SETIAP item yang tercantum dengan persentase atau nominal PERSIS dari dokumen
- allocation = angka persentase PERSIS yang tertulis di dokumen
- Total HARUS = 100 (normalisasi jika perlu)
- category: gunakan nama kategori PERSIS dari dokumen (misal: "Modal Kerja", "Belanja Modal", "Pelunasan Utang")
- description: salin detail spesifik - nama proyek, nama anak perusahaan, nilai nominal dari bagian itu
- JANGAN gunakan deskripsi generik - setiap prospektus punya rencana penggunaan dana yang berbeda
- Minimal 2 item, maksimal 6 item"""
        risk_rule = """WAJIB - Cari bab "Faktor Risiko".
Baca SEMUA risiko yang tercantum di bab itu dengan teliti.
Ekstrak 4-6 risiko PALING SIGNIFIKAN:
- level: "High" jika disebutkan sebagai risiko utama/material atau menyangkut ketergantungan pelanggan/regulasi/keuangan; "Medium" untuk risiko operasional; "Low" untuk risiko minor
- title: nama risiko PERSIS dari dokumen
- desc: 1-2 kalimat dengan fakta SPESIFIK: persentase, nama pelanggan, nilai yang disebut di dokumen
JANGAN tulis deskripsi generik - gunakan data aktual dari dokumen."""
        benefit_rule = """WAJIB - Cari "Keunggulan Kompetitif" atau bagian overview perusahaan.
Ekstrak 4-6 keunggulan SPESIFIK yang benar-benar tercantum di dokumen:
- title: nama keunggulan persis dari dokumen
- desc: data/angka/fakta spesifik pendukung dari dokumen
JANGAN mengarang atau menggeneralisasi - hanya gunakan yang tersebut eksplisit."""
        summary_hint = "3 PARAGRAF BAHASA INDONESIA. P1: Profil perusahaan, kegiatan usaha, angka kunci. P2: Struktur IPO - saham ditawarkan, harga, total dana, tanggal listing. P3: Kinerja keuangan, tren pertumbuhan, prospek usaha."

    prompt = f"""Kamu adalah analis IPO senior Indonesia. Analisis prospektus ini secara AKURAT.

{lang_rule}
Mata uang: {currency}

DATA KPI SISTEM (SALIN PERSIS):
{json.dumps(kpi, ensure_ascii=False)}
Tahun: {years}

TUGAS:

A. IDENTITAS
company_name, ticker (cari "Kode Saham:"), sector, ipo_date, share_price, total_shares
market_cap: SALIN dari DATA KPI

B. SUMMARY
{summary_hint}

C. PENGGUNAAN DANA
{uof_rule}

D. PENJAMIN EMISI
lead, others (array), type ("Full Commitment"/"Best Efforts"), reputation (2-3 kalimat)

E. RISIKO
{risk_rule}
overall_risk_level: "High"/"Medium"/"Low"
overall_risk_reason: 2-3 kalimat

F. KEUNGGULAN
{benefit_rule}

ATURAN OUTPUT:
- JSON murni SAJA, tanpa markdown
- use_of_funds[].allocation = NUMBER
- risks[].level = "High"/"Medium"/"Low" (huruf kapital pertama saja)
- Semua field string diisi ("" jika tidak ada)

DOKUMEN:
{text[:380000]}

OUTPUT JSON:
{{
  "company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"",
  "summary":"",
  "use_of_funds":[{{"category":"","description":"","allocation":60}}],
  "underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
  "overall_risk_level":"Medium","overall_risk_reason":"",
  "risks":[{{"level":"High","title":"","desc":""}}],
  "benefits":[{{"title":"","desc":""}}]
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL, temperature=0.1, max_tokens=8000,
            messages=[{"role":"user","content":prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result: return result
        fixed = re.sub(r",\s*([}\]])",r"\1",raw)
        s, e = fixed.find("{"), fixed.rfind("}")+1
        if s!=-1 and e>s:
            for end in range(e,s,-200):
                try: return json.loads(fixed[s:end])
                except: pass
        raise ValueError(f"JSON parse failed: {raw[:200]}")
    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Gagal analisis kualitatif: {e}")

# ══════════════════════════════════════════════════════
# 6. TICKER SEARCH
# ══════════════════════════════════════════════════════

def search_ticker_by_name(company_name: str) -> str:
    import requests
    HEADERS = {"User-Agent":"Mozilla/5.0 AppleWebKit/537.36","Accept":"application/json"}
    TIMEOUT = 10
    EXCLUDE = {"PT","TBK","IDX","BEI","OJK","IDR","USD","IPO","ROE","ROA","DER","EPS","CEO","CFO","GDP","EBITDA"}

    def clean(name: str) -> str:
        name = re.sub(r"\bPT\.?\s*","",name,flags=re.I)
        name = re.sub(r"\bTbk\.?\b","",name,flags=re.I)
        return re.sub(r"\s+"," ",name).strip()

    cleaned = clean(company_name)
    if not cleaned: return ""

    try:
        resp = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":cleaned,"lang":"id","region":"ID","quotesCount":10,"newsCount":0},
            headers=HEADERS, timeout=TIMEOUT)
        for q in resp.json().get("quotes",[]):
            sym = q.get("symbol","")
            exch = q.get("exchange","")
            if sym.endswith(".JK") or exch in ["JKT","IDX","Jakarta"]:
                t = sym.replace(".JK","").upper()
                if t not in EXCLUDE and 2<=len(t)<=6:
                    logger.info(f"Ticker Yahoo: {t}")
                    return t
    except Exception as e: logger.warning(f"Yahoo: {e}")

    try:
        resp = requests.get("https://idx.co.id/umum/GetStockList/",
            params={"language":"id","querySearch":cleaned},headers=HEADERS,timeout=TIMEOUT)
        data = resp.json()
        results = data if isinstance(data,list) else data.get("data",[])
        if results:
            t = (results[0].get("stockCode") or results[0].get("StockCode") or "").upper()
            if t and re.match(r"^[A-Z]{2,6}$",t) and t not in EXCLUDE:
                logger.info(f"Ticker IDX: {t}")
                return t
    except Exception as e: logger.warning(f"IDX: {e}")

    return ""

# ══════════════════════════════════════════════════════
# 7. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════

def analyze_prospectus(text: str, lang: str="ID") -> dict:
    lang = (lang or "ID").upper()

    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    fin_raw = llm_extract_financials(text)
    if not fin_raw.get("satuan"): fin_raw["satuan"] = unit
    if not fin_raw.get("mata_uang"): fin_raw["mata_uang"] = currency

    financial, kpi = normalize_and_compute(fin_raw, fx_rate)
    logger.info(f"[KPI] {kpi}")

    result = llm_qualitative(text, kpi, financial, lang=lang)
    result["financial"] = financial
    result["kpi"]       = kpi

    # Ticker
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$",ticker):
        company_name = result.get("company_name","")
        if company_name: ticker = search_ticker_by_name(company_name)
        result["ticker"] = ticker
    else:
        result["ticker"] = ticker

    # Validasi use_of_funds
    uof = result.get("use_of_funds",[])
    if uof:
        total_alloc = sum(float(x.get("allocation") or 0) for x in uof)
        if total_alloc>150:
            logger.warning(f"UoF total={total_alloc:.0f}, normalisasi")
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total_alloc*100,1)
        elif total_alloc==0:
            logger.warning("UoF semua allocation=0")

    return result