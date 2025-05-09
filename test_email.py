import os
import pytest
from core.database import setup_database, get_db_connection
from agents.filtering_agent import filter_and_categorize_email
from agents.response_agent import generate_property_management_response

@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    # Use a temporary database file for testing
    db_path = tmp_path_factory.mktemp("data") / "test_pm.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    setup_database()
    yield db_path
    # Cleanup handled by tmp_path_factory

def test_database_setup(test_db):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    tables = {row["table_name"] for row in cursor.fetchall()}
    assert "properties" in tables
    assert "tenants" in tables
    assert "maintenance_tickets" in tables
    conn.close()

def test_filtering_agent_basic(monkeypatch):
    # Mock the LLM call to return a fixed JSON
    monkeypatch.setattr(
        "agents.filtering_agent.ChatGoogleGenerativeAI.invoke",
        lambda self, prompt: '{"category": "maintenance_request", "extracted_issue_summary": "Leaky faucet", "urgency": "normal", "tenant_name_mentioned": "John Doe", "property_address_mentioned": "123 Main St", "unit_mentioned": "2B"}'
    )
    email = {"subject": "Leaky faucet", "body": "My faucet is leaking."}
    result = filter_and_categorize_email(email)
    assert result["category"] == "maintenance_request"
    assert result["extracted_issue_summary"] == "Leaky faucet"
    assert result["unit_mentioned"] == "2B"

def test_response_agent(monkeypatch):
    # Mock the LLM call to return a fixed response
    monkeypatch.setattr(
        "agents.response_agent.ChatGoogleGenerativeAI.invoke",
        lambda self, prompt: "Thank you for reporting the issue. We will address it soon."
    )
    category = "maintenance_request"
    email_data = {"subject": "Leaky faucet", "body": "My faucet is leaking."}
    analysis_results = {"extracted_issue_summary": "Leaky faucet", "urgency": "normal", "maintenance_ticket_id": 1}
    tenant_details = {"name": "John Doe", "email": "john@example.com", "unit": "2B", "property_id": 1}
    property_details = {"address": "123 Main St"}
    response = generate_property_management_response(category, email_data, analysis_results, tenant_details, property_details)
    assert "Thank you for reporting the issue" in response
