import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

@pytest.fixture(scope="module")
def driver():
    driver = webdriver.Chrome(options=chrome_options)
    yield driver
    driver.quit()

def test_signup_and_login(driver):
    driver.get("http://localhost:5000/signup")
    time.sleep(1)
    driver.find_element(By.NAME, "username").send_keys("seleniumuser")
    driver.find_element(By.NAME, "email").send_keys("selenium@example.com")
    driver.find_element(By.NAME, "password").send_keys("testpass")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(1)
    # Debug: print page source after signup
    print("\n--- SIGNUP PAGE SOURCE ---\n", driver.page_source)
    # Assert no common error messages
    assert "already exists" not in driver.page_source
    assert "error" not in driver.page_source.lower()
    assert "Dashboard" in driver.page_source or "dashboard" in driver.current_url.lower()
    # Logout
    driver.find_element(By.LINK_TEXT, "Logout").click()
    time.sleep(1)
    # Login
    driver.get("http://localhost:5000/login")
    driver.find_element(By.NAME, "username").send_keys("seleniumuser")
    driver.find_element(By.NAME, "password").send_keys("testpass")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(1)
    assert "Dashboard" in driver.page_source or "dashboard" in driver.current_url.lower()

def test_dashboard_loads(driver):
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    assert "Recent Legal Documents" in driver.page_source
    assert "Upcoming Legal Events" in driver.page_source

def test_document_actions(driver):
    # Summarize, Ask, Analyze buttons (if any docs)
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    actions = driver.find_elements(By.XPATH, "//button[contains(@title, 'Summarize')]" )
    if actions:
        actions[0].click()
        time.sleep(1)
        assert "Task started" in driver.page_source or "Notification" in driver.page_source
    # Similar for Ask and Analyze
    ask_btns = driver.find_elements(By.XPATH, "//button[contains(@title, 'Ask')]" )
    if ask_btns:
        ask_btns[0].click()
        time.sleep(1)
        assert "Task started" in driver.page_source or "Notification" in driver.page_source
    analyze_btns = driver.find_elements(By.XPATH, "//button[contains(@title, 'Analyze')]" )
    if analyze_btns:
        analyze_btns[0].click()
        time.sleep(1)
        assert "Task started" in driver.page_source or "Notification" in driver.page_source

def test_share_document(driver):
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    share_forms = driver.find_elements(By.XPATH, "//form[contains(@action, '/share_document/')]")
    if share_forms:
        input_box = share_forms[0].find_element(By.NAME, "share_with")
        input_box.send_keys("teammate@example.com")
        share_forms[0].find_element(By.TAG_NAME, "button").click()
        time.sleep(1)
        assert "shared with" in driver.page_source

def test_notifications_and_mark_all_read(driver):
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    if "Notifications" in driver.page_source:
        mark_btns = driver.find_elements(By.XPATH, "//form[@action='/notifications/mark_all_read']//button")
        if mark_btns:
            mark_btns[0].click()
            time.sleep(1)
            assert "marked as read" in driver.page_source

def test_sync_to_google_calendar(driver):
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    sync_btns = driver.find_elements(By.XPATH, "//form[@action='/sync_calendar']//button")
    if sync_btns:
        sync_btns[0].click()
        time.sleep(1)
        assert "Google Calendar sync" in driver.page_source

def test_ai_user_monitor_inbox(driver):
    driver.get("http://localhost:5000/ai_users")
    time.sleep(1)
    monitor_btns = driver.find_elements(By.XPATH, "//form[contains(@action, '/monitor_inbox')]//button")
    if monitor_btns:
        monitor_btns[0].click()
        time.sleep(1)
        assert "Inbox monitoring task started" in driver.page_source

def test_logout(driver):
    driver.get("http://localhost:5000/dashboard")
    time.sleep(1)
    logout_links = driver.find_elements(By.LINK_TEXT, "Logout")
    if logout_links:
        logout_links[0].click()
        time.sleep(1)
        assert "Login" in driver.page_source 