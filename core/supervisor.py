from core.state import EmailState
from agents import filtering_agent, summarization_agent, response_agent, human_review_agent
from langgraph.graph import START, END, StateGraph
from core.database import get_tenant_by_email, get_property_by_id, create_maintenance_ticket_db

"""Originally, each node function was written to expect two parameters—an email and a state.
However, the LangGraph framework is designed to pass only one argument (the state) to each node."""

# Bringing all the states together with a supervisor helps to manage the flow of the email processing.
def supervisor_langgraph(email: dict, state: EmailState,user_name : str,recipient_name:str) -> EmailState:
    """
    Processes an individual email using a LangGraph workflow.
    Each step (filtering, summarization, response generation) is a node.
    Conditional edges are used to exit early for spam or to continue processing.
    """
    
    state.current_email = email
    
    def filtering_node(state: EmailState) -> EmailState:
        current_email = state.current_email
        print('filtering node started for email id : %s' % current_email.get("id", "unknown"))
        classification = filtering_agent.filter_email(current_email)
        current_email["classification"] = classification
        state.metadata[current_email.get("id", "unknown")] = classification
        return state

    
    def summarization_node(state: EmailState) -> EmailState:
        email = state.current_email
        summary = summarization_agent.summarize_email(email)
        email["summary"] = summary
        return state
    
    def response_node(state: EmailState) -> EmailState:
        email = state.current_email
        response = response_agent.generate_response(email, email.get("summary", ""),recipient_name,user_name) # The response agent uses the summary to generate a response.
        # If the classification indicates review or the response is uncertain, let a human intervene
        if email.get("classification") == "needs_review" or "?" in response:
            response = human_review_agent.review_email(email, response)
        email["response"] = response
        state.history.append({
            "email_id": email.get("id", "unkonwn"),
            "response": response
        })
        return state
    
    graph_builder = StateGraph(EmailState)     # now building tther graph from all the states 

    
    # addimng the nodes in the graph 
    graph_builder.add_node("filtering", filtering_node)
    graph_builder.add_node("summarization", summarization_node)
    graph_builder.add_node("response", response_node)
    
    
    
    
    
    
    # building conditional wortking with filtering now that it is not spam if spam then dustbin is the way 
    def post_filtering(state_update: EmailState):
        email = state.current_email
        if email.get("classification") == "spam":
            return END
        else:
            return "summarization"
    
    graph_builder.add_conditional_edges("filtering", post_filtering, {"summarization": "summarization", END: END})
    
    # This creates a direct edge (connection) from the "summarization" node to the "response" node.
    # if reaches summary node then must move to response node
    graph_builder.add_edge("summarization", "response")
    
    graph_builder.add_edge("response", END) # if respone comes then end to all please
    
    # Set the entry point to the filtering node.
    graph_builder.set_entry_point("filtering")
    
    # Compile the graph.
    graph = graph_builder.compile()
    
    # Invoke the graph with the current state.
    final_state = graph.invoke(state)
    return final_state

def supervisor_pm_workflow(email: dict, state: EmailState) -> EmailState:
    """
    Property management workflow: identify tenant/property, categorize, create actions, generate response.
    """
    state.current_email = email
    sender_email = email.get("from")
    tenant_info = get_tenant_by_email(sender_email) if sender_email else None
    property_info = None
    if tenant_info and tenant_info.get("property_id"):
        property_info = get_property_by_id(tenant_info["property_id"])

    # 1. Categorize and extract info
    classification_and_extraction = filtering_agent.filter_and_categorize_email(email, tenant_info, property_info)
    state.current_email["classification_details"] = classification_and_extraction
    category = classification_and_extraction.get("category", "general_inquiry")
    state.current_email["category"] = category

    # 2. Create actions based on category
    actions_taken = []
    if category == "maintenance_request" and tenant_info:
        issue_summary = classification_and_extraction.get("extracted_issue_summary", "Maintenance issue reported.")
        urgency = classification_and_extraction.get("urgency", "normal")
        property_id_for_ticket = tenant_info.get("property_id", None)
        if tenant_info.get("id") and property_id_for_ticket:
            ticket_id = create_maintenance_ticket_db(
                tenant_id=tenant_info["id"],
                property_id=property_id_for_ticket,
                issue=issue_summary,
                priority=urgency
            )
            actions_taken.append({"type": "maintenance_ticket_created", "ticket_id": ticket_id, "issue": issue_summary})
            state.current_email["classification_details"]["maintenance_ticket_id"] = ticket_id
        else:
            actions_taken.append({"type": "maintenance_request_received", "issue": issue_summary, "needs_info": "Tenant or property ID missing for ticket creation"})
    elif category == "rent_inquiry" and tenant_info:
        actions_taken.append({"type": "rent_inquiry_logged", "tenant_id": tenant_info["id"]})
    elif category == "lockout_emergency":
        actions_taken.append({"type": "lockout_emergency_reported", "tenant_id": tenant_info.get("id") if tenant_info else None, "property_address": property_info.get("address") if property_info else None})
    state.current_email["actions_taken"] = actions_taken

    # 3. Generate response
    generated_response = response_agent.generate_property_management_response(
        category=category,
        email_data=email,
        analysis_results=state.current_email["classification_details"],
        tenant_details=tenant_info,
        property_details=property_info
    )
    state.current_email["response"] = generated_response

    state.history.append({
        "email_id": email.get("id"),
        "category": category,
        "actions": actions_taken,
        "response_generated": generated_response[:100] + "..."
    })
    return state
