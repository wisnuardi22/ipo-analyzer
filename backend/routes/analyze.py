from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.gemini_service import analyze_prospectus, MODEL_FLASH, MODEL_PRO
from services.market_data import get_ticker_from_google, get_market_data
from pydantic import BaseModel
from typing import Optional
import json, re, logging

router = APIRouter(prefix="/api", tags=["analyze"])
logger = logging.getLogger(__name__)


class AnalyzeRequest(BaseModel):
    lang: Optional[str] = "ID"
    plan: Optional[str] = "basic"   # "basic" | "pro"


@router.post("/analyze/{analysis_id}")
def run_analysis(
    analysis_id: int,
    body: AnalyzeRequest = AnalyzeRequest(),
    db: Session = Depends(get_db),
):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    lang  = (body.lang or "ID").upper()
    plan  = (body.plan or "basic").lower()
    # Financial extraction: selalu Flash (hemat)
    # Qualitative: Flash untuk basic, Pro untuk pro
    model = MODEL_PRO if plan == "pro" else MODEL_FLASH

    logger.info(f"[ANALYZE] id={analysis_id} lang={lang} plan={plan} model={model}")

    # GUARD: Cek apakah sudah dianalisis dengan plan & lang yang sama
    if analysis.ipo_details:
        try:
            existing = json.loads(analysis.ipo_details)
            existing_plan = existing.get("plan","basic").lower()
            existing_lang = existing.get("lang","ID").upper()
            if existing_plan == plan and existing_lang == lang and analysis.summary:
                logger.info(f"[SKIP] Analisis sudah ada untuk id={analysis_id} plan={plan} lang={lang}, skip LLM call")
                return {
                    "message":      "Analisis sudah ada (cached)",
                    "analysis_id":  analysis_id,
                    "company_name": analysis.company_name,
                    "plan":         plan,
                    "model":        model,
                    "cached":       True,
                }
        except Exception:
            pass  # Jika parse gagal, lanjut re-analyze

    ticker = ""; market = {}; underwriter = {}
    risks = []; benefits = []
    overall_risk_level = "MEDIUM"; overall_risk_reason = ""

    try:
        result = analyze_prospectus(analysis.raw_text, lang=lang, model=model)

        fin = result.get("financial") or {}
        kpi = result.get("kpi") or {}
        logger.info(f"[DEBUG] company={result.get('company_name','')} years={fin.get('years',[])} rasio={len(fin.get('rasio_per_tahun', []))}")
        logger.info(f"[DEBUG] kpi={json.dumps(kpi, ensure_ascii=False)}")
        logger.info(f"[DEBUG] uof={len(result.get('use_of_funds',[]))} benefits={len(result.get('benefits',[]))}")

        analysis.company_name   = result.get("company_name") or analysis.company_name
        analysis.summary        = result.get("summary") or ""
        analysis.financial_data = json.dumps(fin)

        # Aman dari NoneType error
        overall_risk_level  = (result.get("overall_risk_level") or "MEDIUM").upper()
        overall_risk_reason = result.get("overall_risk_reason") or ""
        if overall_risk_level not in ["HIGH","MEDIUM","LOW"]:
            overall_risk_level = "MEDIUM"

        risks       = result.get("risks") or []
        benefits    = result.get("benefits") or []
        underwriter = result.get("underwriter") or {}

        if underwriter:
            rep = (underwriter.get("reputation") or "").lower()
            lead = underwriter.get("lead") or ""
            uw_type = underwriter.get("type") or ""
            others = underwriter.get("others") or []
            others_str = ", ".join(others) if others else ""
            is_good = any(w in rep for w in ["baik","besar","terpercaya","reputable","prominent","established","leading","trusted","experienced"])
            if is_good:
                if lang == "EN":
                    desc = f"This IPO is underwritten by {lead}"
                    if others_str: desc += f" and {others_str}"
                    desc += f" ({uw_type}). {underwriter.get('reputation','')}"
                    benefits.append({"title":"Backed by Reputable Underwriters","desc":desc})
                else:
                    desc = f"IPO ini dijamin oleh {lead}"
                    if others_str: desc += f" bersama {others_str}"
                    desc += f" ({uw_type}). {underwriter.get('reputation','')}"
                    benefits.append({"title":"Didukung Penjamin Emisi Terpercaya","desc":desc})

        analysis.risks    = json.dumps(risks)
        analysis.benefits = json.dumps(benefits)

        company_name  = result.get("company_name") or analysis.company_name
        # Mencegah NoneType Error saat strip()
        ticker_gemini = (result.get("ticker") or "").strip().upper()
        
        if ticker_gemini and re.match(r"^[A-Z]{2,6}$", ticker_gemini):
            ticker = ticker_gemini
            logger.info(f"Ticker dari dokumen: {ticker}")
        else:
            try:
                ticker = get_ticker_from_google(company_name, "")
                logger.info(f"Ticker search: {ticker}")
            except Exception as e:
                logger.warning(f"Ticker gagal: {e}"); ticker = ""

        if ticker:
            try: market = get_market_data(ticker)
            except Exception as e: logger.warning(f"Market data: {e}")

        kpi_data   = result.get("kpi") or {}
        market_cap = market.get("market_cap") or kpi_data.get("market_cap") or result.get("market_cap") or ""

        analysis.ipo_details = json.dumps({
            "ticker":              ticker or "",
            "sector":              result.get("sector") or "",
            "ipo_date":            result.get("ipo_date") or "",
            "share_price":         result.get("share_price") or "",
            "total_shares":        result.get("total_shares") or "",
            "market_cap":          market_cap,
            "current_price":       market.get("current_price") or "",
            "shares_outstanding":  market.get("shares_outstanding") or "",
            "use_of_funds":        result.get("use_of_funds") or [],
            "kpi":                 kpi_data,
            "underwriter":         underwriter,
            "overall_risk_level":  overall_risk_level,
            "overall_risk_reason": overall_risk_reason,
            "lang":                lang,
            "plan":                plan,
            "model":               model,
        })

        db.commit(); db.refresh(analysis)
        return {
            "message":      "Analisis selesai",
            "analysis_id":  analysis_id,
            "company_name": analysis.company_name,
            "plan":         plan,
            "model":        model,
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

    fin_stored = json.loads(analysis.financial_data) if analysis.financial_data else {}
    ipo_stored = json.loads(analysis.ipo_details)    if analysis.ipo_details    else {}
    logger.info(f"[GET] id={analysis_id} years={fin_stored.get('years',[])} kpi={ipo_stored.get('kpi',{})}")

    ipo      = ipo_stored; financial = fin_stored
    risks    = json.loads(analysis.risks)    if analysis.risks    else []
    benefits = json.loads(analysis.benefits) if analysis.benefits else []

    stored_level  = ipo.get("overall_risk_level","")
    stored_reason = ipo.get("overall_risk_reason","")
    lang          = ipo.get("lang","ID").upper(); is_en = lang == "EN"
    plan          = ipo.get("plan","basic")

    label_map = {
        "HIGH":   "High Risk"   if is_en else "Risiko Tinggi",
        "MEDIUM": "Medium Risk" if is_en else "Risiko Sedang",
        "LOW":    "Low Risk"    if is_en else "Risiko Rendah",
    }
    color_map = {"HIGH":"#EF4444","MEDIUM":"#F59E0B","LOW":"#22C55E"}

    if stored_level in label_map:
        risk_level = stored_level; risk_label = label_map[stored_level]; risk_color = color_map[stored_level]
    else:
        risk_level, risk_label, risk_color = _resolve_overall_risk(risks, is_en)

    return {
        "id":                  analysis.id,
        "company_name":        analysis.company_name,
        "created_at":          str(analysis.created_at),
        "lang":                lang,
        "plan":                plan,
        "ticker":              ipo.get("ticker",""),
        "sector":              ipo.get("sector",""),
        "ipo_date":            ipo.get("ipo_date",""),
        "share_price":         ipo.get("share_price",""),
        "current_price":       ipo.get("current_price",""),
        "total_shares":        ipo.get("total_shares",""),
        "shares_outstanding":  ipo.get("shares_outstanding",""),
        "market_cap":          ipo.get("market_cap",""),
        "summary":             analysis.summary,
        "financial":           financial,
        "use_of_funds":        ipo.get("use_of_funds",[]),
        "kpi":                 ipo.get("kpi",{}),
        "underwriter":         ipo.get("underwriter",{}),
        "risk_level":          risk_level,
        "risk_label":          risk_label,
        "risk_color":          risk_color,
        "risk_reason":         stored_reason,
        "risks":               risks,
        "benefits":            benefits,
        "ipo_details":         ipo,
    }


def _resolve_overall_risk(risks, is_en=False):
    p = {"high":3,"medium":2,"low":1}; highest = 0
    for r in risks:
        highest = max(highest, p.get(str(r.get("level","")).lower(), 0))
    if highest>=3: return "HIGH",  ("High Risk"   if is_en else "Risiko Tinggi"),  "#EF4444"
    elif highest==2: return "MEDIUM",("Medium Risk" if is_en else "Risiko Sedang"), "#F59E0B"
    else: return "LOW", ("Low Risk" if is_en else "Risiko Rendah"), "#22C55E"