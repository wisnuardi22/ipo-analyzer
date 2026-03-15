from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.gemini_service import analyze_prospectus
import json

router = APIRouter(prefix="/api", tags=["analyze"])

@router.post("/analyze/{analysis_id}")
def run_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    try:
        result = analyze_prospectus(analysis.raw_text)

        analysis.company_name = result.get("company_name", analysis.company_name)
        analysis.summary = result.get("summary", "")
        analysis.risks = json.dumps(result.get("risks", []))
        analysis.benefits = json.dumps(result.get("benefits", []))
        analysis.financial_data = json.dumps(result.get("financial", {}))

        # Simpan semua data IPO termasuk ticker dan kpi
        analysis.ipo_details = json.dumps({
            "ticker": result.get("ticker", ""),
            "sector": result.get("sector", ""),
            "ipo_date": result.get("ipo_date", ""),
            "share_price": result.get("share_price", ""),
            "total_shares": result.get("total_shares", ""),
            "market_cap": result.get("market_cap", ""),
            "use_of_funds": result.get("use_of_funds", []),
            "kpi": result.get("kpi", {})
        })

        db.commit()
        db.refresh(analysis)

        return {
            "message": "Analisis selesai",
            "analysis_id": analysis_id,
            "company_name": analysis.company_name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal menganalisis: {str(e)}")


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")

    ipo_details = json.loads(analysis.ipo_details) if analysis.ipo_details else {}
    financial = json.loads(analysis.financial_data) if analysis.financial_data else {}

    return {
        "id": analysis.id,
        "company_name": analysis.company_name,
        "ticker": ipo_details.get("ticker", ""),
        "sector": ipo_details.get("sector", ""),
        "summary": analysis.summary,
        "risks": json.loads(analysis.risks) if analysis.risks else [],
        "benefits": json.loads(analysis.benefits) if analysis.benefits else [],
        "financial": financial,
        "ipo_details": ipo_details,
        "created_at": str(analysis.created_at)
    }