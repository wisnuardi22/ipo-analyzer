from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
import logging
import io

router = APIRouter(prefix="/api", tags=["upload"])
logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Ekstrak teks dari PDF menggunakan pdfplumber (primer) atau PyPDF2 (fallback).
    pdfplumber lebih akurat untuk tabel keuangan.
    """
    # Coba pdfplumber dulu
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            logger.info(f"pdfplumber: membaca {len(pdf.pages)} halaman")
            for page_num, page in enumerate(pdf.pages):
                # Ekstrak tabel (untuk data keuangan)
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            if row:
                                cells = [str(c or "").strip() for c in row]
                                line = "\t".join(cells)
                                if any(c.strip() for c in cells):
                                    parts.append(line)
                # Ekstrak teks biasa
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text:
                    parts.append(text)

        result = "\n".join(parts)
        logger.info(f"pdfplumber: {len(result):,} karakter berhasil diekstrak")
        return result

    except ImportError:
        logger.warning("pdfplumber tidak tersedia, fallback ke PyPDF2")
    except Exception as e:
        logger.warning(f"pdfplumber error: {e}, fallback ke PyPDF2")

    # Fallback PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            try:
                text = page.extract_text()
                if text:
                    pages.append(text)
            except Exception:
                pass
        result = "\n".join(pages)
        logger.info(f"PyPDF2: {len(result):,} karakter berhasil diekstrak")
        return result

    except Exception as e:
        logger.error(f"PyPDF2 juga gagal: {e}")
        return ""


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validasi tipe file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima")

    # Baca bytes
    try:
        file_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membaca file: {e}")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="File kosong")

    logger.info(f"Upload: {file.filename} ({len(file_bytes):,} bytes)")

    # Ekstrak teks dari PDF
    raw_text = extract_text_from_pdf(file_bytes)

    if not raw_text or len(raw_text.strip()) < 100:
        logger.error(f"Ekstraksi teks gagal atau terlalu pendek: {len(raw_text)} karakter")
        raise HTTPException(
            status_code=422,
            detail="Gagal mengekstrak teks dari PDF. Pastikan file tidak terpassword atau corrupt."
        )

    logger.info(f"Teks berhasil diekstrak: {len(raw_text):,} karakter")

    # Simpan ke database
    try:
        analysis = Analysis(
            file_name=file.filename,
            raw_text=raw_text,
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        logger.info(f"Analysis tersimpan dengan id={analysis.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"DB error: {e}")
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan ke database: {e}")

    return {
        "analysis_id": analysis.id,
        "file_name": file.filename,
        "text_length": len(raw_text),
        "message": "Upload berhasil",
    }