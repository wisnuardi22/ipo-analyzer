from openai import OpenAI
import json, re, os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)

def analyze_prospectus(text: str) -> dict:
    prompt = f"""Kamu adalah analis keuangan IPO Indonesia kelas dunia (CFA Level 3, 20 tahun pengalaman di Mandiri Sekuritas dan Morgan Stanley). Tugasmu adalah menghasilkan analisis IPO berkualitas institusional dari dokumen prospektus berikut.

PENTING: Setiap analisis HARUS UNIK dan SPESIFIK untuk perusahaan ini. Jangan gunakan data generik atau template. Baca dokumen dengan sangat teliti.

===================================================
BAGIAN 1: IDENTITAS PERUSAHAAN
===================================================
Ekstrak dengan teliti:
- company_name: Nama lengkap perusahaan termasuk "Tbk"
- ticker: Cari kode saham IDX perusahaan ini dari PENGETAHUANMU tentang pasar modal Indonesia.
  Kode saham IDX adalah 2-6 huruf kapital yang unik untuk setiap perusahaan.
  Jika kamu tahu kode sahamnya (contoh: EMAS, BBRI, TLKM, GOTO) → isi dengan benar.
  Jika tidak yakin sama sekali → isi ""
  JANGAN mengarang — hanya isi jika yakin benar.
  Contoh: PT Merdeka Gold Resources Tbk → "EMAS"
          PT Bank Central Asia Tbk → "BBCA"
          PT Telkom Indonesia Tbk → "TLKM"
- sector: Sektor SPESIFIK (contoh: "Pertambangan Emas & Mineral Ikutan", bukan hanya "Pertambangan")
- ipo_date: Tanggal pencatatan di BEI
- share_price: Harga penawaran final (jika ada range, ambil nilai TERTINGGI)
- total_shares: Total saham beredar SETELAH IPO (bukan sebelum)
- market_cap: Nilai kapitalisasi pasar (harga × total saham)

===================================================
BAGIAN 2: RINGKASAN PERUSAHAAN
===================================================
Tulis summary 3 paragraf dalam Bahasa Indonesia AWAM (tidak perlu jargon):

Paragraf 1 — Profil: Perusahaan ini apa, produk/jasa utama, berdiri kapan & di mana, skala bisnis
Paragraf 2 — Posisi Pasar: Pelanggan utama, pangsa pasar, keunggulan vs kompetitor, moat bisnis
Paragraf 3 — Tujuan IPO: Dana dipakai untuk apa, target ke depan, visi pertumbuhan

Pisahkan paragraf dengan \\n\\n. WAJIB spesifik dengan data angka dari prospektus.

===================================================
BAGIAN 3: DATA KEUANGAN — HARUS DARI TABEL DI PROSPEKTUS
===================================================
Cari tabel: "Ikhtisar Data Keuangan Penting", "Laporan Laba Rugi Konsolidasian", "Ringkasan Keuangan"

PENTING: Data keuangan ini WAJIB berbeda antar perusahaan. Baca dan hitung dari angka aktual di tabel.

Tahun yang tersedia: bisa 1, 2, 3, atau 4 tahun — gunakan SEMUA yang ada di dokumen.
Mata uang: IDR atau USD — tulis apa adanya di field "currency".

CARA HITUNG (gunakan angka dari tabel, HARUS berbeda tiap perusahaan):
PENTING: Jika hanya ada 1 tahun data → revenue_growth = 0 untuk tahun itu, isi null untuk D&A jika tidak ada.
PENTING: Jika data tidak ada sama sekali → isi null, JANGAN buat angka fiktif.
A) Revenue Growth (%) = ((Pendapatan_N - Pendapatan_N-1) / |Pendapatan_N-1|) × 100
   → Tahun pertama yang tersedia = 0 (tidak ada pembanding)
   → Contoh: Rev 2023=500M, Rev 2024=750M → Growth 2024 = ((750-500)/500)×100 = 50.0

B) Gross Margin (%) = (Laba Kotor / Pendapatan) × 100
   → Laba Kotor = Pendapatan - Beban Pokok Penjualan (HPP/COGS)
   → Jika langsung ada di tabel rasio, gunakan nilai tersebut

C) Operating Margin (%) = (Laba Usaha / Pendapatan) × 100
   → Laba Usaha = setelah dikurangi semua beban operasional
   → Boleh negatif jika perusahaan masih rugi operasional

D) EBITDA Margin (%) = ((Laba Usaha + D&A) / Pendapatan) × 100
   → Jika D&A tidak ada di ringkasan, cari di laporan arus kas atau catatan keuangan
   → Jika benar-benar tidak ada → null

E) Net Profit Margin (%) = (Laba Bersih / Pendapatan) × 100
   → Laba Bersih = laba setelah pajak (bukan laba kotor)

FORMAT: Semua nilai ANGKA DESIMAL tanpa simbol %, tanpa koma ribuan.
Contoh BENAR: 34.56 | Contoh SALAH: "34.56%" atau "34,56"

===================================================
BAGIAN 4: KPI SPESIFIK INDUSTRI
===================================================
Pilih 4-6 KPI yang PALING RELEVAN dengan industri perusahaan ini:

Pertambangan/Energi: P/E, EV/EBITDA, Cash Cost per unit, Reserve Life (tahun), DER
Perbankan/Keuangan: P/E, P/B, NIM, NPL ratio, CAR, ROA, ROE
Properti/Konstruksi: P/E, P/B, NAV discount, DER, Pre-sales coverage
Teknologi/Digital: P/E, P/S, Revenue Growth, Gross Margin, Burn Rate
Manufaktur: P/E, P/B, ROIC, Asset Turnover, Inventory Days
Retail/Consumer: P/E, EV/EBITDA, Same-store growth, Revenue per outlet
Infrastruktur: P/E, EV/EBITDA, IRR, Debt Coverage Ratio, Backlog

Hitung P/E = Harga IPO / EPS terbaru (jika EPS tersedia di prospektus)
Hitung P/B = Harga IPO / (Total Ekuitas / Total Saham)
Selalu sertakan: pe, pb, roe, der, eps, mktcap

===================================================
BAGIAN 5: PENGGUNAAN DANA IPO — WAJIB DITEMUKAN
===================================================
Cari di seluruh dokumen dengan kata kunci:
- "Rencana Penggunaan Dana"
- "Penggunaan Dana Hasil Penawaran Umum"  
- "Penggunaan Dana IPO"
- "Alokasi Dana"
- Tabel yang menyebutkan persentase penggunaan dana

WAJIB DIISI — jangan biarkan kosong []:
- Ekstrak SETIAP alokasi dana yang disebutkan dengan persentase atau nilai
- Jika tidak ada persentase, hitung sendiri dari nilai dana yang disebutkan
- Jumlah semua allocation HARUS = 100
- Minimal 2 item, maksimal 5 item

description HARUS SPESIFIK (bukan generik):
- BAIK: "Pembelian 3 kapal tanker 50.000 DWT senilai Rp 450 M untuk ekspansi armada"
- BURUK: "Pengembangan bisnis" atau "Modal kerja umum"

Jika sulit menemukan persentase tepat, estimasi berdasarkan konteks kalimat:
- "sebagian besar" → 60-70%
- "sebagian" → 30-40%
- "sisanya" → sisa dari 100%

===================================================
BAGIAN 6: PENJAMIN EMISI EFEK
===================================================
Cari bagian "Penjaminan Emisi Efek" atau "Penjamin Pelaksana Emisi Efek":
- lead: Nama penjamin pelaksana utama
- others: Array nama co-underwriter lainnya
- type: "Kesanggupan Penuh (Full Commitment)" atau "Kesanggupan Terbaik (Best Effort)"
- reputation: Analisis track record penjamin berdasarkan pengetahuan pasar modal Indonesia

Top tier penjamin: Mandiri Sekuritas, BCA Sekuritas, BRI Danareksa, Mirae Asset, CGS-CIMB, Trimegah, Bahana, Indo Premier, Samuel
Full Commitment = semua saham pasti terjual = POSITIF untuk investor

===================================================
BAGIAN 7: ANALISIS RISIKO
===================================================
Langkah A — Tentukan SATU level risiko keseluruhan berdasarkan analisis mendalam:
- "High": Ada risiko sistemik yang bisa mengancam kelangsungan bisnis
- "Medium": Risiko operasional yang bisa dikelola, bisnis tetap viable
- "Low": Risiko minimal, bisnis mature dan stabil

Isi "overall_risk_level" dan "overall_risk_reason" (2-3 kalimat alasan mengapa level ini).

Langkah B — List 3-5 faktor risiko SESUAI level yang dipilih:
- Setiap item: level (sama dengan overall), title (singkat), desc (penjelasan awam 1-2 kalimat)
- SPESIFIK dengan data dari prospektus, BUKAN risiko generik
- Hindari: "Risiko pasar", "Risiko regulasi" yang terlalu umum

===================================================
BAGIAN 8: KEUNGGULAN INVESTASI (BENEFIT)
===================================================
4-6 keunggulan NYATA dan SPESIFIK:
- Sertakan angka konkret dari prospektus
- Fokus pada mengapa investor harus tertarik
- Sertakan analisis penjamin efek jika bereputasi baik

===================================================
ATURAN OUTPUT JSON — WAJIB DIPATUHI
===================================================
1. Output HANYA JSON murni — tidak ada teks sebelum atau sesudah
2. Tidak ada markdown, tidak ada ```
3. Semua string pakai tanda kutip ganda "
4. Tidak ada trailing comma sebelum kurung tutup
5. Nilai null untuk data yang tidak tersedia (bukan string kosong "")

DOKUMEN PROSPEKTUS:
{text[:500000]}

OUTPUT JSON:
{{
  "company_name": "PT Merdeka Gold Resources Tbk",
  "ticker": "",
  "sector": "Pertambangan Emas, Perak & Mineral Ikutan",
  "ipo_date": "23 September 2025",
  "share_price": "Rp 2.880",
  "total_shares": "1.618.023.300 lembar",
  "market_cap": "Rp 4,66 T",
  "summary": "PT Merdeka Gold Resources Tbk (EMAS) adalah perusahaan holding pertambangan emas yang berdiri pada 2022 dan berkedudukan di Jakarta. Perseroan mengelola operasi tambang emas melalui anak usahanya PT Merdeka Mining Investama, dengan dua proyek utama: Tambang Emas Pani di Gorontalo (kapasitas 250.000 oz/tahun) dan Tambang Emas Toka Tindung di Sulawesi Utara (100.000 oz/tahun).\\n\\nPerseroan menjual produksi emasnya kepada pembeli institusional global termasuk Metalor Technologies dan Heraeus. Dengan cadangan emas terbukti (proven reserves) sebesar 4,2 juta oz dan biaya produksi all-in sustaining cost (AISC) USD 950/oz — jauh di bawah harga pasar USD 2.400/oz — perusahaan memiliki margin keuntungan yang sangat tebal dan cadangan yang cukup untuk operasi 15+ tahun.\\n\\nDana IPO senilai Rp 4,66 T akan digunakan untuk mempercepat pembangunan fasilitas pengolahan baru di Pani dan eksplorasi blok-blok prospektif di Sulawesi. Target produksi naik dari 180.000 oz (2024) menjadi 400.000 oz pada 2027, menjadikan perseroan produsen emas terbesar ketiga di Indonesia.",
  "financial": {{
    "currency": "USD",
    "years": ["2023", "2024"],
    "raw_revenue_million": [180.5, 245.3],
    "revenue_growth": [
      {{"year": "2023", "value": 0}},
      {{"year": "2024", "value": 35.9}}
    ],
    "gross_margin": [
      {{"year": "2023", "value": 48.2}},
      {{"year": "2024", "value": 52.7}}
    ],
    "operating_margin": [
      {{"year": "2023", "value": 28.4}},
      {{"year": "2024", "value": 33.1}}
    ],
    "ebitda_margin": [
      {{"year": "2023", "value": 41.5}},
      {{"year": "2024", "value": 46.8}}
    ],
    "net_profit_margin": [
      {{"year": "2023", "value": 18.9}},
      {{"year": "2024", "value": 23.4}}
    ]
  }},
  "kpi": {{
    "pe": "18.5x",
    "pb": "2.8x",
    "roe": "15.2%",
    "der": "0.38x",
    "eps": "Rp 156",
    "mktcap": "Rp 4,66 T",
    "ev_ebitda": "9.2x",
    "aisc_per_oz": "USD 950/oz",
    "reserve_life": "15 tahun"
  }},
  "use_of_funds": [
    {{"category": "Pembangunan Fasilitas Pengolahan Pani Phase 2", "description": "Konstruksi pabrik pengolahan emas kapasitas 4 juta ton bijih/tahun di lokasi Tambang Pani, Gorontalo, untuk meningkatkan kapasitas produksi dari 120.000 oz menjadi 250.000 oz per tahun", "allocation": 55}},
    {{"category": "Eksplorasi & Pengembangan Cadangan", "description": "Program pengeboran eksplorasi di 8 blok prospektif di Sulawesi dan Gorontalo untuk menambah cadangan terbukti yang saat ini 4,2 juta oz", "allocation": 30}},
    {{"category": "Modal Kerja & Biaya Operasional", "description": "Pembiayaan kebutuhan operasional tambang, pembelian bahan kimia pengolahan, gaji 2.400 karyawan, dan cadangan likuiditas perseroan", "allocation": 15}}
  ],
  "underwriter": {{
    "lead": "PT Mandiri Sekuritas",
    "others": ["PT BRI Danareksa Sekuritas", "PT Trimegah Sekuritas Indonesia Tbk"],
    "type": "Kesanggupan Penuh (Full Commitment)",
    "reputation": "Sangat baik — Mandiri Sekuritas adalah penjamin emisi terbesar Indonesia dengan portofolio 60+ IPO dalam 5 tahun terakhir termasuk BREN, AMMN, dan ADRO. Full commitment memastikan seluruh saham terjual meskipun pasar sedang volatile."
  }},
  "overall_risk_level": "Medium",
  "overall_risk_reason": "Meskipun perusahaan memiliki cadangan emas besar dan margin tinggi, ketergantungan total pada harga emas global yang volatile dan fase konstruksi fasilitas baru yang belum selesai menciptakan risiko sedang yang perlu diperhatikan investor.",
  "risks": [
    {{"level": "Medium", "title": "Ketergantungan pada Harga Emas Global", "desc": "Seluruh pendapatan perusahaan berasal dari penjualan emas. Jika harga emas turun dari USD 2.400 ke USD 1.800/oz, laba bersih bisa turun lebih dari 60% karena biaya produksi tetap."}},
    {{"level": "Medium", "title": "Risiko Konstruksi Fasilitas Pani Phase 2", "desc": "Pembangunan pabrik senilai USD 180 juta masih berlangsung dan dijadwalkan selesai 2026. Keterlambatan atau pembengkakan biaya konstruksi bisa menunda peningkatan produksi yang menjadi basis valuasi IPO."}},
    {{"level": "Medium", "title": "Ketergantungan pada Izin Lingkungan & ESDM", "desc": "Operasi tambang sangat bergantung pada perpanjangan izin dari Kementerian ESDM dan KLHK. Pengetatan regulasi lingkungan hidup pasca-insiden tambang di daerah lain berpotensi mempersulit proses perpanjangan izin."}}
  ],
  "benefits": [
    {{"title": "Cadangan Emas Terbukti 4,2 Juta Oz — Visibilitas 15 Tahun", "desc": "Dengan cadangan terbukti terbesar di antara emiten tambang emas yang IPO dalam 5 tahun terakhir, investor mendapat kepastian arus kas hingga 2040+."}},
    {{"title": "Margin Keuntungan Tertinggi di Industri: AISC USD 950/oz vs Harga USD 2.400/oz", "desc": "Spread keuntungan USD 1.450/oz memberikan buffer sangat tebal. Bahkan jika harga emas turun 30%, perusahaan masih sangat profitable."}},
    {{"title": "Pertumbuhan Produksi 120% dalam 3 Tahun", "desc": "Target produksi naik dari 180.000 oz (2024) ke 400.000 oz (2027), menjadikan ini salah satu growth story terkuat di sektor pertambangan Indonesia."}},
    {{"title": "Didukung Penjamin Emisi Tier-1: Mandiri Sekuritas + BRI Danareksa", "desc": "Full commitment dari dua penjamin terbesar Indonesia memastikan IPO pasti sukses. Track record keduanya: semua IPO yang ditangani berhasil mencapai harga penawaran."}},
    {{"title": "Harga Emas di Level Rekor — Momentum Investasi Terbaik", "desc": "Emas diperdagangkan di USD 2.400/oz, level tertinggi sepanjang sejarah. Investor yang masuk di IPO ini mendapat exposure ke komoditas yang sedang berada di puncak siklus bullish."}}
  ]
}}"""

    response = client.chat.completions.create(
        model="gemini/gemini-2.5-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=16000
    )

    raw = response.choices[0].message.content.strip()

    # Bersihkan markdown
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                raw = p
                break

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    # Fix 1: trailing comma
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    raw_fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(raw_fixed)
    except json.JSONDecodeError:
        pass

    # Fix 2: potong sampai valid
    for i in range(len(raw_fixed), 0, -1):
        try:
            return json.loads(raw_fixed[:i])
        except json.JSONDecodeError:
            continue

    raise ValueError(f"Tidak bisa parse JSON. Output (500 char): {raw[:500]}")