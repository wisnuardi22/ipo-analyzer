import { Link, Outlet, useLocation } from "react-router-dom";
import { TrendingUp, BarChart3, Menu, X } from "lucide-react";
import { useState } from "react";

export default function Layout() {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const isActive = (path) => location.pathname === path;

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white shadow-sm sticky top-0 z-50 border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-2">
              <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-white" />
              </div>
              <span className="font-bold text-xl text-gray-900">
                IPO Insights
              </span>
            </Link>
            <div className="hidden md:flex items-center gap-8">
              <Link
                to="/"
                className={`font-medium transition-colors ${isActive("/") ? "text-blue-600" : "text-gray-600 hover:text-gray-900"}`}
              >
                Home
              </Link>
              <Link
                to="/ipo-listings"
                className={`font-medium transition-colors ${isActive("/ipo-listings") ? "text-blue-600" : "text-gray-600 hover:text-gray-900"}`}
              >
                IPO Listings
              </Link>
              <Link
                to="/ipo-listings"
                className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors font-medium"
              >
                <BarChart3 className="w-4 h-4" /> Analyze IPO
              </Link>
            </div>
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 rounded-lg hover:bg-gray-100"
            >
              {mobileMenuOpen ? (
                <X className="w-6 h-6 text-gray-600" />
              ) : (
                <Menu className="w-6 h-6 text-gray-600" />
              )}
            </button>
          </div>
        </div>
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-gray-200 bg-white px-4 py-3 space-y-3">
            <Link
              to="/"
              onClick={() => setMobileMenuOpen(false)}
              className={`block py-2 font-medium ${isActive("/") ? "text-blue-600" : "text-gray-600"}`}
            >
              Home
            </Link>
            <Link
              to="/ipo-listings"
              onClick={() => setMobileMenuOpen(false)}
              className={`block py-2 font-medium ${isActive("/ipo-listings") ? "text-blue-600" : "text-gray-600"}`}
            >
              IPO Listings
            </Link>
          </div>
        )}
      </nav>

      <main>
        <Outlet />
      </main>

      <footer className="bg-gray-900 text-gray-300 mt-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-white" />
                </div>
                <span className="font-bold text-white">IPO Insights</span>
              </div>
              <p className="text-sm">
                Platform analisis IPO terpercaya untuk investor Indonesia.
              </p>
            </div>
            <div>
              <h3 className="font-semibold text-white mb-4">Perusahaan</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a href="#" className="hover:text-white">
                    Tentang Kami
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Karir
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Blog
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-white mb-4">Sumber Daya</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a href="#" className="hover:text-white">
                    Kalender IPO
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Data Pasar
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Laporan Riset
                  </a>
                </li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-white mb-4">Legal</h3>
              <ul className="space-y-2 text-sm">
                <li>
                  <a href="#" className="hover:text-white">
                    Kebijakan Privasi
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Syarat Layanan
                  </a>
                </li>
                <li>
                  <a href="#" className="hover:text-white">
                    Disclaimer
                  </a>
                </li>
              </ul>
            </div>
          </div>
          <div className="border-t border-gray-800 mt-8 pt-8 text-sm text-center">
            <p>&copy; 2026 IPO Insights. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
