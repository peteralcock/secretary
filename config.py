import os
from dotenv import load_dotenv


load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_SERVER = os.getenv("EMAIL_SERVER")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_PORT = os.getenv("EMAIL_PORT")



# IMAP configuration
IMAP_USERNAME = os.getenv("IMAP_USERNAME", EMAIL_USERNAME)  # defaults to EMAIL_USERNAME if not set
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", EMAIL_PASSWORD)
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = os.getenv("IMAP_PORT", 993)

# Postgres database config
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "secretary_pm")
POSTGRES_USER = os.getenv("POSTGRES_USER", "secretary")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "secretarypass")