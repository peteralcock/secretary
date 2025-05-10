import os
import tempfile
import pytest
from app import app, db, User, Notification, AIUser
from flask import url_for
from unittest.mock import patch

@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp()
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
    os.close(db_fd)
    os.unlink(db_path)

def signup(client, username, email, password):
    return client.post('/signup', data={
        'username': username,
        'email': email,
        'password': password
    }, follow_redirects=True)

def login(client, username, password):
    return client.post('/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)

def logout(client):
    return client.get('/logout', follow_redirects=True)

def test_signup_login_logout(client):
    rv = signup(client, 'alice', 'alice@example.com', 'password')
    assert b'Signup successful' in rv.data
    rv = login(client, 'alice', 'password')
    assert b'Logged in as' in rv.data
    rv = logout(client)
    assert b'Logged out successfully' in rv.data

def test_dashboard_requires_login(client):
    rv = client.get('/dashboard', follow_redirects=True)
    assert b'Log In' in rv.data

def test_inbox_requires_login(client):
    rv = client.get('/inbox', follow_redirects=True)
    assert b'Log In' in rv.data

@patch('app.ocr_pdf')
def test_per_user_document_tracking(mock_ocr_pdf, client):
    signup(client, 'bob', 'bob@example.com', 'pw')
    login(client, 'bob', 'pw')
    # Simulate dashboard load triggers OCR for a legal email
    with patch('app.load_emails') as mock_load_emails:
        mock_load_emails.return_value = [{
            'id': '1',
            'subject': 'Motion to Dismiss',
            'from': 'court@example.com',
            'timestamp': '2024-06-01T10:00:00',
        }]
        client.get('/dashboard')
        assert mock_ocr_pdf.delay.called
        args, kwargs = mock_ocr_pdf.delay.call_args
        # Should pass user_id as second arg
        assert kwargs or (len(args) > 1 and args[1] is not None)

@patch('app.ocr_pdf')
def test_my_documents_filter(mock_ocr_pdf, client):
    signup(client, 'carol', 'carol@example.com', 'pw')
    login(client, 'carol', 'pw')
    # Simulate dashboard with filter
    with patch('app.load_emails') as mock_load_emails:
        mock_load_emails.return_value = [{
            'id': '2',
            'subject': 'Order for Hearing',
            'from': 'court@example.com',
            'timestamp': '2024-06-02T10:00:00',
        }]
        rv = client.get('/dashboard?filter=mydocs')
        assert b'(Mine)' in rv.data

@patch('app.ocr_pdf')
def test_my_events_filter(mock_ocr_pdf, client):
    signup(client, 'dave', 'dave@example.com', 'pw')
    login(client, 'dave', 'pw')
    with patch('app.load_emails') as mock_load_emails:
        mock_load_emails.return_value = [{
            'id': '3',
            'subject': 'Notice of Hearing',
            'from': 'court@example.com',
            'timestamp': '2024-06-03T10:00:00',
        }]
        rv = client.get('/dashboard?filter=myevents')
        assert b'(Mine)' in rv.data

def test_ics_download(client):
    signup(client, 'eve', 'eve@example.com', 'pw')
    login(client, 'eve', 'pw')
    # Simulate an ICS file exists
    ics_dir = '/app/ics'
    os.makedirs(ics_dir, exist_ok=True)
    ics_path = os.path.join(ics_dir, 'test_event.ics')
    with open(ics_path, 'w') as f:
        f.write('BEGIN:VCALENDAR\nEND:VCALENDAR')
    rv = client.get('/ics/test_event.ics')
    assert rv.status_code == 200
    assert b'VCALENDAR' in rv.data

def test_notifications_flow(client):
    signup(client, 'notifier', 'notify@example.com', 'pw')
    login(client, 'notifier', 'pw')
    user = User.query.filter_by(username='notifier').first()
    # Add a notification
    notif = Notification(user_id=user.id, type='test', message='Test notification')
    db.session.add(notif)
    db.session.commit()
    rv = client.get('/dashboard')
    assert b'Test notification' in rv.data
    # Mark all as read
    rv = client.post('/notifications/mark_all_read', follow_redirects=True)
    assert b'All notifications marked as read' in rv.data
    rv = client.get('/dashboard')
    assert b'Test notification' not in rv.data

def test_monitor_inbox_endpoint(client):
    signup(client, 'aiuser', 'aiuser@example.com', 'pw')
    login(client, 'aiuser', 'pw')
    user = User.query.filter_by(username='aiuser').first()
    ai = AIUser(user_id=user.id, name='AI', mode='full-auto')
    db.session.add(ai)
    db.session.commit()
    with patch('app.monitor_inbox_for_ai_user') as mock_task:
        rv = client.post(f'/ai_users/{ai.id}/monitor_inbox', follow_redirects=True)
        assert b'Inbox monitoring task started' in rv.data
        mock_task.delay.assert_called_once_with(ai.id, user_id=user.id) 