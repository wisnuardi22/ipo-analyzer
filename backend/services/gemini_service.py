from openai import OpenAI
import json, re, os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)

def analyze_prospectus(text: str) -> dict:

    # ── STEP 1: Ekstrak data keuangan mentah dulu ──────────────────────────
    fin_prompt = f"""Kamu adalah akuntan senior Indonesia. Tugasmu HANYA membaca laporan keuangan dari prospektus IPO berikut dan mengekstrak angka-angka mentah.

TUGAS:
1. Cari laporan laba rugi dengan judul seperti:
   - "LAPORAN LABA RUGI DAN PENGHASILAN KOMPREHENSIF LAIN KONSOLIDASIAN"
   - "LAPORAN LABA RUGI KOMPREHENSIF KONSOLIDASIAN"
   - "Ikhtisar Data Keuangan Penting"
   - "CONSOLIDATED STATEMENTS OF PROFIT OR LOSS"

2. Dari laporan tersebut, catat untuk SETIAP tahun yang ada:
   - Tahun (misal: 2022, 2023, 2024)
   - Total Pendapatan / Revenue
   - Laba Kotor / Gross Profit (atau hitung: Pendapatan - Beban Pokok)
   - Laba Usaha / Operating Profit (boleh negatif)
   - Laba Bersih / Net Profit (boleh negatif)
   - Depresiasi & Amortisasi jika ada

3. Cari juga dari Laporan Posisi Keuangan / Neraca:
   - Total Ekuitas
   - Total Liabilitas
   - Total Saham Beredar

4. Cek satuan angka (dalam jutaan Rupiah? ribuan? USD penuh?)

PERHATIAN: 
- Catat angka PERSIS seperti di dokumen
- Jangan hitung apapun dulu
- Jika tidak ditemukan sama sekali → tulis null

DOKUMEN (5000 karakter pertama):
{text[:5000]}

DOKUMEN (bagian tengah, kemungkinan ada laporan keuangan):
{text[5000:50000]}

Output JSON murni:
{{
  "satuan": "jutaan IDR atau ribuan USD atau full IDR - tulis persis",
  "mata_uang": "IDR atau USD",
  "tahun_tersedia": ["2022", "2023", "2024"],
  "data_per_tahun": [
    {{
      "tahun": "2023",
      "pendapatan": 75765791,
      "laba_kotor": 6378346,
      "laba_usaha": 8234,
      "laba_bersih": 234567,
      "depresiasi": null
    }},
    {{
      "tahun": "2024",
      "pendapatan": 102254765,
      "laba_kotor": 10465141,
      "laba_usaha": 214890,
      "laba_bersih": 456123,
      "depresiasi": null
    }}
  ],
  "total_ekuitas_terakhir": 1234567890,
  "total_liabilitas_terakhir": 987654321,
  "total_saham_beredar": 5000000000,
  "harga_penawaran_angka": 500
}}"""

    fin_raw = {}
    try:
        fin_resp = client.chat.completions.create(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": fin_prompt}],
            temperature=0.05,
            max_tokens=4000
        )
        fin_text = fin_resp.choices[0].message.content.strip()
        if "```" in fin_text:
            for part in fin_text.split("```"):
                p = part.strip().lstrip("json").strip()
                if p.startswith("{"):
                    fin_text = p
                    break
        s = fin_text.find("{")
        e = fin_text.rfind("}") + 1
        if s != -1 and e > s:
            fin_raw = json.loads(fin_text[s:e])
    except Exception as ex:
        fin_raw = {}

    # ── Hitung metrik dari data mentah ─────────────────────────────────────
    def safe_div(a, b):
        try:
            if a is None or b is None or b == 0:
                return None
            return round((float(a) / float(b)) * 100, 2)
        except:
            return None

    def calc_growth(cur, prev):
        try:
            if cur is None or prev is None or prev == 0:
                return None
            return round(((float(cur) - float(prev)) / abs(float(prev))) * 100, 2)
        except:
            return None

    # Bangun financial trends dari data mentah
    revenue_growth = []
    gross_margin   = []
    op_margin      = []
    ebitda_margin  = []
    net_margin     = []
    years_data     = fin_raw.get("data_per_tahun", [])
    currency       = fin_raw.get("mata_uang", "IDR")

    prev_rev = None
    for i, yr in enumerate(years_data):
        y    = str(yr.get("tahun", ""))
        rev  = yr.get("pendapatan")
        gp   = yr.get("laba_kotor")
        op   = yr.get("laba_usaha")
        net  = yr.get("laba_bersih")
        dep  = yr.get("depresiasi")

        # Revenue growth
        if i == 0 or prev_rev is None:
            revenue_growth.append({"year": y, "value": 0})
        else:
            g = calc_growth(rev, prev_rev)
            revenue_growth.append({"year": y, "value": g})
        prev_rev = rev

        gross_margin.append({"year": y, "value": safe_div(gp, rev)})
        op_margin.append({"year": y, "value": safe_div(op, rev)})

        if dep is not None and op is not None:
            try:
                ebitda = float(op) + float(dep)
                ebitda_margin.append({"year": y, "value": safe_div(ebitda, rev)})
            except:
                ebitda_margin.append({"year": y, "value": None})
        else:
            ebitda_margin.append({"year": y, "value": None})

        net_margin.append({"year": y, "value": safe_div(net, rev)})

    # Hitung KPI
    kpi = {"pe": "N/A", "pb": "N/A", "roe": "N/A", "der": "N/A", "eps": "N/A"}
    try:
        ekuitas   = fin_raw.get("total_ekuitas_terakhir")
        liabilitas = fin_raw.get("total_liabilitas_terakhir")
        saham     = fin_raw.get("total_saham_beredar")
        harga     = fin_raw.get("harga_penawaran_angka")
        laba_bersih = years_data[-1].get("laba_bersih") if years_data else None

        if saham and laba_bersih and saham > 0:
            eps_val = float(laba_bersih) / float(saham)
            if currency == "IDR":
                kpi["eps"] = f"Rp {eps_val:,.0f}".replace(",", ".")
            else:
                kpi["eps"] = f"USD {eps_val:.4f}"

            if harga and eps_val != 0:
                pe = float(harga) / eps_val
                kpi["pe"] = f"{pe:.1f}x" if pe > 0 else "N/A (Rugi)"

        if ekuitas and saham and saham > 0 and harga:
            bvps = float(ekuitas) / float(saham)
            if bvps > 0:
                kpi["pb"] = f"{float(harga)/bvps:.2f}x"

        if ekuitas and laba_bersih and ekuitas > 0:
            roe = (float(laba_bersih) / float(ekuitas)) * 100
            kpi["roe"] = f"{roe:.1f}%"

        if ekuitas and liabilitas and ekuitas > 0:
            der = float(liabilitas) / float(ekuitas)
            kpi["der"] = f"{der:.2f}x"
    except Exception as ex:
        pass

    # ── STEP 2: Analisis utama ─────────────────────────────────────────────
    main_prompt = f"""Kamu adalah analis IPO Indonesia senior. Analisis prospektus berikut dan hasilkan JSON analisis lengkap.

DATA KEUANGAN SUDAH DIHITUNG (gunakan ini, jangan hitung ulang):
KPI: {json.dumps(kpi)}
Financial trends sudah diproses terpisah.

TUGAS UTAMA — analisis bagian NON-KEUANGAN dari prospektus:

1. IDENTITAS: company_name, ticker (dari pengetahuanmu tentang IDX), sector, ipo_date, share_price, total_shares, market_cap

2. SUMMARY: 3 paragraf Bahasa Indonesia awam, spesifik dengan angka dari prospektus

3. PENGGUNAAN DANA IPO:
Cari dengan kata kunci: "Rencana Penggunaan Dana" / "Penggunaan Dana Hasil Penawaran Umum" / "Alokasi Dana"
- Ekstrak SETIAP item alokasi dengan persentase
- Jumlah = 100
- Deskripsi SPESIFIK (bukan generik)
- WAJIB diisi, minimal 2 item

4. PENJAMIN EMISI: lead, others (array), type, reputation

5. RISIKO: overall_risk_level (High/Medium/Low), overall_risk_reason, risks (3-5 item sesuai level)

6. BENEFIT: 4-6 keunggulan spesifik dengan angka

ATURAN OUTPUT: JSON murni, tidak ada markdown, tidak ada teks lain

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
  "risks": [
    {{"level": "Medium", "title": "...", "desc": "..."}}
  ],
  "benefits": [
    {{"title": "...", "desc": "..."}}
  ]
}}"""

    main_resp = client.chat.completions.create(
        model="gemini/gemini-2.5-flash",
        messages=[{"role": "user", "content": main_prompt}],
        temperature=0.1,
        max_tokens=12000
    )

    raw = main_resp.choices[0].message.content.strip()
    if "```" in raw:
        for part in raw.split("```"):
            p = part.strip().lstrip("json").strip()
            if p.startswith("{"):
                raw = p
                break

    s = raw.find("{")
    e = raw.rfind("}") + 1
    if s != -1 and e > s:
        raw = raw[s:e]

    try:
        result = json.loads(raw)
    except:
        raw_fixed = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            result = json.loads(raw_fixed)
        except:
            for i in range(len(raw_fixed), 0, -100):
                try:
                    result = json.loads(raw_fixed[:i])
                    break
                except:
                    continue
            else:
                raise ValueError(f"Tidak bisa parse JSON: {raw[:300]}")

    # ── Gabungkan financial ke result ──────────────────────────────────────
    result["financial"] = {
        "currency": currency,
        "years": [d.get("tahun","") for d in years_data],
        "revenue_growth":     revenue_growth  if revenue_growth  else None,
        "gross_margin":       gross_margin    if gross_margin    else None,
        "operating_margin":   op_margin       if op_margin       else None,
        "ebitda_margin":      ebitda_margin   if ebitda_margin   else None,
        "net_profit_margin":  net_margin      if net_margin      else None,
    }
    result["kpi"] = kpi

    return result