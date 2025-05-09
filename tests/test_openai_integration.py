import os
import pytest
from agents.filtering_agent import filter_and_categorize_email
from agents.response_agent import generate_property_management_response

@pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
def test_gemini_end_to_end():
    """End-to-end test for Gemini LLM integration."""
    email = {
        "from": "miki@example.com",
        "subject": "Leaking faucet in kitchen",
        "body": "Hello, my kitchen faucet has started leaking and is dripping constantly. Can someone come fix it soon?"
    }
    # No tenant/property info for this test
    analysis = filter_and_categorize_email(email)
    assert analysis["category"] == "maintenance_request"
    reply = generate_property_management_response(
        category=analysis["category"],
        email_data=email,
        analysis_results=analysis,
        tenant_details=None,
        property_details=None
    )
    print("Category:", analysis["category"])
    print("Reply:\n", reply)
    assert "leak" in reply.lower() or "faucet" in reply.lower()
    assert len(reply) > 20 