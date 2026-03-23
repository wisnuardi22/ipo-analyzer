from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.gemini_service import analyze_prospectus
from services.market_data import get_ticker_from_google, get_market_data
from pydantic import BaseModel
from typing import Optional
import json
import re
import logging

router = APIRouter(prefix="/api", tags=["analyze"])
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    lang: Optional[str] = "ID"


@router.post("/analyze/{analysis_id}")
def run_analysis(
    analysis_id: int,
    body: AnalyzeRequest = AnalyzeRequest(),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    lang = (body.lang or "ID").upper()

    # Cek apakah sudah pernah dianalisis dengan bahasa yang sama
    # Jika sudah ada dan bahasa sama, skip re-analyze (hemat waktu)
    if analysis.ipo_details:
        existing = json.loads(analysis.ipo_details)
        existing_lang = existing.get("lang", "").upper()
        if existing_lang == lang and analysis.summary:
            logger.info(f"Analisis id={analysis_id} lang={lang} sudah ada, skip re-analyze")
            return {
                "message":      "Analisis sudah ada",
                "analysis_id":  analysis_id,
                "company_name": analysis.company_name,
            }

    # Inisialisasi variabel defensif
    ticker      = ""
    market      = {}
    underwriter = {}
    risks       = []
    benefits    = []
    overall_risk_level  = "MEDIUM"
    overall_risk_reason = ""

    try:
        # ── 1. Analisis prospektus via Gemini ─────────────────────────
        result = analyze_prospectus(analysis.raw_text, lang=lang)

        analysis.company_name   = result.get("company_name", analysis.company_name)
        analysis.summary        = result.get("summary", "")
        analysis.financial_data = json.dumps(result.get("financial", {}))

        # ── 2. Risk level ──────────────────────────────────────────────
        overall_risk_level  = result.get("overall_risk_level", "").upper()
        overall_risk_reason = result.get("overall_risk_reason", "")
        if overall_risk_level not in ["HIGH", "MEDIUM", "LOW"]:
            overall_risk_level = "MEDIUM"

        # ── 3. Risks & Benefits ────────────────────────────────────────
        all_risks = result.get("risks", [])
        # Pakai semua risks dari Gemini (sudah difilter di prompt)
        risks    = all_risks
        benefits = result.get("benefits", [])
        underwriter = result.get("underwriter", {})

        # Tambahkan benefit/risk dari underwriter jika relevan
        if underwriter:
            reputation = underwriter.get("reputation", "")
            lead       = underwriter.get("lead", "")
            uw_type    = underwriter.get("type", "")
            others     = underwriter.get("others", [])
            others_str = ", ".join(others) if others else ""
            rep_lower  = reputation.lower()

            is_good = any(w in rep_lower for w in [
                "baik", "besar", "terpercaya", "terkemuka", "terbesar",
                "sangat", "ternama", "top", "reputable", "prominent",
                "established", "leading", "trusted",
            ])

            if is_good:
                if lang == "EN":
                    title = "Backed by Reputable Underwriters"
                    desc  = f"This IPO is underwritten by {lead}"
                    if others_str:
                        desc += f" and {others_str}"
                    desc += f" ({uw_type}). {reputation}"
                else:
                    title = "Didukung Penjamin Emisi Terpercaya"
                    desc  = f"IPO ini dijamin oleh {lead}"
                    if others_str:
                        desc += f" bersama {others_str}"
                    desc += f" ({uw_type}). {reputation}"
                benefits.append({"title": title, "desc": desc})

        analysis.risks    = json.dumps(risks)
        analysis.benefits = json.dumps(benefits)

        # ── 4. Ticker ──────────────────────────────────────────────────
        company_name       = result.get("company_name", analysis.company_name)
        ticker_from_gemini = result.get("ticker", "").strip().upper()

        if ticker_from_gemini and re.match(r"^[A-Z]{2,6}$", ticker_from_gemini):
            ticker = ticker_from_gemini
            logger.info(f"Ticker dari Gemini: {ticker}")
        else:
            try:
                ticker = get_ticker_from_google(company_name, "")
                logger.info(f"Ticker dari search: {ticker}")
            except Exception as e:
                logger.warning(f"Gagal cari ticker: {e}")
                ticker = ""

        # ── 5. Harga live ──────────────────────────────────────────────
        market = {}
        if ticker:
            try:
                market = get_market_data(ticker)
            except Exception as e:
                logger.warning(f"Gagal ambil market data: {e}")

        # ── 6. Simpan ipo_details ──────────────────────────────────────
        kpi_data   = result.get("kpi", {})
        market_cap = (market.get("market_cap") or
                      kpi_data.get("market_cap") or
                      result.get("market_cap", ""))

        analysis.ipo_details = json.dumps({
            "ticker":              ticker or "",
            "sector":              result.get("sector", ""),
            "ipo_date":            result.get("ipo_date", ""),
            "share_price":         result.get("share_price", ""),
            "total_shares":        result.get("total_shares", ""),
            "market_cap":          market_cap,
            "current_price":       market.get("current_price", ""),
            "shares_outstanding":  market.get("shares_outstanding", ""),
            "use_of_funds":        result.get("use_of_funds", []),
            "kpi":                 kpi_data,
            "underwriter":         underwriter,
            "overall_risk_level":  overall_risk_level,
            "overall_risk_reason": overall_risk_reason,
            "lang":                lang,
        })

        db.commit()
        db.refresh(analysis)

        return {
            "message":      "Analisis selesai",
            "analysis_id":  analysis_id,
            "company_name": analysis.company_name,
        }

    except Exception as e:
        import traceback
        logger.error(f"Error analyze {analysis_id}: {traceback.format_exc()}")
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

    stored_level  = ipo.get("overall_risk_level", "")
    stored_reason = ipo.get("overall_risk_reason", "")
    lang          = ipo.get("lang", "ID").upper()
    is_en         = lang == "EN"

    label_map = {
        "HIGH":   "High Risk"    if is_en else "Risiko Tinggi",
        "MEDIUM": "Medium Risk"  if is_en else "Risiko Sedang",
        "LOW":    "Low Risk"     if is_en else "Risiko Rendah",
    }
    color_map = {"HIGH": "#EF4444", "MEDIUM": "#F59E0B", "LOW": "#22C55E"}

    if stored_level in label_map:
        risk_level = stored_level
        risk_label = label_map[stored_level]
        risk_color = color_map[stored_level]
    else:
        risk_level, risk_label, risk_color = _resolve_overall_risk(risks, is_en)

    return {
        "id":                  analysis.id,
        "company_name":        analysis.company_name,
        "created_at":          str(analysis.created_at),
        "lang":                lang,
        "ticker":              ipo.get("ticker", ""),
        "sector":              ipo.get("sector", ""),
        "ipo_date":            ipo.get("ipo_date", ""),
        "share_price":         ipo.get("share_price", ""),
        "current_price":       ipo.get("current_price", ""),
        "total_shares":        ipo.get("total_shares", ""),
        "shares_outstanding":  ipo.get("shares_outstanding", ""),
        "market_cap":          ipo.get("market_cap", ""),
        "summary":             analysis.summary,
        "financial":           financial,
        "use_of_funds":        ipo.get("use_of_funds", []),
        "kpi":                 ipo.get("kpi", {}),
        "underwriter":         ipo.get("underwriter", {}),
        "risk_level":          risk_level,
        "risk_label":          risk_label,
        "risk_color":          risk_color,
        "risk_reason":         stored_reason,
        "risks":               risks,
        "benefits":            benefits,
        "ipo_details":         ipo,
    }


def _resolve_overall_risk(risks: list, is_en: bool = False) -> tuple:
    priority = {"high": 3, "medium": 2, "low": 1}
    highest  = 0
    for r in risks:
        lvl     = str(r.get("level", "")).lower()
        highest = max(highest, priority.get(lvl, 0))
    if highest >= 3:
        return "HIGH",   ("High Risk"   if is_en else "Risiko Tinggi"),   "#EF4444"
    elif highest == 2:
        return "MEDIUM", ("Medium Risk" if is_en else "Risiko Sedang"),   "#F59E0B"
    else:
        return "LOW",    ("Low Risk"    if is_en else "Risiko Rendah"),   "#22C55E"