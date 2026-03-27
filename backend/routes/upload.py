from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
from database.db import get_db, Analysis
import logging
import io

router = APIRouter(prefix="/api", tags=["upload"])
logger = logging.getLogger(__name__)

MAX_PAGES = 300
MAX_TEXT  = 500_000


def extract_text_from_pdf(file_bytes: bytes) -> str:
    # PyPDF2 dulu - lebih ringan
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        total  = len(reader.pages)
        limit  = min(total, MAX_PAGES)
        pages  = []
        logger.info(f"PyPDF2: {total} halaman, proses {limit}")
        for i in range(limit):
            try:
                t = reader.pages[i].extract_text() or ""
                if t.strip():
                    pages.append(t)
            except Exception:
                pass
        result = "\n".join(pages)
        logger.info(f"PyPDF2: {len(result):,} karakter")
        if len(result) > 50_000:
            return result[:MAX_TEXT]
        logger.info("PyPDF2 kurang, coba pdfplumber")
    except Exception as e:
        logger.warning(f"PyPDF2 error: {e}")

    # pdfplumber - hanya halaman strategis
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            total   = len(pdf.pages)
            mid     = total // 2
            indices = list(range(min(80, total)))
            indices += list(range(max(0, mid - 30), min(total, mid + 30)))
            indices += list(range(max(0, total - 40), total))
            indices  = sorted(set(indices))[:MAX_PAGES]
            logger.info(f"pdfplumber: {total} hal, proses {len(indices)} strategis")
            for i in indices:
                try:
                    page = pdf.pages[i]
                    for tbl in (page.extract_tables() or []):
                        for row in tbl:
                            if row:
                                line = "\t".join(str(c or "").strip() for c in row)
                                if line.strip():
                                    parts.append(line)
                    t = page.extract_text(x_tolerance=3, y_tolerance=3)
                    if t:
                        parts.append(t)
                except Exception:
                    pass
        result = "\n".join(parts)
        logger.info(f"pdfplumber: {len(result):,} karakter")
        return result[:MAX_TEXT]
    except ImportError:
        logger.warning("pdfplumber tidak tersedia")
    except Exception as e:
        logger.error(f"pdfplumber error: {e}")

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
            detail="Gagal mengekstrak teks dari PDF. File mungkin terpassword atau corrupt."
        )

    logger.info(f"Teks diekstrak: {len(raw_text):,} karakter")

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