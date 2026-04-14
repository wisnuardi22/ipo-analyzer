"""
gemini_service.py - IPO Analyzer
Arsitektur: 1 LLM CALL per analisis. Financial + Qualitative = 1 mega prompt.
Bahasa output: ENGLISH only (translate via UI button).
"""
from __future__ import annotations
import json, logging, math, os, re, socket, time
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client  = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")
MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = "gemini/gemini-2.5-pro"
_HOST       = socket.gethostname()

# ══════════════════════════════════════════════════════════
# 1. UTILS
# ══════════════════════════════════════════════════════════
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

def fmt_idr(v):
    if v>=1_000_000_000_000: return f"Rp {v/1_000_000_000_000:.2f} Triliun"
    if v>=1_000_000_000:     return f"Rp {v/1_000_000_000:.2f} Miliar"
    return f"Rp {v:,.0f}".replace(",",".")

# ══════════════════════════════════════════════════════════
# 2. METADATA DETECTORS (pure Python)
# ══════════════════════════════════════════════════════════
def detect_currency(text):
    t = text[:5000].lower()
    return "USD" if ("us$" in t or " usd" in t or "dolar amerika" in t) else "IDR"

def detect_unit(text):
    t = text[:10000].lower()
    if re.search(r"dalam\s+jutaan", t): return "jutaan"
    if re.search(r"dalam\s+ribuan", t): return "ribuan"
    if re.search(r"dalam\s+miliar", t): return "miliar"
    return "full"

def detect_fx_rate(text):
    for pat in [r"kurs.*?rp\s*([\d.,]+)\s*per\s*1\s*(?:dollar|dolar|us\$|usd)", r"rp\s*([\d.,]+)\s*/\s*us\$"]:
        m = re.search(pat, text[:20000], re.I)
        if m:
            v = parse_num(m.group(1))
            if v and v>1000: return float(v)
    return None

def is_bank(text):
    t = text[:3000].lower()
    return any(k in t for k in ["bank ","perbankan","banking","simpanan","giro","deposito","tabungan","nim ","car "])

# ══════════════════════════════════════════════════════════
# 3. JSON PARSER
# ══════════════════════════════════════════════════════════
def _safe_json(raw):
    if not raw: return None
    raw = raw.strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"): raw = part; break
    s, e = raw.find("{"), raw.rfind("}")
    if s == -1 or e <= s: return None
    snippet = raw[s:e+1]
    for attempt in [snippet, re.sub(r",\s*([}\]])", r"\1", snippet)]:
        try: return json.loads(attempt)
        except: pass
    return None

# ══════════════════════════════════════════════════════════
# 4. SINGLE LLM CALL — with retry
# ══════════════════════════════════════════════════════════
def _call_llm_once(prompt: str, model: str, max_tokens: int) -> str:
    """Exactly 1 LLM call per analysis. Retry only on rate limit."""
    for attempt in range(4):
        try:
            logger.info(f"[LLM] attempt={attempt+1} model={model} host={_HOST}")
            resp = client.chat.completions.create(
                model=model, temperature=0.1,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            out = resp.choices[0].message.content.strip()
            logger.info(f"[LLM] OK len={len(out)}")
            return out
        except Exception as e:
            err = str(e)
            if "429" in err or "cooling" in err.lower() or "rate" in err.lower():
                wait = 30 * (attempt + 1)
                logger.warning(f"[LLM] Rate limit attempt {attempt+1}/4, wait {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"[LLM] Error: {err[:200]}")
                raise
    raise Exception("Rate limit: server busy, please retry in a few minutes.")

# ══════════════════════════════════════════════════════════
# 5. MEGA PROMPT BUILDER
# ══════════════════════════════════════════════════════════
def _build_mega_prompt(text: str, is_pro: bool, is_banking: bool,
                       currency: str, unit: str) -> str:
    bank_note    = "\nIMPORTANT - THIS IS A BANK: No Gross Profit/Margin. Use NIM/CAR/NPL/BOPO instead." if is_banking else ""
    doc_len      = 250000 if is_pro else 160000
    risk_count   = "5-6" if is_pro else "4-5"
    benefit_count = "5-6" if is_pro else "3-4"
    summary_len  = "3-4 sentences covering company profile, business model, and IPO basics" if is_pro else "2-3 sentences covering company profile and IPO basics"

    return f"""You are a senior IPO analyst with deep expertise in Indonesian capital markets and accounting.
ALL OUTPUT TEXT MUST BE IN ENGLISH. Numbers, dates, and proper nouns stay as-is.{bank_note}

TASK: Complete IPO analysis from the prospectus below. Output ONE JSON object only, no other text.
Read the document VERY CAREFULLY. All data must be ACCURATE per the document.

════════════════════════════════════════
SECTION A — FINANCIAL DATA EXTRACTION
════════════════════════════════════════
1. Find table: "IKHTISAR DATA KEUANGAN PENTING" / "LAPORAN LABA RUGI" / "SELECTED FINANCIAL DATA"
   Read column headers → those are the actual years available in this document.
   For EACH year extract:
   - pendapatan  : Total Revenue / Net Revenue / Penjualan Bersih / Net Interest Income (bank)
   - laba_kotor  : Gross Profit (NULL for banks — they have no gross profit line)
   - laba_usaha  : Operating Profit/Loss — CAN BE NEGATIVE, write as negative number
   - laba_bersih : Net Profit/Loss — CAN BE NEGATIVE, write as negative number
   - depresiasi  : Depreciation & Amortization

2. Find table: "RASIO KEUANGAN PENTING" / "KEY FINANCIAL RATIOS"
   COPY EXACTLY as written — do NOT recalculate:
   - roe  : Return on Equity (%)
   - roa  : Return on Assets (%)
   - der  : Debt/Equity Ratio (x) — NULL for banks
   - npm  : Net Profit Margin (%)
   - eps  : Earnings Per Share (Rp)
   - car  : Capital Adequacy Ratio % — BANKS ONLY
   - npl  : Non-Performing Loan % — BANKS ONLY
   - nim  : Net Interest Margin % — BANKS ONLY
   - bopo : Cost-to-Income Ratio % — BANKS ONLY

3. Balance sheet (LAST YEAR ONLY): total_ekuitas, total_liabilitas, total_aset

4. IPO data: total_saham_beredar (post-IPO shares), harga_penawaran (number only, null if DRHP)

UNIT: "{unit}" — read from table header. Numbers in parentheses = negative: (1.234) → -1234

════════════════════════════════════════
SECTION B — QUALITATIVE ANALYSIS (ALL IN ENGLISH)
════════════════════════════════════════
5. IDENTITY:
   - company_name: full official name including Tbk
   - ticker: find "Kode Saham:" in document
   - sector: industry/sector in English
   - ipo_date: listing date as written
   - share_price: offering price exact string (e.g. "Rp 635")
   - total_shares: exact string from document
   - market_cap: calculate from shares × price or write "N/A"

6. SUMMARY: {summary_len}. Write in English, be specific with numbers.

7. USE OF PROCEEDS — MUST BE ACCURATE:
   Find "Rencana Penggunaan Dana" / "Use of Proceeds"
   - category: translated to English (e.g. "Working Capital", "Capital Expenditure")
   - description: DETAILED with exact nominal amounts (e.g. "Rp 215 billion for 99.99% acquisition of PT XYZ")
   - allocation: EXACT percentage (total MUST equal 100)
   Min 2, max 6 items. NO generic descriptions — each prospectus has unique use of funds.

8. UNDERWRITER:
   - lead: full name of lead underwriter
   - others: array of co-underwriter names (empty [] if none)
   - type: "Full Commitment" or "Best Efforts"
   - reputation: 1-2 sentences in English about track record

9. RISK FACTORS — MUST HAVE VARIED LEVELS (High/Medium/Low):
   Find chapter "Faktor Risiko" / "Risk Factors"
   Extract {risk_count} most important risks.

   LEVEL RULES — STRICT:
   - "High": ONLY if directly threatens business survival:
     • License/permit revocation risk
     • Going concern doubt
     • Single customer >50% of total revenue
     • Material debt default risk
     • Critical acquisition that cannot be completed
   - "Medium": Significant but manageable operational risks:
     • Technology/system dependency • Competition pressure
     • Regulatory changes requiring adaptation
     • Credit/NPL risk • Key person dependency • Cybersecurity
   - "Low": General market risks present in most companies:
     • Share price volatility • Minor FX exposure
     • Force majeure • General macroeconomic conditions

   DISTRIBUTION: 0-2 High, 2-3 Medium, 1-2 Low
   Assess this prospectus INDEPENDENTLY — not all companies have the same risk profile.
   Title and desc MUST be in ENGLISH.

   overall_risk_level: ONE WORD ONLY — "High", "Medium", or "Low". NEVER combined.
   overall_risk_reason: 2 sentences with specific financial facts from THIS prospectus.

10. BENEFITS: {benefit_count} competitive strengths from "Keunggulan Kompetitif" with concrete data.
    Title and desc in ENGLISH.

════════════════════════════════════════
OUTPUT — PURE JSON, NO OTHER TEXT
════════════════════════════════════════
{{
  "financial": {{
    "satuan": "{unit}",
    "mata_uang": "{currency}",
    "tahun_tersedia": ["YEAR_A","YEAR_B","YEAR_C"],
    "data_per_tahun": [
      {{"tahun":"YEAR_A","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}},
      {{"tahun":"YEAR_B","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}}
    ],
    "rasio_per_tahun": [
      {{"tahun":"YEAR_A","roe":null,"roa":null,"der":null,"npm":null,"eps":null,"car":null,"npl":null,"nim":null,"bopo":null}},
      {{"tahun":"YEAR_B","roe":null,"roa":null,"der":null,"npm":null,"eps":null,"car":null,"npl":null,"nim":null,"bopo":null}}
    ],
    "total_ekuitas": null,
    "total_liabilitas": null,
    "total_aset": null,
    "total_saham_beredar": null,
    "harga_penawaran": null
  }},
  "company_name": "",
  "ticker": "",
  "sector": "",
  "ipo_date": "",
  "share_price": "",
  "total_shares": "",
  "market_cap": "",
  "summary": "",
  "use_of_funds": [
    {{"category":"Working Capital","description":"exact detail with nominal amounts","allocation":70}},
    {{"category":"Capital Expenditure","description":"exact detail with nominal amounts","allocation":30}}
  ],
  "underwriter": {{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
  "overall_risk_level": "Medium",
  "overall_risk_reason": "",
  "risks": [
    {{"level":"High","title":"","desc":""}},
    {{"level":"Medium","title":"","desc":""}},
    {{"level":"Medium","title":"","desc":""}},
    {{"level":"Low","title":"","desc":""}}
  ],
  "benefits": [
    {{"title":"","desc":""}}
  ]
}}

PROSPECTUS DOCUMENT:
{text[:doc_len]}"""

# ══════════════════════════════════════════════════════════
# 6. KPI COMPUTATION (pure Python — no LLM)
# ══════════════════════════════════════════════════════════
def _compute_kpi(fin_section: Dict, fx_rate, is_banking: bool, currency: str, unit: str):
    years_data = []
    for d in fin_section.get("data_per_tahun", []):
        nd = dict(d)
        for k in ("pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"):
            nd[k] = apply_unit(nd.get(k), unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data.sort(key=lambda x: str(x.get("tahun","")))

    ekuitas    = apply_unit(fin_section.get("total_ekuitas"), unit)
    liabilitas = apply_unit(fin_section.get("total_liabilitas"), unit)
    saham      = parse_num(fin_section.get("total_saham_beredar"))
    harga      = parse_num(fin_section.get("harga_penawaran"))
    harga_idr  = harga * fx_rate if (harga and currency == "USD" and fx_rate) else harga

    rev_growth, gross_m, op_m, ebitda_m, net_m = [], [], [], [], []
    prev_rev = None
    for yr in years_data:
        y   = str(yr.get("tahun",""))
        rev = yr.get("pendapatan")
        gp  = yr.get("laba_kotor")
        op  = yr.get("laba_usaha")
        net = yr.get("laba_bersih")
        dep = yr.get("depresiasi")
        rev_growth.append({"year": y, "value": 0.0 if prev_rev is None else calc_growth(rev, prev_rev)})
        prev_rev = rev
        gross_m.append({"year": y, "value": None if is_banking else to_pct(safe_div(gp, rev))})
        op_m.append({"year": y, "value": to_pct(safe_div(op, rev))})
        try:
            ebitda_val = to_pct(safe_div(float(op)+float(dep), rev)) if (dep is not None and op is not None and rev) else None
        except: ebitda_val = None
        ebitda_m.append({"year": y, "value": ebitda_val})
        net_m.append({"year": y, "value": to_pct(safe_div(net, rev))})

    # KPI — ROE, ROA, DER, EPS + bank extras
    kpi = {
        "pe": "N/A", "pb": "N/A",
        "roe": "N/A", "roa": "N/A", "der": "N/A", "eps": "N/A",
        "market_cap": "N/A",
        "roe_by_year": {}, "roa_by_year": {}, "der_by_year": {}, "eps_by_year": {},
        "extra_by_year": {}
    }
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    rasio_list = fin_section.get("rasio_per_tahun", [])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, key in [("roe","roe_by_year"),("roa","roa_by_year"),
                                ("der","der_by_year"),("eps","eps_by_year")]:
                v = parse_num(r.get(field))
                if v is not None: kpi[key][y] = v
            # Bank extras: CAR, NPL, NIM, BOPO
            extra = {f: parse_num(r.get(f)) for f in ("car","npl","nim","bopo")
                     if parse_num(r.get(f)) is not None}
            if extra: kpi["extra_by_year"][y] = extra

        last_r = rasio_list[-1] if rasio_list else {}
        if parse_num(last_r.get("roe")) is not None: kpi["roe"] = f"{parse_num(last_r['roe']):.2f}%"
        if parse_num(last_r.get("roa")) is not None: kpi["roa"] = f"{parse_num(last_r['roa']):.2f}%"
        if parse_num(last_r.get("der")) is not None: kpi["der"] = f"{parse_num(last_r['der']):.2f}x"
        if parse_num(last_r.get("eps")) is not None: kpi["eps"] = f"Rp {parse_num(last_r['eps']):.2f}"

    # Fallback calculations if no ratio table
    try:
        if saham and laba_last and saham > 0 and kpi["eps"] == "N/A":
            ev = laba_last / saham
            kpi["eps"] = f"Rp {ev:,.2f}".replace(",",".")
            if harga_idr and ev > 0:  kpi["pe"] = f"{harga_idr/ev:.1f}x"
            elif harga_idr and ev < 0: kpi["pe"] = "N/A (Loss)"
    except: pass
    try:
        if ekuitas and saham and saham > 0 and harga_idr and ekuitas > 0:
            bv = ekuitas / saham
            if bv > 0: kpi["pb"] = f"{harga_idr/bv:.2f}x"
    except: pass
    try:
        if not has_rasio and ekuitas and laba_last and ekuitas > 0 and kpi["roe"] == "N/A":
            kpi["roe"] = f"{laba_last/ekuitas*100:.2f}%"
    except: pass
    try:
        if not has_rasio and not is_banking and ekuitas and liabilitas and ekuitas > 0 and kpi["der"] == "N/A":
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
    except: pass
    try:
        if saham and harga and saham > 0 and harga > 0:
            kpi["market_cap"] = fmt_idr(saham * (harga_idr if harga_idr else harga))
    except: pass

    financial = {
        "currency": currency,
        "years": [str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun": rasio_list,
        "absolute_data": years_data,
        "is_banking": is_banking,
        "revenue_growth":    rev_growth or None,
        "gross_margin":      gross_m    or None,
        "operating_margin":  op_m       or None,
        "ebitda_margin":     ebitda_m   or None,
        "net_profit_margin": net_m      or None,
    }
    return financial, kpi

# ══════════════════════════════════════════════════════════
# 7. RISK SCORING (pure Python — no LLM)
# ══════════════════════════════════════════════════════════
_HIGH_SIGNALS = [
    "pencabutan izin", "license revocation", "going concern", "substantial doubt",
    "gagal bayar", "material default", "pailit", "bankruptcy",
    r"satu pelanggan.*\d{2,3}%", r"single customer.*\d{2,3}%",
    r"konsentrasi.*>\s*40%", "perubahan status pma",
    "tidak dapat mempertahankan izin", "material adverse",
]
_LOW_SIGNALS = [
    "harga saham", "share price volatility", "likuiditas saham",
    "market liquidity", "volatilitas pasar modal", "general market",
    "force majeure", "bencana alam", "natural disaster",
    "pandemi", "pandemic", "kondisi ekonomi makro secara umum",
    "general macroeconomic",
]

def score_risk(title: str, desc: str) -> str:
    """Validate & correct LLM risk level using keyword signals."""
    text = (title + " " + (desc or "")).lower()
    for sig in _HIGH_SIGNALS:
        if re.search(sig, text): return "High"
    low_count = sum(1 for s in _LOW_SIGNALS if re.search(s, text))
    if low_count >= 1: return "Low"
    return "Medium"

# ══════════════════════════════════════════════════════════
# 8. TICKER SEARCH
# ══════════════════════════════════════════════════════════
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
            params={"q":cleaned,"lang":"id","region":"ID","quotesCount":10,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=8)
        for q in resp.json().get("quotes",[]):
            sym = q.get("symbol","")
            if sym.endswith(".JK"):
                t = sym.replace(".JK","").upper()
                if t not in EXCLUDE and 2 <= len(t) <= 6: return t
    except: pass
    return ""

# ══════════════════════════════════════════════════════════
# 9. MAIN — 1 LLM CALL TOTAL
# ══════════════════════════════════════════════════════════
def analyze_prospectus(text: str, lang: str="ID", model: str=None) -> dict:
    """
    ONE LLM call per analysis.
    Output is always in English regardless of lang parameter.
    lang parameter kept for API compatibility.
    """
    is_pro   = (model == MODEL_PRO)
    banking  = is_bank(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)
    fx_rate  = detect_fx_rate(text)
    _model   = MODEL_PRO if is_pro else MODEL_FLASH
    max_tok  = 12000 if is_pro else 8000

    logger.info(f"[START] host={_HOST} model={_model} is_pro={is_pro} len={len(text)} banking={banking} unit={unit}")

    # ── SINGLE LLM CALL ───────────────────────────────────
    prompt = _build_mega_prompt(text, is_pro, banking, currency, unit)
    raw    = _call_llm_once(prompt, model=_model, max_tokens=max_tok)
    parsed = _safe_json(raw)

    # Repair truncated JSON
    if not parsed:
        fixed = re.sub(r",\s*([}\]])", r"\1", raw)
        s = fixed.find("{")
        if s != -1:
            snippet = fixed[s:]
            ob = max(0, snippet.count("{") - snippet.count("}"))
            ol = max(0, snippet.count("[") - snippet.count("]"))
            parsed = _safe_json(snippet + ("]"*ol) + ("}"*ob))
    if not parsed:
        raise ValueError(f"Failed to parse LLM JSON output: {raw[:300]}")

    # ── EXTRACT & COMPUTE FINANCIAL ───────────────────────
    fin_section = parsed.pop("financial", {})
    fin_section.setdefault("satuan", unit)
    fin_section.setdefault("mata_uang", currency)
    financial, kpi = _compute_kpi(fin_section, fx_rate, banking, currency, unit)
    logger.info(f"[KPI] {json.dumps(kpi, ensure_ascii=False)}")

    parsed["financial"] = financial
    parsed["kpi"]       = kpi

    # ── RISK LEVEL CORRECTION ─────────────────────────────
    high_count = medium_count = 0
    for r in parsed.get("risks", []):
        llm_lvl   = str(r.get("level","Medium")).strip().capitalize()
        scored    = score_risk(r.get("title",""), r.get("desc",""))
        prio      = {"High":3,"Medium":2,"Low":1}
        # Use lower of LLM vs scoring — prevent inflation to High
        final_lvl = scored if prio.get(scored,2) < prio.get(llm_lvl,2) else llm_lvl
        r["level"] = final_lvl
        if final_lvl == "High":    high_count += 1
        elif final_lvl == "Medium": medium_count += 1

    # Force overall_risk_level to single word
    if high_count >= 2:                          parsed["overall_risk_level"] = "High"
    elif high_count == 1 or medium_count >= 2:   parsed["overall_risk_level"] = "Medium"
    else:                                        parsed["overall_risk_level"] = "Low"

    # ── TICKER ────────────────────────────────────────────
    ticker = str(parsed.get("ticker","")).strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$", ticker):
        company = parsed.get("company_name","")
        if company: ticker = search_ticker(company)
        parsed["ticker"] = ticker

    # ── VALIDATE USE OF FUNDS ─────────────────────────────
    uof = parsed.get("use_of_funds", [])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total*100, 2)

    logger.info(f"[DONE] company={parsed.get('company_name','')} ticker={parsed.get('ticker','')} risks={len(parsed.get('risks',[]))}")
    return parsed