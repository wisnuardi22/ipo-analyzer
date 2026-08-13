import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getAnalysis } from "../services/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  Building2,
  Loader2,
  Download,
  ArrowRight,
  CheckCircle,
  ArrowLeft,
} from "lucide-react";

export default function Dashboard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAnalysis(id)
      .then(setData)
      .catch(() => setError("Gagal memuat data analisis"));
  }, [id]);

  if (error)
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 text-lg mb-4">{error}</p>
          <button
            onClick={() => navigate("/")}
            className="text-blue-600 hover:underline"
          >
            Kembali ke Home
          </button>
        </div>
      </div>
    );

  if (!data)
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2
            className="text-blue-600 animate-spin mx-auto mb-4"
            size={48}
          />
          <p className="text-gray-600">Memuat analisis...</p>
        </div>
      </div>
    );

  const riskColors = {
    High: "border-red-500 bg-red-50",
    Medium: "border-yellow-500 bg-yellow-50",
    Low: "border-green-500 bg-green-50",
  };
  const riskBadge = {
    High: "bg-red-500",
    Medium: "bg-yellow-500",
    Low: "bg-green-500",
  };

  const MiniChart = ({ chartData, color, label }) => (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 shadow-sm">
      <div className="mb-3">
        <span className="inline-block bg-gray-900 text-white text-xs font-bold px-3 py-1 rounded-full">
          {label}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={110}>
        <LineChart data={chartData || []}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="year" tick={{ fontSize: 10, fill: "#9ca3af" }} />
          <YAxis tick={{ fontSize: 9, fill: "#9ca3af" }} />
          <Tooltip
            contentStyle={{
              background: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: "8px",
              fontSize: "11px",
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2.5}
            dot={{ fill: color, r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate("/ipo-listings")}
                className="flex items-center gap-2 text-gray-500 hover:text-gray-800 transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
                  <Building2 className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-gray-900">
                    {data.company_name}
                  </h1>
                  <p className="text-gray-500 text-sm">
                    {data.ipo_details?.sector}
                  </p>
                </div>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => window.print()}
                className="flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                <Download className="w-4 h-4" /> Unduh PDF
              </button>
              <button
                onClick={() => navigate("/")}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                Analisa Lagi <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* About Company */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-gray-900 text-white px-4 py-2 rounded-full text-sm font-bold">
              About Company
            </div>
            <p className="text-gray-500 text-sm">
              Perusahaan, sejarah singkat, lokasi, dan visi misi
            </p>
          </div>
          <p className="text-gray-700 leading-relaxed">{data.summary}</p>
          <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-100">
            <div>
              <p className="text-xs text-gray-400 mb-1">Harga IPO</p>
              <p className="font-bold text-gray-900">
                {data.ipo_details?.share_price || "-"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Total Saham</p>
              <p className="font-bold text-gray-900">
                {data.ipo_details?.total_shares || "-"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Tanggal IPO</p>
              <p className="font-bold text-gray-900">
                {data.ipo_details?.ipo_date || "-"}
              </p>
            </div>
          </div>
        </div>

        {/* Financial */}
        <div>
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-gray-900 text-white px-4 py-2 rounded-full text-sm font-bold">
              Financial
            </div>
            <p className="text-gray-500 text-sm">
              Grafik finansial 4 tahun terakhir beserta pertumbuhannya
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MiniChart
              chartData={data.financial?.revenue}
              color="#2563eb"
              label="Revenue"
            />
            <MiniChart
              chartData={data.financial?.gross_margin}
              color="#7c3aed"
              label="Gross Margin"
            />
            <MiniChart
              chartData={data.financial?.operating_margin}
              color="#0891b2"
              label="Operating Margin"
            />
            <MiniChart
              chartData={data.financial?.ebitda_margin}
              color="#059669"
              label="EBITDA Margin"
            />
          </div>
        </div>

        {/* Use of Proceeds */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center gap-3 mb-5">
            <div className="bg-gray-900 text-white px-4 py-2 rounded-full text-sm font-bold">
              Use of Proceeds
            </div>
            <p className="text-gray-500 text-sm">
              Dana IPO digunakan untuk apa
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b-2 border-gray-100">
                  <th className="text-left text-gray-600 text-sm font-semibold py-3 pr-6">
                    Category
                  </th>
                  <th className="text-left text-gray-600 text-sm font-semibold py-3 pr-6">
                    Description
                  </th>
                  <th className="text-left text-gray-600 text-sm font-semibold py-3">
                    Allocation (%)
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.ipo_details?.use_of_funds?.length > 0 ? (
                  data.ipo_details.use_of_funds.map((item, i) => (
                    <tr
                      key={i}
                      className="border-b border-gray-50 hover:bg-gray-50"
                    >
                      <td className="py-4 pr-6 font-bold text-gray-900">
                        {item.category}
                      </td>
                      <td className="py-4 pr-6 text-gray-600 text-sm">
                        {item.description}
                      </td>
                      <td className="py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex-1 bg-gray-100 rounded-full h-2 max-w-[100px]">
                            <div
                              className="bg-blue-600 h-2 rounded-full"
                              style={{ width: `${item.allocation}%` }}
                            ></div>
                          </div>
                          <span className="text-blue-600 font-bold text-sm">
                            {item.allocation}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={3} className="py-6 text-center text-gray-400">
                      Data tidak tersedia
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Risk & Benefit */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="bg-gray-900 text-white px-4 py-2 rounded-full text-sm font-bold">
                Risk
              </div>
              <p className="text-gray-500 text-sm">
                Risiko ketika membeli saham
              </p>
            </div>
            <div className="space-y-3">
              {data.risks?.map((r, i) => (
                <div
                  key={i}
                  className={`border-l-4 rounded-xl p-4 ${riskColors[r.level] || "border-gray-400 bg-gray-50"}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full text-white font-bold ${riskBadge[r.level] || "bg-gray-500"}`}
                    >
                      {r.level}
                    </span>
                    <span className="font-semibold text-gray-900 text-sm">
                      {r.title}
                    </span>
                  </div>
                  <p className="text-gray-600 text-xs leading-relaxed">
                    {r.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="bg-gray-900 text-white px-4 py-2 rounded-full text-sm font-bold">
                Benefit
              </div>
              <p className="text-gray-500 text-sm">Keuntungan membeli saham</p>
            </div>
            <div className="space-y-3">
              {data.benefits?.map((b, i) => (
                <div
                  key={i}
                  className="bg-green-50 border border-green-200 rounded-xl p-4"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <CheckCircle className="w-4 h-4 text-green-600 shrink-0" />
                    <span className="font-semibold text-green-800 text-sm">
                      {b.title}
                    </span>
                  </div>
                  <p className="text-gray-600 text-xs leading-relaxed">
                    {b.description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
