from groq import Groq
import json, os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

def analyze_prospectus(text: str) -> dict:
    prompt = f"""Kamu adalah analis keuangan IPO Indonesia senior (CFA level 3). Baca dokumen berikut — bisa berupa PROSPEKTUS RINGKAS atau PROSPEKTUS LENGKAP — dengan sangat teliti.

============================
LANGKAH 1 — IDENTIFIKASI DOKUMEN
============================
Tentukan dulu:
- Apakah ini prospektus ringkas atau lengkap?
- Berapa tahun data keuangan yang tersedia? (bisa 2, 3, atau 4 tahun)
- Mata uang laporan: IDR (Rupiah) atau USD?
- PERINGATAN: Jika hanya ada 2 tahun (perusahaan baru berdiri), gunakan 2 tahun saja. JANGAN mengarang tahun yang tidak ada.

============================
LANGKAH 2 — EKSTRAK DATA IDENTITAS
============================
- Nama perusahaan lengkap (termasuk Tbk)
- Kode ticker saham: 4 huruf kapital. Biasanya tertulis di judul halaman, di tabel struktur modal, atau di bagian pencatatan BEI. Contoh: CDIA, BBRI, TLKM
- Sektor industri utama
- Tanggal Pencatatan di BEI (bukan tanggal efektif, bukan tanggal penawaran awal)
- Harga penawaran: jika ada range (misal Rp170–Rp190), ambil NILAI TERTINGGI
- Total saham beredar SETELAH IPO (bukan sebelum IPO)
- Total nilai IPO / market cap

============================
LANGKAH 3 — HITUNG INDIKATOR KEUANGAN
============================
Cari di: "Ikhtisar Data Keuangan Penting", "Laporan Laba Rugi", "Rasio-Rasio Keuangan"

ATURAN KETAT:
✓ Gunakan TAHUN AKTUAL dari prospektus (misal "2023", "2024")
✓ Untuk tahun pertama berdiri / tidak ada pembanding: revenue_growth = 0
✓ Semua margin: angka desimal TANPA simbol persen. Contoh: 10.23 bukan "10.23%"
✓ Jika data benar-benar tidak ada: gunakan null (bukan 0)
✓ Mata uang bisa USD atau IDR — tulis apa adanya di field "currency"

RUMUS PERHITUNGAN:

A) Revenue Growth (%) — hitung sendiri:
   = ((Rev_N - Rev_N-1) / |Rev_N-1|) × 100
   → Tahun pertama = 0
   → Contoh CDIA: Rev 2024=102.254.765, Rev 2023=75.765.791
     Growth 2024 = ((102254765-75765791)/75765791)×100 = 34.96

B) Gross Margin (%) — cari atau hitung:
   = (Laba Kotor / Pendapatan) × 100
   → Laba Kotor = Pendapatan - Beban Pokok Pendapatan (COGS/HPP)
   → Bisa langsung ambil dari tabel "Rasio Usaha: Laba Kotor/Pendapatan"
   → Contoh CDIA 2024: 10.465.141/102.254.765×100 = 10.23

C) Operating Margin (%) — cari atau hitung:
   = (Laba Usaha / Pendapatan) × 100
   → Laba Usaha = Laba Kotor - Beban Penjualan - Beban Umum & Administrasi
   → Atau ambil dari tabel "Laba Usaha/Pendapatan"
   → Jika negatif, tulis minus: misal -3.45

D) EBITDA Margin (%) — cari atau hitung:
   = (EBITDA / Pendapatan) × 100
   → EBITDA = Laba Usaha + Depresiasi + Amortisasi
   → Jika D&A tidak tersedia di ringkasan, cari di tabel "Rasio Pertumbuhan: EBITDA"
   → Jika benar-benar tidak bisa dihitung: null

E) Raw Revenue — nilai pendapatan asli (untuk bar chart):
   → Dalam satuan JUTA jika IDR (bagi 1.000.000)
   → Dalam satuan asli jika USD (tulis nilai full, contoh: 102.25 untuk USD juta)

============================
LANGKAH 4 — KPI
============================
Cari di bagian "Rasio Keuangan" atau "Rasio-Rasio Keuangan Konsolidasian":
- P/E = Harga Penawaran / EPS. EPS biasanya ada di baris "Laba Per Saham Dasar"
  → Jika EPS dalam USD, konversi ke Rp dulu (×kurs ~16.000) sebelum hitung P/E dengan Harga Rp
  → Atau hitung: P/E = (Harga × Total Saham) / Laba Bersih
- P/B = Harga / (Total Ekuitas / Total Saham Beredar)
- ROE = Laba Bersih / Total Ekuitas × 100 → format: "4.37%"
- D/E = Total Liabilitas / Total Ekuitas → format: "0.44x"
- EPS = tulis apa adanya dari prospektus dengan mata uang aslinya
- Market Cap = tulis dalam Rp Triliun

============================
LANGKAH 5 — PENGGUNAAN DANA IPO
============================
Baca bagian "Rencana Penggunaan Dana". Hitung persentase setiap alokasi dari total dana bersih IPO.
Minimal 2 item, maksimal 5 item. Jumlah alokasi harus = 100.

============================
LANGKAH 6 — RISIKO (5–7 item)
============================
Dari "Faktor Risiko" atau "Bab VI Prospektus". Urutkan dari dampak terbesar:
- High: Risiko Utama (disebutkan pertama di prospektus, risiko ketergantungan pelanggan, dll)
- Medium: Risiko operasional, regulasi, persaingan
- Low: Risiko umum pasar modal, makroekonomi

============================
LANGKAH 7 — KEUNGGULAN / BENEFIT (4–6 item)
============================
Dari bagian prospek usaha, keunggulan kompetitif, atau simpulkan dari model bisnis:
- Posisi strategis, ekosistem grup, kontrak jangka panjang, pertumbuhan revenue, diversifikasi bisnis

============================
ATURAN OUTPUT — WAJIB DIPATUHI
============================
1. Output HANYA JSON murni — tidak ada teks sebelum atau sesudah
2. Tidak ada markdown, tidak ada ```json, tidak ada penjelasan
3. Semua string menggunakan tanda kutip ganda "
4. Tidak ada trailing comma
5. Array years HARUS sama panjang dengan semua array financial lainnya

PROSPEKTUS UNTUK DIANALISIS:
{text[:5000]}

OUTPUT JSON (ikuti struktur PERSIS ini, sesuaikan isi dengan data aktual dari prospektus):
{{
  "company_name": "PT Chandra Daya Investasi Tbk",
  "ticker": "CDIA",
  "sector": "Aktivitas Perusahaan Holding",
  "ipo_date": "8 Juli 2025",
  "share_price": "Rp 190",
  "total_shares": "124.829.374.700 lembar",
  "market_cap": "Rp 23,72 T",
  "summary": "PT Chandra Daya Investasi Tbk (CDI) adalah perusahaan holding yang merupakan anak usaha dari PT Chandra Asri Pacific Tbk (TPIA), salah satu perusahaan petrokimia terbesar di Asia Tenggara milik Grup Barito Pacific. CDI mengelola portofolio bisnis infrastruktur dan energi melalui empat pilar utama: energi kelistrikan, logistik maritim, pelabuhan & penyimpanan, serta pengelolaan air.\\n\\nPerseroan didirikan pada 8 Februari 2023 dan berkedudukan di Jakarta Barat. Dalam waktu singkat, CDI telah membangun ekosistem bisnis yang terintegrasi melalui anak-anak perusahaannya, termasuk PT Krakatau Chandra Energi (listrik), PT Chandra Shipping International (logistik laut), PT Chandra Cilegon Port (pelabuhan & tangki penyimpanan), dan PT Krakatau Tirta Industri (air).\\n\\nDengan dukungan penuh dari TPIA (pemegang saham 60%) dan Phoenix Power BV (30%), CDI memiliki posisi strategis sebagai backbone infrastruktur Grup Barito Pacific di kawasan industri Cilegon dan sekitarnya. IPO ini bertujuan memperkuat pilar logistik dan pelabuhan untuk mendukung pertumbuhan industri petrokimia Indonesia.",
  "financial": {{
    "currency": "USD",
    "years": ["2023", "2024"],
    "raw_revenue_million": [75.77, 102.25],
    "revenue_growth": [
      {{"year": "2023", "value": 0}},
      {{"year": "2024", "value": 34.96}}
    ],
    "gross_margin": [
      {{"year": "2023", "value": 8.41}},
      {{"year": "2024", "value": 10.23}}
    ],
    "operating_margin": [
      {{"year": "2023", "value": 0.01}},
      {{"year": "2024", "value": 0.21}}
    ],
    "ebitda_margin": [
      {{"year": "2023", "value": null}},
      {{"year": "2024", "value": null}}
    ]
  }},
  "kpi": {{
    "pe": "~588x",
    "pb": "N/A",
    "roe": "4.37%",
    "der": "0.44x",
    "eps": "USD 0.000323",
    "mktcap": "Rp 23,72 T"
  }},
  "use_of_funds": [
    {{"category": "Pilar Logistik (CSI & MIM)", "description": "Penyetoran modal ke PT Chandra Shipping International dan PT Marina Indah Maritim untuk pembelian kapal dan pembiayaan operasional armada logistik laut", "allocation": 37}},
    {{"category": "Pilar Pelabuhan & Penyimpanan (CCP)", "description": "Penyetoran modal ke PT Chandra Samudera Port lalu diteruskan ke PT Chandra Cilegon Port untuk pembuatan tangki penyimpanan ethylene, pipa saluran, dan fasilitas penunjang pelabuhan", "allocation": 63}}
  ],
  "risks": [
    {{"level": "High", "title": "Risiko Ketergantungan Pelanggan", "desc": "Perseroan sangat bergantung pada pelanggan strategis dalam ekosistem Grup Barito Pacific. Kehilangan penunjukan sebagai pemasok dapat berdampak material terhadap pendapatan dan kelangsungan usaha"}},
    {{"level": "High", "title": "Risiko Investasi & Aksi Korporasi", "desc": "Keputusan investasi pada anak perusahaan baru dapat membawa risiko gagal bayar, overestimasi nilai aset, atau underperformance yang mempengaruhi konsolidasi keuangan"}},
    {{"level": "Medium", "title": "Risiko Regulasi Energi & Kelistrikan", "desc": "Kegagalan memenuhi peraturan sektor energi listrik atau perubahan kebijakan subsidi listrik dapat mengganggu kontrak dan perizinan operasional PT Krakatau Chandra Energi"}},
    {{"level": "Medium", "title": "Risiko Operasional Logistik & Maritim", "desc": "Risiko kecelakaan maritim, kerusakan armada kapal, ketidakmampuan memenuhi kewajiban kontrak pengiriman, dan ketergantungan pada vendor suku cadang tertentu"}},
    {{"level": "Medium", "title": "Risiko Nilai Tukar USD/IDR", "desc": "Laporan keuangan konsolidasi disusun dalam USD, sehingga pergerakan nilai tukar Rupiah berpengaruh signifikan terhadap nilai aset, liabilitas, dan laba yang dilaporkan"}},
    {{"level": "Low", "title": "Risiko Likuiditas Saham di Pasar Modal", "desc": "Saham CDIA baru tercatat di BEI, volume perdagangan awal mungkin rendah sehingga investor bisa mengalami kesulitan menjual saham pada harga wajar"}},
    {{"level": "Low", "title": "Risiko Perubahan Kondisi Makroekonomi", "desc": "Perlambatan ekonomi regional/global, perubahan kebijakan pemerintah, atau guncangan geopolitik dapat mempengaruhi permintaan energi dan logistik"}}
  ],
  "benefits": [
    {{"title": "Backbone Infrastruktur Grup Barito Pacific", "desc": "CDI adalah entitas infrastruktur terintegrasi dari grup petrokimia terbesar di Asia Tenggara, memastikan demand captive yang stabil dari TPIA dan anak usaha Barito"}},
    {{"title": "Diversifikasi Bisnis 4 Pilar yang Saling Mendukung", "desc": "Kombinasi energi listrik, logistik maritim, pelabuhan & penyimpanan ethylene, dan pengelolaan air menciptakan ketahanan bisnis dan peluang cross-selling antar segmen"}},
    {{"title": "Pertumbuhan Revenue Signifikan +34.96% YoY", "desc": "Pendapatan tumbuh dari USD 75,77 juta (2023) menjadi USD 102,25 juta (2024), didorong oleh tambahan segmen logistik kapal dan peningkatan layanan kelistrikan"}},
    {{"title": "Posisi Strategis di Kawasan Industri Cilegon", "desc": "Aset-aset operasional CDI berlokasi di Cilegon, pusat industri petrokimia dan baja terbesar Indonesia, dengan akses langsung ke Selat Sunda dan pelanggan industri besar"}},
    {{"title": "Dukungan Finansial & Governance Kuat dari Induk", "desc": "TPIA sebagai pemegang saham pengendali 60% memberikan dukungan permodalan, jaringan bisnis, dan tata kelola korporasi yang kuat, mengurangi risiko kebangkrutan"}},
    {{"title": "Dana IPO untuk Aset Produktif Jangka Panjang", "desc": "100% dana IPO dialokasikan untuk pembelian kapal dan pembangunan tangki ethylene — aset fisik produktif yang menghasilkan pendapatan berulang jangka panjang"}}
  ]
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=4000
    )

    raw = response.choices[0].message.content.strip()

    # Bersihkan markdown jika ada
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
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    return json.loads(raw)