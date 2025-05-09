import os
import psycopg2
from psycopg2.extras import RealDictCursor
from utils.logger import get_logger

logger = get_logger(__name__)

def get_db_connection():
    DB_HOST = os.getenv("POSTGRES_HOST", "db")
    DB_PORT = os.getenv("POSTGRES_PORT", "5432")
    DB_NAME = os.getenv("POSTGRES_DB", "secretary_pm")
    DB_USER = os.getenv("POSTGRES_USER", "secretary")
    DB_PASS = os.getenv("POSTGRES_PASSWORD", "secretarypass")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        cursor_factory=RealDictCursor
    )
    return conn

def setup_database():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Properties Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id SERIAL PRIMARY KEY,
            address TEXT UNIQUE NOT NULL,
            units INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Tenants Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            name TEXT,
            email TEXT UNIQUE NOT NULL,
            property_id INTEGER REFERENCES properties(id),
            unit TEXT,
            rent REAL,
            balance REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Maintenance Tickets Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maintenance_tickets (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER REFERENCES tenants(id),
            property_id INTEGER REFERENCES properties(id),
            issue TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Persons of Interest Table (optional)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS persons_of_interest (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            email TEXT UNIQUE,
            interest_level INTEGER DEFAULT 1,
            notes TEXT,
            trigger_words TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Postgres database setup complete.")

# --- CRUD Functions ---
def get_tenant_by_email(email_address):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tenants WHERE email = %s', (email_address,))
    tenant = cursor.fetchone()
    cursor.close()
    conn.close()
    return tenant

def create_maintenance_ticket_db(tenant_id, property_id, issue, priority='normal'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO maintenance_tickets (tenant_id, property_id, issue, priority, status)
        VALUES (%s, %s, %s, %s, 'open')
        RETURNING id
    ''', (tenant_id, property_id, issue, priority))
    ticket_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    logger.info(f"Created maintenance ticket ID: {ticket_id} for tenant {tenant_id}")
    return ticket_id

def get_property_by_id(property_id):
    conn = get_db_connection()
    property_row = conn.execute('SELECT * FROM properties WHERE id = %s', (property_id,)).fetchone()
    conn.close()
    return property_row

def get_tenant_by_id(tenant_id):
    conn = get_db_connection()
    tenant = conn.execute('SELECT * FROM tenants WHERE id = %s', (tenant_id,)).fetchone()
    conn.close()
    return tenant

def get_all_tenants():
    conn = get_db_connection()
    tenants = conn.execute('SELECT * FROM tenants').fetchall()
    conn.close()
    return tenants

def get_all_properties():
    conn = get_db_connection()
    properties = conn.execute('SELECT * FROM properties').fetchall()
    conn.close()
    return properties

def create_property(address, units):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO properties (address, units) VALUES (%s, %s) RETURNING id''',
        (address, units)
    )
    prop_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    logger.info(f"Created property ID: {prop_id} at {address}")
    return prop_id

def create_tenant(name, email, property_id, unit, rent=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO tenants (name, email, property_id, unit, rent) VALUES (%s, %s, %s, %s, %s) RETURNING id''',
        (name, email, property_id, unit, rent)
    )
    tenant_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()
    logger.info(f"Created tenant ID: {tenant_id} for {name}")
    return tenant_id 