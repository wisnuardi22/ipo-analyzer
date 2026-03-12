import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Filter,
  TrendingUp,
  Upload,
  FileText,
  Sparkles,
  Loader2,
  BarChart3,
  ArrowRight,
} from "lucide-react";
import { uploadPDF, runAnalysis } from "../services/api";

const ipoList = [
  {
    id: "rlco",
    name: "PT Abadi Lestari Indonesia Tbk",
    ticker: "RLCO",
    sector: "Kesehatan",
    ipoPrice: 168,
    currentPrice: 172,
    marketCap: "Rp 539M",
    status: "trading",
    date: "2025-12-08",
  },
  {
    id: "tekn",
    name: "PT Teknologi Nusantara Tbk",
    ticker: "TEKN",
    sector: "Teknologi",
    ipoPrice: 250,
    currentPrice: 310,
    marketCap: "Rp 1.2T",
    status: "trading",
    date: "2025-11-15",
  },
  {
    id: "ehij",
    name: "PT Energi Hijau Indonesia Tbk",
    ticker: "EHIJ",
    sector: "Energi",
    ipoPrice: 500,
    currentPrice: 480,
    marketCap: "Rp 2.4T",
    status: "trading",
    date: "2025-10-20",
  },
  {
    id: "dfin",
    name: "PT Digital Finansial Tbk",
    ticker: "DFIN",
    sector: "Keuangan",
    ipoPrice: 300,
    currentPrice: 300,
    marketCap: "Rp 900M",
    status: "upcoming",
    date: "2026-04-15",
  },
  {
    id: "agro",
    name: "PT Agro Makmur Tbk",
    ticker: "AGRO",
    sector: "Pertanian",
    ipoPrice: 180,
    currentPrice: 180,
    marketCap: "Rp 540M",
    status: "upcoming",
    date: "2026-05-01",
  },
  {
    id: "mfin",
    name: "PT Maju Finansial Tbk",
    ticker: "MFIN",
    sector: "Keuangan",
    ipoPrice: 420,
    currentPrice: 390,
    marketCap: "Rp 1.6T",
    status: "trading",
    date: "2025-09-10",
  },
];

export default function IPOListings() {
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef();
  const navigate = useNavigate();

  const sectors = ["All", ...Array.from(new Set(ipoList.map((i) => i.sector)))];
  const filtered = ipoList.filter((i) => {
    const matchSearch =
      i.name.toLowerCase().includes(search.toLowerCase()) ||
      i.ticker.toLowerCase().includes(search.toLowerCase());
    const matchSector = sector === "All" || i.sector === sector;
    const matchStatus = statusFilter === "All" || i.status === statusFilter;
    return matchSearch && matchSector && matchStatus;
  });

  const handleFile = (f) => {
    if (f && f.type === "application/pdf") setFile(f);
  };

  const handleAnalyze = async () => {
    if (!file) return;
    setLoading(true);
    try {
      setUploadStatus("Mengupload PDF...");
      const res = await uploadPDF(file);
      setUploadStatus("Menganalisis dengan AI...");
      await runAnalysis(res.analysis_id);
      navigate(`/dashboard/${res.analysis_id}`);
    } catch (e) {
      setUploadStatus("Error: " + (e.response?.data?.detail || e.message));
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            IPO Listings
          </h1>
          <p className="text-gray-600">
            Database lengkap IPO terkini dan yang akan datang di Indonesia
          </p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Upload Panel */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-2xl shadow-md border border-gray-200 p-6 sticky top-24">
              <h2 className="text-xl font-bold text-gray-900 mb-2 flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-blue-600" /> Analisis
                Prospektus
              </h2>
              <p className="text-gray-500 text-sm mb-4">
                Upload PDF prospektus untuk mendapatkan analisis AI mendalam
              </p>
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
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all mb-4 ${isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"}`}
              >
                <div className="flex flex-col items-center gap-3">
                  <div className="relative">
                    <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center">
                      <Upload className="w-7 h-7 text-blue-600" />
                    </div>
                    <div className="absolute -top-1 -right-1 w-6 h-6 bg-blue-500 rounded-full flex items-center justify-center">
                      <Sparkles className="w-3 h-3 text-white" />
                    </div>
                  </div>
                  {file ? (
                    <div className="flex items-center gap-2 bg-blue-50 px-3 py-2 rounded-lg">
                      <FileText className="w-4 h-4 text-blue-600" />
                      <span className="text-blue-800 font-medium text-xs truncate max-w-[160px]">
                        {file.name}
                      </span>
                    </div>
                  ) : (
                    <>
                      <p className="text-gray-700 font-semibold text-sm">
                        Drop PDF di sini
                      </p>
                      <p className="text-gray-400 text-xs">
                        atau klik untuk pilih file
                      </p>
                    </>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={(e) => handleFile(e.target.files[0])}
                  className="hidden"
                />
              </div>
              {uploadStatus && (
                <p
                  className={`text-sm text-center mb-3 ${uploadStatus.startsWith("Error") ? "text-red-500" : "text-blue-600"}`}
                >
                  {uploadStatus}
                </p>
              )}
              <button
                onClick={handleAnalyze}
                disabled={!file || loading}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-3 rounded-xl font-bold hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
              <p className="text-center text-xs text-gray-400 mt-3">
                Powered by Groq AI
              </p>
            </div>
          </div>

          {/* IPO List */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Cari nama atau kode saham..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="relative">
                  <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
                  <select
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    className="pl-9 pr-8 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white min-w-[140px]"
                  >
                    {sectors.map((s) => (
                      <option key={s} value={s}>
                        {s === "All" ? "Semua Sektor" : s}
                      </option>
                    ))}
                  </select>
                </div>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                >
                  <option value="All">Semua Status</option>
                  <option value="trading">Trading</option>
                  <option value="upcoming">Upcoming</option>
                </select>
              </div>
              <p className="mt-3 text-sm text-gray-500">
                Menampilkan {filtered.length} perusahaan
              </p>
            </div>

            <div className="space-y-4">
              {filtered.map((ipo) => {
                const perf = (
                  ((ipo.currentPrice - ipo.ipoPrice) / ipo.ipoPrice) *
                  100
                ).toFixed(2);
                const isPos = parseFloat(perf) >= 0;
                return (
                  <div
                    key={ipo.id}
                    className="bg-white rounded-xl shadow-sm hover:shadow-md transition-shadow p-5 border border-gray-200"
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="text-lg font-bold text-gray-900">
                          {ipo.name}
                        </h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-blue-600 font-semibold text-sm">
                            {ipo.ticker}
                          </span>
                          <span className="text-gray-300">•</span>
                          <span className="text-gray-500 text-sm">
                            {ipo.sector}
                          </span>
                        </div>
                      </div>
                      <span
                        className={`px-3 py-1 rounded-full text-xs font-medium ${ipo.status === "trading" ? "bg-green-100 text-green-700" : "bg-orange-100 text-orange-700"}`}
                      >
                        {ipo.status === "trading" ? "Trading" : "Upcoming"}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm mb-3">
                      <div>
                        <span className="text-gray-500 block text-xs mb-0.5">
                          Harga IPO
                        </span>
                        <span className="font-semibold">Rp{ipo.ipoPrice}</span>
                      </div>
                      <div>
                        <span className="text-gray-500 block text-xs mb-0.5">
                          Harga Saat Ini
                        </span>
                        <span className="font-semibold">
                          Rp{ipo.currentPrice}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500 block text-xs mb-0.5">
                          Market Cap
                        </span>
                        <span className="font-semibold">{ipo.marketCap}</span>
                      </div>
                      <div>
                        <span className="text-gray-500 block text-xs mb-0.5">
                          Tanggal
                        </span>
                        <span className="font-semibold">
                          {new Date(ipo.date).toLocaleDateString("id-ID")}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                      {ipo.status === "trading" ? (
                        <span
                          className={`flex items-center gap-1 font-semibold text-sm ${isPos ? "text-green-600" : "text-red-600"}`}
                        >
                          <TrendingUp
                            className={`w-4 h-4 ${isPos ? "" : "rotate-180"}`}
                          />
                          {isPos ? "+" : ""}
                          {perf}%
                        </span>
                      ) : (
                        <span className="text-orange-500 text-sm font-medium">
                          Segera Listing
                        </span>
                      )}
                      <button
                        onClick={() => fileInputRef.current.click()}
                        className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-sm font-medium"
                      >
                        <BarChart3 className="w-4 h-4" /> Analisis{" "}
                        <ArrowRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
