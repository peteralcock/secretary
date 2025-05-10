from celery import Celery
import subprocess
import os

# Configure Celery to use Redis as the broker
celery_app = Celery('paralegal', broker='redis://redis:6379/0')

@celery_app.task
def ocr_pdf(pdf_path):
    """
    Run ocrmypdf on the given PDF and save the extracted text to a .txt file.
    """
    base, _ = os.path.splitext(pdf_path)
    txt_path = base + '.txt'
    try:
        # Run ocrmypdf with --sidecar to extract text
        subprocess.run([
            'ocrmypdf', '--sidecar', txt_path, pdf_path, pdf_path
        ], check=True)
        print(f"OCR complete for {pdf_path}, text saved to {txt_path}")
    except Exception as e:
        print(f"OCR failed for {pdf_path}: {e}")
    return txt_path 