"""
gemini_service.py - IPO Analyzer
SEMUA pakai Gemini Flash (hemat). Basic vs Pro dibedakan dari OUTPUT saja, bukan model.
"""
from __future__ import annotations
import json, logging, math, os, re, socket
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
logger = logging.getLogger(__name__)

client = OpenAI(api_key=os.environ.get("SUMOPOD_API_KEY"), base_url="https://ai.sumopod.com/v1")

# FORCE FLASH - semua analisis pakai Flash, hemat token
MODEL_FLASH = "gemini/gemini-2.5-flash"
MODEL_PRO   = MODEL_FLASH   # Override: Pro juga pakai Flash, beda di output saja
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
# 3. FINANCIAL EXTRACTION - HEMAT: 1 CALL SAJA
# ══════════════════════════════════════════
_FIN_SYSTEM = """Kamu adalah akuntan senior. Ekstrak data keuangan dari prospektus IPO Indonesia.
Output HANYA JSON murni, tanpa teks lain.

INSTRUKSI - Baca dokumen dengan cermat:

A. LAPORAN LABA RUGI (cari tabel: "IKHTISAR DATA KEUANGAN", "LAPORAN LABA RUGI", "SELECTED FINANCIAL")
   Untuk SETIAP tahun di header kolom, ekstrak:
   - pendapatan: Total Pendapatan/Net Revenue/Penjualan Bersih/Pendapatan Bunga Bersih
   - laba_kotor: Laba Kotor/Gross Profit (null untuk bank)
   - laba_usaha: Laba/Rugi Usaha/Operating Profit (boleh negatif)
   - laba_bersih: Laba/Rugi Bersih/Net Profit (boleh negatif)
   - depresiasi: Depresiasi & Amortisasi

B. RASIO KEUANGAN PENTING (cari tabel: "RASIO KEUANGAN", "KEY FINANCIAL RATIOS")
   SALIN PERSIS angka yang tertulis, per tahun:
   - roe: ROE/Imbal Hasil Ekuitas (%)
   - roa: ROA/Return on Asset (%)
   - der: DER/Debt to Equity (x) — null untuk bank
   - npm: Net Profit Margin (%)
   - eps: EPS/Laba per Saham (Rp)
   - car: Capital Adequacy Ratio (%) — khusus bank
   - npl: Non Performing Loan (%) — khusus bank
   - nim: Net Interest Margin (%) — khusus bank
   - bopo: BOPO/Cost to Income (%) — khusus bank
   PENTING: Salin angka PERSIS dari tabel, JANGAN hitung sendiri!

C. NERACA (tahun TERAKHIR):
   total_ekuitas, total_liabilitas, total_aset

D. INFO IPO:
   total_saham_beredar (setelah IPO), harga_penawaran (angka saja, null jika DRHP)

E. SATUAN: "jutaan"/"ribuan"/"miliar"/"full" — baca dari header tabel
   Angka negatif dalam kurung: (1.234) → tulis -1234

OUTPUT:
{"satuan":"jutaan","mata_uang":"IDR","tahun_tersedia":["2022","2023","2024"],
"data_per_tahun":[{"tahun":"2022","pendapatan":null,"laba_kotor":null,"laba_usaha":null,"laba_bersih":null,"depresiasi":null}],
"rasio_per_tahun":[{"tahun":"2022","roe":null,"roa":null,"der":null,"npm":null,"eps":null,"car":null,"npl":null,"nim":null,"bopo":null}],
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
    for attempt in [snippet, re.sub(r",\s*([}\]])",r"\1",snippet)]:
        try: return json.loads(attempt)
        except: pass
    return None

def llm_extract_financials(text: str) -> Dict:
    """HEMAT: 1 call LLM saja dengan chunk terbaik."""
    # Ambil bagian tengah dokumen (biasanya ada tabel keuangan) + akhir
    n = len(text)
    # Tabel keuangan biasanya di 30%-80% dokumen
    start = max(0, int(n * 0.25))
    end   = min(n, int(n * 0.85))
    core  = text[start:end]

    # Ambil max 80K karakter dari area tabel keuangan
    if len(core) > 80000:
        # Cari posisi kata kunci keuangan
        keywords = ["ikhtisar data keuangan","laporan laba rugi","rasio keuangan","selected financial","data keuangan penting"]
        best_pos = 0
        for kw in keywords:
            pos = core.lower().find(kw)
            if pos > 0:
                best_pos = max(best_pos, pos)
                break
        chunk = core[max(0, best_pos-2000):best_pos+78000] if best_pos > 0 else core[:80000]
    else:
        chunk = core

    try:
        resp = client.chat.completions.create(
            model=MODEL_FLASH, temperature=0.0, max_tokens=4000,
            messages=[
                {"role":"system","content":_FIN_SYSTEM},
                {"role":"user","content":f"DOKUMEN PROSPEKTUS:\n\n{chunk}"},
            ],
        )
        result = _safe_json(resp.choices[0].message.content) or {}
        logger.info(f"[FIN] host={_HOST} tahun={result.get('tahun_tersedia')} rasio={len(result.get('rasio_per_tahun',[]))}")
        return result
    except Exception as e:
        logger.error(f"FIN error: {e}")
        return {}

# ══════════════════════════════════════════
# 4. NORMALIZE + KPI
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

    kpi = {"pe":"N/A","pb":"N/A","roe":"N/A","der":"N/A","eps":"N/A","market_cap":"N/A",
           "roe_by_year":{},"der_by_year":{},"eps_by_year":{},"extra_by_year":{}}
    laba_last = years_data[-1].get("laba_bersih") if years_data else None

    rasio_list = fin_raw.get("rasio_per_tahun",[])
    has_rasio  = bool(rasio_list)
    if has_rasio:
        for r in rasio_list:
            y = str(r.get("tahun","")).strip()
            if not y: continue
            for field, key in [("roe","roe_by_year"),("der","der_by_year"),("eps","eps_by_year")]:
                v = parse_num(r.get(field))
                if v is not None: kpi[key][y] = v
            extra = {}
            for field in ("car","npl","nim","bopo","roa"):
                v = parse_num(r.get(field))
                if v is not None: extra[field] = v
            if extra: kpi["extra_by_year"][y] = extra
        last_r = rasio_list[-1] if rasio_list else {}
        for field, kkey, fmt in [("roe","roe","{:.2f}%"),("der","der","{:.2f}x"),("eps","eps","Rp {:.2f}")]:
            v = parse_num(last_r.get(field))
            if v is not None: kpi[kkey] = fmt.format(v)

    # Fallback dari laporan keuangan jika tidak ada rasio
    try:
        if saham and laba_last and saham>0 and kpi["eps"]=="N/A":
            ev = laba_last/saham
            kpi["eps"] = f"Rp {ev:,.2f}".replace(",",".")
            if harga_idr and ev>0: kpi["pe"] = f"{harga_idr/ev:.1f}x"
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

    return {
        "currency":currency,"years":[str(d.get("tahun","")) for d in years_data],
        "rasio_per_tahun":rasio_list,"absolute_data":years_data,"is_banking":is_banking,
        "revenue_growth":rev_growth or None,"gross_margin":gross_m or None,
        "operating_margin":op_m or None,"ebitda_margin":ebitda_m or None,
        "net_profit_margin":net_m or None,
    }, kpi

# ══════════════════════════════════════════
# 5. RISK SCORING
# ══════════════════════════════════════════
# High: risiko yang benar-benar mengancam kelangsungan bisnis
_HIGH_SIGNALS = [
    "pencabutan izin","going concern","gagal bayar","pailit",
    r"satu pelanggan.*\d{2,3}%",r"konsentrasi.*>.*40%","perubahan status pma",
    "akuisisi.*tidak dapat dilaksanakan","tidak dapat mempertahankan izin",
    "license revocation","material adverse","substantial doubt",
]
# Low: risiko pasar umum yang ada di semua bisnis
_LOW_SIGNALS = [
    "harga saham","likuiditas saham","volatilitas pasar modal",
    "share price","market liquidity","nilai tukar.*tidak material",
    "force majeure","bencana alam","pandemi","kondisi ekonomi makro secara umum",
]

def score_risk(title: str, desc: str) -> str:
    text = (title + " " + (desc or "")).lower()
    for sig in _HIGH_SIGNALS:
        if re.search(sig, text): return "High"
    low_count = sum(1 for s in _LOW_SIGNALS if re.search(s, text))
    if low_count >= 1: return "Low"
    return "Medium"

# ══════════════════════════════════════════
# 6. QUALITATIVE - 1 CALL, HEMAT
# ══════════════════════════════════════════
def llm_qualitative(text: str, kpi: Dict, financial: Dict, lang: str="ID", is_pro: bool=False) -> Dict:
    is_en    = lang.upper() == "EN"
    currency = financial.get("currency","IDR")
    years    = financial.get("years",[])
    rasio    = financial.get("rasio_per_tahun",[])
    banking  = financial.get("is_banking", False)

    lang_note   = "Output ALL text fields in ENGLISH." if is_en else "Output SEMUA teks dalam BAHASA INDONESIA."
    banking_note = "\nINI ADALAH BANK: gunakan NIM/CAR/NPL/BOPO. Gross margin tidak relevan." if banking else ""
    doc_limit   = 150000 if is_pro else 100000
    max_tok     = 8000   if is_pro else 5000

    prompt = f"""Kamu adalah analis IPO senior Indonesia yang berpengalaman.
{lang_note}{banking_note}

DATA KPI (SALIN PERSIS ke output, jangan ubah): {json.dumps(kpi, ensure_ascii=False)}
Tahun keuangan: {years}
Rasio keuangan dari tabel: {json.dumps(rasio[-3:] if rasio else [], ensure_ascii=False)}

TUGAS ANALISIS - baca dokumen dengan sangat cermat:

A. IDENTITAS: company_name (lengkap+Tbk), ticker (cari "Kode Saham:"), sector, ipo_date, share_price (exact), total_shares, market_cap (salin dari KPI)

B. SUMMARY: 1 paragraf singkat {'English' if is_en else 'Indonesia'} — profil perusahaan + info IPO utama (max 4 kalimat)

C. USE OF PROCEEDS — WAJIB AKURAT:
   Cari bagian "Rencana Penggunaan Dana"/"Use of Proceeds" di dokumen.
   Baca SETIAP item dengan TELITI. Ekstrak:
   - category: nama PERSIS dari dokumen
   - description: deskripsi detail DENGAN nilai nominal (Rp X miliar/%) dari dokumen
   - allocation: persentase PERSIS (total = 100)
   JANGAN generik. Setiap prospektus punya rencana penggunaan yang unik.

D. UNDERWRITER: lead (nama lengkap), others (array), type ("Full Commitment"/"Best Efforts"), reputation (1-2 kalimat)

E. RISK FACTORS — WAJIB BERVARIASI (High/Medium/Low):
   Cari bab "Faktor Risiko". Ekstrak {"5-6" if is_pro else "4-5"} risiko.
   
   ATURAN LEVEL (WAJIB IKUTI):
   - "High" HANYA untuk: pencabutan izin usaha, going concern doubt, ketergantungan 1 pelanggan >50% revenue, gagal bayar material, akuisisi kritis yang bisa gagal
   - "Medium": risiko operasional, teknologi, SDM, persaingan, kredit, regulasi yang membutuhkan adaptasi
   - "Low": volatilitas harga saham, risiko nilai tukar minor, risiko pasar umum, force majeure
   
   PENTING: TIDAK SEMUA RISIKO ADALAH HIGH. Distribusi wajar: 1-2 High, 2-3 Medium, 1 Low.
   Setiap prospektus berbeda — analisis sesuai kondisi SPESIFIK perusahaan ini.
   
   overall_risk_level: "High" hanya jika 2+ risiko genuinely High. Sinon "Medium".
   overall_risk_reason: 2 kalimat dengan fakta spesifik dari prospektus ini.

F. BENEFITS: {"5-6" if is_pro else "3-4"} keunggulan spesifik dari dokumen dengan data konkret.

DOKUMEN:
{text[:doc_limit]}

OUTPUT JSON (WAJIB semua field terisi):
{{"company_name":"","ticker":"","sector":"","ipo_date":"","share_price":"","total_shares":"","market_cap":"",
"summary":"",
"use_of_funds":[{{"category":"","description":"detail dengan nilai nominal","allocation":70}},{{"category":"","description":"","allocation":30}}],
"underwriter":{{"lead":"","others":[],"type":"Full Commitment","reputation":""}},
"overall_risk_level":"Medium","overall_risk_reason":"",
"risks":[
  {{"level":"High","title":"","desc":""}},
  {{"level":"Medium","title":"","desc":""}},
  {{"level":"Medium","title":"","desc":""}},
  {{"level":"Low","title":"","desc":""}}
],
"benefits":[{{"title":"","desc":""}}]}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL_FLASH, temperature=0.1, max_tokens=max_tok,
            messages=[{"role":"user","content":prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        result = _safe_json(raw)
        if result:
            # Koreksi risk level dengan scoring logic kita
            for r in result.get("risks",[]):
                llm_lvl  = r.get("level","Medium")
                scored   = score_risk(r.get("title",""), r.get("desc",""))
                prio     = {"High":3,"Medium":2,"Low":1}
                # Ambil yang lebih rendah — hindari inflate ke High
                r["level"] = scored if prio.get(scored,2) < prio.get(llm_lvl,2) else llm_lvl
            return result

        # Repair JSON terpotong
        fixed = re.sub(r",\s*([}\]])",r"\1",raw)
        s = fixed.find("{")
        if s != -1:
            snippet = fixed[s:]
            ob = snippet.count("{") - snippet.count("}")
            ol = snippet.count("[") - snippet.count("]")
            closed = snippet + ("]"*max(0,ol)) + ("}"*max(0,ob))
            result = _safe_json(closed)
            if result: return result
        raise ValueError(f"JSON parse failed: {raw[:200]}")
    except Exception as e:
        logger.error(f"LLM qualitative error: {e}")
        raise ValueError(f"Gagal analisis: {e}")

# ══════════════════════════════════════════
# 7. TICKER SEARCH
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
                if t not in EXCLUDE and 2<=len(t)<=6:
                    return t
    except: pass
    return ""

# ══════════════════════════════════════════
# 8. MAIN
# ══════════════════════════════════════════
def analyze_prospectus(text: str, lang: str="ID", model: str=None) -> dict:
    """
    model parameter diabaikan — selalu pakai Flash untuk efisiensi.
    Perbedaan Basic vs Pro hanya di output (jumlah detail).
    """
    lang    = (lang or "ID").upper()
    is_pro  = (model == "gemini/gemini-2.5-pro")  # flag untuk output detail
    banking = is_bank(text)
    logger.info(f"[START] host={_HOST} lang={lang} is_pro={is_pro} len={len(text)} banking={banking}")

    fx_rate  = detect_fx_rate(text)
    currency = detect_currency(text)
    unit     = detect_unit(text)

    # 1 call financial extraction
    fin_raw = llm_extract_financials(text)
    if not fin_raw.get("satuan"):    fin_raw["satuan"]    = unit
    if not fin_raw.get("mata_uang"): fin_raw["mata_uang"] = currency

    financial, kpi = normalize_and_compute(fin_raw, fx_rate, is_banking=banking)
    logger.info(f"[KPI] {json.dumps(kpi, ensure_ascii=False)}")

    # 1 call qualitative
    result = llm_qualitative(text, kpi, financial, lang=lang, is_pro=is_pro)
    result["financial"] = financial
    result["kpi"]       = kpi

    # Ticker
    ticker = str(result.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z]{2,6}$",ticker):
        company = result.get("company_name","")
        if company: ticker = search_ticker(company)
        result["ticker"] = ticker

    # Validasi UoF
    uof = result.get("use_of_funds",[])
    if uof:
        total = sum(float(x.get("allocation") or 0) for x in uof)
        if 0 < total < 95 or total > 105:
            for item in uof:
                item["allocation"] = round(float(item.get("allocation") or 0)/total*100,2)

    logger.info(f"[DONE] company={result.get('company_name','')} ticker={result.get('ticker','')} risks={len(result.get('risks',[]))}")
    return result