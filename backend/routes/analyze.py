from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.gemini_service import analyze_prospectus
from services.market_data import get_ticker_from_google, get_market_data
import json

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze/{analysis_id}")
def run_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    try:
        # ── 1. Analisis prospektus via Groq ───────────────────────────────
        result = analyze_prospectus(analysis.raw_text)

        analysis.company_name   = result.get("company_name", analysis.company_name)
        analysis.summary        = result.get("summary", "")
        analysis.risks          = json.dumps(result.get("risks", []))
        analysis.benefits       = json.dumps(result.get("benefits", []))
        analysis.financial_data = json.dumps(result.get("financial", {}))

        # ── 2. Cari ticker aktual via Google Search ────────────────────────
        # Groq sudah ekstrak ticker dari prospektus, tapi bisa saja salah.
        # Google Search dipakai untuk verifikasi & ambil ticker yang benar.
        ticker_from_prospectus = result.get("ticker", "")
        company_name           = result.get("company_name", analysis.company_name)
        ticker = get_ticker_from_google(company_name, ticker_from_prospectus)

        # ── 3. Ambil data live dari Google Finance ─────────────────────────
        market = get_market_data(ticker) if ticker else {}

        # ── 4. Simpan ipo_details ──────────────────────────────────────────
        analysis.ipo_details = json.dumps({
            "ticker":             ticker or ticker_from_prospectus,
            "sector":             result.get("sector", ""),
            "ipo_date":           result.get("ipo_date", ""),
            "share_price":        result.get("share_price", ""),
            "total_shares":       result.get("total_shares", ""),
            # market_cap & current_price: prioritaskan data live, fallback ke prospektus
            "market_cap":         market.get("market_cap") or result.get("market_cap", ""),
            "current_price":      market.get("current_price", ""),
            "shares_outstanding": market.get("shares_outstanding", ""),
            "use_of_funds":       result.get("use_of_funds", []),
            "kpi":                result.get("kpi", {}),
        })

        db.commit()
        db.refresh(analysis)

        return {
            "message":      "Analisis selesai",
            "analysis_id":  analysis_id,
            "company_name": analysis.company_name,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal menganalisis: {str(e)}")


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    ipo      = json.loads(analysis.ipo_details)    if analysis.ipo_details    else {}
    financial = json.loads(analysis.financial_data) if analysis.financial_data else {}
    risks     = json.loads(analysis.risks)          if analysis.risks          else []
    benefits  = json.loads(analysis.benefits)       if analysis.benefits       else []

    # ── Tentukan satu level risiko dari daftar risks ───────────────────────
    # Groq sudah mengembalikan tiap risiko dengan field "level" (High/Medium/Low).
    # Kita ambil level TERTINGGI sebagai overall risk level.
    risk_level, risk_label, risk_color = _resolve_overall_risk(risks)

    return {
        "id":           analysis.id,
        "company_name": analysis.company_name,
        "created_at":   str(analysis.created_at),

        # ── IPO Overview ─────────────────────────────────────────────────
        "ticker":       ipo.get("ticker", ""),
        "sector":       ipo.get("sector", ""),
        "ipo_date":     ipo.get("ipo_date", ""),

        # ── Harga & Market ────────────────────────────────────────────────
        "share_price":        ipo.get("share_price", ""),       # harga penawaran awal dari prospektus
        "current_price":      ipo.get("current_price", ""),     # harga live dari Google Finance
        "total_shares":       ipo.get("total_shares", ""),      # lembar saham dari prospektus
        "shares_outstanding": ipo.get("shares_outstanding", ""),# dari Google Finance
        "market_cap":         ipo.get("market_cap", ""),        # live atau fallback prospektus

        # ── Konten Analisis ───────────────────────────────────────────────
        "summary":      analysis.summary,
        "financial":    financial,
        "use_of_funds": ipo.get("use_of_funds", []),
        "kpi":          ipo.get("kpi", {}),

        # ── Risk: satu level keseluruhan ──────────────────────────────────
        "risk_level":  risk_level,   # "HIGH" | "MEDIUM" | "LOW"
        "risk_label":  risk_label,   # "Risiko Tinggi" | "Risiko Sedang" | "Risiko Rendah"
        "risk_color":  risk_color,   # hex color untuk badge UI
        "risks":       risks,        # detail lengkap tetap dikirim untuk tooltip/detail view

        "benefits": benefits,
    }


# ── Helper ─────────────────────────────────────────────────────────────────────

def _resolve_overall_risk(risks: list) -> tuple[str, str, str]:
    """
    Dari daftar risiko yang dikembalikan Groq (masing-masing punya field 'level'),
    ambil level TERTINGGI sebagai overall risk perusahaan.

    Priority: High > Medium > Low
    """
    priority = {"high": 3, "medium": 2, "low": 1}
    highest = 0

    for r in risks:
        lvl = str(r.get("level", "")).lower()
        highest = max(highest, priority.get(lvl, 0))

    if highest >= 3:
        return "HIGH", "Risiko Tinggi", "#EF4444"
    elif highest == 2:
        return "MEDIUM", "Risiko Sedang", "#F59E0B"
    else:
        return "LOW", "Risiko Rendah", "#22C55E"