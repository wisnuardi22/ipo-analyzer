from openai import OpenAI
import json, re, os, math
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)

MODEL = "gemini/gemini-2.5-flash"

def parse_number(raw: Optional[str]) -> Optional[float]:
    """Parse angka Indonesia/Inggris; dukung (xxx) = negatif."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    s2 = re.sub(r'[^0-9\-,\.]', '', s)
    if '.' in s2 and ',' in s2:
        s2 = s2.replace('.', '').replace(',', '.')
    elif ',' in s2 and '.' not in s2:
        s2 = s2.replace(',', '')
    try:
        val = float(s2)
        return -val if neg else val
    except Exception:
        return None

def safe_div(a, b) -> Optional[float]:
    try:
        if a is None or b is None or float(b) == 0:
            return None
        return float(a) / float(b)
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
        if cur is None or prev is None or float(prev) == 0:
            return None
        return round(((float(cur) - float(prev)) / abs(float(prev))) * 100, 2)
    except:
        return None

def apply_unit(val, unit: str) -> Optional[float]:
    if val is None:
        return None
    try:
        v = float(val)
        if unit == "jutaan":
            return v * 1_000_000
        if unit == "ribuan":
            return v * 1_000
        return v
    except:
        return None

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

def llm_extract_financials(text: str) -> Dict[str, Any]:
    """
    Kirim potongan teks ke Gemini, minta ekstrak angka mentah keuangan.
    Multi-chunk: gabungkan hasil tiap chunk.
    """
    sys_prompt = """Kamu adalah akuntan Indonesia. Ekstrak angka mentah dari potongan prospektus IPO.
Output HANYA JSON murni tanpa teks lain:
{
  "satuan": "full|jutaan|ribuan",
  "mata_uang": "IDR|USD",
  "tahun_tersedia": ["2022","2023","2024"],
  "data_per_tahun": [
    {"tahun":"2023","pendapatan":75765791,"laba_kotor":6378346,"laba_usaha":8234,"laba_bersih":234567,"depresiasi":null}
  ],
  "total_ekuitas_terakhir": 1234567890,
  "total_liabilitas_terakhir": 987654321,
  "total_saham_beredar": 5000000000,
  "harga_penawaran_angka": 500
}
PENTING:
- Catat angka PERSIS seperti di dokumen (jika satuan jutaan, tulis nilai jutaannya)
- Cari di: "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN KONSOLIDASIAN", "Ikhtisar Data Keuangan Penting"
- Jika tidak ada di potongan ini → isi null/[]"""

    merged = {
        "satuan": None, "mata_uang": None,
        "tahun_tersedia": [], "data_per_tahun": [],
        "total_ekuitas_terakhir": None, "total_liabilitas_terakhir": None,
        "total_saham_beredar": None, "harga_penawaran_angka": None
    }

    chunks = chunk_text(text, max_len=15000, overlap=500)
    priority_chunks = []
    keywords = ["laporan laba rugi", "ikhtisar data keuangan", "pendapatan bersih", "laba kotor", "gross profit"]
    for c in chunks:
        cl = c.lower()
        if any(k in cl for k in keywords):
            priority_chunks.append(c)
    if chunks and chunks[0] not in priority_chunks:
        priority_chunks.insert(0, chunks[0])
    if len(chunks) > 1 and chunks[-1] not in priority_chunks:
        priority_chunks.append(chunks[-1])
    selected_chunks = priority_chunks[:5]

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
                temperature=0.05,
                max_tokens=3000,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"DOKUMEN:\n{chunk}"}
                ]
            )
            part = safe_json(resp.choices[0].message.content) or {}
        except Exception as e:
            part = {}

        if not merged["satuan"] and part.get("satuan"):
            merged["satuan"] = part["satuan"]
        if not merged["mata_uang"] and part.get("mata_uang"):
            merged["mata_uang"] = part["mata_uang"]
        if part.get("tahun_tersedia"):
            merged["tahun_tersedia"] = sorted(set(merged["tahun_tersedia"]) | set(part["tahun_tersedia"]))
        if part.get("data_per_tahun"):
            m_dict = {d["tahun"]: d for d in merged["data_per_tahun"] if d.get("tahun")}
            for d in part["data_per_tahun"]:
                y = str(d.get("tahun","")).strip()
                if not y:
                    continue
                if y in m_dict:
                    # Merge field: prefer non-null
                    for k in ["pendapatan","laba_kotor","laba_usaha","laba_bersih","depresiasi"]:
                        if m_dict[y].get(k) is None and d.get(k) is not None:
                            m_dict[y][k] = d[k]
                else:
                    m_dict[y] = d
            merged["data_per_tahun"] = [m_dict[k] for k in sorted(m_dict.keys())]
        for k in ["total_ekuitas_terakhir","total_liabilitas_terakhir","total_saham_beredar","harga_penawaran_angka"]:
            if merged.get(k) is None and part.get(k) is not None:
                merged[k] = part[k]

    return merged

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
    saham      = fin_raw.get("total_saham_beredar")
    harga      = fin_raw.get("harga_penawaran_angka")

    revenue_growth, gross_margin, op_margin, ebitda_margin, net_margin = [], [], [], [], []
    prev_rev = None
    for i, yr in enumerate(years_data):
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
        if saham and laba_bersih and float(saham) > 0:
            eps_val = float(laba_bersih) / float(saham)
            kpi["eps"] = f"Rp {eps_val:,.0f}".replace(",",".") if currency=="IDR" else f"USD {eps_val:.6f}"
            if harga and eps_val != 0:
                if currency == "USD" and fx_rate and fx_rate > 0:
                    price_ccy = float(harga) / fx_rate
                else:
                    price_ccy = float(harga)
                pe = price_ccy / eps_val
                kpi["pe"] = f"{pe:.1f}x" if pe > 0 else "N/A (Rugi)"
    except:
        pass

    try:
        if ekuitas and saham and float(saham) > 0 and harga:
            bvps = float(ekuitas) / float(saham)
            if bvps > 0:
                price_ccy = float(harga)/(fx_rate or 1) if currency=="USD" else float(harga)
                kpi["pb"] = f"{price_ccy/bvps:.2f}x"
    except:
        pass

    try:
        if ekuitas and laba_bersih and float(ekuitas) > 0:
            kpi["roe"] = f"{(float(laba_bersih)/float(ekuitas))*100:.1f}%"
    except:
        pass

    try:
        if ekuitas and liabilitas and float(ekuitas) > 0:
            kpi["der"] = f"{float(liabilitas)/float(ekuitas):.2f}x"
    except:
        pass

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

def llm_qualitative(text: str, kpi: Dict, financial: Dict) -> Dict:
    """Analisis non-keuangan: summary, use of funds, risiko, penjamin, benefit."""
    prompt = f"""Kamu adalah analis IPO Indonesia senior (CFA Level 3). Analisis prospektus berikut.

DATA KEUANGAN SUDAH DIHITUNG (gunakan ini sebagai referensi, jangan hitung ulang):
KPI: {json.dumps(kpi, ensure_ascii=False)}
Tahun data: {financial.get('years', [])}

TUGAS — Hasilkan JSON analisis lengkap:

1. IDENTITAS:
   - company_name: nama lengkap + Tbk
   - ticker: kode saham IDX dari pengetahuanmu (2-6 huruf kapital), kosong "" jika tidak tahu
   - sector: spesifik (misal "Pertambangan Emas & Mineral Ikutan")
   - ipo_date: tanggal pencatatan BEI
   - share_price: harga penawaran final dengan "Rp" (jika range, nilai tertinggi)
   - total_shares: total saham beredar setelah IPO
   - market_cap: nilai pasar (harga × saham)

2. SUMMARY: 3 paragraf Bahasa Indonesia awam, spesifik dengan angka dari prospektus.
   Pisahkan dengan \\n\\n.

3. PENGGUNAAN DANA IPO:
   Cari: "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum" / "Alokasi Dana"
   - WAJIB diisi minimal 2 item (jangan kosong [])
   - allocation: persentase, total = 100
   - description: SPESIFIK (nama anak usaha, nilai, tujuan konkret)

4. PENJAMIN EMISI:
   - lead, others (array), type, reputation (analisis track record)

5. RISIKO:
   - overall_risk_level: "High"/"Medium"/"Low"
   - overall_risk_reason: 2-3 kalimat
   - risks: 3-5 item sesuai level, title + desc spesifik

6. BENEFIT: 4-6 keunggulan spesifik dengan angka konkret

ATURAN: Output JSON murni, tidak ada teks lain, tidak ada markdown.

DOKUMEN:
{text[:400000]}

OUTPUT JSON:
{{
  "company_name": "...",
  "ticker": "",
  "sector": "...",
  "ipo_date": "...",
  "share_price": "...",
  "total_shares": "...",
  "market_cap": "...",
  "summary": "...",
  "use_of_funds": [
    {{"category": "...", "description": "...", "allocation": 60}},
    {{"category": "...", "description": "...", "allocation": 40}}
  ],
  "underwriter": {{
    "lead": "...",
    "others": [],
    "type": "...",
    "reputation": "..."
  }},
  "overall_risk_level": "Medium",
  "overall_risk_reason": "...",
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

def analyze_prospectus(text: str) -> dict:
    fx_rate = detect_fx_rate(text)
    fin_raw = llm_extract_financials(text)
    financial, kpi = normalize_and_compute(fin_raw, fx_rate)
    result = llm_qualitative(text, kpi, financial)
    result["financial"] = financial
    result["kpi"]       = kpi
    return result