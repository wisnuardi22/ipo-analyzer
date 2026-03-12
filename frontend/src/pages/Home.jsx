import { useState, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  TrendingUp,
  Building2,
  DollarSign,
  Users,
  ArrowRight,
  Upload,
  FileText,
  Sparkles,
  BarChart3,
  Loader2,
} from "lucide-react";
import { uploadPDF, runAnalysis } from "../services/api";

const featuredIPOs = [
  {
    id: 1,
    name: "PT Abadi Lestari Indonesia",
    ticker: "RLCO",
    sector: "Kesehatan",
    ipoPrice: 168,
    currentPrice: 172,
    marketCap: "Rp 539M",
  },
  {
    id: 2,
    name: "PT Teknologi Nusantara",
    ticker: "TEKN",
    sector: "Teknologi",
    ipoPrice: 250,
    currentPrice: 310,
    marketCap: "Rp 1.2T",
  },
  {
    id: 3,
    name: "PT Energi Hijau Indonesia",
    ticker: "EHIJ",
    sector: "Energi",
    ipoPrice: 500,
    currentPrice: 480,
    marketCap: "Rp 2.4T",
  },
];

const upcomingIPOs = [
  {
    id: 4,
    name: "PT Digital Finansial",
    ticker: "DFIN",
    sector: "Keuangan",
    ipoDate: "2026-04-15",
    ipoPrice: 300,
    marketCap: "Rp 900M",
    description:
      "Perusahaan fintech terkemuka yang menyediakan layanan pembayaran digital.",
  },
  {
    id: 5,
    name: "PT Agro Makmur",
    ticker: "AGRO",
    sector: "Pertanian",
    ipoDate: "2026-05-01",
    ipoPrice: 180,
    marketCap: "Rp 540M",
    description:
      "Perusahaan agribisnis modern dengan teknologi pertanian terkini.",
  },
];

export default function Home() {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef();
  const navigate = useNavigate();

  const handleFile = (f) => {
    if (f && f.type === "application/pdf") setFile(f);
  };

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    try {
      setStatus("Mengupload PDF...");
      const res = await uploadPDF(file);
      setStatus("Menganalisis dengan AI...");
      await runAnalysis(res.analysis_id);
      navigate(`/dashboard/${res.analysis_id}`);
    } catch (e) {
      setStatus("Error: " + (e.response?.data?.detail || e.message));
      setLoading(false);
    }
  };

  return (
    <div>
      {/* Hero */}
      <div className="bg-gradient-to-br from-blue-700 to-blue-900 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <h1 className="text-5xl font-bold mb-6 leading-tight">
                Analisis IPO dengan{" "}
                <span className="text-blue-200">Kecerdasan AI</span>
              </h1>
              <p className="text-xl text-blue-100 mb-8 leading-relaxed">
                Upload prospektus IPO dan dapatkan analisis mendalam secara
                otomatis dalam hitungan detik.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/ipo-listings"
                  className="inline-flex items-center justify-center gap-2 bg-white text-blue-700 px-6 py-3 rounded-lg hover:bg-blue-50 transition-colors font-semibold"
                >
                  Lihat IPO Listings <ArrowRight className="w-5 h-5" />
                </Link>
                <a
                  href="#upload"
                  className="inline-flex items-center justify-center gap-2 border-2 border-white text-white px-6 py-3 rounded-lg hover:bg-white/10 transition-colors font-semibold"
                >
                  <Upload className="w-5 h-5" /> Analisis Sekarang
                </a>
              </div>
            </div>

            {/* Upload Zone */}
            <div
              id="upload"
              className="bg-white/10 backdrop-blur rounded-2xl p-6 border border-white/20"
            >
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragging(false);
                  handleFile(e.dataTransfer.files[0]);
                }}
                onClick={() => fileInputRef.current.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${isDragging ? "border-blue-300 bg-blue-400/20" : "border-white/40 hover:border-white/60 hover:bg-white/10"}`}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center">
                      <Upload className="w-8 h-8 text-white" />
                    </div>
                    <div className="absolute -top-1 -right-1 w-7 h-7 bg-blue-400 rounded-full flex items-center justify-center">
                      <Sparkles className="w-4 h-4 text-white" />
                    </div>
                  </div>
                  {file ? (
                    <div className="flex items-center gap-2 bg-white/20 px-4 py-2 rounded-lg">
                      <FileText className="w-5 h-5 text-blue-200" />
                      <span className="text-white font-medium text-sm">
                        {file.name}
                      </span>
                    </div>
                  ) : (
                    <>
                      <p className="text-white font-semibold">
                        Drop prospektus PDF di sini
                      </p>
                      <p className="text-blue-200 text-sm">
                        atau klik untuk pilih file
                      </p>
                    </>
                  )}
                  <p className="text-blue-300 text-xs">Powered by Groq AI</p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={(e) => handleFile(e.target.files[0])}
                  className="hidden"
                />
              </div>
              {status && (
                <p className="text-blue-200 text-sm text-center mt-3">
                  {status}
                </p>
              )}
              <button
                onClick={handleAnalyze}
                disabled={!file || loading}
                className="w-full mt-4 flex items-center justify-center gap-2 bg-white text-blue-700 py-3 rounded-xl font-bold hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" /> Menganalisis...
                  </>
                ) : (
                  <>
                    <BarChart3 className="w-5 h-5" /> Analisis Sekarang
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-8">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            {
              icon: <Building2 className="w-5 h-5 text-blue-600" />,
              bg: "bg-blue-100",
              label: "Total IPO",
              value: "847",
            },
            {
              icon: <TrendingUp className="w-5 h-5 text-green-600" />,
              bg: "bg-green-100",
              label: "Rata-rata Return",
              value: "+18.5%",
            },
            {
              icon: <DollarSign className="w-5 h-5 text-purple-600" />,
              bg: "bg-purple-100",
              label: "Total Market Cap",
              value: "Rp 74.9T",
            },
            {
              icon: <Users className="w-5 h-5 text-orange-600" />,
              bg: "bg-orange-100",
              label: "Total Karyawan",
              value: "27.3K",
            },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-xl shadow-lg p-5">
              <div className="flex items-center gap-3 mb-2">
                <div
                  className={`w-10 h-10 ${s.bg} rounded-lg flex items-center justify-center`}
                >
                  {s.icon}
                </div>
                <span className="text-gray-600 text-sm">{s.label}</span>
              </div>
              <div className="text-2xl font-bold text-gray-900">{s.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Featured IPOs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h2 className="text-3xl font-bold text-gray-900 mb-2">
              IPO Unggulan
            </h2>
            <p className="text-gray-600">
              Perusahaan yang baru listing dengan performa terbaik
            </p>
          </div>
          <Link
            to="/ipo-listings"
            className="hidden sm:flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium"
          >
            Lihat Semua <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {featuredIPOs.map((ipo) => {
            const perf = (
              ((ipo.currentPrice - ipo.ipoPrice) / ipo.ipoPrice) *
              100
            ).toFixed(2);
            const isPos = parseFloat(perf) >= 0;
            return (
              <Link
                key={ipo.id}
                to="/ipo-listings"
                className="bg-white rounded-xl shadow-md hover:shadow-xl transition-shadow p-6 border border-gray-200"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="text-lg font-bold text-gray-900 mb-1">
                      {ipo.name}
                    </h3>
                    <p className="text-gray-500 text-sm">{ipo.ticker}</p>
                  </div>
                  <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs font-medium rounded-full">
                    {ipo.sector}
                  </span>
                </div>
                <div className="space-y-2 mb-4 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Harga IPO</span>
                    <span className="font-medium">Rp{ipo.ipoPrice}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Harga Saat Ini</span>
                    <span className="font-medium">Rp{ipo.currentPrice}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Market Cap</span>
                    <span className="font-medium">{ipo.marketCap}</span>
                  </div>
                </div>
                <div className="pt-3 border-t border-gray-100 flex items-center justify-between">
                  <span className="text-gray-500 text-sm">Performa</span>
                  <span
                    className={`flex items-center gap-1 font-semibold text-sm ${isPos ? "text-green-600" : "text-red-600"}`}
                  >
                    <TrendingUp
                      className={`w-4 h-4 ${isPos ? "" : "rotate-180"}`}
                    />
                    {isPos ? "+" : ""}
                    {perf}%
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Upcoming */}
      <div className="bg-gray-100 py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-gray-900 mb-2">
              IPO Mendatang
            </h2>
            <p className="text-gray-600">
              Perusahaan yang akan segera melantai di bursa
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {upcomingIPOs.map((ipo) => (
              <Link
                key={ipo.id}
                to="/ipo-listings"
                className="bg-white rounded-xl shadow-md hover:shadow-xl transition-shadow p-6 border border-gray-200"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h3 className="text-xl font-bold text-gray-900 mb-1">
                      {ipo.name}
                    </h3>
                    <p className="text-gray-500 mb-2 text-sm">{ipo.ticker}</p>
                    <p className="text-gray-700 text-sm line-clamp-2">
                      {ipo.description}
                    </p>
                  </div>
                  <span className="px-3 py-1 bg-orange-100 text-orange-700 text-xs font-medium rounded-full whitespace-nowrap ml-4">
                    Upcoming
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
                  <div>
                    <span className="text-gray-500 block mb-1 text-xs">
                      Tanggal IPO
                    </span>
                    <span className="font-medium">
                      {new Date(ipo.ipoDate).toLocaleDateString("id-ID")}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500 block mb-1 text-xs">
                      Harga IPO
                    </span>
                    <span className="font-medium">Rp{ipo.ipoPrice}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block mb-1 text-xs">
                      Sektor
                    </span>
                    <span className="font-medium">{ipo.sector}</span>
                  </div>
                  <div>
                    <span className="text-gray-500 block mb-1 text-xs">
                      Est. Market Cap
                    </span>
                    <span className="font-medium">{ipo.marketCap}</span>
                  </div>
                </div>
                <div className="pt-3 border-t border-gray-100 flex items-center justify-between">
                  <span className="text-blue-600 flex items-center gap-2 text-sm font-medium">
                    <BarChart3 className="w-4 h-4" />
                    Lihat Analisis
                  </span>
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="bg-gradient-to-r from-blue-600 to-blue-800 rounded-2xl p-12 text-center text-white">
          <h2 className="text-3xl font-bold mb-4">
            Siap Analisis IPO Sekarang?
          </h2>
          <p className="text-xl text-blue-100 mb-8 max-w-2xl mx-auto">
            Upload prospektus PDF dan dapatkan analisis lengkap dalam hitungan
            detik.
          </p>
          <a
            href="#upload"
            className="inline-flex items-center gap-2 bg-white text-blue-700 px-8 py-3 rounded-lg hover:bg-blue-50 transition-colors font-bold"
          >
            <Upload className="w-5 h-5" /> Upload Prospektus
          </a>
        </div>
      </div>
    </div>
  );
}
