from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, send_file
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
from celery.result import AsyncResult
import csv
from io import StringIO, BytesIO
from functools import wraps
from cryptography.fernet import Fernet, InvalidToken

# Import Celery OCR task
try:
    from celery_worker import ocr_pdf, summarize_legal_document, qa_legal_document, analyze_for_party, monitor_inbox_for_ai_user
except ImportError:
    ocr_pdf = None  # For local dev if celery_worker not available
    summarize_legal_document = None
    qa_legal_document = None
    analyze_for_party = None
    monitor_inbox_for_ai_user = None

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "devsecret")
# Use Postgres if DATABASE_URL is set, otherwise default to SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///paralegal.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

FERNET_KEY = os.getenv('FERNET_KEY')
if not FERNET_KEY:
    print('WARNING: FERNET_KEY environment variable not set. Sensitive fields will not be encrypted!')
    fernet = None
else:
    fernet = Fernet(FERNET_KEY.encode())

def encrypt_value(value):
    if not fernet or value is None:
        return value
    return fernet.encrypt(value.encode()).decode()

def decrypt_value(value):
    if not fernet or value is None:
        return value
    try:
        return fernet.decrypt(value.encode()).decode()
    except (InvalidToken, AttributeError):
        return value

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    _gemini_api_key = db.Column('gemini_api_key', db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    # Relationships: llm_services, ai_users

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def gemini_api_key(self):
        return decrypt_value(self._gemini_api_key)

    @gemini_api_key.setter
    def gemini_api_key(self, value):
        self._gemini_api_key = encrypt_value(value)

class LegalDocumentResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doc_id = db.Column(db.String(128), nullable=False)
    result_type = db.Column(db.String(32), nullable=False)  # 'summary', 'qa', 'analysis'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    question = db.Column(db.Text, nullable=True)
    party = db.Column(db.String(32), nullable=True)

    user = db.relationship('User', backref=db.backref('legal_results', lazy=True))

class LLMService(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    service_type = db.Column(db.String(32), nullable=False)  # e.g. 'gemini', 'openai', 'anthropic'
    _api_key = db.Column('api_key', db.String(256), nullable=False)
    user = db.relationship('User', backref=db.backref('llm_services', lazy=True))

    @property
    def api_key(self):
        return decrypt_value(self._api_key)

    @api_key.setter
    def api_key(self, value):
        self._api_key = encrypt_value(value)

class AIUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=True)
    personality_profile = db.Column(db.Text, nullable=True)
    mode = db.Column(db.String(16), nullable=False, default='semi-automated')  # 'full-auto' or 'semi-automated'
    llm_service_id = db.Column(db.Integer, db.ForeignKey('llm_service.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('ai_users', lazy=True))
    llm_service = db.relationship('LLMService', backref=db.backref('ai_users', lazy=True))

class SMTPIMAPProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ai_user_id = db.Column(db.Integer, db.ForeignKey('ai_user.id'), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(8), nullable=False)  # 'smtp' or 'imap'
    host = db.Column(db.String(128), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(128), nullable=False)
    _password = db.Column('password', db.String(256), nullable=False)
    use_ssl = db.Column(db.Boolean, default=True)
    ai_user = db.relationship('AIUser', backref=db.backref('email_profiles', lazy=True))
    user = db.relationship('User', backref=db.backref('email_profiles', lazy=True))

    @property
    def password(self):
        return decrypt_value(self._password)

    @password.setter
    def password(self, value):
        self._password = encrypt_value(value)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(32), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref=db.backref('notifications', lazy=True))

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
    # Notifications: last 10 results for this user
    notifications = Notification.query.filter_by(user_id=user_id, read=False).order_by(Notification.created_at.desc()).limit(10).all() if user_id else []
    # AI users for this user
    ai_users = AIUser.query.filter_by(user_id=current_user.id).all()
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
        user_event_count=user_event_count,
        notifications=notifications,
        ai_users=ai_users
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

# Helper to get txt_path from doc_id (base name of JSON file)
def get_txt_path_from_doc_id(doc_id):
    llm_results_dir = '/app/llm_results'
    json_path = os.path.join(llm_results_dir, f'{doc_id}.json')
    if not os.path.exists(json_path):
        return None
    # Assume original txt is in /app/attachments or /app/llm_results
    # Try both
    txt_path = os.path.join('/app/llm_results', f'{doc_id}.txt')
    if os.path.exists(txt_path):
        return txt_path
    txt_path = os.path.join('/app/attachments', f'{doc_id}.txt')
    if os.path.exists(txt_path):
        return txt_path
    return None

@app.route('/summarize/<doc_id>', methods=['POST'])
@login_required
def summarize_doc(doc_id):
    if not summarize_legal_document:
        return {"error": "Summarization not available."}, 500
    txt_path = get_txt_path_from_doc_id(doc_id)
    if not txt_path:
        return {"error": "Document text not found."}, 404
    user_id = current_user.get_id()
    ai_user_id = request.form.get('ai_user_id')
    ai_user = AIUser.query.filter_by(id=ai_user_id, user_id=user_id).first() if ai_user_id else None
    task = summarize_legal_document.delay(txt_path, user_id=user_id, doc_id=doc_id, ai_user_id=ai_user.id if ai_user else None)
    return {"status": "Summarization started", "task_id": task.id}

@app.route('/ask/<doc_id>', methods=['POST'])
@login_required
def ask_doc(doc_id):
    if not qa_legal_document:
        return {"error": "QA not available."}, 500
    txt_path = get_txt_path_from_doc_id(doc_id)
    if not txt_path:
        return {"error": "Document text not found."}, 404
    question = request.form.get('question')
    if not question:
        return {"error": "No question provided."}, 400
    user_id = current_user.get_id()
    ai_user_id = request.form.get('ai_user_id')
    ai_user = AIUser.query.filter_by(id=ai_user_id, user_id=user_id).first() if ai_user_id else None
    task = qa_legal_document.delay(txt_path, question, user_id=user_id, doc_id=doc_id, ai_user_id=ai_user.id if ai_user else None)
    return {"status": "QA started", "task_id": task.id}

@app.route('/analyze/<doc_id>', methods=['POST'])
@login_required
def analyze_doc(doc_id):
    if not analyze_for_party:
        return {"error": "Analysis not available."}, 500
    txt_path = get_txt_path_from_doc_id(doc_id)
    if not txt_path:
        return {"error": "Document text not found."}, 404
    party = request.form.get('party')
    if party not in ['defendant', 'plaintiff']:
        return {"error": "Party must be 'defendant' or 'plaintiff'."}, 400
    user_id = current_user.get_id()
    ai_user_id = request.form.get('ai_user_id')
    ai_user = AIUser.query.filter_by(id=ai_user_id, user_id=user_id).first() if ai_user_id else None
    task = analyze_for_party.delay(txt_path, party, user_id=user_id, doc_id=doc_id, ai_user_id=ai_user.id if ai_user else None)
    return {"status": f"Analysis for {party} started", "task_id": task.id}

from celery.result import AsyncResult

@app.route('/task_status/<task_id>')
@login_required
def task_status(task_id):
    # Check Celery task status
    res = AsyncResult(task_id)
    status = res.status
    # Try to find result in DB for this user
    user_id = current_user.get_id()
    result = LegalDocumentResult.query.filter_by(user_id=user_id).order_by(LegalDocumentResult.created_at.desc()).first()
    result_data = None
    if result:
        result_data = {
            'result_type': result.result_type,
            'content': result.content,
            'question': result.question,
            'party': result.party,
            'created_at': result.created_at.isoformat()
        }
    return jsonify({'status': status, 'result': result_data})

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def user_settings():
    if request.method == 'POST':
        gemini_api_key = request.form.get('gemini_api_key')
        current_user.gemini_api_key = gemini_api_key
        db.session.commit()
        flash('Gemini API key updated.')
        return redirect(url_for('user_settings'))
    return render_template('settings.html', gemini_api_key=current_user.gemini_api_key)

@app.route('/results')
@login_required
def results():
    q = request.args.get('q', '')
    result_type = request.args.get('type')
    party = request.args.get('party')
    doc_id = request.args.get('doc_id')
    query = LegalDocumentResult.query.filter_by(user_id=current_user.id)
    if q:
        query = query.filter(LegalDocumentResult.content.ilike(f'%{q}%'))
    if result_type:
        query = query.filter_by(result_type=result_type)
    if party:
        query = query.filter_by(party=party)
    if doc_id:
        query = query.filter_by(doc_id=doc_id)
    results = query.order_by(LegalDocumentResult.created_at.desc()).all()
    return render_template('results.html', results=results, q=q, result_type=result_type, party=party, doc_id=doc_id)

@app.route('/results/export/csv')
@login_required
def export_results_csv():
    query = LegalDocumentResult.query.filter_by(user_id=current_user.id)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Document', 'Party', 'Question', 'Content', 'Created'])
    for r in query:
        writer.writerow([r.result_type, r.doc_id, r.party or '', r.question or '', r.content, r.created_at])
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='results.csv')

@app.route('/results/export/pdf')
@login_required
def export_results_pdf():
    query = LegalDocumentResult.query.filter_by(user_id=current_user.id)
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = 750
    for r in query:
        c.drawString(30, y, f"Type: {r.result_type} | Doc: {r.doc_id} | Party: {r.party or ''} | Q: {r.question or ''}")
        y -= 15
        for line in r.content.splitlines():
            c.drawString(40, y, line[:100])
            y -= 12
            if y < 50:
                c.showPage()
                y = 750
        y -= 10
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name='results.pdf')

@app.route('/document/<doc_id>/results')
@login_required
def document_results(doc_id):
    results = LegalDocumentResult.query.filter_by(user_id=current_user.id, doc_id=doc_id).order_by(LegalDocumentResult.created_at.desc()).all()
    return render_template('document_results.html', doc_id=doc_id, results=results)

# Admin-only decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash('Admin access required.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    ai_users = AIUser.query.all()
    llm_services = LLMService.query.all()
    return render_template('admin_dashboard.html', users=users, ai_users=ai_users, llm_services=llm_services)

@app.route('/llm_services', methods=['GET', 'POST'])
@login_required
def llm_services():
    if request.method == 'POST':
        name = request.form.get('name')
        service_type = request.form.get('service_type')
        api_key = request.form.get('api_key')
        if not name or not service_type or not api_key:
            flash('All fields are required.')
        else:
            llm = LLMService(user_id=current_user.id, name=name, service_type=service_type, api_key=api_key)
            db.session.add(llm)
            db.session.commit()
            flash('LLM service added.')
        return redirect(url_for('llm_services'))
    services = LLMService.query.filter_by(user_id=current_user.id).all()
    return render_template('llm_services.html', services=services)

@app.route('/llm_services/<int:llm_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_llm_service(llm_id):
    llm = LLMService.query.get_or_404(llm_id)
    if llm.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('llm_services'))
    if request.method == 'POST':
        llm.name = request.form.get('name')
        llm.service_type = request.form.get('service_type')
        llm.api_key = request.form.get('api_key')
        db.session.commit()
        flash('LLM service updated.')
        return redirect(url_for('llm_services'))
    return render_template('edit_llm_service.html', llm=llm)

@app.route('/llm_services/<int:llm_id>/delete', methods=['POST'])
@login_required
def delete_llm_service(llm_id):
    llm = LLMService.query.get_or_404(llm_id)
    if llm.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('llm_services'))
    db.session.delete(llm)
    db.session.commit()
    flash('LLM service deleted.')
    return redirect(url_for('llm_services'))

@app.route('/ai_users', methods=['GET', 'POST'])
@login_required
def ai_users():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        personality_profile = request.form.get('personality_profile')
        mode = request.form.get('mode')
        llm_service_id = request.form.get('llm_service_id')
        if not name or not mode:
            flash('Name and mode are required.')
        else:
            ai = AIUser(
                user_id=current_user.id,
                name=name,
                description=description,
                personality_profile=personality_profile,
                mode=mode,
                llm_service_id=llm_service_id if llm_service_id else None
            )
            db.session.add(ai)
            db.session.commit()
            flash('AI user added.')
        return redirect(url_for('ai_users'))
    ai_users = AIUser.query.filter_by(user_id=current_user.id).all()
    llm_services = LLMService.query.filter_by(user_id=current_user.id).all()
    return render_template('ai_users.html', ai_users=ai_users, llm_services=llm_services)

@app.route('/ai_users/<int:ai_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ai_user(ai_id):
    ai = AIUser.query.get_or_404(ai_id)
    if ai.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('ai_users'))
    llm_services = LLMService.query.filter_by(user_id=current_user.id).all()
    if request.method == 'POST':
        ai.name = request.form.get('name')
        ai.description = request.form.get('description')
        ai.personality_profile = request.form.get('personality_profile')
        ai.mode = request.form.get('mode')
        ai.llm_service_id = request.form.get('llm_service_id') or None
        db.session.commit()
        flash('AI user updated.')
        return redirect(url_for('ai_users'))
    return render_template('edit_ai_user.html', ai=ai, llm_services=llm_services)

@app.route('/ai_users/<int:ai_id>/delete', methods=['POST'])
@login_required
def delete_ai_user(ai_id):
    ai = AIUser.query.get_or_404(ai_id)
    if ai.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('ai_users'))
    db.session.delete(ai)
    db.session.commit()
    flash('AI user deleted.')
    return redirect(url_for('ai_users'))

@app.route('/ai_users/<int:ai_id>/email_profiles', methods=['GET', 'POST'])
@login_required
def email_profiles(ai_id):
    ai = AIUser.query.get_or_404(ai_id)
    if ai.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('ai_users'))
    if request.method == 'POST':
        name = request.form.get('name')
        type_ = request.form.get('type')
        host = request.form.get('host')
        port = request.form.get('port')
        username = request.form.get('username')
        password = request.form.get('password')
        use_ssl = bool(request.form.get('use_ssl'))
        if not name or not type_ or not host or not port or not username or not password:
            flash('All fields are required.')
        else:
            profile = SMTPIMAPProfile(
                user_id=current_user.id,
                ai_user_id=ai.id,
                name=name,
                type=type_,
                host=host,
                port=int(port),
                username=username,
                password=password,
                use_ssl=use_ssl
            )
            db.session.add(profile)
            db.session.commit()
            flash('Email profile added.')
        return redirect(url_for('email_profiles', ai_id=ai.id))
    profiles = SMTPIMAPProfile.query.filter_by(ai_user_id=ai.id).all()
    return render_template('email_profiles.html', ai=ai, profiles=profiles)

@app.route('/email_profiles/<int:profile_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_email_profile(profile_id):
    profile = SMTPIMAPProfile.query.get_or_404(profile_id)
    if profile.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('ai_users'))
    if request.method == 'POST':
        profile.name = request.form.get('name')
        profile.type = request.form.get('type')
        profile.host = request.form.get('host')
        profile.port = int(request.form.get('port'))
        profile.username = request.form.get('username')
        profile.password = request.form.get('password')
        profile.use_ssl = bool(request.form.get('use_ssl'))
        db.session.commit()
        flash('Email profile updated.')
        return redirect(url_for('email_profiles', ai_id=profile.ai_user_id))
    return render_template('edit_email_profile.html', profile=profile)

@app.route('/email_profiles/<int:profile_id>/delete', methods=['POST'])
@login_required
def delete_email_profile(profile_id):
    profile = SMTPIMAPProfile.query.get_or_404(profile_id)
    if profile.user_id != current_user.id:
        flash('Not authorized.')
        return redirect(url_for('ai_users'))
    ai_id = profile.ai_user_id
    db.session.delete(profile)
    db.session.commit()
    flash('Email profile deleted.')
    return redirect(url_for('email_profiles', ai_id=ai_id))

# Helper to get LLM API key and provider for an AI user or LLMService

def get_llm_api_info(ai_user=None, user=None):
    """
    Returns (service_type, api_key) for the given AI user or user's default LLM.
    """
    if ai_user and ai_user.llm_service:
        return ai_user.llm_service.service_type, ai_user.llm_service.api_key
    if user:
        # Prefer user's Gemini key if set
        if user.gemini_api_key:
            return 'gemini', user.gemini_api_key
        # Fallback: first LLMService
        llm = LLMService.query.filter_by(user_id=user.id).first()
        if llm:
            return llm.service_type, llm.api_key
    return None, None

@app.route('/share_document/<doc_id>', methods=['POST'])
@login_required
def share_document(doc_id):
    share_with = request.form.get('share_with')
    # In the future, look up the user and add sharing permissions
    print(f"User {current_user.username} wants to share doc {doc_id} with {share_with}")
    flash(f"Document {doc_id} shared with {share_with} (stub).", 'info')
    return redirect(url_for('dashboard'))

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/sync_calendar', methods=['POST'])
@login_required
def sync_calendar():
    # In the future, sync events to Google Calendar
    flash('Google Calendar sync (stub) triggered.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/help')
def help_page():
    return render_template('help.html')

@app.route('/feedback', methods=['POST'])
def feedback():
    email = request.form.get('email')
    message = request.form.get('message')
    print(f'User feedback from {email}: {message}')
    flash('Thank you for your feedback! We will get back to you soon.', 'success')
    return redirect(url_for('help_page'))

@app.route('/ai_users/<int:ai_id>/monitor_inbox', methods=['POST'])
@login_required
def monitor_inbox(ai_id):
    monitor_inbox_for_ai_user.delay(ai_id, user_id=current_user.id)
    flash('Inbox monitoring task started for AI user.', 'info')
    return redirect(url_for('ai_users'))

@app.route('/notifications/mark_all_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('dashboard'))

@app.errorhandler(500)
def internal_error(error):
    import traceback
    print('Internal server error:', traceback.format_exc())
    return render_template('500.html'), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 