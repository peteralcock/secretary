import os
import json
import shutil
import tempfile
import pytest
from unittest.mock import patch
from pathlib import Path

# Patch environment and imports for celery_worker
os.environ['GEMINI_API_KEY'] = 'fake-key'

@pytest.fixture(autouse=True)
def setup_dirs(tmp_path, monkeypatch):
    # Patch /app/llm_results and /app/ics to tmp_path
    llm_results = tmp_path / 'llm_results'
    ics_dir = tmp_path / 'ics'
    llm_results.mkdir()
    ics_dir.mkdir()
    monkeypatch.setattr('celery_worker.os.path.exists', lambda p: True)
    monkeypatch.setattr('celery_worker.os.makedirs', lambda p, exist_ok=True: None)
    monkeypatch.setattr('celery_worker.os.path.join', lambda a, b: str(Path(a) / b))
    monkeypatch.setattr('celery_worker.os.path.splitext', lambda p: os.path.splitext(p))
    monkeypatch.setattr('celery_worker.os.path.basename', lambda p: os.path.basename(p))
    monkeypatch.setattr('celery_worker.open', open)
    monkeypatch.setattr('celery_worker.json.dump', json.dump)
    monkeypatch.setattr('celery_worker.json.loads', json.loads)
    monkeypatch.setattr('celery_worker.json.load', json.load)
    monkeypatch.setattr('celery_worker.print', print)
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)

@patch('celery_worker.ChatGoogleGenerativeAI')
@patch('celery_worker.Calendar')
@patch('celery_worker.Event')
def test_analyze_legal_document_saves_user_id_and_ics(mock_event, mock_calendar, mock_llm, tmp_path):
    from celery_worker import analyze_legal_document
    # Simulate LLM response
    mock_llm.return_value.invoke.return_value.content = '''
    {
        "document_type": "Order",
        "case_number": "2024-CV-999",
        "court": "Test Court",
        "parties": ["A", "B"],
        "event_dates": ["2024-07-01T10:00:00"],
        "raw_excerpt": "Test excerpt"
    }
    '''
    # Prepare a fake text file
    txt_path = tmp_path / "test.txt"
    txt_path.write_text("Order for hearing on 2024-07-01T10:00:00")
    # Call the worker
    result = analyze_legal_document(str(txt_path), user_id=42)
    assert result['user_id'] == 42
    # Check JSON file written
    llm_results = tmp_path.parent / "llm_results"
    found = False
    for root, dirs, files in os.walk(tmp_path.parent):
        for file in files:
            if file.endswith('.json'):
                with open(os.path.join(root, file)) as f:
                    data = json.load(f)
                    if data['user_id'] == 42:
                        found = True
    assert found, "No LLM result JSON file written with user_id"
    # Check ICS file written
    found_ics = False
    for root, dirs, files in os.walk(tmp_path.parent):
        for file in files:
            if file.endswith('.ics'):
                found_ics = True
    assert found_ics, "No ICS file written"

@patch('celery_worker.ChatGoogleGenerativeAI')
def test_analyze_legal_document_handles_llm_json_error(mock_llm, tmp_path):
    from celery_worker import analyze_legal_document
    # Simulate LLM response with invalid JSON
    mock_llm.return_value.invoke.return_value.content = 'not a json'
    txt_path = tmp_path / "bad.txt"
    txt_path.write_text("Some text")
    result = analyze_legal_document(str(txt_path), user_id=1)
    assert result is None

@patch('celery_worker.ChatGoogleGenerativeAI')
def test_analyze_legal_document_handles_missing_fields(mock_llm, tmp_path):
    from celery_worker import analyze_legal_document
    # Simulate LLM response with missing fields
    mock_llm.return_value.invoke.return_value.content = '{"document_type": "Motion"}'
    txt_path = tmp_path / "missing.txt"
    txt_path.write_text("Some text")
    result = analyze_legal_document(str(txt_path), user_id=2)
    assert result['document_type'] == 'Motion'
    assert result['user_id'] == 2
    # Should still write a JSON file
    found = False
    for root, dirs, files in os.walk(tmp_path.parent):
        for file in files:
            if file.endswith('.json'):
                found = True
    assert found 