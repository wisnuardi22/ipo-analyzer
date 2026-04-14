"""
gemini_service.py - IPO Analyzer
Revisi: Wajib Bahasa Inggris, KPI (ROA, ROE, ROI, DER), 1 Warna Risiko, Format Angka Murni
"""
from __future__ import annotations
import json, logging, math, os, re, socket, time
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")

def _call_llm(messages, max_tokens=4000, temperature=0.0, retries=4, model=None):
    _model = model or MODEL_FLASH
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=_model, temperature=temperature,
                max_tokens=max_tokens, messages=messages,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate" in err.lower() or "cooling" in err.lower():
                wait = 15 * (attempt + 1)
                logger.warning(f"Sumopod Rate limit hit, wait {wait}s: {err[:100]}")
                time.sleep(wait)
            else:
                raise
    raise Exception("Rate limit: server terlalu sibuk. Coba lagi dalam beberapa menit.")

MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = "gemini/gemini-2.5-pro"
MODEL       = MODEL_FLASH
_HOST       = socket.gethostname()

# ══════════════════════════════════════════
# 1. UTILS (Format Angka Anti-Hancur)
# ══════════════════════════════════════════
def parse_num(raw):
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
        p = s.split(","); s = s.replace(",",".") if len(p)==2 and len(p[1])<=2 else s.replace(",","")
    elif "." in s:
        p = s.split(".")
        if not (len(p)==2 and len(p[1])<=2): s = s.replace(".","")
    try: v = float(s); return -v if neg else v
    except: return None

def apply_unit(val, unit):
    v = parse_num(val)
    if v is None: return None
    return v * {"jutaan":1_000_000,"ribuan":1_000,"miliar":1_000_000_000,"triliun":1_000_000_000_000}.get((unit or "").lower(),1)

def safe_div(a, b):
    try:
        af, bf = parse_num(a), parse_num(b)
        return af/bf if af is not None and bf else None
    except: return None

def to_pct(v):
    x = parse_num(v)
    return round(x*100,2) if x is not None and not math.isnan(x) else None

def calc_growth(cur, prev):
    c, p = parse_num(cur), parse_num(prev)
    if c is None or p is None or p==0: return None
    return round((c-p)/abs(p)*100,2)

# ══════════════════════════════════════════
# 2. METADATA
# ══════════════════════════════════════════
def detect_currency(text):
    t = text[:5000].lower()
    return "USD" if ("us$" in t or " usd" in t or "dolar amerika" in t) else "IDR"

def detect_unit(text):
    t = text[:10000].lower()
    if re.search(r"dalam\s+jutaan",t): return "jutaan"
    if re.search(r"dalam\s+ribuan",t): return "ribuan"
    if re.search(r"dalam\s+miliar",t): return "miliar"
    return "full"

def detect_fx_rate(text):
    for pat in [r"kurs.*?rp\s*([\d.,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)",r"rp\s*([\d.,]+)\s*/\s*us\$"]:
        m = re.search(pat, text[:20000], re.I)
        if m:
            v = parse_num(m.group(1))
            if v and v>1000: return float(v)
    return None

def is_bank(text):
    t = text[:3000].lower()
    return any(k in t for k in ["bank ","perbankan","banking","simpanan","giro","deposito","tabungan","nim ","car "])

# ══════════════════════════════════════════
# 3. PENGUATAN FINANCIAL EXTRACTION 
# ══════════════════════════════════════════
_FIN_SYSTEM = """You are a senior financial analyst. Extract financial data from the Indonesian IPO prospectus.
Output EXACTLY pure JSON, no other text.

INSTRUCTIONS - Read carefully:

A. INCOME STATEMENT (Look for "IKHTISAR DATA KEUANGAN" or "LAPORAN LABA RUGI")
   For EACH year, extract:
   - pendapatan: Net Revenue / Total Pendapatan. BE AGGRESSIVE in finding this.
   - laba_kotor: Gross Profit / Laba Kotor. If missing, calculate: Pendapatan - Beban Pokok Pendapatan. (null for banks).
   - laba_usaha: Operating Profit / Laba Usaha.
   - laba_bersih: Net Profit / Laba Tahun Berjalan.
   - depresiasi: Depreciation & Amortization.

B. NERACA / BALANCE SHEET (LAST YEAR ONLY):
   total_ekuitas (Total Equity), total_liabilitas (Total Liabilities), total_aset (Total Assets)

C. KEY RATIOS (Look for "RASIO KEUANGAN"):
   Copy exactly per year:
   - roa: Return on Asset (%)
   - roe: Return on Equity (%)
   - roi: Return on Investment / ROIC (%)
   - der: Debt to Equity Ratio (x)

D. IPO INFO:
   total_saham_beredar: Total shares AFTER IPO (angka saja).
   harga_penawaran: Offering price (angka saja).

E. SATUAN (Unit): "jutaan"/"ribuan"/"miliar"/"full".

OUTPUT FORMAT:
{"satuan":"jutaan","mata_uang":"IDR","tahun_tersedia":["2021","2022","2023"],
"data_per_tahun":[{"tahun":"2021","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}],
"rasio_per_tahun":[{"tahun":"2021","roa":null,"roe":null,"roi":null,"der":null}],
"total_ekuitas":null,"total_liabilitas":null,"total_aset":null,"total_saham_beredar":null,"harga_penawaran":null}"""

def _safe_json(raw):
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"): raw = part; break
    s, e = raw.find("{"), raw.rfind("}")
    if s==-1 or e<=s: return None
    snippet = raw[s:e+1]
    try: return json.loads(snippet)
    except:
        try: return json.loads(re.sub(r",\s*([}\]])",r"\1",snippet))
        except: return None

def llm_extract_financials(text: str) -> Dict:
    n = len(text)
    start = max(0, int(n * 0.20))
    end   = min(n, int(n * 0.85))
    core  = text[start:end]

    if len(core) > 80000:
        chunk = core[:80000]
    else:
        chunk = core

    try:
        raw = _call_llm(
            messages=[
                {"role":"system","content":_FIN_SYSTEM},
                {"role":"user","content":f"PROSPECTUS DOCUMENT:\n\n{chunk}"},
            ],
            max_tokens=4000, temperature=0.0,
            model=MODEL_FLASH, 
        )
        return _safe_json(raw) or {}
    except Exception as e:
        logger.error(f"FIN error: {e}")
        return {}

# ══════════════════════════════════════════
# 4. NORMALIZE + 4 KPI UTAMA (ROA, ROE, ROI, DER)
# ══════════════════════════════════════════
def normalize_and_compute(fin_raw: Dict, fx_rate, is_banking=False):
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
    aset       = apply_unit(fin_raw.get("total_aset"),unit)
    saham      = parse_num(fin_raw.get("total_saham_beredar"))
    harga      = parse_num(fin_raw.get("harga_penawaran"))
    harga_idr  = harga*fx_rate if (harga and currency=="USD" and fx_rate) else harga

    rev_growth, gross_m, op_m, ebitda_m, net_m = [],[],[],[],[]
    prev_rev = None
    for yr in years_data:
        y   = str(yr.get("tahun",""))
        rev = yr.get("pendapatan")
        gp  = yr.get("laba_kotor")
        op  = yr.get("laba_usaha")
        net = yr.get("laba_bersih")
        dep = yr.get("depresiasi")
        rev_growth.append({"year":y,"value":0.0 if prev_rev is None else calc_growth(rev,prev_rev)})
        prev_rev = rev
        gross_m.append({"year":y,"value":None if is_banking else to_pct(safe_div(gp,rev))})
        op_m.append({"year":y,"value":to_pct(safe_div(op,rev))})
        ebitda_m.append({"year":y,"value":to_pct(safe_div(float(op)+float(dep),rev)) if (dep is not None and op is not None and rev) else None})
        net_m.append({"year":y,"value":to_pct(safe_div(net,rev))})

    # FOKUS PADA 4 KPI: ROA, ROE, ROI, DER
    kpi = {"roa":"N/A","roe":"N/A","roi":"N/A","der":"N/A"}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    rasio_list = fin_raw.get("rasio_per_tahun",[])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        last_r = rasio_list[-1]
        for field, fmt in [("roa","{:.2f}%"),("roe","{:.2f}%"),("roi","{:.2f}%"),("der","{:.2f}x")]:
            v = parse_num(last_r.get(field))
            if v is not None: kpi[field] = fmt.format(v)

    # Fallback Perhitungan Manual jika AI tidak menemukan rasio di tabel
    try:
        if kpi["roa"] == "N/A" and laba_last and aset and aset > 0:
            kpi["roa"] = f"{laba_last/aset*100:.2f}%"
        if kpi["roe"] == "N/A" and laba_last and ekuitas and ekuitas > 0:
            kpi["roe"] = f"{laba_last/ekuitas*100:.2f}%"
        if kpi["der"] == "N/A" and liabilitas and ekuitas and ekuitas > 0:
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
        # ROI secara manual seringkali diaproksimasi dengan Laba Bersih / (Ekuitas + Liabilitas Jangka Panjang)
        # Jika tidak ada, kita asumsikan N/A atau samakan dengan ROA jika disetujui (disini kita biarkan N/A agar akurat)
    except: pass

    market_cap_num = None
    try:
        if saham and harga and saham>0 and harga>0:
            market_cap_num = saham * (harga_idr if harga_idr else harga)
    except: pass

    # Return pure numbers for the structural fields to avoid frontend breaks
    structural_data = {
        "offering_price_num": harga,
        "total_shares_num": saham,
        "market_cap_num": market_cap_num
    }

    return {
        "currency":currency,"years":[str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun":rasio_list,"absolute_data":years_data,"is_banking":is_banking,
        "revenue_growth":rev_growth or None,"gross_margin":gross_m or None,
        "operating_margin":op_m or None,"ebitda_margin":ebitda_m or None,
        "net_profit_margin":net_m or None,
    }, kpi, structural_data

# ══════════════════════════════════════════
# 5. QUALITATIVE - WAJIB ENGLISH & 1 WARNA RISIKO
# ══════════════════════════════════════════
def llm_qualitative(text: str, kpi: Dict, financial: Dict, is_pro: bool=False) -> Dict:
    doc_limit = 150000 if is_pro else 90000
    max_tok   = 8000   if is_pro else 5000

    prompt = f"""You are an expert IPO analyst. 
CRITICAL RULE: ALL OUTPUT MUST BE IN STRICT ENGLISH. DO NOT USE INDONESIAN.

DATA (Do not change): {json.dumps(kpi, ensure_ascii=False)}

TASKS:
A. IDENTITY: company_name (Full + Tbk), ticker (find "Kode Saham:"), sector, ipo_date.
B. SUMMARY: 1 high-level paragraph in English outlining the company profile and IPO details.
C. USE OF PROCEEDS:
   Extract "Rencana Penggunaan Dana" / "Use of Proceeds".
   - category: exact name
   - description: detailed description with nominal values (e.g. Rp X billion)
   - allocation: Exact percentage (total must = 100).
D. UNDERWRITER: lead (full name), others (array), type ("Full Commitment" or "Best Efforts"), reputation (1 sentence).

E. HIGH-LEVEL RISK ANALYSIS (ONE COLOR ONLY):
   - overall_risk_level: Choose ONLY ONE for the entire company: "High", "Medium", or "Low".
   - overall_risk_analysis: 1 comprehensive paragraph explaining the primary risks and why you chose that level.
   - risks: An array of 4-5 key risk bullet points (STRINGS ONLY, NO INDIVIDUAL LEVELS/COLORS).
   
F. BENEFITS: 3-4 specific advantages based on concrete data from the prospectus.

DOCUMENT:
{text[:doc_limit]}

OUTPUT JSON FORMAT (STRICTLY ENGLISH):
{{"company_name":"","ticker":"","sector":"","ipo_date":"",
"summary":"",
"use_of_funds":[{{"category":"","description":"","allocation":70}}],
"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
"overall_risk_level":"Medium",
"overall_risk_analysis":"The overall risk is medium, primarily driven by...",
"risks":["Risk of failure in acquisition...", "Dependence on major customers...", "Intense business competition..."],
"benefits":[{{"title":"Market Leader","desc":"Holds 40% market share..."}}]}}"""

    try:
        _model = MODEL_PRO if is_pro else MODEL_FLASH
        raw = _call_llm(
            messages=[{"role":"user","content":prompt}],
            max_tokens=max_tok, temperature=0.1,
            model=_model,
        )
        return _safe_json(raw) or {}
    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Analysis failed: {e}")

# ══════════════════════════════════════════
# 6. TICKER SEARCH
# ══════════════════════════════════════════
def search_ticker(company_name: str) -> str:
    import requests
    EXCLUDE = {"PT","TBK","IDX","BEI","OJK","IDR","USD","IPO"}
    def clean(n):
        n = re.sub(r"\bPT\.?\s*","",n,flags=re.I)
        n = re.sub(r"\bTbk\.?\b","",n,flags=re.I)
        return re.sub(r"\s+"," ",n).strip()
    cleaned = clean(company_name)
    if not cleaned: return ""
    try:
        resp = requests.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":cleaned,"lang":"en","region":"US","quotesCount":5,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        for q in resp.json().get("quotes",[]):
            sym = q.get("symbol","")
            if sym.endswith(".JK"):
                t = sym.replace(".JK","").upper()
                if t not in EXCLUDE and 2<=len(t)<=6:
                    return t
    except: pass
    return ""

# ══════════════════════════════════════════
# 7. MAIN LOGIC
# ══════════════════════════════════════════
def analyze_prospectus(text: str, lang: str="EN", model: str=None) -> dict:
    is_pro  = (model == "gemini/gemini-2.5-pro")
    banking = is_bank(text)
    
    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    # 1. Financial LLM Call
    fin_raw = llm_extract_financials(text)
    if not fin_raw.get("satuan"):    fin_raw["satuan"]    = unit
    if not fin_raw.get("mata_uang"): fin_raw["mata_uang"] = currency

    financial, kpi, structural = normalize_and_compute(fin_raw, fx_rate, is_banking=banking)

    logger.info("Anti Rate Limit Sumopod: Waiting 15s...")
    time.sleep(15)

    # 2. Qualitative LLM Call (Always English now)
    result = llm_qualitative(text, kpi, financial, is_pro=is_pro)
    
    # 3. Compile final response ensuring numbers aren't broken
    result["financial"] = financial
    result["kpi"]       = kpi
    
    # Force strict formatting for frontend reliability
    result["offering_price"] = structural["offering_price_num"]
    result["total_shares"]   = structural["total_shares_num"]
    result["market_cap"]     = structural["market_cap_num"]

    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$",ticker):
        company = result.get("company_name","")
        if company: ticker = search_ticker(company)
        result["ticker"] = ticker

    # Normalize Use of Funds percentage
    uof = result.get("use_of_funds",[])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total*100,2)

    return result