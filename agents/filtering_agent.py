import json
from langchain.prompts import PromptTemplate
from config import GEMINI_API_KEY  # Use Gemini API key from config
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.logger import get_logger
from utils.formatter import clean_text

logger = get_logger(__name__)

def filter_and_categorize_email(email: dict, tenant_info: dict = None, property_info: dict = None) -> dict:
    """
    Uses an LLM to analyze the email and classify it into property management categories, extracting key information.
    Categories: maintenance_request, rent_inquiry, lockout_emergency, lease_question, general_inquiry, spam, other
    Extracts: issue summary, urgency, tenant name, property address, unit
    """
    prompt_template = PromptTemplate(
        input_variables=["subject", "body", "tenant_name", "property_address"],
        template=(
            "You are an AI assistant for a property management company. "
            "Analyze the following email and categorize it.\n"
            "Email Subject: {subject}\n"
            "Email Body:\n{body}\n\n"
            "Known Tenant: {tenant_name}\n"
            "Known Property Address: {property_address}\n\n"
            "Categorize into ONE of the following: "
            "'maintenance_request', 'rent_inquiry', 'lockout_emergency', "
            "'lease_question', 'general_inquiry', 'spam', 'other'.\n"
            "Also extract key information: \n"
            " - 'extracted_issue_summary' (for maintenance, a brief summary of the problem) \n"
            " - 'urgency' ('low', 'normal', 'high', 'emergency') \n"
            " - 'tenant_name_mentioned' (if different from known sender) \n"
            " - 'property_address_mentioned' (if any specific address is in the email) \n"
            " - 'unit_mentioned' (e.g., Apt 3B) \n"
            "Respond with a JSON object with keys: 'category', 'extracted_issue_summary', 'urgency', 'tenant_name_mentioned', 'property_address_mentioned', 'unit_mentioned'. "
            "If a field is not applicable or found, use null or an empty string for its value."
        )
    )

    prompt = prompt_template.format(
        subject=email.get("subject", ""),
        body=email.get("body", ""),
        tenant_name=tenant_info.get("name", "Unknown") if tenant_info else "Unknown",
        property_address=property_info.get("address", "Unknown") if property_info else "Unknown"
    )

    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0.2,
        google_api_key=GEMINI_API_KEY
    )

    result = model.invoke(prompt)
    classification_text = clean_text(str(result.content if hasattr(result, "content") else result))
    logger.debug("Raw model output: %s", classification_text)

    # Remove markdown code block markers if present
    text = classification_text.strip()
    if text.startswith("```"):
        # Handle single-line code block: e.g., ```json { ... } ```
        if text.endswith("```"):
            # Remove leading and trailing code block markers
            # Remove possible language tag (e.g., ```json)
            first_marker_end = text.find("\n")
            if first_marker_end == -1:
                # Single-line code block
                # Remove leading ``` or ```json and trailing ```
                for marker in ["```json", "```"]:
                    if text.startswith(marker) and text.endswith("```"):
                        text = text[len(marker):]
                        text = text[:-3]
                        break
                text = text.strip()
            else:
                # Multi-line code block
                lines = text.splitlines()
                if lines[0].startswith("```") and lines[-1].startswith("```") and len(lines) > 2:
                    text = "\n".join(lines[1:-1])
                else:
                    text = "\n".join(line for line in lines if not line.strip().startswith("```"))
        classification_text = text

    try:
        parsed_output = json.loads(classification_text)
        logger.debug(f"LLM classification and extraction output: {parsed_output}")
        return parsed_output
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON from LLM: {classification_text}")
        return {"category": "unknown_format", "error": "LLM output not valid JSON"}