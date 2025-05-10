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
        # After OCR, trigger LLM analysis
        analyze_legal_document.delay(txt_path)
    except Exception as e:
        print(f"OCR failed for {pdf_path}: {e}")
    return txt_path

@celery_app.task
def analyze_legal_document(txt_path):
    """
    Simulate calling Gemini/LLM to analyze the legal document text.
    """
    try:
        with open(txt_path, 'r') as f:
            text = f.read()
        # Simulate LLM response
        # In real use, call Gemini API here
        result = {
            'document_type': 'Motion',
            'case_number': '2024-CV-12345',
            'court': 'Superior Court',
            'parties': ['John Doe', 'Jane Smith'],
            'event_dates': ['2024-06-01T10:00:00'],
            'raw_excerpt': text[:200]
        }
        print(f"LLM analysis for {txt_path}: {result}")
        # TODO: Save result to DB or file for dashboard use
        return result
    except Exception as e:
        print(f"LLM analysis failed for {txt_path}: {e}")
        return None 