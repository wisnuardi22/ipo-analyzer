from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
from services.pdf_extractor import extract_text_from_pdf
import os
import shutil
import uuid

router = APIRouter(prefix="/api", tags=["upload"])
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diizinkan")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    pdf_data = extract_text_from_pdf(file_path)

    analysis = Analysis(
        company_name=file.filename.replace(".pdf", ""),
        file_name=file.filename,
        raw_text=pdf_data["text"]
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    return {
        "analysis_id": analysis.id,
        "company_name": analysis.company_name,
        "page_count": pdf_data["page_count"],
        "message": "PDF berhasil diupload dan diproses"
    }

@router.get("/analyses")
def get_all_analyses(db: Session = Depends(get_db)):
    return db.query(Analysis).all()