from flask import Flask, render_template, request, redirect, url_for, flash
import json
from agents.filtering_agent import filter_and_categorize_email
from agents.response_agent import generate_property_management_response
from core.state import EmailState
from core.supervisor import supervisor_pm_workflow
import os
from datetime import datetime
from collections import Counter, defaultdict

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "devsecret")

# For demo, load emails from sample_emails.json
EMAILS_PATH = os.getenv("EMAILS_PATH", "sample_emails.json")

def load_emails():
    with open(EMAILS_PATH) as f:
        return json.load(f)

@app.route("/")
def home():
    return redirect(url_for("dashboard"))

@app.route("/email/<email_id>", methods=["GET", "POST"])
def process_email(email_id):
    emails = load_emails()
    email = next((e for e in emails if e["id"] == email_id), None)
    if not email:
        flash("Email not found.")
        return redirect(url_for("home"))

    if request.method == "POST":
        your_name = request.form.get("your_name")
        recipient_name = request.form.get("recipient_name")
        # Run workflow
        state = EmailState()
        state.emails = [email]
        state.current_email = email
        state = supervisor_pm_workflow(email, state)
        response = state.current_email.get("response", "No response generated.")
        return render_template("edit_response.html", email=email, response=response, your_name=your_name, recipient_name=recipient_name)

    return render_template("process_email.html", email=email)

@app.route("/email/<email_id>/submit", methods=["POST"])
def submit_response(email_id):
    emails = load_emails()
    email = next((e for e in emails if e["id"] == email_id), None)
    if not email:
        flash("Email not found.")
        return redirect(url_for("home"))
    response = request.form.get("response")
    action = request.form.get("action")
    recipient_name = request.form.get("recipient_name", "")
    # Here you would send or draft the email using core.email_sender
    # For demo, just show a success page
    return render_template("success.html", email=email, response=response, action=action, recipient_name=recipient_name)

@app.route("/dashboard")
def dashboard():
    emails = load_emails()
    # For demo, assume emails with a 'response' field are replied, others are not
    # In a real app, this would come from the database
    # We'll simulate by marking even IDs as replied
    for e in emails:
        e["replied"] = int(e["id"]) % 2 == 0
        # Simulate legal communication detection
        subj = e["subject"].lower()
        sender = e["from"].lower()
        legal_keywords = ["law", "court", "attorney", "judge", "legal", "firm", "clerk"]
        e["is_legal_communication"] = any(k in subj or k in sender for k in legal_keywords)
        # Simulate attachments
        e["attachments"] = []
        if any(word in subj for word in ["document", "attachment", "pdf", "serve", "motion", "order"]):
            e["attachments"].append(f"{e['id']}_document.pdf")
        # Simulate categories using filtering agent (could be cached in DB in real app)
        if "category" not in e:
            if e["is_legal_communication"]:
                e["category"] = "legal_document"
            else:
                e["category"] = "general_communication"
        # Parse timestamp
        e["dt"] = datetime.fromisoformat(e["timestamp"])
    # Unaddressed messages
    unaddressed = [e for e in emails if not e["replied"]]
    # Issue counts by category
    category_counts = Counter(e["category"] for e in emails)
    category_counts_dict = {k: int(v) for k, v in category_counts.items()}
    # Issues by day/week/month
    by_day = Counter(e["dt"].date() for e in emails)
    by_day = {str(k): v for k, v in by_day.items()}
    by_week = Counter(e["dt"].strftime("%Y-W%U") for e in emails)
    by_week = {str(k): v for k, v in by_week.items()}
    by_month = Counter(e["dt"].strftime("%Y-%m") for e in emails)
    by_month = {str(k): v for k, v in by_month.items()}
    # Replied vs not replied by period
    replied_by_day = defaultdict(lambda: [0,0])  # [replied, not replied]
    for e in emails:
        d = e["dt"].date()
        if e["replied"]:
            replied_by_day[d][0] += 1
        else:
            replied_by_day[d][1] += 1
    replied_by_day = {str(k): v for k, v in replied_by_day.items()}
    # Drafts saved (simulate: odd IDs are drafts for demo)
    drafts = [e for e in emails if int(e["id"]) % 2 == 1]
    num_drafts = len(drafts)
    # Top issues (by extracted_issue_summary, if present)
    issue_summaries = [e.get("extracted_issue_summary", e["subject"]) for e in emails if e.get("category") != "spam"]
    top_issues = Counter(issue_summaries).most_common(5)
    # Top categories (sorted)
    top_categories = category_counts.most_common(5)
    return render_template(
        "dashboard.html",
        unaddressed=unaddressed,
        category_counts=category_counts_dict,
        by_day=by_day,
        by_week=by_week,
        by_month=by_month,
        replied_by_day=replied_by_day,
        emails=emails,
        num_drafts=num_drafts,
        top_issues=top_issues,
        top_categories=category_counts.most_common(5)
    )

@app.route("/inbox")
def inbox():
    emails = load_emails()
    return render_template("home.html", emails=emails)

@app.route("/scoreboard")
def scoreboard():
    # Placeholder scoreboard data
    users = [
        {"username": "alice", "replies": 12},
        {"username": "bob", "replies": 8},
        {"username": "carol", "replies": 5},
    ]
    return render_template("scoreboard.html", users=users)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 