import fitz
import os

def extract_text_from_pdf(file_path: str) -> dict:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File tidak ditemukan: {file_path}")

    doc = fitz.open(file_path)
    page_count = len(doc)
    full_text = []

    for page_num in range(page_count):
        page = doc.load_page(page_num)
        text = page.get_text()
        if text.strip():
            full_text.append(text)

    doc.close()

    combined_text = '\n'.join(full_text)

    # Ambil bagian awal (info umum) + bagian tengah (keuangan)
    total = len(combined_text)
    awal = combined_text[:20000]
    tengah_start = total // 3
    tengah = combined_text[tengah_start:tengah_start + 20000]

    smart_text = awal + "\n\n---LANJUTAN---\n\n" + tengah

    return {
        'text': smart_text,
        'page_count': page_count,
        'char_count': len(combined_text)
    }