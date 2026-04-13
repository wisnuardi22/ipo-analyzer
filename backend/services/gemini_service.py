"""
gemini_service.py - IPO Analyzer
Arsitektur: 1 LLM CALL per analisis (hemat maksimal).
Financial + Qualitative digabung dalam 1 prompt.
"""
from __future__ import annotations
import json, logging, math, os, re, socket, time
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")
MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = "gemini/gemini-2.5-pro"
MODEL       = MODEL_FLASH
_HOST       = socket.gethostname()

# ══════════════════════════════════════════
# 1. UTILS
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

def fmt_idr(v):
    if v>=1_000_000_000_000: return f"Rp {v/1_000_000_000_000:.2f} Triliun"
    if v>=1_000_000_000:     return f"Rp {v/1_000_000_000:.2f} Miliar"
    return f"Rp {v:,.0f}".replace(",",".")

# ══════════════════════════════════════════
# 2. METADATA (pure Python, no LLM)
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
            v = parse_num(m.group(1)); return float(v) if v and v>1000 else None
    return None

def is_bank(text):
    t = text[:3000].lower()
    return any(k in t for k in ["bank ","perbankan","banking","simpanan","giro","deposito","tabungan","nim ","car "])

# ══════════════════════════════════════════
# 3. SAFE JSON PARSER
# ══════════════════════════════════════════
def _safe_json(raw):
    if not raw: return None
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

# ══════════════════════════════════════════
# 4. SINGLE LLM CALL — MEGA PROMPT
# ══════════════════════════════════════════
def _call_llm_once(prompt: str, model: str, max_tokens: int) -> str:
    """
    1 LLM call dengan retry untuk rate limit.
    Tidak ada loop, tidak ada multi-chunk.
    """
    for attempt in range(4):
        try:
            logger.info(f"[LLM] attempt={attempt+1} model={model} max_tok={max_tokens} host={_HOST}")
            resp = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            result = resp.choices[0].message.content.strip()
            logger.info(f"[LLM] OK len={len(result)}")
            return result
        except Exception as e:
            err = str(e)
            if "429" in err or "cooling" in err.lower() or "rate" in err.lower():
                wait = 30 * (attempt + 1)
                logger.warning(f"[LLM] Rate limit attempt {attempt+1}/4, tunggu {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"[LLM] Error: {err[:200]}")
                raise
    raise Exception("Rate limit: server sibuk, coba lagi dalam beberapa menit.")

# ══════════════════════════════════════════
# 5. MEGA PROMPT — semua dalam 1 call
# ══════════════════════════════════════════
def _build_mega_prompt(text: str, lang: str, is_pro: bool, is_banking: bool,
                       currency: str, unit: str) -> str:
    is_en     = lang.upper() == "EN"
    lang_note = "ALL text fields MUST be in ENGLISH." if is_en else "SEMUA field teks WAJIB dalam BAHASA INDONESIA."
    bank_note = "\nPERHATIAN - INI ADALAH BANK: Tidak ada Gross Profit/Margin. Gunakan NIM/CAR/NPL/BOPO." if is_banking else ""
    doc_len   = 250000 if is_pro else 160000
    risk_count = "5-6" if is_pro else "4-5"
    benefit_count = "5-6" if is_pro else "3-4"

    doc_excerpt = text[:doc_len]

    prompt = f"""Kamu adalah analis IPO senior Indonesia dengan keahlian akuntansi dan investasi.
{lang_note}{bank_note}

TUGAS: Analisis LENGKAP prospektus IPO berikut dalam SATU output JSON.
Baca dokumen dengan SANGAT TELITI. Semua data harus AKURAT sesuai dokumen.

═══════════════════════════════════════
BAGIAN A — DATA KEUANGAN
═══════════════════════════════════════
1. Cari tabel "IKHTISAR DATA KEUANGAN PENTING" / "LAPORAN LABA RUGI" / "SELECTED FINANCIAL DATA"
   Baca header kolom → itulah tahun-tahun yang tersedia (pakai tahun PERSIS dari dokumen)
   Untuk SETIAP tahun, ekstrak:
   - pendapatan: Total Pendapatan / Net Revenue / Penjualan Bersih / Pendapatan Bunga Bersih (bank)
   - laba_kotor: Laba Kotor / Gross Profit (NULL untuk bank)
   - laba_usaha: Laba/Rugi Usaha / Operating Profit (BOLEH NEGATIF)
   - laba_bersih: Laba/Rugi Bersih / Net Profit (BOLEH NEGATIF)
   - depresiasi: Depresiasi & Amortisasi

2. Cari tabel "RASIO KEUANGAN PENTING" / "KEY FINANCIAL RATIOS"
   SALIN PERSIS angka yang tertulis, jangan hitung sendiri:
   - roe: ROE / Imbal Hasil Ekuitas (%)
   - roa: ROA / Return on Asset (%)
   - der: DER / Debt to Equity (NULL untuk bank)
   - npm: Net Profit Margin (%)
   - eps: EPS / Laba per Saham (Rp)
   - car: Capital Adequacy Ratio % (BANK ONLY)
   - npl: Non Performing Loan % (BANK ONLY)
   - nim: Net Interest Margin % (BANK ONLY)
   - bopo: BOPO / Cost to Income % (BANK ONLY)

3. Neraca (TAHUN TERAKHIR): total_ekuitas, total_liabilitas, total_aset

4. IPO info: total_saham_beredar (setelah IPO), harga_penawaran (angka saja, null jika DRHP)

SATUAN: "{unit}" (baca dari header tabel). Angka dalam kurung = negatif: (1.234) → -1234

═══════════════════════════════════════
BAGIAN B — ANALISIS KUALITATIF
═══════════════════════════════════════
5. IDENTITAS: company_name (lengkap+Tbk), ticker (cari "Kode Saham:"), sector, ipo_date, share_price (exact string), total_shares (exact string), market_cap (hitung dari saham×harga atau tulis N/A)

6. SUMMARY: 1 paragraf {'English' if is_en else 'Bahasa Indonesia'} — profil + IPO info (max 4 kalimat)

7. USE OF PROCEEDS — WAJIB AKURAT:
   Cari "Rencana Penggunaan Dana" / "Use of Proceeds"
   - category: nama PERSIS dari dokumen
   - description: DETAIL dengan nilai nominal (misal: "Rp 215 miliar untuk akuisisi 99,99% PT XYZ")
   - allocation: persentase PERSIS (total HARUS = 100)
   Min 2 item, max 6 item. JANGAN generik.

8. UNDERWRITER: lead (nama lengkap), others (array kosong [] jika tidak ada), type ("Full Commitment"/"Best Efforts"), reputation (1-2 kalimat)

9. RISK FACTORS — WAJIB BERVARIASI:
   Cari bab "Faktor Risiko"
   Ekstrak {risk_count} risiko TERPENTING. Aturan level KETAT:
   - "High": HANYA jika ancam kelangsungan bisnis langsung:
     * Pencabutan izin usaha * Going concern doubt
     * 1 pelanggan >50% revenue * Gagal bayar material
     * Akuisisi kritis tidak dapat dilaksanakan
   - "Medium": Risiko signifikan tapi manageable:
     * Ketergantungan teknologi * Persaingan * Regulasi
     * Risiko kredit/NPL * SDM/manajemen * Operasional
   - "Low": Risiko pasar umum minor:
     * Volatilitas harga saham * FX exposure kecil
     * Force majeure * Kondisi makro umum
   DISTRIBUSI NORMAL: 0-2 High, 2-3 Medium, 1-2 Low
   Nilai setiap prospektus SECARA INDEPENDEN berdasarkan kondisi SPESIFIK perusahaan ini.
   overall_risk_level: PILIH SATU KATA SAJA: "High" atau "Medium" atau "Low"
   overall_risk_reason: 2 kalimat fakta spesifik perusahaan ini

10. BENEFITS: {benefit_count} keunggulan dari "Keunggulan Kompetitif" dengan data konkret

═══════════════════════════════════════
OUTPUT FORMAT — JSON MURNI, TIDAK ADA TEKS LAIN
═══════════════════════════════════════
{{
  "financial": {{
    "satuan": "{unit}",
    "mata_uang": "{currency}",
    "tahun_tersedia": ["TAHUN_A","TAHUN_B"],
    "data_per_tahun": [
      {{"tahun":"TAHUN_A","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}}
    ],
    "rasio_per_tahun": [
      {{"tahun":"TAHUN_A","roe":null,"roa":null,"der":null,"npm":null,"eps":null,"car":null,"npl":null,"nim":null,"bopo":null}}
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
  "use_of_funds": [{{"category":"","description":"detail nominal","allocation":70}}],
  "underwriter": {{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
  "overall_risk_level": "Medium",
  "overall_risk_reason": "",
  "risks": [
    {{"level":"High","title":"","desc":""}},
    {{"level":"Medium","title":"","desc":""}},
    {{"level":"Low","title":"","desc":""}}
  ],
  "benefits": [{{"title":"","desc":""}}]
}}

DOKUMEN PROSPEKTUS:
{doc_excerpt}"""

    return prompt

# ══════════════════════════════════════════
# 6. KPI COMPUTATION (pure Python)
# ══════════════════════════════════════════
def _compute_kpi(fin_section: Dict, fx_rate, is_banking: bool, currency: str, unit: str):
    years_data = []
    for d in fin_section.get("data_per_tahun",[]):
        nd = dict(d)
        for k in ("pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"):
            nd[k] = apply_unit(nd.get(k),unit) if nd.get(k) is not None else None
        years_data.append(nd)
    years_data.sort(key=lambda x: str(x.get("tahun","")))

    ekuitas    = apply_unit(fin_section.get("total_ekuitas"), unit)
    liabilitas = apply_unit(fin_section.get("total_liabilitas"), unit)
    saham      = parse_num(fin_section.get("total_saham_beredar"))
    harga      = parse_num(fin_section.get("harga_penawaran"))
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

    kpi = {"pe":"N/A","pb":"N/A","roe":"N/A","der":"N/A","eps":"N/A","market_cap":"N/A",
           "roe_by_year":{},"der_by_year":{},"eps_by_year":{},"extra_by_year":{}}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    rasio_list = fin_section.get("rasio_per_tahun",[])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, key in [("roe","roe_by_year"),("der","der_by_year"),("eps","eps_by_year")]:
                v = parse_num(r.get(field))
                if v is not None: kpi[key][y] = v
            extra = {f: parse_num(r.get(f)) for f in ("car","npl","nim","bopo","roa") if parse_num(r.get(f)) is not None}
            if extra: kpi["extra_by_year"][y] = extra
        last_r = rasio_list[-1] if rasio_list else {}
        for field, kkey, fmt in [("roe","roe","{:.2f}%"),("der","der","{:.2f}x"),("eps","eps","Rp {:.2f}")]:
            v = parse_num(last_r.get(field))
            if v is not None: kpi[kkey] = fmt.format(v)

    try:
        if saham and laba_last and saham>0 and kpi["eps"]=="N/A":
            ev = laba_last/saham; kpi["eps"] = f"Rp {ev:,.2f}".replace(",",".")
            if harga_idr and ev>0:  kpi["pe"] = f"{harga_idr/ev:.1f}x"
            elif harga_idr and ev<0: kpi["pe"] = "N/A (Rugi)"
    except: pass
    try:
        if ekuitas and saham and saham>0 and harga_idr and ekuitas>0:
            bv = ekuitas/saham
            if bv>0: kpi["pb"] = f"{harga_idr/bv:.2f}x"
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
            kpi["market_cap"] = fmt_idr(saham*(harga_idr if harga_idr else harga))
    except: pass

    financial = {
        "currency":currency,"years":[str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun":rasio_list,"absolute_data":years_data,"is_banking":is_banking,
        "revenue_growth":rev_growth or None,"gross_margin":gross_m or None,
        "operating_margin":op_m or None,"ebitda_margin":ebitda_m or None,
        "net_profit_margin":net_m or None,
    }
    return financial, kpi

# ══════════════════════════════════════════
# 7. RISK SCORING
# ══════════════════════════════════════════
_HIGH_SIGNALS = [
    "pencabutan izin","going concern","gagal bayar","pailit",
    r"satu pelanggan.*\d{2,3}%",r"konsentrasi.*>\s*40%",
    "perubahan status pma","akuisisi.*tidak dapat dilaksanakan",
    "tidak dapat mempertahankan izin","license revocation",
    "material adverse","substantial doubt",
]
_LOW_SIGNALS = [
    "harga saham","likuiditas saham","volatilitas pasar modal",
    "share price","market liquidity","force majeure",
    "bencana alam","pandemi","kondisi ekonomi makro secara umum",
]

def score_risk(title: str, desc: str) -> str:
    text = (title + " " + (desc or "")).lower()
    for sig in _HIGH_SIGNALS:
        if re.search(sig, text): return "High"
    low_count = sum(1 for s in _LOW_SIGNALS if re.search(s, text))
    if low_count >= 1: return "Low"
    return "Medium"

# ══════════════════════════════════════════
# 8. TICKER SEARCH
# ══════════════════════════════════════════
def search_ticker(company_name: str) -> str:
    import requests
    EXCLUDE = {"PT","TBK","IDX","BEI","OJK","IDR","USD","IPO","ROE","DER","EPS"}
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
                if t not in EXCLUDE and 2<=len(t)<=6: return t
    except: pass
    return ""

# ══════════════════════════════════════════
# 9. MAIN — 1 LLM CALL TOTAL
# ══════════════════════════════════════════
def analyze_prospectus(text: str, lang: str="ID", model: str=None) -> dict:
    lang     = (lang or "ID").upper()
    is_pro   = (model == MODEL_PRO)
    banking  = is_bank(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)
    fx_rate  = detect_fx_rate(text)

    logger.info(f"[START] host={_HOST} lang={lang} is_pro={is_pro} len={len(text)} banking={banking} unit={unit}")

    # ── SATU LLM CALL ─────────────────────
    _model   = MODEL_PRO if is_pro else MODEL_FLASH
    max_tok  = 12000 if is_pro else 8000
    prompt   = _build_mega_prompt(text, lang, is_pro, banking, currency, unit)

    raw      = _call_llm_once(prompt, model=_model, max_tokens=max_tok)
    parsed   = _safe_json(raw)

    if not parsed:
        # Coba repair JSON terpotong
        fixed = re.sub(r",\s*([}\]])",r"\1",raw)
        s = fixed.find("{")
        if s != -1:
            snippet = fixed[s:]
            ob = max(0, snippet.count("{") - snippet.count("}"))
            ol = max(0, snippet.count("[") - snippet.count("]"))
            closed = snippet + ("]"*ol) + ("}"*ob)
            parsed = _safe_json(closed)
    if not parsed:
        raise ValueError(f"Gagal parse JSON dari LLM: {raw[:300]}")

    # ── EXTRACT FINANCIAL SECTION ──────────
    fin_section = parsed.pop("financial", {})
    fin_section.setdefault("satuan", unit)
    fin_section.setdefault("mata_uang", currency)

    # ── COMPUTE KPI (pure Python) ──────────
    financial, kpi = _compute_kpi(fin_section, fx_rate, banking, currency, unit)
    logger.info(f"[KPI] {json.dumps(kpi, ensure_ascii=False)}")

    # ── ATTACH ────────────────────────────
    parsed["financial"] = financial
    parsed["kpi"]       = kpi

    # ── RISK SCORING KOREKSI ──────────────
    high_count = medium_count = 0
    for r in parsed.get("risks",[]):
        llm_lvl   = str(r.get("level","Medium")).strip().capitalize()
        scored    = score_risk(r.get("title",""), r.get("desc",""))
        prio      = {"High":3,"Medium":2,"Low":1}
        final_lvl = scored if prio.get(scored,2) < prio.get(llm_lvl,2) else llm_lvl
        r["level"] = final_lvl
        if final_lvl == "High":    high_count += 1
        elif final_lvl == "Medium": medium_count += 1

    # Paksa overall_risk_level jadi 1 kata
    if high_count >= 2:   parsed["overall_risk_level"] = "High"
    elif high_count == 1 or medium_count >= 2: parsed["overall_risk_level"] = "Medium"
    else:                 parsed["overall_risk_level"] = "Low"

    # ── TICKER ────────────────────────────
    ticker = str(parsed.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$", ticker):
        company = parsed.get("company_name","")
        if company: ticker = search_ticker(company)
        parsed["ticker"] = ticker

    # ── VALIDASI UoF ──────────────────────
    uof = parsed.get("use_of_funds",[])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            for item in uof: item["allocation"] = round(float(item.get("allocation") or 0)/total*100,2)

    logger.info(f"[DONE] company={parsed.get('company_name','')} ticker={parsed.get('ticker','')} risks={len(parsed.get('risks',[]))}")
    return parsed