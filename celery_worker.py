from celery import Celery
import subprocess
import os
import json
from config import GEMINI_API_KEY
from langchain_google_genai import ChatGoogleGenerativeAI
from ics import Calendar, Event

# Configure Celery to use Redis as the broker
celery_app = Celery('paralegal', broker='redis://redis:6379/0')

try:
    from app import db, LegalDocumentResult, User
    from flask import Flask
    flask_app = Flask(__name__)
    flask_app.app_context().push()
except Exception:
    db = None
    LegalDocumentResult = None
    flask_app = None

@celery_app.task
def ocr_pdf(pdf_path, user_id=None):
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
        analyze_legal_document.delay(txt_path, user_id)
    except Exception as e:
        print(f"OCR failed for {pdf_path}: {e}")
    return txt_path

@celery_app.task
def analyze_legal_document(txt_path, user_id=None):
    """
    Call Gemini LLM to analyze the legal document text and extract metadata.
    """
    try:
        with open(txt_path, 'r') as f:
            text = f.read()
        # Build prompt for Gemini
        prompt = (
            "You are a legal document analysis assistant. "
            "Given the following legal document text, extract the following as JSON: "
            "document_type (e.g. Motion, Order, Notice, etc.), "
            "case_number, court, parties (list), event_dates (list of ISO 8601 datetimes for hearings, deadlines, etc.), "
            "and a raw_excerpt (first 200 chars of the text). "
            "If any field is missing, use null or an empty list.\n\n"
            f"Document Text:\n{text[:4000]}"
        )
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.2,
            google_api_key=GEMINI_API_KEY
        )
        response = model.invoke(prompt)
        # Try to parse the response as JSON
        import re
        import ast
        import logging
        # Extract JSON from response
        content = response.content if hasattr(response, "content") else str(response)
        # Try to find the first JSON object in the response
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            json_str = match.group(0)
            try:
                result = json.loads(json_str)
            except Exception:
                # Try ast.literal_eval as fallback
                try:
                    result = ast.literal_eval(json_str)
                except Exception as e:
                    logging.error(f"Failed to parse LLM JSON: {e}\nRaw: {json_str}")
                    return None
        else:
            logging.error(f"No JSON found in LLM response: {content}")
            return None
        # Add excerpt if not present
        if 'raw_excerpt' not in result:
            result['raw_excerpt'] = text[:200]
        # Add user_id to result
        result['user_id'] = user_id
        print(f"LLM analysis for {txt_path}: {result}")
        # Save result to /app/llm_results/
        results_dir = '/app/llm_results'
        os.makedirs(results_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(txt_path))[0]
        result_path = os.path.join(results_dir, f'{base}.json')
        with open(result_path, 'w') as out:
            json.dump(result, out)
        print(f"Saved LLM result to {result_path}")
        # Generate ICS files for each event date
        ics_dir = '/app/ics'
        os.makedirs(ics_dir, exist_ok=True)
        case_number = result.get('case_number', 'unknown')
        doc_type = result.get('document_type', 'event')
        for dt in result.get('event_dates', []):
            c = Calendar()
            e = Event()
            e.name = f"{doc_type} for Case {case_number}"
            e.begin = dt
            e.description = f"{doc_type} in {result.get('court', '')} for case {case_number}. Parties: {', '.join(result.get('parties', []))}"
            c.events.add(e)
            safe_case = case_number.replace('/', '_').replace(' ', '_')
            safe_doc = doc_type.replace(' ', '_')
            safe_dt = dt.replace(':', '').replace('-', '').replace('T', '_')
            ics_filename = f"{safe_case}_{safe_doc}_{safe_dt}"
            if user_id:
                ics_filename += f"_user{user_id}"
            ics_filename += ".ics"
            ics_path = os.path.join(ics_dir, ics_filename)
            with open(ics_path, 'w') as icsfile:
                icsfile.writelines(c)
            print(f"Generated ICS file: {ics_path}")
        return result
    except Exception as e:
        print(f"LLM analysis failed for {txt_path}: {e}")
        return None

def get_user_gemini_key(user_id):
    if db and User and user_id:
        user = User.query.get(user_id)
        if user and user.gemini_api_key:
            return user.gemini_api_key
    return GEMINI_API_KEY

@celery_app.task
def summarize_legal_document(txt_path, user_id=None, doc_id=None):
    """
    Summarize the legal document in 3-5 sentences using the LLM.
    """
    try:
        with open(txt_path, 'r') as f:
            text = f.read()
        prompt = (
            "You are a legal assistant. Summarize the following legal document in 3-5 sentences, focusing on the main issues, parties, and outcomes.\n\n"
            f"Document Text:\n{text[:4000]}"
        )
        api_key = get_user_gemini_key(user_id)
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
            google_api_key=api_key
        )
        response = model.invoke(prompt)
        summary = response.content if hasattr(response, "content") else str(response)
        # Save summary as a .summary.txt file next to the original txt
        summary_path = txt_path + ".summary.txt"
        with open(summary_path, 'w') as out:
            out.write(summary)
        print(f"Saved summary to {summary_path}")
        # Save to DB if possible
        if db and LegalDocumentResult and user_id and doc_id:
            result = LegalDocumentResult(
                user_id=user_id,
                doc_id=doc_id,
                result_type='summary',
                content=summary
            )
            db.session.add(result)
            db.session.commit()
        return summary_path
    except Exception as e:
        print(f"Summarization failed for {txt_path}: {e}")
        return None

@celery_app.task
def qa_legal_document(txt_path, question, user_id=None, doc_id=None):
    """
    Answer a user question about the legal document using the LLM.
    """
    try:
        with open(txt_path, 'r') as f:
            text = f.read()
        prompt = (
            "You are a legal assistant. Given the following legal document, answer the user's question as clearly and concisely as possible.\n\n"
            f"Document Text:\n{text[:4000]}\n\nQuestion: {question}\nAnswer:"
        )
        api_key = get_user_gemini_key(user_id)
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.2,
            google_api_key=api_key
        )
        response = model.invoke(prompt)
        answer = response.content if hasattr(response, "content") else str(response)
        print(f"QA answer: {answer}")
        # Save to DB if possible
        if db and LegalDocumentResult and user_id and doc_id:
            result = LegalDocumentResult(
                user_id=user_id,
                doc_id=doc_id,
                result_type='qa',
                content=answer,
                question=question
            )
            db.session.add(result)
            db.session.commit()
        return answer
    except Exception as e:
        print(f"QA failed for {txt_path}: {e}")
        return None

@celery_app.task
def analyze_for_party(txt_path, party, user_id=None, doc_id=None):
    """
    Generate legal analysis in support of either the defendant or plaintiff.
    """
    try:
        with open(txt_path, 'r') as f:
            text = f.read()
        prompt = (
            f"You are a legal assistant. Read the following legal document and generate a legal analysis in support of the {party}. "
            "List key arguments, cite relevant facts, and suggest possible legal precedents if appropriate.\n\n"
            f"Document Text:\n{text[:4000]}"
        )
        api_key = get_user_gemini_key(user_id)
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3,
            google_api_key=api_key
        )
        response = model.invoke(prompt)
        analysis = response.content if hasattr(response, "content") else str(response)
        # Save analysis as a .analysis.{party}.txt file
        analysis_path = txt_path + f".analysis.{party}.txt"
        with open(analysis_path, 'w') as out:
            out.write(analysis)
        print(f"Saved {party} analysis to {analysis_path}")
        # Save to DB if possible
        if db and LegalDocumentResult and user_id and doc_id:
            result = LegalDocumentResult(
                user_id=user_id,
                doc_id=doc_id,
                result_type='analysis',
                content=analysis,
                party=party
            )
            db.session.add(result)
            db.session.commit()
        return analysis_path
    except Exception as e:
        print(f"Legal analysis for {party} failed for {txt_path}: {e}")
        return None 