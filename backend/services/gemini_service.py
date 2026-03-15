from groq import Groq
import json, os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

client = Groq(api_key=os.environ.get('GROQ_API_KEY'))

def analyze_prospectus(text: str) -> dict:
    prompt = f"""Kamu adalah analis keuangan IPO Indonesia senior (CFA level 3). Baca dokumen prospektus berikut dengan sangat teliti dan ekstrak semua informasi yang diminta.

============================
LANGKAH 1 — IDENTIFIKASI DOKUMEN
============================
- Prospektus ringkas atau lengkap?
- Berapa tahun data keuangan? (bisa 2, 3, atau 4 tahun)
- Mata uang: IDR atau USD?
- JANGAN mengarang data yang tidak ada di prospektus

============================
LANGKAH 2 — DATA IDENTITAS
============================
- Nama perusahaan lengkap (termasuk Tbk)
- Kode ticker saham: 4 huruf kapital. Cari di: judul halaman, tabel struktur modal, bagian pencatatan BEI, atau frasa "Kode Saham: XXXX"
- Sektor industri: tulis spesifik (contoh: "Pertambangan Emas & Mineral", bukan hanya "Pertambangan")
- Tanggal Pencatatan di BEI
- Harga penawaran: jika range, ambil NILAI TERTINGGI
- Total saham beredar SETELAH IPO
- Market cap

============================
LANGKAH 3 — RINGKASAN PERUSAHAAN (summary)
============================
Tulis dalam Bahasa Indonesia yang MUDAH DIMENGERTI orang awam (bukan investor profesional).
Gunakan bahasa sehari-hari, hindari jargon teknis berlebihan.
Struktur 3 paragraf:
1. Paragraf 1: Perusahaan ini bergerak di bidang apa, produk/jasa utamanya apa, berdiri kapan dan di mana
2. Paragraf 2: Siapa pelanggan utamanya, posisi di industri, keunggulan utama dibanding kompetitor
3. Paragraf 3: Tujuan IPO ini dan apa yang ingin dicapai perusahaan ke depan
Pisahkan tiap paragraf dengan \\n\\n

============================
LANGKAH 4 — DATA KEUANGAN
============================
Cari di: "Ikhtisar Data Keuangan Penting", "Laporan Laba Rugi", tabel keuangan apapun.

ATURAN KETAT:
✓ Gunakan TAHUN AKTUAL dari prospektus
✓ Tahun pertama: revenue_growth = 0
✓ Semua margin: angka desimal TANPA persen. Contoh: 10.23 bukan "10.23%"
✓ Data tidak ada = null (bukan 0)
✓ FOKUS PADA TREN: cari data dari tabel laporan keuangan multi-tahun

RUMUS:
A) Revenue Growth (%) = ((Rev_N - Rev_N-1) / |Rev_N-1|) × 100, tahun pertama = 0
B) Gross Margin (%) = (Laba Kotor / Pendapatan) × 100
C) Operating Margin (%) = (Laba Usaha / Pendapatan) × 100, boleh negatif
D) EBITDA Margin (%) = (EBITDA / Pendapatan) × 100, jika D&A tidak ada = null
E) Net Profit Margin (%) = (Laba Bersih / Pendapatan) × 100

============================
LANGKAH 5 — KPI RELEVAN DENGAN INDUSTRI
============================
PENTING: Sesuaikan KPI dengan industri perusahaan!

Contoh KPI per industri:
- Pertambangan: EV/EBITDA, Reserve Life Index, Cash Cost/oz
- Perbankan: NIM, NPL, CAR, ROA
- Properti: NAV discount, Pre-sales, DER
- Teknologi: P/S Ratio, ARR Growth, Churn Rate
- Manufaktur: Asset Turnover, Inventory Turnover, ROIC
- Retail: Same-store sales growth, Revenue/sq m
- Infrastruktur: EV/EBITDA, Debt Coverage Ratio, IRR

Untuk IPO ini, pilih 4-6 KPI yang paling relevan dengan sektornya.
Selalu sertakan: P/E, Market Cap.
Tambahkan KPI spesifik industri sebagai field tambahan di object kpi.

============================
LANGKAH 6 — PENGGUNAAN DANA IPO
============================
Baca bagian "Rencana Penggunaan Dana" dengan SANGAT TELITI.
- Ekstrak SETIAP alokasi dana beserta deskripsi detailnya
- Hitung persentase dari total dana bersih IPO
- Jumlah allocation HARUS = 100
- Minimal 2, maksimal 5 item
- description: jelaskan secara spesifik uang tersebut untuk apa (beli apa, bangun apa, bayar apa)

============================
LANGKAH 7 — RISIKO (5-7 item)
============================
Dari bagian "Faktor Risiko". Aturan baru:
- Setiap risiko hanya boleh SATU level: High, Medium, atau Low
- High: Risiko yang bisa mengancam kelangsungan bisnis atau revenue utama
- Medium: Risiko operasional yang perlu dikelola tapi tidak mengancam eksistensi
- Low: Risiko umum yang dialami semua perusahaan di sektor ini
- desc: jelaskan dengan bahasa sederhana MENGAPA level ini dipilih

============================
LANGKAH 8 — KEUNGGULAN / BENEFIT (4-6 item)
============================
Dari bagian prospek usaha dan keunggulan kompetitif:
- Tulis manfaat nyata bagi investor, bukan sekadar pujian perusahaan
- Sertakan angka/data konkret jika tersedia

============================
ATURAN OUTPUT
============================
1. Output HANYA JSON murni — tidak ada teks apapun di luar JSON
2. Tidak ada markdown, tidak ada ```json
3. String pakai tanda kutip ganda "
4. Tidak ada trailing comma

PROSPEKTUS:
{text[:5000]}

OUTPUT JSON (struktur persis ini):
{{
  "company_name": "PT Merdeka Gold Resources Tbk",
  "ticker": "MGRO",
  "sector": "Pertambangan Emas & Mineral",
  "ipo_date": "23 September 2025",
  "share_price": "Rp 2.880",
  "total_shares": "1.618.023.300 lembar",
  "market_cap": "Rp 4,66 T",
  "summary": "PT Merdeka Gold Resources Tbk adalah perusahaan holding yang bergerak di bidang pertambangan emas dan mineral. Perusahaan ini memiliki dan mengelola tambang emas di beberapa lokasi di Indonesia, dengan fokus pada penambangan, pengolahan, dan penjualan emas beserta mineral ikutannya.\\n\\nPerusahaan melayani pelanggan industri dan pasar komoditas global. Posisinya cukup kuat karena didukung cadangan emas yang sudah terbukti dan teknologi pengolahan yang teruji.\\n\\nIPO ini bertujuan memperluas kapasitas produksi dan eksplorasi tambang baru untuk meningkatkan cadangan emas jangka panjang.",
  "financial": {{
    "currency": "IDR",
    "years": ["2023"],
    "raw_revenue_million": [850000],
    "revenue_growth": [
      {{"year": "2023", "value": 0}}
    ],
    "gross_margin": [
      {{"year": "2023", "value": 42.5}}
    ],
    "operating_margin": [
      {{"year": "2023", "value": 18.3}}
    ],
    "ebitda_margin": [
      {{"year": "2023", "value": null}}
    ],
    "net_profit_margin": [
      {{"year": "2023", "value": 12.1}}
    ]
  }},
  "kpi": {{
    "pe": "24.5x",
    "pb": "3.2x",
    "roe": "18.4%",
    "der": "0.45x",
    "eps": "Rp 25",
    "mktcap": "Rp 4,66 T",
    "ev_ebitda": "12.3x",
    "cash_cost_per_oz": "USD 850/oz"
  }},
  "use_of_funds": [
    {{"category": "Ekspansi Kapasitas Tambang", "description": "Pembelian alat berat dan pembangunan fasilitas pengolahan emas di lokasi tambang utama untuk meningkatkan kapasitas produksi dari 50.000 oz menjadi 80.000 oz per tahun", "allocation": 60}},
    {{"category": "Eksplorasi Cadangan Baru", "description": "Biaya eksplorasi dan pengeboran di blok-blok potensial yang sudah diidentifikasi untuk menambah cadangan terbukti perusahaan", "allocation": 30}},
    {{"category": "Modal Kerja", "description": "Pembiayaan operasional sehari-hari termasuk pembelian bahan kimia, bahan bakar, dan gaji karyawan tambang", "allocation": 10}}
  ],
  "risks": [
    {{"level": "High", "title": "Risiko Fluktuasi Harga Emas", "desc": "Pendapatan perusahaan 100% bergantung pada harga emas global yang sangat volatile. Penurunan harga emas 20% bisa langsung memotong setengah laba bersih perusahaan"}},
    {{"level": "High", "title": "Risiko Cadangan Tambang Terbatas", "desc": "Jika eksplorasi gagal menemukan cadangan baru, umur tambang yang ada hanya tersisa 8-10 tahun sehingga pendapatan jangka panjang terancam"}},
    {{"level": "Medium", "title": "Risiko Operasional Pertambangan", "desc": "Kecelakaan kerja, kerusakan alat berat, atau bencana alam dapat menghentikan produksi dan menyebabkan kerugian signifikan"}},
    {{"level": "Medium", "title": "Risiko Regulasi Pertambangan", "desc": "Perubahan peraturan ESDM atau pencabutan izin konsesi tambang dapat menghambat operasional meski risiko ini moderat karena izin sudah dipegang lama"}},
    {{"level": "Low", "title": "Risiko Likuiditas Saham", "desc": "Sebagai emiten baru, volume perdagangan awal mungkin rendah, namun hal ini wajar dan umumnya membaik seiring waktu"}}
  ],
  "benefits": [
    {{"title": "Cadangan Emas Terbukti yang Besar", "desc": "Perusahaan memiliki cadangan emas terbukti sebesar 1,2 juta oz, cukup untuk operasi 10+ tahun ke depan tanpa eksplorasi tambahan"}},
    {{"title": "Harga Emas Sedang di Level Tertinggi Sepanjang Masa", "desc": "Emas diperdagangkan di atas USD 2.000/oz, memberikan margin keuntungan yang sangat tebal bagi produsen emas berbiaya rendah"}},
    {{"title": "Cash Cost Kompetitif", "desc": "Biaya produksi USD 850/oz jauh di bawah harga pasar, memberikan buffer keuntungan yang kuat meski harga emas turun"}},
    {{"title": "Manajemen Berpengalaman di Sektor Tambang", "desc": "Tim manajemen rata-rata 15+ tahun pengalaman di industri pertambangan, dengan track record operasi tambang yang efisien"}}
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