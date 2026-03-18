from openai import OpenAI
import json, os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Gemini via OpenAI-compatible endpoint
client = OpenAI(
    api_key=os.environ.get('SUMOPOD_API_KEY'),
    base_url="https://ai.sumopod.com/v1"
)

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
LANGKAH 7 — RISIKO (5-8 item)
============================
Dari bagian "Faktor Risiko" + analisis penjamin efek. Aturan:
- Setiap risiko hanya boleh SATU level: High, Medium, atau Low
- High: Risiko yang bisa mengancam kelangsungan bisnis atau revenue utama
- Medium: Risiko operasional yang perlu dikelola tapi tidak mengancam eksistensi
- Low: Risiko umum yang dialami semua perusahaan di sektor ini
- desc: jelaskan dengan bahasa sederhana MENGAPA level ini dipilih
- Jika penjamin efek kurang dikenal/reputasi buruk: tambahkan sebagai risiko Medium/High

============================
LANGKAH 8 — KEUNGGULAN / BENEFIT (4-7 item)
============================
Dari bagian prospek usaha, keunggulan kompetitif, DAN analisis penjamin efek:
- Tulis manfaat nyata bagi investor, bukan sekadar pujian perusahaan
- Sertakan angka/data konkret jika tersedia
- Jika penjamin efek bereputasi baik (mis: Mandiri Sekuritas, BCA Sekuritas, CGS-CIMB, UBS, dll):
  tambahkan sebagai benefit dengan title "Didukung Penjamin Emisi Terpercaya"
  dan desc berisi nama penjamin + track record singkatnya

============================
LANGKAH 9 — PENJAMIN EFEK (UNDERWRITER)
============================
Cari di bagian "Penjaminan Emisi Efek" atau "Agen Penjual":
- Nama penjamin emisi utama (lead underwriter)
- Nama penjamin emisi lainnya jika ada
- Jumlah saham yang dijamin masing-masing
- Sifat penjaminan: penuh (full commitment) atau terbaik (best effort)
- Komisi penjaminan jika disebutkan

ANALISIS TRACK RECORD PENJAMIN:
Berikan analisis singkat reputasi penjamin berdasarkan pengetahuan umum:
- Apakah penjamin ini terkenal dan terpercaya di pasar modal Indonesia?
- Berapa banyak IPO besar yang pernah mereka tangani?
- Apakah ada catatan negatif yang diketahui?

Hasil analisis penjamin efek akan dimasukkan ke:
- "benefits" jika penjamin memiliki reputasi baik dan track record kuat
- "risks" jika penjamin kurang dikenal atau ada catatan negatif

============================
LANGKAH 9 — PENJAMIN EMISI EFEK
============================
Dari bagian "Penjaminan Emisi Efek" atau "Penjamin Pelaksana Emisi Efek":
- Ekstrak SEMUA nama penjamin (penjamin pelaksana + co-underwriter)
- Jumlah porsi penjaminan masing-masing (lembar saham atau persentase)
- Jenis penjaminan: "Kesanggupan Penuh" (full commitment) atau lainnya

============================
ATURAN OUTPUT — WAJIB DIPATUHI KETAT
============================
1. Output HANYA JSON murni — TIDAK ADA teks apapun sebelum atau sesudah JSON
2. DILARANG menggunakan markdown, DILARANG menggunakan ```json atau ```
3. Semua string WAJIB pakai tanda kutip ganda " bukan tanda kutip tunggal '
4. DILARANG trailing comma — tidak boleh ada koma sebelum } atau ]
5. Semua field wajib diisi — jika data tidak ada gunakan null bukan string kosong
6. JANGAN tambahkan komentar // atau /* */ di dalam JSON
7. Pastikan semua kurung buka {{ memiliki pasangan kurung tutup }}

PROSPEKTUS:
{text[:500000]}

OUTPUT JSON (struktur persis ini):
{{
  "company_name": "PT Merdeka Gold Resources Tbk",
  "ticker": "MGRO",
  "underwriter": {{
    "lead": "Mandiri Sekuritas",
    "others": ["BCA Sekuritas", "CGS-CIMB Sekuritas"],
    "type": "Penjaminan Penuh (Full Commitment)",
    "reputation": "Sangat baik — Mandiri Sekuritas adalah penjamin emisi terbesar di Indonesia dengan 50+ IPO besar"
  }},
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
  "underwriter_risk": "Tidak ada — penjamin emisi memiliki reputasi baik",
  "benefits": [
    {{"title": "Cadangan Emas Terbukti yang Besar", "desc": "Perusahaan memiliki cadangan emas terbukti sebesar 1,2 juta oz, cukup untuk operasi 10+ tahun ke depan tanpa eksplorasi tambahan"}},
    {{"title": "Harga Emas Sedang di Level Tertinggi Sepanjang Masa", "desc": "Emas diperdagangkan di atas USD 2.000/oz, memberikan margin keuntungan yang sangat tebal bagi produsen emas berbiaya rendah"}},
    {{"title": "Cash Cost Kompetitif", "desc": "Biaya produksi USD 850/oz jauh di bawah harga pasar, memberikan buffer keuntungan yang kuat meski harga emas turun"}},
    {{"title": "Manajemen Berpengalaman di Sektor Tambang", "desc": "Tim manajemen rata-rata 15+ tahun pengalaman di industri pertambangan, dengan track record operasi tambang yang efisien"}},
    {{"title": "Didukung Penjamin Emisi Terpercaya", "desc": "IPO ini dijamin penuh oleh Mandiri Sekuritas — penjamin emisi terbesar Indonesia yang telah menangani 50+ IPO besar seperti BREN, GOTO, TLKM rights issue. Full commitment berarti seluruh saham pasti terjual"}}
  ],
  "underwriters": [
    {{"name": "PT Mandiri Sekuritas", "role": "Penjamin Pelaksana Emisi Efek", "portion_pct": 70, "commitment_type": "Kesanggupan Penuh"}},
    {{"name": "PT BRI Danareksa Sekuritas", "role": "Penjamin Emisi Efek", "portion_pct": 30, "commitment_type": "Kesanggupan Penuh"}}
  ]
}}"""

    response = client.chat.completions.create(
        model="gemini/gemini-2.5-flash",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=8000
    )

    raw = response.choices[0].message.content.strip()

    # ── Bersihkan markdown/formatting ──────────────────────────────────
    # Hapus ```json ... ``` wrapper
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                raw = p
                break

    # Ambil hanya bagian JSON { ... }
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    # ── Coba parse langsung ─────────────────────────────────────────────
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # ── Fix 1: Hapus trailing comma sebelum } atau ] ────────────────────
    import re
    raw_fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(raw_fixed)
    except json.JSONDecodeError:
        pass

    # ── Fix 2: Pakai json5 / ast literal eval sebagai fallback ──────────
    try:
        import ast
        # Ganti true/false/null Python-style
        raw_py = raw_fixed.replace('true', 'True').replace('false', 'False').replace('null', 'None')
        return ast.literal_eval(raw_py)
    except Exception:
        pass

    # ── Fix 3: Potong sampai JSON valid terakhir ─────────────────────────
    for i in range(len(raw_fixed), 0, -1):
        try:
            return json.loads(raw_fixed[:i])
        except json.JSONDecodeError:
            continue

    # ── Fix 4: Return partial data daripada crash ────────────────────────
    raise ValueError(f"Tidak bisa parse JSON dari Gemini. Raw output (500 char): {raw[:500]}")