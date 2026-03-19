from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.gemini_service import analyze_prospectus
from services.market_data import get_ticker_from_google, get_market_data
import json
import logging

router = APIRouter(prefix="/api", tags=["analyze"])
logger = logging.getLogger(__name__)


@router.post("/analyze/{analysis_id}")
def run_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    try:
        # ── 1. Analisis prospektus via Gemini ────────────────────────────
        result = analyze_prospectus(analysis.raw_text)

        analysis.company_name   = result.get("company_name", analysis.company_name)
        analysis.summary        = result.get("summary", "")
        analysis.financial_data = json.dumps(result.get("financial", {}))

        # ── 2. Ambil overall risk level dari Gemini ───────────────────────
        overall_risk_level  = result.get("overall_risk_level", "").upper()  # HIGH/MEDIUM/LOW
        overall_risk_reason = result.get("overall_risk_reason", "")

        # Normalisasi
        if overall_risk_level not in ["HIGH", "MEDIUM", "LOW"]:
            overall_risk_level = "MEDIUM"

        # ── 3. Filter risks — hanya tampilkan yang sesuai overall level ───
        all_risks = result.get("risks", [])
        # Risks dari Gemini sudah difilter sesuai level, tapi kita pastikan lagi
        level_map = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
        target_level = level_map.get(overall_risk_level, "Medium")
        risks = [r for r in all_risks if str(r.get("level","")).strip().capitalize() == target_level]
        # Jika filter kosong, pakai semua risks dari Gemini
        if not risks:
            risks = all_risks

        benefits    = result.get("benefits", [])
        underwriter = result.get("underwriter", {})

        if underwriter:
            reputation = underwriter.get("reputation", "")
            lead       = underwriter.get("lead", "")
            uw_type    = underwriter.get("type", "")
            others     = underwriter.get("others", [])
            others_str = ", ".join(others) if others else ""

            rep_lower = reputation.lower()
            is_good   = any(w in rep_lower for w in [
                "baik", "besar", "terpercaya", "terkemuka",
                "terbesar", "sangat", "ternama", "top"
            ])

            if is_good:
                desc = f"IPO ini dijamin oleh {lead}"
                if others_str:
                    desc += f" bersama {others_str}"
                desc += f" ({uw_type}). {reputation}"
                benefits.append({
                    "title": "Didukung Penjamin Emisi Terpercaya",
                    "desc":  desc
                })
            else:
                desc = f"Penjamin emisi {lead} memiliki reputasi yang perlu diperhatikan. {reputation}"
                risks.append({
                    "level": "Medium",
                    "title": "Risiko Reputasi Penjamin Emisi",
                    "desc":  desc
                })

        analysis.risks    = json.dumps(risks)
        analysis.benefits = json.dumps(benefits)

        # ── 3. Cari ticker via IDX/Yahoo Finance (bukan dari Gemini) ─────
        company_name = result.get("company_name", analysis.company_name)

        try:
            # Langsung cari berdasarkan nama perusahaan, ignore ticker dari Gemini
            ticker = get_ticker_from_google(company_name, "")
            logger.info(f"Ticker ditemukan via search: {ticker} untuk {company_name}")
        except Exception as e:
            logger.warning(f"Gagal cari ticker: {e}")
            ticker = ""

        # ── 4. Ambil harga live dari Google Finance ───────────────────────
        market = {}
        if ticker:
            try:
                market = get_market_data(ticker)
            except Exception as e:
                logger.warning(f"Gagal ambil market data: {e}")

        # ── 5. Simpan ipo_details ─────────────────────────────────────────
        analysis.ipo_details = json.dumps({
            "ticker":               ticker or "",
            "sector":               result.get("sector", ""),
            "ipo_date":             result.get("ipo_date", ""),
            "share_price":          result.get("share_price", ""),
            "total_shares":         result.get("total_shares", ""),
            "market_cap":           market.get("market_cap") or result.get("market_cap", ""),
            "current_price":        market.get("current_price", ""),
            "shares_outstanding":   market.get("shares_outstanding", ""),
            "use_of_funds":         result.get("use_of_funds", []),
            "kpi":                  result.get("kpi", {}),
            "underwriter":          underwriter,
            "overall_risk_level":   overall_risk_level,
            "overall_risk_reason":  overall_risk_reason,
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

    ipo       = json.loads(analysis.ipo_details)    if analysis.ipo_details    else {}
    financial = json.loads(analysis.financial_data) if analysis.financial_data else {}
    risks     = json.loads(analysis.risks)          if analysis.risks          else []
    benefits  = json.loads(analysis.benefits)       if analysis.benefits       else []

    # Ambil overall risk dari Gemini (lebih akurat) atau hitung dari risks
    stored_level  = ipo.get("overall_risk_level", "")
    stored_reason = ipo.get("overall_risk_reason", "")

    if stored_level in ["HIGH", "MEDIUM", "LOW"]:
        risk_level = stored_level
        risk_label = {"HIGH": "Risiko Tinggi", "MEDIUM": "Risiko Sedang", "LOW": "Risiko Rendah"}[stored_level]
        risk_color = {"HIGH": "#EF4444", "MEDIUM": "#F59E0B", "LOW": "#22C55E"}[stored_level]
    else:
        risk_level, risk_label, risk_color = _resolve_overall_risk(risks)

    return {
        "id":                   analysis.id,
        "company_name":         analysis.company_name,
        "created_at":           str(analysis.created_at),
        "ticker":               ipo.get("ticker", ""),
        "sector":               ipo.get("sector", ""),
        "ipo_date":             ipo.get("ipo_date", ""),
        "share_price":          ipo.get("share_price", ""),
        "current_price":        ipo.get("current_price", ""),
        "total_shares":         ipo.get("total_shares", ""),
        "shares_outstanding":   ipo.get("shares_outstanding", ""),
        "market_cap":           ipo.get("market_cap", ""),
        "summary":              analysis.summary,
        "financial":            financial,
        "use_of_funds":         ipo.get("use_of_funds", []),
        "kpi":                  ipo.get("kpi", {}),
        "underwriter":          ipo.get("underwriter", {}),
        "risk_level":           risk_level,
        "risk_label":           risk_label,
        "risk_color":           risk_color,
        "risk_reason":          stored_reason,
        "risks":                risks,
        "benefits":             benefits,
        "ipo_details":          ipo,
    }


def _resolve_overall_risk(risks: list) -> tuple[str, str, str]:
    priority = {"high": 3, "medium": 2, "low": 1}
    highest  = 0
    for r in risks:
        lvl     = str(r.get("level", "")).lower()
        highest = max(highest, priority.get(lvl, 0))
    if highest >= 3:
        return "HIGH",   "Risiko Tinggi", "#EF4444"
    elif highest == 2:
        return "MEDIUM", "Risiko Sedang", "#F59E0B"
    else:
        return "LOW",    "Risiko Rendah", "#22C55E"