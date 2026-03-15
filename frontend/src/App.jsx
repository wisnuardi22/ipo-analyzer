import { useState, useRef, useEffect, forwardRef } from "react";
import {
  Menu,
  X,
  User,
  ExternalLink,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Sparkles,
  Brain,
  Shield,
  Zap,
  Clock,
  Mail,
  Phone,
  MapPin,
  Send,
  Linkedin,
  Twitter,
  Github,
  Sun,
  Moon,
  Globe,
  LogOut,
  Upload,
  FileText,
  Check,
  Loader2,
  BarChart2,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  Download,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import axios from "axios";

// ── TradingView Widget Components ──────────────────────────────
const TradingViewSingleQuote = forwardRef(({ symbol }, ref) => {
  useEffect(() => {
    if (!ref?.current) return;
    ref.current.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    const div = document.createElement("div");
    div.className = "tradingview-widget-container__widget";
    wrapper.appendChild(div);
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol,
      width: "100%",
      colorTheme: "dark",
      isTransparent: true,
      locale: "en",
    });
    wrapper.appendChild(script);
    ref.current.appendChild(wrapper);
  }, [symbol]);
  return <div ref={ref} />;
});

const TradingViewMiniChart = forwardRef(({ symbol }, ref) => {
  useEffect(() => {
    if (!ref?.current) return;
    ref.current.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container";
    const div = document.createElement("div");
    div.className = "tradingview-widget-container__widget";
    wrapper.appendChild(div);
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol,
      width: "100%",
      height: 200,
      locale: "en",
      dateRange: "1M",
      colorTheme: "dark",
      isTransparent: true,
      autosize: true,
      largeChartUrl: `https://www.tradingview.com/chart/?symbol=${symbol}`,
    });
    wrapper.appendChild(script);
    ref.current.appendChild(wrapper);
  }, [symbol]);
  return <div ref={ref} />;
});

const API_BASE = "http://localhost:8000/api";

// ── TRANSLATIONS ──────────────────────────────────────────────
const T = {
  EN: {
    nav: {
      home: "Home",
      service: "Service",
      about: "About",
      contact: "Contact",
    },
    hero: {
      badge: "Powered by Gemini AI",
      title: "Indonesian IPO Analysis with Gemini AI",
      subtitle:
        "Transform complex IPO prospectuses into actionable insights with artificial intelligence",
      ab_t: "About",
      ab_d: "Our AI-powered platform analyzes IPO prospectuses in seconds, delivering comprehensive financial insights, risk assessments, and growth projections.",
      sv_t: "Service",
      sv_b: "Basic:",
      sv_bd: "Essential IPO metrics & analysis",
      sv_p: "Pro:",
      sv_pd: "Advanced analytics, risk modeling & forecasts",
      ct_t: "Contact",
    },
    svc: {
      title: "Choose Your Analysis Plan",
      sub: "Select the plan that fits your investment strategy",
      basic: "Basic",
      free: "Free",
      pro: "Pro",
      bf: [
        "Comprehensive Company Profile",
        "Use of Proceeds Overview",
        "IPO Offering Summary",
        "Standard Risk Assessment",
      ],
      pf: [
        "Everything in Basic",
        "Industry-Specific KPIs",
        "Comprehensive Financial Highlights",
        "Revenue, EBITDA & Profit Trends",
        "Advanced Risk Analysis",
      ],
      pop: "Most Popular",
      sel: "Select Plan",
      seld: "Selected",
      s1t: "Download IPO Prospectus",
      s1d: "Get the official IPO prospectus document from the Indonesian Stock Exchange",
      vis: "Visit e-ipo.co.id",
      s2t: "Upload PDF for AI Analysis",
      s2d: "Our Gemini AI will analyze the document and generate comprehensive insights",
      drop: "Drop your IPO prospectus here",
      browse: "or click to browse (PDF only)",
      ubtn: "Select File",
      pow: "Powered by",
      abtn: "Analyze Now",
      analyzing: "Analyzing...",
      uploaded: "File uploaded! Click Analyze to start.",
    },
    about: {
      title: "About Indonesian IPO Analysis",
      sub: "Revolutionizing IPO investment decisions with cutting-edge AI technology",
      mt: "Our Mission",
      md: "To democratize access to sophisticated IPO analysis. We believe every investor deserves institutional-grade insights.",
      vt: "Our Vision",
      vd: "To become the world's most trusted AI-powered IPO analysis platform.",
      why: "Why Choose Us",
      fast: "Lightning Fast",
      fastd: "Comprehensive analysis in seconds",
      ai: "AI-Powered",
      aid: "Gemini AI delivers institutional-grade insights",
      sec: "Secure & Private",
      secd: "Documents encrypted and never stored",
      avl: "24/7 Available",
      avld: "Access analysis anytime, anywhere",
      imp: "Our Impact",
      an: "Analyses Completed",
      ac: "Accuracy Rate",
      us: "Active Users",
      tm: "Avg Analysis Time",
      how: "How It Works",
      h1: "Upload Document",
      h1d: "Upload the IPO prospectus PDF to our secure platform",
      h2: "AI Analysis",
      h2d: "Gemini AI processes document, extracting key financial metrics",
      h3: "Get Insights",
      h3d: "Receive comprehensive analysis with charts and risk assessment",
    },
    con: {
      title: "Get In Touch",
      sub: "Have questions? We'd love to hear from you.",
      em: "Email Us",
      emd: "Our team is here to help",
      ca: "Call Us",
      cad: "Mon-Fri from 8am to 6pm",
      vi: "Visit Us",
      vid: "Come say hello",
      ft: "Send us a Message",
      nm: "Full Name",
      el: "Email Address",
      sj: "Subject",
      ms: "Message",
      sb: "Send Message",
      ok: "Message sent successfully. We'll get back to you soon!",
      sc: "Or connect with us on social media",
    },
    dash: {
      badge: "Analysis Complete",
      title: "AI-Powered Indonesian IPO Analysis",
      profile: "Company Profile",
      about_co: "About Company",
      sector: "Sector",
      ipo_date: "IPO Date",
      offer: "Offering Price",
      cur: "Current Price",
      shares: "Total Shares",
      fin: "Financial Highlights",
      fin_sub:
        "4-year trend analysis · All values in % · Calculated from prospectus",
      rev: "Revenue Growth (%)",
      gm: "Gross Margin (%)",
      om: "Operating Margin (%)",
      eb: "EBITDA Margin (%)",
      kpi: "Key Performance Indicators",
      pe: "P/E Ratio",
      pb: "P/B Ratio",
      roe: "ROE (%)",
      der: "D/E Ratio",
      eps: "EPS",
      mktcap: "Market Cap",
      proceeds: "Use of Proceeds",
      risk: "Risk & Benefits Analysis",
      rf: "Risk Factors",
      ben: "Investment Benefits",
      live: "Current Price",
      change: "Change",
      refresh: "Refresh Price",
      stockbit: "View on Stockbit",
      trend_up: "Uptrend",
      trend_down: "Downtrend",
      trend_stable: "Stable",
      why: "Why this level?",
    },
    login: {
      title: "Sign In",
      sub: "Sign in to your account",
      em: "Email",
      pw: "Password",
      btn: "Sign In",
      reg: "Don't have an account?",
      regl: "Register",
      out: "Logout",
    },
    footer: "Making Indonesian IPO investing smarter",
  },
  ID: {
    nav: {
      home: "Beranda",
      service: "Layanan",
      about: "Tentang",
      contact: "Kontak",
    },
    hero: {
      badge: "Didukung Gemini AI",
      title: "Indonesian IPO Analysis — Cerdas dengan Gemini AI",
      subtitle:
        "Ubah prospektus IPO yang kompleks menjadi wawasan investasi actionable dengan kecerdasan buatan",
      ab_t: "Tentang",
      ab_d: "Platform AI kami menganalisis prospektus IPO dalam detik, memberikan wawasan keuangan, penilaian risiko, dan proyeksi pertumbuhan.",
      sv_t: "Layanan",
      sv_b: "Dasar:",
      sv_bd: "Metrik & analisis IPO esensial",
      sv_p: "Pro:",
      sv_pd: "Analitik lanjutan, pemodelan risiko & prakiraan",
      ct_t: "Kontak",
    },
    svc: {
      title: "Pilih Paket Analisis",
      sub: "Pilih paket yang sesuai dengan strategi investasi Anda",
      basic: "Dasar",
      free: "Gratis",
      pro: "Pro",
      bf: [
        "Profil Perusahaan Lengkap",
        "Ikhtisar Penggunaan Dana IPO",
        "Ringkasan Penawaran IPO",
        "Penilaian Risiko Standar",
      ],
      pf: [
        "Semua fitur Dasar",
        "KPI Spesifik Industri",
        "Sorotan Keuangan Komprehensif",
        "Tren Revenue, EBITDA & Laba",
        "Analisis Risiko Mendalam",
      ],
      pop: "Paling Populer",
      sel: "Pilih Paket",
      seld: "Terpilih",
      s1t: "Unduh Prospektus IPO",
      s1d: "Dapatkan dokumen prospektus IPO resmi dari Bursa Efek Indonesia",
      vis: "Kunjungi e-ipo.co.id",
      s2t: "Upload PDF untuk Analisis AI",
      s2d: "AI Gemini kami akan menganalisis dokumen dan menghasilkan wawasan komprehensif",
      drop: "Letakkan prospektus PDF di sini",
      browse: "atau klik untuk pilih file (PDF saja)",
      ubtn: "Pilih File",
      pow: "Didukung oleh",
      abtn: "Analisis Sekarang",
      analyzing: "Menganalisis...",
      uploaded: "File terupload! Klik Analisis untuk mulai.",
    },
    about: {
      title: "Tentang Indonesian IPO Analysis",
      sub: "Merevolusi keputusan investasi IPO dengan AI terdepan",
      mt: "Misi Kami",
      md: "Mendemokratisasi akses ke analisis IPO canggih. Setiap investor berhak mendapat wawasan tingkat institusional.",
      vt: "Visi Kami",
      vd: "Menjadi platform analisis IPO bertenaga AI paling dipercaya di dunia.",
      why: "Mengapa Memilih Kami",
      fast: "Super Cepat",
      fastd: "Analisis komprehensif dalam hitungan detik",
      ai: "Bertenaga AI",
      aid: "Gemini AI memberikan wawasan tingkat institusional",
      sec: "Aman & Privat",
      secd: "Dokumen dienkripsi dan tidak pernah disimpan",
      avl: "Tersedia 24/7",
      avld: "Akses analisis kapan saja, di mana saja",
      imp: "Dampak Kami",
      an: "Analisis Selesai",
      ac: "Tingkat Akurasi",
      us: "Pengguna Aktif",
      tm: "Waktu Analisis Rata-rata",
      how: "Cara Kerja",
      h1: "Upload Dokumen",
      h1d: "Upload PDF prospektus IPO ke platform aman kami",
      h2: "Analisis AI",
      h2d: "Gemini AI memproses dokumen, mengekstrak metrik keuangan utama",
      h3: "Dapatkan Wawasan",
      h3d: "Terima analisis komprehensif dengan grafik dan penilaian risiko",
    },
    con: {
      title: "Hubungi Kami",
      sub: "Ada pertanyaan? Kami senang mendengar dari Anda.",
      em: "Email Kami",
      emd: "Tim kami siap membantu",
      ca: "Hubungi Kami",
      cad: "Senin-Jumat pukul 08.00-18.00",
      vi: "Kunjungi Kami",
      vid: "Datang dan sapa kami",
      ft: "Kirim Pesan",
      nm: "Nama Lengkap",
      el: "Alamat Email",
      sj: "Subjek",
      ms: "Pesan",
      sb: "Kirim Pesan",
      ok: "Pesan berhasil dikirim. Kami akan segera merespons!",
      sc: "Atau hubungi kami di media sosial",
    },
    dash: {
      badge: "Analisis Selesai",
      title: "Analisis Indonesian IPO — Bertenaga AI",
      profile: "Profil Perusahaan",
      about_co: "Tentang Perusahaan",
      sector: "Sektor",
      ipo_date: "Tanggal IPO",
      offer: "Harga Penawaran",
      cur: "Harga Saat Ini",
      shares: "Total Saham",
      fin: "Sorotan Keuangan",
      fin_sub:
        "Analisis tren 4 tahun · Semua nilai dalam % · Dihitung dari prospektus",
      rev: "Pertumbuhan Pendapatan (%)",
      gm: "Margin Kotor (%)",
      om: "Margin Operasi (%)",
      eb: "Margin EBITDA (%)",
      kpi: "Indikator Kinerja Utama",
      pe: "Rasio P/E",
      pb: "Rasio P/B",
      roe: "ROE (%)",
      der: "Rasio D/E",
      eps: "EPS",
      mktcap: "Kapitalisasi Pasar",
      proceeds: "Penggunaan Dana",
      risk: "Analisis Risiko & Manfaat",
      rf: "Faktor Risiko",
      ben: "Keunggulan Investasi",
      live: "Harga Saat Ini",
      change: "Perubahan",
      refresh: "Perbarui Harga",
      stockbit: "Lihat di Stockbit",
      trend_up: "Tren Naik",
      trend_down: "Tren Turun",
      trend_stable: "Stabil",
      why: "Mengapa level ini?",
    },
    login: {
      title: "Masuk",
      sub: "Masuk ke akun Anda",
      em: "Email",
      pw: "Kata Sandi",
      btn: "Masuk",
      reg: "Belum punya akun?",
      regl: "Daftar",
      out: "Keluar",
    },
    footer: "Membuat investasi Indonesian IPO lebih cerdas",
  },
};

// ── MOCK DATA (fallback) ───────────────────────────────────────
const MOCK = {
  company: {
    name: "PT Contoh Tbk",
    ticker: "CONT",
    sector: "Technology - Financial Services",
    description:
      "PT Contoh Tbk is a leading financial technology company focused on digital payment solutions and micro-lending for the SME segment in Indonesia. Founded in 2018, the company has served over 2 million active users nationwide with average revenue growth of 45% per year. The company aims to democratize access to financial services through innovative AI-driven credit scoring and seamless payment infrastructure.",
    ipoDate: "15 March 2026",
    offerPrice: "Rp 500",
    currentPrice: "Rp 620",
    totalShares: "5,000,000,000 shares",
    marketCap: "Rp 3.1 T",
    currency: "IDR",
  },
  kpi: {
    pe: "24.5x",
    pb: "3.2x",
    roe: "18.4%",
    der: "0.45x",
    eps: "Rp 25",
    mktcap: "Rp 3,1 T",
  },
  financialTrends: {
    // Semua dalam PERSEN (%)
    revenue: [
      { year: "2021", value: 0 },
      { year: "2022", value: 54.2 },
      { year: "2023", value: 56.8 },
      { year: "2024", value: 55.2 },
    ],
    grossMargin: [
      { year: "2021", value: 48.5 },
      { year: "2022", value: 52.3 },
      { year: "2023", value: 56.1 },
      { year: "2024", value: 59.4 },
    ],
    operatingMargin: [
      { year: "2021", value: 8.2 },
      { year: "2022", value: 11.5 },
      { year: "2023", value: 16.3 },
      { year: "2024", value: 21.8 },
    ],
    ebitdaMargin: [
      { year: "2021", value: 14.7 },
      { year: "2022", value: 18.9 },
      { year: "2023", value: 24.2 },
      { year: "2024", value: 29.6 },
    ],
  },
  useOfProceeds: [
    { name: "R&D", value: 35, color: "#10B981" },
    { name: "Ekspansi", value: 30, color: "#3B82F6" },
    { name: "Operasional", value: 20, color: "#F59E0B" },
    { name: "Akuisisi", value: 10, color: "#8B5CF6" },
    { name: "Modal Kerja", value: 5, color: "#EC4899" },
  ],
  riskFactors: [
    {
      level: "High",
      title: "Persaingan pasar yang ketat",
      desc: "Banyak kompetitor fintech lokal dan asing",
    },
    {
      level: "High",
      title: "Risiko regulasi",
      desc: "Perubahan regulasi OJK dapat mempengaruhi bisnis",
    },
    {
      level: "Medium",
      title: "Risiko teknologi",
      desc: "Ketergantungan pada infrastruktur cloud pihak ketiga",
    },
    {
      level: "Medium",
      title: "Risiko kredit",
      desc: "Potensi gagal bayar dari portofolio pinjaman mikro",
    },
    {
      level: "Low",
      title: "Risiko mata uang",
      desc: "Eksposur terbatas pada transaksi valuta asing",
    },
  ],
  potentialBenefits: [
    {
      title: "Strong Market Position",
      desc: "Market leader in digital SME lending segment with 35% market share",
    },
    {
      title: "High Revenue Growth",
      desc: "45% CAGR over the last 4 years, consistently outperforming sector peers",
    },
    {
      title: "92% Customer Retention",
      desc: "Best-in-class user loyalty driven by seamless UX and competitive rates",
    },
    {
      title: "Experienced Management Team",
      desc: "CEO and CFO with combined 30+ years in fintech unicorn leadership",
    },
    {
      title: "Broad Digital Ecosystem",
      desc: "Integration with 200+ e-commerce platforms enabling merchant network effects",
    },
    {
      title: "Proprietary AI Technology",
      desc: "Patented credit scoring AI with 94% accuracy, reducing NPL to under 1.2%",
    },
  ],
  trendTags: {
    revenue: "up",
    grossMargin: "up",
    operatingMargin: "up",
    ebitdaMargin: "up",
  },
};

export default function App() {
  const [lang, setLang] = useState("EN");
  const [dark, setDark] = useState(false);
  const [menu, setMenu] = useState(false);
  const [plan, setPlan] = useState(null);
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState(null);
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [status, setStatus] = useState("");
  const [data, setData] = useState(null);
  const [ready, setReady] = useState(false);
  const [livePrice, setLivePrice] = useState(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const tvTickerRef = useRef(null);
  const tvMiniChartRef = useRef(null);
  const tvSymbolRef = useRef(null);
  const [contactForm, setContactForm] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
  });
  const [sent, setSent] = useState(false);
  const [showLogin, setShowLogin] = useState(false);
  const [user, setUser] = useState(null);
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [loginErr, setLoginErr] = useState("");
  const fileRef = useRef();
  const l = T[lang];

  useEffect(() => {
    if (dark) document.documentElement.classList.add("dark");
    else document.documentElement.classList.remove("dark");
  }, [dark]);

  // Auto-load TradingView widgets when ticker becomes available
  useEffect(() => {
    if (ready && data) {
      const ticker =
        data?.ipo_details?.ticker || data?.ipo_details?.ticker_code || "";
      if (ticker) {
        // Small delay to ensure DOM is ready
        setTimeout(() => loadTradingViewWidgets(ticker), 400);
      }
    }
  }, [ready, data]);

  const go = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setMenu(false);
  };

  // ── TradingView widget loader ──
  const loadTradingViewWidgets = (ticker) => {
    if (!ticker) return;
    const symbol = `IDX:${ticker}`;

    // Single Quote widget (harga + % change real-time)
    if (tvSymbolRef.current) {
      tvSymbolRef.current.innerHTML = "";
      const s1 = document.createElement("script");
      s1.src =
        "https://s3.tradingview.com/external-embedding/embed-widget-single-quote.js";
      s1.async = true;
      s1.innerHTML = JSON.stringify({
        symbol,
        width: "100%",
        colorTheme: "dark",
        isTransparent: true,
        locale: "en",
      });
      tvSymbolRef.current.appendChild(s1);
    }

    // Mini Chart widget (grafik 1 bulan)
    if (tvMiniChartRef.current) {
      tvMiniChartRef.current.innerHTML = "";
      const s2 = document.createElement("script");
      s2.src =
        "https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js";
      s2.async = true;
      s2.innerHTML = JSON.stringify({
        symbol,
        width: "100%",
        height: 220,
        locale: "en",
        dateRange: "1M",
        colorTheme: "dark",
        isTransparent: true,
        autosize: true,
        largeChartUrl: `https://www.tradingview.com/chart/?symbol=${symbol}`,
      });
      tvMiniChartRef.current.appendChild(s2);
    }
  };

  // backward compat shim
  const fetchLivePrice = (ticker) => loadTradingViewWidgets(ticker);

  // ── upload file ──
  const handleFile = (f) => {
    if (!f || f.type !== "application/pdf") return;
    setFile(f);
    setFileName(f.name);
    setStatus(l.svc.uploaded);
  };

  // ── analyze ──
  const handleAnalyze = async () => {
    if (!file) return;
    setAnalyzing(true);
    setStatus(lang === "EN" ? "Uploading PDF..." : "Mengupload PDF...");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const up = await axios.post(`${API_BASE}/upload`, fd);
      setStatus(
        lang === "EN"
          ? "AI is analyzing document..."
          : "AI sedang menganalisis dokumen...",
      );
      await axios.post(`${API_BASE}/analyze/${up.data.analysis_id}`);
      const res = await axios.get(
        `${API_BASE}/analysis/${up.data.analysis_id}`,
      );
      const d = res.data;
      // Ticker: dari field ticker, atau dari ipo_details, atau 4 huruf pertama nama
      const ticker =
        d.ipo_details?.ticker ||
        d.ipo_details?.ticker_code ||
        d.company_name
          ?.replace(/[^A-Z]/gi, "")
          .slice(0, 4)
          .toUpperCase();

      // Helper: pastikan nilai persen sudah angka, bukan string
      const toNum = (v) =>
        v === null || v === undefined
          ? null
          : parseFloat(String(v).replace("%", ""));

      // Normalisasi array financial dari Gemini
      const normFinancial = (arr) => {
        if (!arr || !Array.isArray(arr)) return null;
        return arr
          .map((item) => ({
            year: String(item.year || ""),
            value: toNum(item.value),
          }))
          .filter((x) => x.year && x.value !== null);
      };

      // ── trend analysis helper ──
      const trendTag = (arr) => {
        if (!arr || arr.length < 2) return null;
        const valid = arr.filter((x) => x.value !== null);
        if (valid.length < 2) return null;
        const first = valid[0].value;
        const last = valid[valid.length - 1].value;
        const diff = last - first;
        if (diff > 2) return "up";
        if (diff < -2) return "down";
        return "stable";
      };

      // ── financial summary for each chart ──
      const chartSummary = (arr, label) => {
        if (!arr || arr.length === 0) return "";
        const valid = arr.filter((x) => x.value !== null && x.value !== 0);
        if (valid.length === 0) return "";
        const last = valid[valid.length - 1];
        const avg = (
          valid.reduce((s, x) => s + x.value, 0) / valid.length
        ).toFixed(1);
        return `Latest: ${last.value?.toFixed(1)}% (${last.year}) · Avg: ${avg}%`;
      };

      const mapped = {
        company: {
          name: d.company_name || MOCK.company.name,
          ticker,
          sector: d.sector || d.ipo_details?.sector || "",
          description: d.summary || MOCK.company.description,
          ipoDate: d.ipo_details?.ipo_date || MOCK.company.ipoDate,
          offerPrice: d.ipo_details?.share_price || MOCK.company.offerPrice,
          currentPrice: d.ipo_details?.share_price || MOCK.company.currentPrice,
          totalShares: d.ipo_details?.total_shares || MOCK.company.totalShares,
          marketCap:
            d.ipo_details?.market_cap || d.market_cap || MOCK.company.marketCap,
          currency: d.financial?.currency || "IDR",
        },
        kpi: {
          pe: d.ipo_details?.kpi?.pe || MOCK.kpi.pe,
          pb: d.ipo_details?.kpi?.pb || MOCK.kpi.pb,
          roe: d.ipo_details?.kpi?.roe || MOCK.kpi.roe,
          der: d.ipo_details?.kpi?.der || MOCK.kpi.der,
          eps: d.ipo_details?.kpi?.eps || MOCK.kpi.eps,
          mktcap: d.ipo_details?.market_cap || d.market_cap || MOCK.kpi.mktcap,
          // KPI tambahan spesifik industri dari AI
          ...Object.fromEntries(
            Object.entries(d.ipo_details?.kpi || {}).filter(
              ([k]) => !["pe", "pb", "roe", "der", "eps", "mktcap"].includes(k),
            ),
          ),
        },
        financialTrends: {
          revenue:
            normFinancial(d.financial?.revenue_growth) ||
            MOCK.financialTrends.revenue,
          grossMargin:
            normFinancial(d.financial?.gross_margin) ||
            MOCK.financialTrends.grossMargin,
          operatingMargin:
            normFinancial(d.financial?.operating_margin) ||
            MOCK.financialTrends.operatingMargin,
          ebitdaMargin:
            normFinancial(d.financial?.ebitda_margin) ||
            MOCK.financialTrends.ebitdaMargin,
        },
        // pre-computed trend tags
        trendTags: {
          revenue: trendTag(
            normFinancial(d.financial?.revenue_growth) ||
              MOCK.financialTrends.revenue,
          ),
          grossMargin: trendTag(
            normFinancial(d.financial?.gross_margin) ||
              MOCK.financialTrends.grossMargin,
          ),
          operatingMargin: trendTag(
            normFinancial(d.financial?.operating_margin) ||
              MOCK.financialTrends.operatingMargin,
          ),
          ebitdaMargin: trendTag(
            normFinancial(d.financial?.ebitda_margin) ||
              MOCK.financialTrends.ebitdaMargin,
          ),
        },
        useOfProceeds:
          d.ipo_details?.use_of_funds?.map((x, i) => ({
            name: x.category,
            value: x.allocation,
            color: ["#10B981", "#3B82F6", "#F59E0B", "#8B5CF6", "#EC4899"][
              i % 5
            ],
          })) || MOCK.useOfProceeds,
        riskFactors: d.risks || MOCK.riskFactors,
        potentialBenefits: d.benefits || MOCK.potentialBenefits,
      };
      setData(mapped);
      setReady(true);
      setStatus("");
      if (ticker) fetchLivePrice(ticker);
      setTimeout(() => go("dashboard"), 600);
    } catch (e) {
      setStatus("Error: " + (e.response?.data?.detail || e.message));
    } finally {
      setAnalyzing(false);
    }
  };

  const handleLogin = (e) => {
    e.preventDefault();
    if (loginForm.email && loginForm.password) {
      setUser({ email: loginForm.email, name: loginForm.email.split("@")[0] });
      setShowLogin(false);
      setLoginErr("");
    } else
      setLoginErr(
        lang === "EN" ? "Please fill all fields" : "Harap isi semua field",
      );
  };

  const handleContact = (e) => {
    e.preventDefault();
    setSent(true);
    setTimeout(() => {
      setSent(false);
      setContactForm({ name: "", email: "", subject: "", message: "" });
    }, 3000);
  };

  const D = data || MOCK;
  const tt = {
    backgroundColor: "rgba(15,23,42,0.95)",
    border: "1px solid #334155",
    borderRadius: "8px",
    color: "#fff",
    fontSize: "13px",
  };
  const riskColor = (level) =>
    ({
      High: "border-red-500 bg-red-50 dark:bg-red-900/20",
      Medium: "border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20",
      Low: "border-green-500 bg-green-50 dark:bg-green-900/20",
    })[level] || "border-gray-300 bg-gray-50";
  const riskBadge = (level) =>
    ({
      High: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
      Medium:
        "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
      Low: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    })[level] || "";

  return (
    <div
      className={`min-h-screen ${dark ? "bg-gray-900" : "bg-gray-50"}`}
      style={{ fontFamily: "Inter,sans-serif" }}
    >
      {/* ── LOGIN MODAL ── */}
      {showLogin && (
        <div
          className="fixed inset-0 z-[100] bg-black/60 flex items-center justify-center p-4"
          onClick={() => setShowLogin(false)}
        >
          <div
            className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl p-8 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {l.login.title}
                </h2>
                <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
                  {l.login.sub}
                </p>
              </div>
              <button
                onClick={() => setShowLogin(false)}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {l.login.em}
                </label>
                <input
                  type="email"
                  value={loginForm.email}
                  onChange={(e) =>
                    setLoginForm({ ...loginForm, email: e.target.value })
                  }
                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="john@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {l.login.pw}
                </label>
                <input
                  type="password"
                  value={loginForm.password}
                  onChange={(e) =>
                    setLoginForm({ ...loginForm, password: e.target.value })
                  }
                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  placeholder="••••••••"
                />
              </div>
              {loginErr && <p className="text-red-500 text-sm">{loginErr}</p>}
              <button
                type="submit"
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-3 rounded-lg font-semibold transition-colors"
              >
                {l.login.btn}
              </button>
              <p className="text-center text-sm text-gray-500">
                {l.login.reg}{" "}
                <button
                  type="button"
                  className="text-emerald-600 font-medium hover:underline"
                >
                  {l.login.regl}
                </button>
              </p>
            </form>
          </div>
        </div>
      )}

      {/* ── HEADER ── */}
      <header className="sticky top-0 z-50 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div
              className="flex items-center gap-2 cursor-pointer"
              onClick={() => go("home")}
            >
              <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center">
                <BarChart2 className="w-6 h-6 text-white" />
              </div>
              <span className="text-xl font-bold text-gray-900 dark:text-white">
                Indonesian IPO Analysis
              </span>
            </div>
            <nav className="hidden md:flex items-center gap-8">
              {["home", "service", "about", "contact"].map((k) => (
                <button
                  key={k}
                  onClick={() => go(k)}
                  className="text-gray-700 dark:text-gray-300 hover:text-emerald-600 dark:hover:text-emerald-400 font-medium transition-colors"
                >
                  {l.nav[k]}
                </button>
              ))}
            </nav>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setLang(lang === "EN" ? "ID" : "EN")}
                className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 dark:bg-gray-700 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 rounded-full text-sm font-bold text-gray-700 dark:text-gray-300 transition-colors"
              >
                <Globe className="w-4 h-4" />
                {lang === "EN" ? "ID" : "EN"}
              </button>
              <button
                onClick={() => setDark(!dark)}
                className="relative w-14 h-7 bg-gray-300 dark:bg-gray-600 rounded-full transition-colors focus:outline-none"
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-6 h-6 bg-white rounded-full shadow-md transform transition-transform flex items-center justify-center ${dark ? "translate-x-7" : "translate-x-0"}`}
                >
                  {dark ? (
                    <Moon className="w-3.5 h-3.5 text-gray-700" />
                  ) : (
                    <Sun className="w-3.5 h-3.5 text-yellow-500" />
                  )}
                </span>
              </button>
              {user ? (
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center">
                    <span className="text-white text-sm font-bold">
                      {user.name[0].toUpperCase()}
                    </span>
                  </div>
                  <button
                    onClick={() => setUser(null)}
                    className="text-xs text-gray-500 hover:text-red-500 flex items-center gap-1"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    {l.login.out}
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowLogin(true)}
                  className="w-9 h-9 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  <User className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
              )}
              <button
                onClick={() => setMenu(!menu)}
                className="md:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              >
                {menu ? (
                  <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
                ) : (
                  <Menu className="w-6 h-6 text-gray-700 dark:text-gray-300" />
                )}
              </button>
            </div>
          </div>
          {menu && (
            <div className="md:hidden py-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
              {["home", "service", "about", "contact"].map((k) => (
                <button
                  key={k}
                  onClick={() => go(k)}
                  className="block w-full text-left text-gray-700 dark:text-gray-300 hover:text-emerald-600 py-1 font-medium"
                >
                  {l.nav[k]}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* ── HERO ── */}
      <section
        id="home"
        className="bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white py-20"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-4 py-2 mb-6">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span className="text-emerald-400 text-sm font-semibold">
                {l.hero.badge}
              </span>
            </div>
            <h1 className="text-5xl md:text-6xl font-bold mb-6 bg-gradient-to-r from-white to-gray-300 bg-clip-text text-transparent">
              {l.hero.title}
            </h1>
            <p className="text-xl text-gray-300 max-w-3xl mx-auto">
              {l.hero.subtitle}
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
              <h3 className="text-xl font-bold mb-3">{l.hero.ab_t}</h3>
              <p className="text-gray-300">{l.hero.ab_d}</p>
            </div>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
              <h3 className="text-xl font-bold mb-3">{l.hero.sv_t}</h3>
              <div className="text-gray-300 space-y-2">
                <p>
                  <span className="text-emerald-400 font-semibold">
                    {l.hero.sv_b}
                  </span>{" "}
                  {l.hero.sv_bd}
                </p>
                <p>
                  <span className="text-emerald-400 font-semibold">
                    {l.hero.sv_p}
                  </span>{" "}
                  {l.hero.sv_pd}
                </p>
              </div>
            </div>
            <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6">
              <h3 className="text-xl font-bold mb-3">{l.hero.ct_t}</h3>
              <div className="text-gray-300 space-y-1">
                <p>Email: support@ipoanalysis.ai</p>
                <p>Phone: +62 21 5086 4219</p>
                <p>Hours: 24/7 AI Support</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SERVICE ── */}
      <section id="service" className="py-20 bg-white dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              {l.svc.title}
            </h2>
            <p className="text-xl text-gray-600 dark:text-gray-400">
              {l.svc.sub}
            </p>
          </div>

          {/* Pricing Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto mb-16">
            {[
              {
                key: "basic",
                title: l.svc.basic,
                price: l.svc.free,
                unit: null,
                features: l.svc.bf,
                pop: false,
              },
              {
                key: "pro",
                title: l.svc.pro,
                price: "Rp 49.000",
                unit: "/analisis",
                features: l.svc.pf,
                pop: true,
              },
            ].map((p) => (
              <div
                key={p.key}
                onClick={() => setPlan(p.key)}
                className={`relative rounded-2xl p-8 border-2 cursor-pointer transition-all bg-white dark:bg-gray-800 ${plan === p.key ? "border-emerald-500 shadow-xl shadow-emerald-500/20" : "border-gray-200 dark:border-gray-700 hover:border-emerald-300 dark:hover:border-emerald-600"}`}
              >
                {p.pop && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-emerald-500 text-white px-4 py-1 rounded-full text-sm font-semibold">
                    {l.svc.pop}
                  </div>
                )}
                <div className="text-center mb-6">
                  <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                    {p.title}
                  </h3>
                  <div className="flex items-baseline justify-center gap-1">
                    <span className="text-4xl font-bold text-gray-900 dark:text-white">
                      {p.price}
                    </span>
                    {p.unit && (
                      <span className="text-gray-500 dark:text-gray-400">
                        {p.unit}
                      </span>
                    )}
                  </div>
                </div>
                <ul className="space-y-3 mb-8">
                  {p.features.map((f, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <Check className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                      <span className="text-gray-700 dark:text-gray-300">
                        {f}
                      </span>
                    </li>
                  ))}
                </ul>
                <button
                  className={`w-full py-3 rounded-lg font-semibold transition-colors ${plan === p.key ? "bg-emerald-500 text-white hover:bg-emerald-600" : "bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-200 dark:hover:bg-gray-600"}`}
                >
                  {plan === p.key ? l.svc.seld : l.svc.sel}
                </button>
              </div>
            ))}
          </div>

          {/* Upload Steps — only when plan selected */}
          {plan && (
            <div className="max-w-4xl mx-auto space-y-8">
              {/* Step 1 */}
              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl p-6">
                <div className="flex items-start gap-4">
                  <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0 text-white font-bold text-sm">
                    1
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                      {l.svc.s1t}
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300 mb-4">
                      {l.svc.s1d}
                    </p>
                    <a
                      href="https://e-ipo.co.id"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-semibold transition-colors"
                    >
                      {l.svc.vis}
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                </div>
              </div>

              {/* Step 2 — Upload */}
              <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-2xl p-6">
                <div className="flex items-start gap-4 mb-6">
                  <div className="w-8 h-8 bg-emerald-600 rounded-full flex items-center justify-center flex-shrink-0 text-white font-bold text-sm">
                    2
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                      {l.svc.s2t}
                    </h3>
                    <p className="text-gray-700 dark:text-gray-300">
                      {l.svc.s2d}
                    </p>
                  </div>
                </div>

                {/* Drop Zone */}
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDrag(true);
                  }}
                  onDragLeave={() => setDrag(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDrag(false);
                    handleFile(e.dataTransfer.files[0]);
                  }}
                  onClick={() =>
                    !uploading && !analyzing && fileRef.current.click()
                  }
                  className={`border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${drag ? "border-emerald-500 bg-emerald-100 dark:bg-emerald-800/30" : "border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50 hover:border-emerald-400"}`}
                >
                  <input
                    ref={fileRef}
                    type="file"
                    accept=".pdf"
                    onChange={(e) => handleFile(e.target.files[0])}
                    className="hidden"
                  />
                  <div className="flex flex-col items-center gap-4">
                    <div className="relative">
                      <div className="w-20 h-20 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center">
                        <Upload className="w-10 h-10 text-emerald-600 dark:text-emerald-400" />
                      </div>
                      <div className="absolute -top-1 -right-1 w-8 h-8 bg-emerald-500 rounded-full flex items-center justify-center">
                        <Sparkles className="w-5 h-5 text-white" />
                      </div>
                    </div>
                    {fileName ? (
                      <div className="flex items-center gap-2 bg-white dark:bg-gray-700 px-4 py-2 rounded-lg border border-emerald-200 dark:border-emerald-700">
                        <FileText className="w-5 h-5 text-emerald-600" />
                        <span className="text-gray-900 dark:text-white font-medium">
                          {fileName}
                        </span>
                        <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                      </div>
                    ) : (
                      <>
                        <div>
                          <p className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                            {l.svc.drop}
                          </p>
                          <p className="text-gray-500 dark:text-gray-400">
                            {l.svc.browse}
                          </p>
                        </div>
                        <label
                          className="cursor-pointer"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="file"
                            accept=".pdf"
                            onChange={(e) => handleFile(e.target.files[0])}
                            className="hidden"
                          />
                          <span className="inline-flex items-center gap-2 bg-emerald-500 hover:bg-emerald-600 text-white px-6 py-3 rounded-lg font-semibold transition-colors">
                            <Upload className="w-5 h-5" />
                            {l.svc.ubtn}
                          </span>
                        </label>
                      </>
                    )}
                    <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <span>{l.svc.pow}</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">
                        Gemini AI
                      </span>
                    </div>
                  </div>
                </div>

                {/* Status message */}
                {status && (
                  <p
                    className={`text-center mt-3 text-sm font-medium ${status.startsWith("Error") ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"}`}
                  >
                    {status}
                  </p>
                )}

                {/* ANALYZE BUTTON — shown after file selected */}
                {fileName && (
                  <div className="mt-6 flex justify-center">
                    <button
                      onClick={handleAnalyze}
                      disabled={analyzing}
                      className="inline-flex items-center gap-3 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white px-10 py-4 rounded-xl font-bold text-lg transition-colors shadow-lg shadow-emerald-500/30"
                    >
                      {analyzing ? (
                        <>
                          <Loader2 className="w-6 h-6 animate-spin" />
                          {l.svc.analyzing}
                        </>
                      ) : (
                        <>
                          <BarChart2 className="w-6 h-6" />
                          {l.svc.abtn}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── DASHBOARD — muncul di bawah service setelah analyze ── */}
      {ready && (
        <section id="dashboard" className="py-20 bg-slate-50 dark:bg-gray-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            {/* Header dashboard */}
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between mb-10 gap-4">
              <div>
                <div className="inline-flex items-center gap-2 bg-emerald-100 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-700 rounded-full px-4 py-1.5 mb-3">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <span className="text-emerald-600 dark:text-emerald-400 text-sm font-semibold">
                    {l.dash.badge}
                  </span>
                </div>
                <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
                  {l.dash.title}
                </h2>
                <p className="text-gray-500 dark:text-gray-400 mt-1">
                  {D.company.name}{" "}
                  {D.company.ticker && (
                    <span className="font-mono bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded text-sm">
                      {D.company.ticker}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => {
                    setReady(false);
                    setFileName(null);
                    setFile(null);
                    setData(null);
                    setStatus("");
                  }}
                  className="inline-flex items-center gap-2 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 px-4 py-2.5 rounded-lg font-semibold text-sm transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  {lang === "EN" ? "New Analysis" : "Analisis Baru"}
                </button>
              </div>
            </div>

            {/* ── IPO SUMMARY CARDS ── */}
            <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl p-6 mb-8 text-white">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <p className="text-gray-400 text-xs mb-1">{l.dash.offer}</p>
                  <p className="text-xl font-bold text-white">
                    {D.company.offerPrice}
                  </p>
                </div>
                <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <p className="text-gray-400 text-xs mb-1">{l.dash.cur}</p>
                  {D.company.ticker ? (
                    <a
                      href={`https://www.tradingview.com/chart/?symbol=IDX:${D.company.ticker}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-emerald-400 hover:text-emerald-300 font-bold text-sm mt-1"
                    >
                      <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-1"></span>
                      IDX:{D.company.ticker}
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : (
                    <p className="text-gray-400 text-sm mt-1">
                      {lang === "EN" ? "Not yet listed" : "Belum listing"}
                    </p>
                  )}
                </div>
                <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <p className="text-gray-400 text-xs mb-1">{l.dash.shares}</p>
                  <p className="text-base font-bold text-white leading-tight">
                    {D.company.totalShares}
                  </p>
                </div>
                <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <p className="text-gray-400 text-xs mb-1">{l.dash.mktcap}</p>
                  <p className="text-xl font-bold text-white">
                    {D.company.marketCap || D.kpi.mktcap}
                  </p>
                </div>
              </div>
            </div>

            {/* ── COMPANY PROFILE ── */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 mb-8">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
                <div>
                  <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                    {D.company.name}
                  </h3>
                  {D.company.ticker && (
                    <span className="inline-block mt-1 font-mono bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 text-sm font-bold px-3 py-1 rounded-full">
                      {D.company.ticker}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      {l.dash.ipo_date}:
                    </span>
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {D.company.ipoDate}
                    </span>
                  </div>
                  {D.company.sector && (
                    <span className="inline-flex items-center bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs font-semibold px-3 py-1 rounded-full">
                      {D.company.sector}
                    </span>
                  )}
                  {D.company.currency && D.company.currency !== "IDR" && (
                    <span className="inline-flex items-center gap-1 bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-xs font-semibold px-3 py-1 rounded-full">
                      📊 Laporan dalam {D.company.currency}
                    </span>
                  )}
                </div>
              </div>
              <h4 className="text-base font-semibold text-gray-700 dark:text-gray-300 mb-3">
                {l.dash.about_co}
              </h4>
              <div className="text-gray-700 dark:text-gray-300 leading-relaxed space-y-3">
                {D.company.description?.split("\n\n").map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            </div>

            {/* ── KPI CARDS ── */}
            <div className="mb-8">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
                {l.dash.kpi}
              </h3>
              {(() => {
                const extraColors = [
                  "text-teal-600 dark:text-teal-400",
                  "text-rose-600 dark:text-rose-400",
                  "text-indigo-600 dark:text-indigo-400",
                  "text-amber-600 dark:text-amber-400",
                ];
                const stdKpis = [
                  {
                    label: l.dash.pe,
                    val: D.kpi.pe,
                    color: "text-blue-600 dark:text-blue-400",
                  },
                  {
                    label: l.dash.pb,
                    val: D.kpi.pb,
                    color: "text-purple-600 dark:text-purple-400",
                  },
                  {
                    label: l.dash.roe,
                    val: D.kpi.roe,
                    color: "text-emerald-600 dark:text-emerald-400",
                  },
                  {
                    label: l.dash.der,
                    val: D.kpi.der,
                    color: "text-orange-600 dark:text-orange-400",
                  },
                  {
                    label: l.dash.eps,
                    val: D.kpi.eps,
                    color: "text-cyan-600 dark:text-cyan-400",
                  },
                  {
                    label: l.dash.mktcap,
                    val: D.kpi.mktcap,
                    color: "text-pink-600 dark:text-pink-400",
                  },
                ];
                const skipKeys = ["pe", "pb", "roe", "der", "eps", "mktcap"];
                const extraKpis = Object.entries(D.kpi)
                  .filter(([k, v]) => !skipKeys.includes(k) && v)
                  .map(([k, v], i) => ({
                    label: k.replace(/_/g, " ").toUpperCase(),
                    val: v,
                    color: extraColors[i % extraColors.length],
                  }));
                const allKpis = [...stdKpis, ...extraKpis];
                const gridClass =
                  allKpis.length <= 6
                    ? "grid-cols-2 md:grid-cols-3 lg:grid-cols-6"
                    : "grid-cols-2 md:grid-cols-3 lg:grid-cols-4";
                return (
                  <div className={`grid ${gridClass} gap-4`}>
                    {allKpis.map((k, i) => (
                      <div
                        key={i}
                        className="bg-white dark:bg-gray-900 rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm text-center"
                      >
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                          {k.label}
                        </p>
                        <p className={`text-lg font-bold ${k.color}`}>
                          {k.val}
                        </p>
                      </div>
                    ))}
                  </div>
                );
              })()}
            </div>

            {/* ── FINANCIAL CHARTS (2x2 grid) ── */}
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 mb-8">
              <div className="flex items-start justify-between mb-1">
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white">
                  {l.dash.fin}
                </h3>
                <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-3 py-1 rounded-full font-semibold">
                  {D.financialTrends.revenue?.length || 0}{" "}
                  {lang === "EN" ? "years data" : "tahun data"}
                </span>
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                {l.dash.fin_sub}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                {[
                  {
                    title: l.dash.rev,
                    data: D.financialTrends.revenue,
                    color: "#10B981",
                    type: "bar",
                    trendKey: "revenue",
                    note:
                      lang === "EN"
                        ? "YoY revenue growth · First year = 0 baseline"
                        : "Pertumbuhan revenue YoY · Tahun pertama = 0",
                  },
                  {
                    title: l.dash.gm,
                    data: D.financialTrends.grossMargin,
                    color: "#3B82F6",
                    type: "line",
                    trendKey: "grossMargin",
                    note:
                      lang === "EN"
                        ? "Gross Profit / Revenue × 100"
                        : "Laba Kotor / Pendapatan × 100",
                  },
                  {
                    title: l.dash.om,
                    data: D.financialTrends.operatingMargin,
                    color: "#F59E0B",
                    type: "line",
                    trendKey: "operatingMargin",
                    note:
                      lang === "EN"
                        ? "Operating Profit / Revenue × 100"
                        : "Laba Usaha / Pendapatan × 100",
                  },
                  {
                    title: l.dash.eb,
                    data: D.financialTrends.ebitdaMargin,
                    color: "#8B5CF6",
                    type: "line",
                    trendKey: "ebitdaMargin",
                    note:
                      lang === "EN"
                        ? "EBITDA / Revenue × 100"
                        : "EBITDA / Pendapatan × 100",
                  },
                ].map((ch, i) => {
                  const tag = D.trendTags?.[ch.trendKey];
                  const valid =
                    ch.data?.filter((x) => x.value !== null && x.value !== 0) ||
                    [];
                  const lastVal = valid.length
                    ? valid[valid.length - 1]?.value
                    : null;
                  const avgVal = valid.length
                    ? (
                        valid.reduce((s, x) => s + x.value, 0) / valid.length
                      ).toFixed(1)
                    : null;
                  return (
                    <div
                      key={i}
                      className="bg-gray-50 dark:bg-gray-800 rounded-xl p-6 border border-gray-100 dark:border-gray-700"
                    >
                      <div className="flex items-start justify-between mb-1">
                        <h4 className="text-base font-semibold text-gray-900 dark:text-white">
                          {ch.title}
                        </h4>
                        <div className="flex items-center gap-2">
                          {tag && (
                            <span
                              className={`text-xs font-bold px-2 py-0.5 rounded-full flex items-center gap-1 ${
                                tag === "up"
                                  ? "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400"
                                  : tag === "down"
                                    ? "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
                                    : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
                              }`}
                            >
                              {tag === "up" ? "↑" : tag === "down" ? "↓" : "→"}
                              {tag === "up"
                                ? l.dash.trend_up
                                : tag === "down"
                                  ? l.dash.trend_down
                                  : l.dash.trend_stable}
                            </span>
                          )}
                          <span className="text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 px-2 py-0.5 rounded-full font-mono font-bold">
                            %
                          </span>
                        </div>
                      </div>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mb-1 italic">
                        {ch.note}
                      </p>
                      {lastVal !== null && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                          <span className="font-semibold text-gray-700 dark:text-gray-300">
                            {lastVal?.toFixed(2)}%
                          </span>
                          {lang === "EN" ? " latest" : " terkini"}
                          {avgVal && (
                            <>
                              {" "}
                              · <span>{avgVal}%</span>
                              {lang === "EN" ? " avg" : " rata-rata"}
                            </>
                          )}
                        </p>
                      )}
                      <ResponsiveContainer width="100%" height={200}>
                        {ch.type === "bar" ? (
                          <BarChart data={ch.data}>
                            <CartesianGrid
                              strokeDasharray="3 3"
                              stroke="#374151"
                              opacity={0.2}
                            />
                            <XAxis
                              dataKey="year"
                              stroke="#9CA3AF"
                              fontSize={12}
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              fontSize={12}
                              unit="%"
                              domain={["auto", "auto"]}
                              tickFormatter={(v) => `${v.toFixed(1)}`}
                            />
                            <Tooltip
                              contentStyle={tt}
                              formatter={(v) => [
                                `${Number(v).toFixed(2)}%`,
                                ch.title,
                              ]}
                            />
                            <Bar
                              dataKey="value"
                              fill={ch.color}
                              radius={[4, 4, 0, 0]}
                            />
                          </BarChart>
                        ) : (
                          <LineChart data={ch.data}>
                            <CartesianGrid
                              strokeDasharray="3 3"
                              stroke="#374151"
                              opacity={0.2}
                            />
                            <XAxis
                              dataKey="year"
                              stroke="#9CA3AF"
                              fontSize={12}
                            />
                            <YAxis
                              stroke="#9CA3AF"
                              fontSize={12}
                              unit="%"
                              domain={["auto", "auto"]}
                              tickFormatter={(v) => `${v.toFixed(1)}`}
                            />
                            <Tooltip
                              contentStyle={tt}
                              formatter={(v) => [
                                `${Number(v).toFixed(2)}%`,
                                ch.title,
                              ]}
                            />
                            <Line
                              type="monotone"
                              dataKey="value"
                              stroke={ch.color}
                              strokeWidth={3}
                              dot={{ fill: ch.color, r: 5, strokeWidth: 0 }}
                            />
                          </LineChart>
                        )}
                      </ResponsiveContainer>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* ── USE OF PROCEEDS + RISK vs BENEFIT (side by side persis Figma) ── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
              {/* Use of Proceeds */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
                  {l.dash.proceeds}
                </h3>
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={D.useOfProceeds}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={3}
                      dataKey="value"
                      label={({
                        cx,
                        cy,
                        midAngle,
                        innerRadius,
                        outerRadius,
                        value,
                      }) => {
                        const RADIAN = Math.PI / 180;
                        const r =
                          innerRadius + (outerRadius - innerRadius) * 0.5;
                        const x = cx + r * Math.cos(-midAngle * RADIAN);
                        const y = cy + r * Math.sin(-midAngle * RADIAN);
                        return value >= 8 ? (
                          <text
                            x={x}
                            y={y}
                            fill="white"
                            textAnchor="middle"
                            dominantBaseline="central"
                            fontSize={12}
                            fontWeight="bold"
                          >
                            {`${value}%`}
                          </text>
                        ) : null;
                      }}
                      labelLine={false}
                    >
                      {D.useOfProceeds.map((e, i) => (
                        <Cell key={i} fill={e.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={tt}
                      formatter={(v, name) => [`${v}%`, name]}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Static legend with % */}
                <div className="mt-3 grid grid-cols-1 gap-2">
                  {D.useOfProceeds.map((e, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between px-1"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: e.color }}
                        />
                        <span className="text-sm text-gray-700 dark:text-gray-300">
                          {e.name}
                        </span>
                      </div>
                      <span
                        className="text-sm font-bold"
                        style={{ color: e.color }}
                      >
                        {e.value}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risk & Benefits — full redesign */}
              <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
                <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
                  {l.dash.risk}
                </h3>
                <div className="flex gap-4 mb-5">
                  <span className="text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 px-2 py-1 rounded-full font-semibold">
                    {D.riskFactors.filter((r) => r.level === "High").length}{" "}
                    High
                  </span>
                  <span className="text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300 px-2 py-1 rounded-full font-semibold">
                    {D.riskFactors.filter((r) => r.level === "Medium").length}{" "}
                    Medium
                  </span>
                  <span className="text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-2 py-1 rounded-full font-semibold">
                    {D.riskFactors.filter((r) => r.level === "Low").length} Low
                  </span>
                </div>
                <div className="space-y-5">
                  {/* Risk Factors */}
                  <div>
                    <h4 className="text-base font-semibold text-red-600 dark:text-red-400 mb-3 flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      {l.dash.rf}
                    </h4>
                    <div className="space-y-2.5">
                      {D.riskFactors.map((r, i) => {
                        const level = r.level || "Medium";
                        const title = r.title || r;
                        const levelIcon =
                          level === "High"
                            ? "🔴"
                            : level === "Low"
                              ? "🟢"
                              : "🟡";
                        return (
                          <div
                            key={i}
                            className={`border-l-4 rounded-r-xl px-4 py-3 ${riskColor(level)}`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex items-start gap-2 flex-1 min-w-0">
                                <span className="text-sm mt-0.5">
                                  {levelIcon}
                                </span>
                                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                                  {title}
                                </p>
                              </div>
                              <span
                                className={`text-xs font-bold px-2.5 py-1 rounded-full flex-shrink-0 ${riskBadge(level)}`}
                              >
                                {level}
                              </span>
                            </div>
                            {r.desc && (
                              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1.5 ml-6 leading-relaxed">
                                {r.desc}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  {/* Benefits */}
                  <div>
                    <h4 className="text-base font-semibold text-emerald-600 dark:text-emerald-400 mb-3 flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" />
                      {l.dash.ben}
                    </h4>
                    <div className="space-y-2.5">
                      {D.potentialBenefits.map((b, i) => {
                        const title = b.title || b;
                        const desc = b.desc || null;
                        const icons = [
                          "🚀",
                          "💡",
                          "📈",
                          "🏆",
                          "🌐",
                          "🔒",
                          "⚡",
                          "💎",
                        ];
                        return (
                          <div
                            key={i}
                            className="bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/10 border border-emerald-200 dark:border-emerald-800 rounded-xl px-4 py-3"
                          >
                            <div className="flex items-start gap-3">
                              <span className="text-base flex-shrink-0 mt-0.5">
                                {icons[i % icons.length]}
                              </span>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold text-emerald-800 dark:text-emerald-200">
                                  {title}
                                </p>
                                {desc && (
                                  <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 leading-relaxed">
                                    {desc}
                                  </p>
                                )}
                              </div>
                              <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0 mt-0.5" />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ── ABOUT ── */}
      <section id="about" className="py-20 bg-white dark:bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              {l.about.title}
            </h2>
            <p className="text-xl text-gray-600 dark:text-gray-400 max-w-3xl mx-auto">
              {l.about.sub}
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 mb-16">
            <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 dark:from-emerald-900/20 dark:to-emerald-800/10 rounded-2xl p-8 border border-emerald-200 dark:border-emerald-800">
              <div className="w-12 h-12 bg-emerald-500 rounded-lg flex items-center justify-center mb-4">
                <Brain className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
                {l.about.mt}
              </h3>
              <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                {l.about.md}
              </p>
            </div>
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/10 rounded-2xl p-8 border border-blue-200 dark:border-blue-800">
              <div className="w-12 h-12 bg-blue-500 rounded-lg flex items-center justify-center mb-4">
                <Shield className="w-6 h-6 text-white" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
                {l.about.vt}
              </h3>
              <p className="text-gray-700 dark:text-gray-300 leading-relaxed">
                {l.about.vd}
              </p>
            </div>
          </div>
          <div className="mb-16">
            <h3 className="text-3xl font-bold text-gray-900 dark:text-white text-center mb-12">
              {l.about.why}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
              {[
                {
                  icon: <Zap className="w-8 h-8 text-emerald-600" />,
                  bg: "bg-emerald-100 dark:bg-emerald-900/30",
                  t: l.about.fast,
                  d: l.about.fastd,
                },
                {
                  icon: <Brain className="w-8 h-8 text-blue-600" />,
                  bg: "bg-blue-100 dark:bg-blue-900/30",
                  t: l.about.ai,
                  d: l.about.aid,
                },
                {
                  icon: <Shield className="w-8 h-8 text-purple-600" />,
                  bg: "bg-purple-100 dark:bg-purple-900/30",
                  t: l.about.sec,
                  d: l.about.secd,
                },
                {
                  icon: <Clock className="w-8 h-8 text-orange-600" />,
                  bg: "bg-orange-100 dark:bg-orange-900/30",
                  t: l.about.avl,
                  d: l.about.avld,
                },
              ].map((x, i) => (
                <div key={i} className="text-center">
                  <div
                    className={`w-16 h-16 ${x.bg} rounded-full flex items-center justify-center mx-auto mb-4`}
                  >
                    {x.icon}
                  </div>
                  <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                    {x.t}
                  </h4>
                  <p className="text-gray-600 dark:text-gray-400">{x.d}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl p-12 text-white mb-16">
            <h3 className="text-3xl font-bold text-center mb-12">
              {l.about.imp}
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
              {[
                ["10,000+", l.about.an],
                ["98%", l.about.ac],
                ["5,000+", l.about.us],
                ["<30s", l.about.tm],
              ].map(([v, lb], i) => (
                <div key={i} className="text-center">
                  <div className="text-4xl font-bold text-emerald-400 mb-2">
                    {v}
                  </div>
                  <div className="text-gray-300">{lb}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="text-3xl font-bold text-gray-900 dark:text-white text-center mb-12">
              {l.about.how}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {[
                { n: "1", c: "bg-emerald-500", t: l.about.h1, d: l.about.h1d },
                { n: "2", c: "bg-blue-500", t: l.about.h2, d: l.about.h2d },
                { n: "3", c: "bg-purple-500", t: l.about.h3, d: l.about.h3d },
              ].map((s, i) => (
                <div
                  key={i}
                  className="relative bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-8"
                >
                  <div
                    className={`absolute -top-4 left-8 w-8 h-8 ${s.c} rounded-full flex items-center justify-center text-white font-bold`}
                  >
                    {s.n}
                  </div>
                  <h4 className="text-xl font-bold text-gray-900 dark:text-white mt-2 mb-3">
                    {s.t}
                  </h4>
                  <p className="text-gray-600 dark:text-gray-400">{s.d}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── CONTACT ── */}
      <section id="contact" className="py-20 bg-gray-50 dark:bg-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h2 className="text-4xl font-bold text-gray-900 dark:text-white mb-4">
              {l.con.title}
            </h2>
            <p className="text-xl text-gray-600 dark:text-gray-400">
              {l.con.sub}
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-12">
            {[
              {
                icon: <Mail className="w-6 h-6 text-emerald-600" />,
                bg: "bg-emerald-100 dark:bg-emerald-900/30",
                t: l.con.em,
                d: l.con.emd,
                link: "support@ipoanalysis.ai",
                href: "mailto:support@ipoanalysis.ai",
                c: "text-emerald-600",
              },
              {
                icon: <Phone className="w-6 h-6 text-blue-600" />,
                bg: "bg-blue-100 dark:bg-blue-900/30",
                t: l.con.ca,
                d: l.con.cad,
                link: "+62 21 5086 4219",
                href: "tel:+622150864219",
                c: "text-blue-600",
              },
              {
                icon: <MapPin className="w-6 h-6 text-purple-600" />,
                bg: "bg-purple-100 dark:bg-purple-900/30",
                t: l.con.vi,
                d: l.con.vid,
                link: "Jl. Jend. Sudirman No.1\nJakarta Pusat 10220",
                href: null,
                c: "text-gray-600 dark:text-gray-400",
              },
            ].map((c, i) => (
              <div
                key={i}
                className="bg-white dark:bg-gray-900 rounded-2xl p-6 border border-gray-200 dark:border-gray-700 text-center"
              >
                <div
                  className={`w-12 h-12 ${c.bg} rounded-full flex items-center justify-center mx-auto mb-4`}
                >
                  {c.icon}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  {c.t}
                </h3>
                <p className="text-gray-600 dark:text-gray-400 mb-2">{c.d}</p>
                {c.href ? (
                  <a href={c.href} className={`${c.c} hover:underline`}>
                    {c.link}
                  </a>
                ) : (
                  <p className={`${c.c} whitespace-pre-line`}>{c.link}</p>
                )}
              </div>
            ))}
          </div>
          <div className="max-w-3xl mx-auto">
            <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-6 text-center">
                {l.con.ft}
              </h3>
              <form onSubmit={handleContact} className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-gray-700 dark:text-gray-300 mb-2 font-medium">
                      {l.con.nm} *
                    </label>
                    <input
                      type="text"
                      value={contactForm.name}
                      onChange={(e) =>
                        setContactForm({ ...contactForm, name: e.target.value })
                      }
                      className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-gray-900 dark:text-white"
                      placeholder="John Doe"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-gray-700 dark:text-gray-300 mb-2 font-medium">
                      {l.con.el} *
                    </label>
                    <input
                      type="email"
                      value={contactForm.email}
                      onChange={(e) =>
                        setContactForm({
                          ...contactForm,
                          email: e.target.value,
                        })
                      }
                      className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-gray-900 dark:text-white"
                      placeholder="john@example.com"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-gray-700 dark:text-gray-300 mb-2 font-medium">
                    {l.con.sj} *
                  </label>
                  <input
                    type="text"
                    value={contactForm.subject}
                    onChange={(e) =>
                      setContactForm({
                        ...contactForm,
                        subject: e.target.value,
                      })
                    }
                    className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-gray-900 dark:text-white"
                    placeholder="How can we help?"
                    required
                  />
                </div>
                <div>
                  <label className="block text-gray-700 dark:text-gray-300 mb-2 font-medium">
                    {l.con.ms} *
                  </label>
                  <textarea
                    value={contactForm.message}
                    onChange={(e) =>
                      setContactForm({
                        ...contactForm,
                        message: e.target.value,
                      })
                    }
                    className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 text-gray-900 dark:text-white resize-none"
                    rows={6}
                    placeholder="Tell us more about your inquiry..."
                    required
                  />
                </div>
                {sent && (
                  <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 rounded-lg p-4 flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                    <p className="text-emerald-700 dark:text-emerald-300 font-medium">
                      {l.con.ok}
                    </p>
                  </div>
                )}
                <button
                  type="submit"
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-4 rounded-lg font-semibold transition-colors flex items-center justify-center gap-2 group"
                >
                  {l.con.sb}
                  <Send className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                </button>
              </form>
              <div className="mt-8 pt-8 border-t border-gray-200 dark:border-gray-700">
                <p className="text-center text-gray-600 dark:text-gray-400 mb-4">
                  {l.con.sc}
                </p>
                <div className="flex justify-center gap-4">
                  {[Linkedin, Twitter, Github].map((Icon, i) => (
                    <a
                      key={i}
                      href="#"
                      className="w-10 h-10 bg-gray-100 dark:bg-gray-800 rounded-full flex items-center justify-center hover:bg-emerald-100 dark:hover:bg-emerald-900/30 transition-colors group"
                    >
                      <Icon className="w-5 h-5 text-gray-600 dark:text-gray-400 group-hover:text-emerald-600" />
                    </a>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="bg-slate-900 text-white py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="flex items-center justify-center gap-2 mb-4">
            <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center">
              <BarChart2 className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold">Indonesian IPO Analysis</span>
          </div>
          <p className="text-gray-400 mb-4">
            Powered by Gemini AI • {l.footer}
          </p>
          <p className="text-gray-500 text-sm">
            &copy; 2026 Indonesian IPO Analysis. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
