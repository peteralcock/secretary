import os
import pytest
from unittest.mock import patch, MagicMock
from core.database import setup_database, get_db_connection, create_property, create_tenant, create_maintenance_ticket_db
from agents.filtering_agent import filter_and_categorize_email
from agents.response_agent import generate_property_management_response
from core.supervisor import supervisor_pm_workflow
from core.state import EmailState
import json

@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "test_pm.db"
    os.environ["POSTGRES_DB"] = "secretary_pm"
    os.environ["POSTGRES_USER"] = "secretary"
    os.environ["POSTGRES_PASSWORD"] = "secretarypass"
    os.environ["POSTGRES_HOST"] = "db"
    os.environ["POSTGRES_PORT"] = "5432"
    setup_database()
    yield db_path


@pytest.fixture(autouse=True)
def clean_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("TRUNCATE maintenance_tickets, tenants, properties RESTART IDENTITY CASCADE;")
    conn.commit()
    cursor.close()
    conn.close()


def test_property_crud(test_db):
    conn = get_db_connection()
    prop_id = create_property("123 Main St", 4)
    assert prop_id is not None
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM properties WHERE address=%s", ("123 Main St",))
    row = cursor.fetchone()
    assert row["address"] == "123 Main St"


def test_tenant_crud(test_db):
    conn = get_db_connection()
    prop_id = create_property("456 Oak Ave", 2)
    tenant_id = create_tenant("Alice", "alice@example.com", prop_id, "101")
    assert tenant_id is not None
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants WHERE email=%s", ("alice@example.com",))
    row = cursor.fetchone()
    assert row["name"] == "Alice"


def test_ticket_crud(test_db):
    conn = get_db_connection()
    prop_id = create_property("789 Pine Rd", 3)
    tenant_id = create_tenant("Bob", "bob@example.com", prop_id, "202")
    ticket_id = create_maintenance_ticket_db(tenant_id, prop_id, "Leaky faucet", "low")
    assert ticket_id is not None
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM maintenance_tickets WHERE id=%s", (ticket_id,))
    row = cursor.fetchone()
    assert row["issue"] == "Leaky faucet"


@pytest.mark.parametrize("email_obj,expected_category", [
    ( {"subject": "Leaking faucet in kitchen", "body": "My kitchen faucet is leaking."}, "maintenance_request" ),
    ( {"subject": "Question about rent payment", "body": "Did you get my rent?"}, "rent_inquiry" ),
    ( {"subject": "Locked out of my apartment", "body": "I am locked out."}, "lockout_emergency" ),
    ( {"subject": "Lease renewal question", "body": "Can I renew my lease?"}, "lease_question" ),
    ( {"subject": "General question", "body": "What are the office hours?"}, "general_inquiry" ),
    ( {"subject": "You won a prize!", "body": "Click here for a free iPad."}, "spam" ),
])
def test_filtering_agent(email_obj, expected_category):
    with patch("agents.filtering_agent.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value.invoke.return_value = json.dumps({
            "category": expected_category,
            "extracted_issue_summary": email_obj["body"],
            "urgency": "low",
            "tenant_name_mentioned": None,
            "property_address_mentioned": None,
            "unit_mentioned": None
        })
        result = filter_and_categorize_email(email_obj)
        assert result["category"] == expected_category


def test_response_agent():
    class FakeLLMResponse:
        def __init__(self, content):
            self.content = content
    with patch("agents.response_agent.ChatGoogleGenerativeAI") as mock_llm:
        mock_llm.return_value.invoke.return_value = FakeLLMResponse("Thank you for your request.")
        response = generate_property_management_response(
            "maintenance_request",
            {"subject": "Leaking faucet", "body": "My faucet leaks."},
            {"category": "maintenance_request", "extracted_issue_summary": "My faucet leaks."},
            {"name": "Alice", "email": "alice@example.com"},
            {"address": "123 Main St"}
        )
        assert "Thank you" in response


def test_supervisor_workflow():
    email = {"from": "alice@example.com", "subject": "Leaking faucet", "body": "My faucet leaks."}
    state = EmailState()
    state.emails = [email]
    state.current_email = email
    with patch("agents.filtering_agent.filter_and_categorize_email") as mock_filter, \
         patch("agents.response_agent.generate_property_management_response") as mock_response:
        mock_filter.return_value = {"category": "maintenance_request", "extracted_issue_summary": "My faucet leaks."}
        mock_response.return_value = "Thank you for your request."
        new_state = supervisor_pm_workflow(email, state)
        assert new_state.current_email["response"] == "Thank you for your request." 