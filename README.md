
![Secretary](splash.jpg?raw=true "Secretary")
Your Ai-Powered Property Management Inbox Assistant

**Transform your property management workflows with Secretary, an intelligent system designed to automate email handling, streamline tenant communication, and integrate seamlessly with your operations.**

Secretary leverages advanced AI (Langchain & Large Language Models) to read, understand, categorize, and respond to emails from tenants, prospects, and other contacts. It's built to save property managers valuable time, reduce manual effort, and improve response consistency. This system is ideal for property management software companies looking to embed cutting-edge AI capabilities into their platforms.

## Why Secretary for Property Management Software?

* **Automated Triage & Categorization:** Secretary intelligently categorizes incoming emails into key property management areas:
    * **Maintenance Requests:** Identifies issues, urgency, and relevant details.
    * **Rent Inquiries:** Flags questions about payments, balances, and due dates.
    * **Lease Questions:** Recognizes inquiries about lease terms, renewals, and agreements.
    * **Lockout Emergencies:** Prioritizes urgent access issues.
    * **General Inquiries & Spam.**
* **Intelligent Response Generation:** Drafts context-aware, professional responses tailored to each category, referencing tenant and property details where available.
* **Actionable Insights & Workflow Triggers:**
    * Automatically creates maintenance tickets in its internal database (extensible to your system).
    * Logs communication and actions for audit trails.
    * (Future Potential) Trigger notifications or workflows in your existing property management software via API integrations.
* **Database Integration:** Comes with a built-in SQLite database to manage:
    * Properties and Units
    * Tenant Information (contact, lease details, balance)
    * Maintenance Tickets (status, priority, issue description)
* **Web Interface for Oversight:** A Flask-based web UI allows managers to:
    * View incoming emails and Secretary's analysis.
    * Review and edit AI-generated responses before sending.
    * Manually dispatch emails or save them as drafts.
    * (Future Potential) View dashboards and reports on email traffic and resolutions.
* **Powered by Langchain & LLMs:** Utilizes the flexibility of Langchain and the power of models like Deepseek (or your preferred LLM) for sophisticated natural language understanding and generation.
* **Customizable & Extensible:** Built with Python, Flask, and Langchain, making it adaptable to your specific needs and integration points.

## Core Features for Property Management

* **Automated Email Processing:** Connects to an IMAP inbox to fetch and process new emails.
* **Tenant Recognition:** Attempts to identify tenants based on sender email or information within the email body, cross-referencing with its database.
* **Property Contextualization:** Links communications to specific properties and units.
* **Maintenance Workflow Initiation:**
    * Extracts key details from maintenance requests.
    * Can automatically assign priority (low, normal, high, emergency).
    * Creates a maintenance ticket in the database.
* **Rent & Lease Inquiry Handling:** Provides tenants with relevant information or drafts responses for manager review.
* **Emergency Prioritization:** Flags and helps manage urgent situations like lockouts.
* **Professional Communication:** Ensures all tenant communications are polite, consistent, and informative.
* **Human-in-the-Loop:** AI-generated responses can be reviewed and modified through the web interface, ensuring manager control.

## System Flow (Property Management Focus)
![Secretary](splash-2.png?raw=true "Secretary")


1.  **Email Ingestion:** Secretary connects to the designated IMAP email account.
2.  **Tenant/Property Identification:** Attempts to match sender/content to known tenants and properties in its database.
3.  **AI Categorization & Extraction:** The Langchain-powered agent analyzes the email to:
    * Determine the category (maintenance, rent, lease, etc.).
    * Extract key details (e.g., issue for maintenance, specific question).
    * Assess urgency.
4.  **Action Generation:** Based on the category, Secretary initiates internal actions:
    * **Maintenance:** Creates a ticket, logs details.
    * **Rent/Lease:** Prepares context for response.
    * **Emergency:** Highlights for immediate attention.
5.  **AI Response Drafting:** A tailored, professional response is generated using LLMs, incorporating relevant tenant/property data and addressing the specific inquiry.
6.  **Web UI Review:** The property manager can view the original email, Secretary's analysis, actions taken (e.g., ticket created), and the drafted response via the Flask web interface.
7.  **Edit & Dispatch:** The manager can approve, edit, or discard the AI response, then send it or save it as a draft.
8.  **Logging & Data Update:** All interactions and generated data (tickets, responses) are logged and stored.

## Technical Stack

* **Backend:** Python, Flask, Langchain, LangGraph
* **AI Models:** Configured for Deepseek API (easily adaptable to other LLMs like OpenAI, Anthropic)
* **Database:** SQLite (for easy setup; can be replaced with other SQL databases)
* **Email Protocols:** IMAP for fetching, SMTP for sending.

## Installation

### Prerequisites
* Python 3.8+
* pip, virtualenv (recommended)

### Setup
1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/yourusername/secretary-pm-ai.git](https://github.com/yourusername/secretary-pm-ai.git) # Update with your repo name
    cd secretary-pm-ai
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Environment Variables:** Create a `.env` file in the project root (see `config.py` for variables to set):
    ```dotenv
    DEEPSEEK_API_KEY=your_deepseek_api_key # Or your chosen LLM API key
    
    EMAIL_SERVER=smtp.yourserver.com
    EMAIL_USERNAME=your_property_management_email@example.com
    EMAIL_PASSWORD=your_email_password
    EMAIL_PORT=587

    IMAP_USERNAME=your_property_management_email@example.com
    IMAP_PASSWORD=your_email_password
    IMAP_SERVER=imap.yourserver.com
    IMAP_PORT=993

    DATABASE_PATH=data/secretary_pm.db # Default path
    ```
    **Important:** For email providers like Gmail, you might need to enable "less secure app access" or generate an "app password."

## Usage

1.  **Initialize Database:** The database and tables are created automatically on the first run of `app.py` if they don't exist.
2.  **Run the Secretary Application:**
    ```bash
    python app.py
    ```
3.  **Access the Web Interface:** Open your browser and go to `http://127.0.0.1:5000/`.
    * The main page will list incoming emails.
    * Click an email to see Secretary's analysis, actions (like ticket creation), and the AI-drafted response.
    * Edit the response as needed and use the buttons to send or draft the email.

## Directory Structure

```plaintext
secretary-pm-ai/
├── agents/                 # Langchain agents (categorization, response generation)
├── core/                   # Core logic (email I/O, DB, supervisor workflow)
│   ├── database.py         # New: Database setup and interaction logic
│   └── supervisor.py       # Updated for PM workflows
├── static/                 # CSS, JS for Flask UI
├── templates/              # Jinja2 HTML templates for Flask UI
├── utils/                  # Utility modules
├── data/                   # SQLite database file, other data (e.g., logs, saved actions)
├── app.py                  # Main Flask application
├── config.py               # Configuration loading
├── requirements.txt
├── README.md               # This file
└── .env.example            # Example environment file

```

## Sample Emails for Testing

The `sample_emails.json` file provides a set of realistic, fictional tenant emails to help you test Secretary's property management logic. Each email is crafted to trigger a different workflow or category in the system:

- **Maintenance Request:**
  - From: miki@example.com
  - Subject: Leaking faucet in kitchen
  - Body: Describes a leaking kitchen faucet and requests repair.

- **Rent Inquiry:**
  - From: wilkin@example.com
  - Subject: Question about rent payment
  - Body: Asks if the rent payment was received and requests current balance.

- **Lockout Emergency:**
  - From: john@example.com
  - Subject: Locked out of my apartment
  - Body: Reports being locked out of unit 3B at Greenwich Ave and asks for help.

- **Lease Question:**
  - From: miki@example.com
  - Subject: Lease renewal inquiry
  - Body: Inquires about the lease renewal process and possible rent changes.

- **General Inquiry:**
  - From: wilkin@example.com
  - Subject: Question about parking
  - Body: Asks about additional guest parking at 2000 Holland Av.

- **Spam Example:**
  - From: unknown@spamdomain.com
  - Subject: Congratulations! You've won a free cruise!
  - Body: Obvious spam with a suspicious link.

These examples allow you to verify that Secretary correctly categorizes, extracts, and responds to a variety of common property management scenarios, as well as filters out spam. You can extend this file with more cases as needed for your own testing or demos.
