from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
import logging
import io

router = APIRouter(prefix="/api", tags=["upload"])
logger = logging.getLogger(__name__)

MAX_TEXT = 400_000


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Ekstrak teks PDF menggunakan PyMuPDF (fitz) - cepat dan ringan."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        total = len(doc)
        logger.info(f"PyMuPDF: {total} halaman")

        parts = []
        for i in range(total):
            try:
                text = doc[i].get_text()
                if text and text.strip():
                    parts.append(text)
            except Exception:
                pass

        doc.close()
        result = "\n".join(parts)
        logger.info(f"PyMuPDF OK: {len(result):,} karakter")
        return result[:MAX_TEXT]

    except Exception as e:
        logger.error(f"PyMuPDF gagal: {e}")
        return ""


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima")

    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca file: {e}")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="File kosong")

    logger.info(f"Upload: {file.filename} ({len(file_bytes):,} bytes)")

    raw_text = extract_text_from_pdf(file_bytes)

    if not raw_text or len(raw_text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Gagal mengekstrak teks. File mungkin terpassword atau corrupt."
        )

    logger.info(f"Teks OK: {len(raw_text):,} karakter")

    try:
        analysis = Analysis(file_name=file.filename, raw_text=raw_text)
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        logger.info(f"Tersimpan id={analysis.id}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Gagal simpan database: {e}")

    return {
        "analysis_id": analysis.id,
        "file_name":   file.filename,
        "text_length": len(raw_text),
        "message":     "Upload berhasil",
    }