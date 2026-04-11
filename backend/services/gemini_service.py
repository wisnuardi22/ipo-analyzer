"""
gemini_service.py - IPO Analyzer Backend
Pipeline: detect metadata → LLM financial extraction → Python KPI → LLM qualitative (Basic/Pro)
"""
from __future__ import annotations
import json, logging, math, os, re
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")
MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = "gemini/gemini-2.5-pro"
MODEL       = MODEL_FLASH

# ── UTILS ─────────────────────────────────────────────────────────────
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
        p = s.split(",")
        s = s.replace(",",".") if len(p)==2 and len(p[1])<=2 else s.replace(",","")
    elif "." in s:
        p = s.split(".")
        if not (len(p)==2 and len(p[1])<=2): s = s.replace(".","")
    try:
        v = float(s); return -v if neg else v
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

def to_pct(val):
    v = parse_num(val)
    return round(v*100,2) if v is not None and not math.isnan(v) else None

def calc_growth(cur, prev):
    c, p = parse_num(cur), parse_num(prev)
    if c is None or p is None or p==0: return None
    return round((c-p)/abs(p)*100,2)

def fmt_idr(value):
    if value>=1_000_000_000_000: return f"Rp {value/1_000_000_000_000:.2f} Triliun"
    if value>=1_000_000_000: return f"Rp {value/1_000_000_000:.2f} Miliar"
    return f"Rp {value:,.0f}".replace(",",".")

# ── METADATA ──────────────────────────────────────────────────────────
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
    return any(k in t for k in ["bank","perbankan","banking","simpanan","giro","deposito","tabungan","kredit","nim "])

# ── LLM FINANCIAL EXTRACTION ──────────────────────────────────────────
_FIN_KEYWORDS = [
    "laporan laba rugi","ikhtisar data keuangan","data keuangan penting",
    "ringkasan keuangan","informasi keuangan","laba kotor","laba usaha",
    "laba bersih","pendapatan usaha","pendapatan bersih","penjualan bersih",
    "posisi keuangan","neraca","ekuitas","liabilitas","31 desember",
    "rasio keuangan","rasio penting","rasio keuangan penting","konsolidasian",
    "gross profit","net revenue","operating profit","net income","profit or loss",
    "statement of profit","balance sheet","selected financial","financial highlights",
    "total aset","total assets","return on equity","return on asset",
    "debt to equity","earnings per share","laba per saham","imbal hasil",
    "pendapatan bunga","net interest income","nim","car","npl","bopo",
]

_FIN_SYSTEM = """Kamu adalah akuntan senior Indonesia. Ekstrak data keuangan LENGKAP dari potongan prospektus IPO.
Output HANYA JSON murni tanpa teks lain, tanpa markdown.

STEP 1 - LAPORAN LABA RUGI / INCOME STATEMENT
Cari tabel: "LAPORAN LABA RUGI","IKHTISAR DATA KEUANGAN PENTING","SELECTED FINANCIAL DATA"
Untuk SETIAP tahun di kolom header:
  pendapatan  = Total Pendapatan / Net Revenue / Pendapatan Bunga Bersih (untuk bank)
  laba_kotor  = Laba Kotor / Gross Profit (null untuk bank)
  laba_usaha  = Laba/Rugi Usaha / Operating Profit/Loss (BISA NEGATIF)
  laba_bersih = Laba/Rugi Bersih / Net Profit/Loss (BISA NEGATIF)
  depresiasi  = Depresiasi & Amortisasi

STEP 2 - RASIO KEUANGAN PENTING (WAJIB DIBACA)
Cari tabel: "RASIO KEUANGAN PENTING","KEY FINANCIAL RATIOS","RASIO-RASIO PENTING"
SALIN PERSIS angka yang tertulis untuk setiap tahun:
  roe = ROE / Imbal Hasil Ekuitas (%)
  roa = ROA / Imbal Hasil Aset (%)
  der = DER / Debt to Equity (x) — untuk bank biasanya N/A, tulis null
  npm = Net Profit Margin (%)
  gpm = Gross Profit Margin (%) — untuk bank biasanya N/A
  eps = EPS / Laba per Saham (Rp)
  car = CAR / Capital Adequacy Ratio (%) — khusus bank
  npl = NPL / Non Performing Loan (%) — khusus bank
  nim = NIM / Net Interest Margin (%) — khusus bank
  bopo = BOPO / Cost to Income Ratio (%) — khusus bank
PENTING: SALIN angka PERSIS, JANGAN hitung sendiri!

STEP 3 - NERACA
Dari tabel posisi keuangan, tahun TERAKHIR:
  total_ekuitas, total_liabilitas, total_aset

STEP 4 - INFO IPO
  total_saham_beredar = total saham setelah IPO
  harga_penawaran = harga per saham (angka saja, null jika DRHP)

OUTPUT JSON:
{
  "satuan": "jutaan",
  "mata_uang": "IDR",
  "tahun_tersedia": ["2022","2023","2024"],
  "data_per_tahun": [
    {"tahun":"2022","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}
  ],
  "rasio_per_tahun": [
    {"tahun":"2022","roe":null,"roa":null,"der":null,"npm":null,"gpm":null,"eps":null,"car":null,"npl":null,"nim":null,"bopo":null}
  ],
  "total_ekuitas": null,
  "total_liabilitas": null,
  "total_aset": null,
  "total_saham_beredar": null,
  "harga_penawaran": null
}"""

def _chunk_text(text, max_len=18000, overlap=800):
    if len(text)<=max_len: return [text]
    chunks, i = [], 0
    while i<len(text):
        chunks.append(text[i:i+max_len])
        i += max_len-overlap
    return chunks

def _safe_json(raw):
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

def llm_extract_financials(text, model=None):
    _m = model or MODEL_FLASH
    merged = {
        "satuan":None,"mata_uang":None,
        "tahun_tersedia":[],"data_per_tahun":[],
        "rasio_per_tahun":[],
        "total_ekuitas":None,"total_liabilitas":None,"total_aset":None,
        "total_saham_beredar":None,"harga_penawaran":None,
    }
    all_chunks = _chunk_text(text)
    priority, others = [], []
    for c in all_chunks:
        cl = c.lower()
        if "daftar isi" in cl and cl.count("halaman")>5: continue
        if any(k in cl for k in _FIN_KEYWORDS): priority.append(c)
        else: others.append(c)

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
                    {"role":"user","content":f"EKSTRAK DATA KEUANGAN:\n\n{chunk}"},
                ],
            )
            part = _safe_json(resp.choices[0].message.content) or {}
        except Exception as e:
            logger.warning(f"FIN chunk: {e}"); part = {}

        for k in ("satuan","mata_uang"):
            if not merged[k] and part.get(k): merged[k] = part[k]
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(set(merged["tahun_tersedia"])|{str(y) for y in part["tahun_tersedia"]})
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
        if part.get("rasio_per_tahun"):
            r = {str(x.get("tahun","")).strip():x for x in merged["rasio_per_tahun"]}
            for x in part["rasio_per_tahun"]:
                y = str(x.get("tahun","")).strip()
                if not y: continue
                if y in r:
                    for k in ("roe","roa","der","npm","gpm","eps","car","npl","nim","bopo"):
                        v = x.get(k)
                        if r[y].get(k) is None and v is not None and str(v).strip() not in ("null",""):
                            r[y][k] = v
                else: r[y] = x
            merged["rasio_per_tahun"] = [r[k] for k in sorted(r.keys())]
        for k in ("total_ekuitas","total_liabilitas","total_aset","total_saham_beredar","harga_penawaran"):
            v = part.get(k)
            if merged.get(k) is None and v is not None and str(v).strip() not in ("null",""):
                merged[k] = v

    logger.info(f"[FIN] tahun={merged.get('tahun_tersedia')} saham={merged.get('total_saham_beredar')} harga={merged.get('harga_penawaran')} rasio={len(merged.get('rasio_per_tahun',[]))}")
    return merged

# ── NORMALIZE + COMPUTE KPI ───────────────────────────────────────────
def normalize_and_compute(fin_raw, fx_rate, is_banking=False):
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
        # Bank tidak punya gross margin
        gross_margin.append({"year":y,"value":to_pct(safe_div(gp,rev)) if not is_banking else None})
        op_margin.append({"year":y,"value":to_pct(safe_div(op,rev))})
        ebitda_margin.append({
            "year":y,
            "value":to_pct(safe_div(float(op)+float(dep),rev)) if (dep is not None and op is not None and rev) else None
        })
        net_margin.append({"year":y,"value":to_pct(safe_div(net,rev))})

    kpi: Dict = {
        "pe":"N/A","pb":"N/A","roe":"N/A","der":"N/A","eps":"N/A","market_cap":"N/A",
        "roe_by_year":{},"der_by_year":{},"eps_by_year":{},
        "extra_by_year":{}  # untuk bank: CAR, NPL, NIM, BOPO
    }
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    # Baca rasio dari tabel Rasio Keuangan Penting
    rasio_list = fin_raw.get("rasio_per_tahun",[])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, key in [("roe","roe_by_year"),("der","der_by_year"),("eps","eps_by_year")]:
                v = parse_num(r.get(field))
                if v is not None: kpi[key][y] = v
            # Extra rasio untuk bank
            extra = {}
            for field in ("car","npl","nim","bopo","roa"):
                v = parse_num(r.get(field))
                if v is not None: extra[field] = v
            if extra: kpi["extra_by_year"][y] = extra

        last_r = rasio_list[-1] if rasio_list else {}
        roe_v = parse_num(last_r.get("roe"))
        der_v = parse_num(last_r.get("der"))
        eps_v = parse_num(last_r.get("eps"))
        if roe_v is not None: kpi["roe"] = f"{roe_v:.2f}%"
        if der_v is not None: kpi["der"] = f"{der_v:.2f}x"
        if eps_v is not None:
            kpi["eps"] = f"Rp {eps_v:,.2f}".replace(",",".") if currency=="IDR" else f"{eps_v:.2f}"

    # Fallback kalkulasi hanya jika tidak ada rasio
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
        if not has_rasio and not is_banking and ekuitas and liabilitas and ekuitas>0 and kpi["der"]=="N/A":
            kpi["der"] = f"{liabilitas/ekuitas:.2f}x"
    except: pass
    try:
        if saham and harga and saham>0 and harga>0:
            mc = saham*(harga_idr if harga_idr else harga)
            kpi["market_cap"] = fmt_idr(mc)
    except: pass

    financial = {
        "currency":         currency,
        "years":            [str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun":  rasio_list,
        "absolute_data":    years_data,
        "revenue_growth":   revenue_growth or None,
        "gross_margin":     gross_margin or None,
        "operating_margin": op_margin or None,
        "ebitda_margin":    ebitda_margin or None,
        "net_profit_margin":net_margin or None,
        "is_banking":       is_banking,
    }
    return financial, kpi

# ── RISK SCORING LOGIC ────────────────────────────────────────────────
_RISK_HIGH_KEYWORDS = [
    "ketergantungan","konsentrasi","pelanggan utama","satu pelanggan",
    "perizinan","regulasi otoritas","pencabutan izin","sanksi",
    "gagal bayar","kredit bermasalah","npl tinggi","modal minimum",
    "akuisisi tidak selesai","status pma","perubahan status",
    "fraud","penipuan","keamanan data","siber","kebocoran data",
    "rugi bersih","kerugian material","going concern",
    "customer concentration","regulatory","license revocation",
    "data breach","cyber attack","material loss",
]
_RISK_LOW_KEYWORDS = [
    "fluktuasi nilai tukar","perubahan kecil","minor","terbatas",
    "tidak material","dampak minimal","risiko umum","pasar modal",
    "harga saham","likuiditas saham","volatilitas",
    "exchange rate","minor impact","general market",
]

def score_risk(title, desc):
    """Tentukan level risiko berdasarkan konten, bukan hanya kata LLM."""
    text = (title + " " + desc).lower()
    high_score = sum(1 for k in _RISK_HIGH_KEYWORDS if k in text)
    low_score  = sum(1 for k in _RISK_LOW_KEYWORDS if k in text)
    if high_score >= 2: return "High"
    if low_score >= 2:  return "Low"
    if high_score == 1: return "Medium"
    return "Medium"

# ── LLM QUALITATIVE ───────────────────────────────────────────────────
def llm_qualitative(text, kpi, financial, lang="ID", model=None):
    _m = model or MODEL_FLASH
    is_pro  = _m == MODEL_PRO
    is_en   = lang.upper() == "EN"
    currency = financial.get("currency","IDR")
    years    = financial.get("years",[])
    rasio    = financial.get("rasio_per_tahun",[])
    banking  = financial.get("is_banking", False)

    lang_instr = "ALL text in ENGLISH." if is_en else "SEMUA teks dalam BAHASA INDONESIA."
    sector_note = "This is a BANK - no gross margin, use NIM/CAR/NPL/BOPO ratios." if banking else ""

    # Summary length
    summary_instr = (
        "summary: 1 SHORT paragraph (max 3 sentences) covering company profile and IPO basics." if not is_pro
        else "summary: 3 detailed paragraphs (\\n\\n separated). P1: company profile + metrics. P2: IPO structure. P3: financial performance + outlook."
    )

    # UoF detail level
    uof_instr = (
        """use_of_funds: Find 'Rencana Penggunaan Dana'/'Use of Proceeds'. Extract ALL items.
CRITICAL: Read the EXACT nominal amounts and percentages from the document.
- category: exact name from document
- description: include SPECIFIC amounts (e.g. 'Rp 215 miliar untuk akuisisi 99,99% saham PT XYZ')
- allocation: EXACT percentage from document (must sum to 100)
DO NOT use generic descriptions. Every prospectus has unique use of proceeds."""
    )

    # Risk detail
    if is_pro:
        risk_instr = """risks: Find 'Faktor Risiko'/'Risk Factors'. Extract 5-7 risks.
IMPORTANT - Assign level based on actual impact:
- "High": material risk that could threaten business survival or major revenue loss (e.g. license revocation, customer concentration >50%, going concern doubt)
- "Medium": significant but manageable operational/financial risk (e.g. technology dependency, competition, regulatory changes)  
- "Low": minor/market-general risks (e.g. share price volatility, minor FX exposure, general market conditions)
Each risk: level (High/Medium/Low), title (exact from doc), desc (2-3 sentences with specific data/percentages)
overall_risk_level: aggregate assessment. overall_risk_reason: 3 sentences with specific facts."""
        benefit_instr = """benefits: Find 'Keunggulan Kompetitif'/'Competitive Strengths'. Extract 5-7 items.
Each: title (exact from doc), desc (2-3 sentences with specific numbers/market share)"""
    else:
        risk_instr = """risks: Find 'Faktor Risiko'. Extract 4-5 main risks.
Assign level based on actual impact severity:
- "High": could threaten core business operations or major revenue
- "Medium": significant but manageable risk  
- "Low": minor/general market risk
Each: level (High/Medium/Low), title (exact name), desc (1 sentence)
overall_risk_level: High/Medium/Low. overall_risk_reason: 2 sentences."""
        benefit_instr = """benefits: Find 'Keunggulan Kompetitif'. Extract 3-4 main strengths.
Each: title (exact from doc), desc (1 sentence with key number)"""

    prompt = f"""You are a senior IPO analyst. Analyze this prospectus accurately. Output ONLY JSON.

{lang_instr}
{sector_note}
Currency: {currency}
KPI data (copy exactly, do not recalculate): {json.dumps(kpi, ensure_ascii=False)}
Financial years: {years}
Ratio table: {json.dumps(rasio[:5], ensure_ascii=False)}

EXTRACT:
A. company_name, ticker (find "Kode Saham:"/"Stock Code:"), sector, ipo_date, share_price (exact), total_shares, market_cap (copy from KPI)
B. {summary_instr}
C. {uof_instr}
D. underwriter: lead, others (array), type ("Full Commitment"/"Best Efforts"), reputation (2 sentences analyzing track record)
E. {risk_instr}
F. {benefit_instr}

DOCUMENT (read carefully):
{text[:380000] if is_pro else text[:200000]}

OUTPUT JSON (all fields required):
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"",
"summary":"",
"use_of_funds":[{{"category":"","description":"","allocation":70}},{{"category":"","description":"","allocation":30}}],
"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
"overall_risk_level":"Medium","overall_risk_reason":"",
"risks":[{{"level":"High","title":"","desc":""}},{{"level":"Medium","title":"","desc":""}},{{"level":"Low","title":"","desc":""}}],
"benefits":[{{"title":"","desc":""}}]}}"""

    try:
        resp = client.chat.completions.create(
            model=_m, temperature=0.1, max_tokens=16000,
            messages=[{"role":"user","content":prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result:
            # Re-score risk levels menggunakan logika kita
            for r in result.get("risks",[]):
                llm_level = r.get("level","Medium")
                scored    = score_risk(r.get("title",""), r.get("desc",""))
                # Ambil yang lebih tinggi antara LLM dan scoring kita
                priority  = {"High":3,"Medium":2,"Low":1}
                r["level"] = llm_level if priority.get(llm_level,2) >= priority.get(scored,2) else scored
            return result

        # Repair truncated JSON
        fixed = re.sub(r",\s*([}\]])",r"\1",raw)
        s = fixed.find("{")
        if s != -1:
            snippet = fixed[s:]
            ob = snippet.count("{") - snippet.count("}")
            ol = snippet.count("[") - snippet.count("]")
            closed = snippet + ("]"*max(0,ol)) + ("}"*max(0,ob))
            result = _safe_json(closed)
            if result: return result
            for end in range(len(fixed), s, -100):
                try: return json.loads(fixed[s:end])
                except: pass
        raise ValueError(f"JSON parse failed: {raw[:200]}")
    except Exception as e:
        logger.error(f"LLM qualitative: {e}")
        raise ValueError(f"Gagal analisis kualitatif: {e}")

# ── TICKER SEARCH ─────────────────────────────────────────────────────
def search_ticker_by_name(company_name):
    import requests
    HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
    EXCLUDE = {"PT","TBK","IDX","BEI","OJK","IDR","USD","IPO","ROE","DER","EPS","CAR","NPL","NIM"}
    def clean(n):
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
                    logger.info(f"Ticker: {t}"); return t
    except Exception as e: logger.warning(f"Yahoo: {e}")
    return ""

# ── MAIN ──────────────────────────────────────────────────────────────
def analyze_prospectus(text, lang="ID", model=None):
    lang   = (lang or "ID").upper()
    _model = model or MODEL_FLASH
    banking = is_bank(text)
    logger.info(f"[START] lang={lang} model={_model} len={len(text)} banking={banking}")

    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    fin_raw = llm_extract_financials(text, model=_model)
    if not fin_raw.get("satuan"):    fin_raw["satuan"]    = unit
    if not fin_raw.get("mata_uang"): fin_raw["mata_uang"] = currency

    financial, kpi = normalize_and_compute(fin_raw, fx_rate, is_banking=banking)
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

    # Validasi UoF
    uof = result.get("use_of_funds",[])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            logger.warning(f"UoF total={total:.1f}, normalisasi")
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total*100,2)

    return result