from langchain.prompts import PromptTemplate
from config import DEEPSEEK_API_KEY, GEMINI_API_KEY  # Import the key from your config
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from utils.formatter import clean_text, format_email


from email.utils import parseaddr


def generate_response(email: dict, summary: str, recipient_name: str, your_name: str) -> str:
    prompt_template = PromptTemplate(
        input_variables=["sender", "subject", "content", "summary", "user_name","recipient_name"],
        template=(
            "You are an email assistant. Do not use placeholders like [User's Name]"
            "You are an email assistant. Do not include any greeting or signature lines in your response.\n\n"
            "Email Details:\n"
            "From: {sender}\n"
            "Subject: {subject}\n"
            "Content: {content}\n"
            "Summary: {summary}\n\n"
            
            "Reply in a formal tone."
        )
    )
    
    prompt = prompt_template.format(
        sender=recipient_name,  # Use the recipient's name (supplied manually)
        subject=email.get("subject", ""),
        content=email.get("body", ""),
        summary=summary,
        user_name=your_name
    )
    
    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0.5,
        google_api_key=GEMINI_API_KEY
    )
    
    response = model.invoke(prompt)
    response_text = response.content if hasattr(response, "content") else str(response)
    
    # Pass recipient_name (for greeting) and your_name (for signature)
    formatted_response = format_email(email.get("subject", ""), recipient_name, response_text, your_name)
    return formatted_response.strip()

def generate_property_management_response(category: str, email_data: dict, analysis_results: dict, tenant_details: dict = None, property_details: dict = None) -> str:
    """
    Generate a property management–specific response using extracted info and database context.
    """
    # Build context for the prompt
    prompt_context = f"Responding to a '{category}'.\n"
    if tenant_details:
        prompt_context += (
            f"Tenant: {tenant_details['name']} (Email: {tenant_details['email']}, Unit: {tenant_details.get('unit', 'N/A')}).\n"
            f"Property: {property_details['address'] if property_details else 'N/A'}.\n"
        )
    else:
        prompt_context += "Sender not currently identified as a tenant in our system.\n"

    if category == "maintenance_request":
        prompt_context += f"Issue reported: {analysis_results.get('extracted_issue_summary', 'Not specified')}.\n"
        prompt_context += f"Urgency assessed as: {analysis_results.get('urgency', 'normal')}.\n"
        ticket_id = analysis_results.get("maintenance_ticket_id")
        if ticket_id:
            prompt_context += f"A maintenance ticket (ID: {ticket_id}) has been created. \n"
        else:
            prompt_context += "We are processing this request. \n"
    elif category == "rent_inquiry":
        if tenant_details:
            prompt_context += f"Current rent: ${tenant_details.get('rent', 'N/A')}, Balance: ${tenant_details.get('balance', 'N/A')}.\n"
    elif category == "lockout_emergency":
        prompt_context += "Lockout/emergency situation reported. Provide emergency contact info.\n"
    elif category == "lease_question":
        prompt_context += "Lease inquiry. Provide lease details or request more info if needed.\n"
    elif category == "general_inquiry":
        prompt_context += "General inquiry. Respond politely and request more info if needed.\n"
    elif category == "spam":
        prompt_context += "This email appears to be spam.\n"
    else:
        prompt_context += "Other/unknown category.\n"

    template = (
        "You are 'Secretary', an AI assistant for a property management company. "
        "Craft a polite, professional, and helpful email response based on the following information.\n"
        "Sign off as 'Secretary Property Management Team'.\n\n"
        "Context:\n{context}\n\n"
        "Original Email Subject: {original_subject}\n"
        "Original Email Body Snippet (for reference):\n{original_body_snippet}\n\n"
        "Task: Write the response email body. If necessary information to fully address the query is missing (e.g. tenant not identified but email is about a specific unit), politely request the missing details."
    )

    prompt = PromptTemplate(input_variables=["context", "original_subject", "original_body_snippet"], template=template)

    final_prompt_str = prompt.format(
        context=prompt_context,
        original_subject=email_data.get("subject", ""),
        original_body_snippet=email_data.get("body", "")[:200] + "..."
    )

    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0.5,
        google_api_key=GEMINI_API_KEY
    )

    response = model.invoke(final_prompt_str)
    response_text = response.content if hasattr(response, "content") else str(response)
    # Optionally, format the response with a signature
    formatted_response = format_email(email_data.get("subject", ""), tenant_details["name"] if tenant_details else "Resident", response_text, "Secretary Property Management Team")
    return formatted_response.strip()
