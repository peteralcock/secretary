from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import json
from agents.filtering_agent import filter_and_categorize_email
from agents.response_agent import generate_property_management_response
from core.state import EmailState
from core.supervisor import supervisor_pm_workflow
import os
from datetime import datetime
from collections import Counter, defaultdict
import glob
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Import Celery OCR task
try:
    from celery_worker import ocr_pdf
except ImportError:
    ocr_pdf = None  # For local dev if celery_worker not available

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "devsecret")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paralegal.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create DB if not exists
with app.app_context():
    db.create_all()

# Signup route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.')
            return redirect(url_for('signup'))
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Signup successful. Please log in.')
        return redirect(url_for('login'))
    return render_template('signup.html')

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.')
    return render_template('login.html')

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

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
@login_required
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
            filename = f"{e['id']}_document.pdf"
            e["attachments"].append(filename)
            # Enqueue OCR task for each legal PDF attachment (simulate path)
            if e["is_legal_communication"] and ocr_pdf:
                pdf_path = f"/app/attachments/{filename}"
                user_id = current_user.get_id() if current_user.is_authenticated else None
                # This will enqueue the OCR task in the background, with user_id for tracking
                ocr_pdf.delay(pdf_path, user_id)
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
    # Load LLM results (legal document analysis)
    llm_results_dir = '/app/llm_results'
    recent_legal_docs = []
    upcoming_events = []
    user_id = current_user.get_id() if current_user.is_authenticated else None
    if os.path.exists(llm_results_dir):
        for fpath in glob.glob(os.path.join(llm_results_dir, '*.json')):
            try:
                with open(fpath) as f:
                    doc = json.load(f)
                    # If user_id is in doc, filter by user if requested
                    doc_user_id = doc.get('user_id')
                    recent_legal_docs.append(doc)
                    for dt in doc.get('event_dates', []):
                        upcoming_events.append({
                            'date': dt,
                            'case_number': doc.get('case_number'),
                            'document_type': doc.get('document_type'),
                            'court': doc.get('court'),
                            'user_id': doc_user_id
                        })
            except Exception as e:
                print(f"Error loading LLM result {fpath}: {e}")
    # Sort events chronologically
    upcoming_events.sort(key=lambda x: x['date'])
    # Filtering by user
    filter_type = request.args.get('filter')
    if filter_type == 'mydocs':
        recent_legal_docs = [d for d in recent_legal_docs if d.get('user_id') == user_id]
    if filter_type == 'myevents':
        upcoming_events = [e for e in upcoming_events if e.get('user_id') == user_id]
    # Per-user stats
    user_doc_count = sum(1 for d in recent_legal_docs if d.get('user_id') == user_id)
    user_event_count = sum(1 for e in upcoming_events if e.get('user_id') == user_id)
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
        top_categories=category_counts.most_common(5),
        recent_legal_docs=recent_legal_docs,
        upcoming_events=upcoming_events,
        current_user=current_user,
        user_doc_count=user_doc_count,
        user_event_count=user_event_count
    )

@app.route("/inbox")
@login_required
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

@app.route("/ics/<filename>")
def download_ics(filename):
    return send_from_directory("/app/ics", filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 