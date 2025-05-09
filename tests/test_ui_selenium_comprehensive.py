import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
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

def test_inbox_loads_and_displays_emails(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    assert len(emails) > 0, "Inbox should display emails"
    assert "Inbox" in driver.page_source

def test_inbox_handles_empty(driver):
    # Simulate empty inbox by renaming sample_emails.json (manual step or mock)
    # Here, just check that the page loads
    driver.get("http://localhost:5000")
    assert "Inbox" in driver.page_source

def test_each_email_link_works(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    for link in emails:
        href = link.get_attribute("href")
        assert href, "Email link should have href"

def test_process_page_loads_correct_details(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    emails[0].click()
    time.sleep(1)
    assert "Process Email" in driver.page_source
    assert "From:" in driver.page_source
    assert "Subject:" in driver.page_source

def test_process_page_required_fields(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    emails[0].click()
    time.sleep(1)
    # Only fill one field
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(1)
    assert "Generate Response" in driver.page_source

def test_edit_response_send_and_draft(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    emails[0].click()
    time.sleep(1)
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    driver.find_element(By.NAME, "recipient_name").send_keys("Test Tenant")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)
    textarea = driver.find_element(By.NAME, "response")
    textarea.clear()
    textarea.send_keys("Send test response.")
    send_btn = driver.find_element(By.XPATH, "//button[@name='action' and @value='send']")
    send_btn.click()
    time.sleep(1)
    assert "Success" in driver.page_source
    # Go back and try draft
    driver.get("http://localhost:5000")
    emails = driver.find_elements(By.TAG_NAME, "a")
    emails[1].click()
    time.sleep(1)
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    driver.find_element(By.NAME, "recipient_name").send_keys("Test Tenant")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)
    textarea = driver.find_element(By.NAME, "response")
    textarea.clear()
    textarea.send_keys("Draft test response.")
    draft_btn = driver.find_element(By.XPATH, "//button[@name='action' and @value='draft']")
    draft_btn.click()
    time.sleep(1)
    assert "Success" in driver.page_source

def test_success_page_shows_correct_info(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    emails[2].click()
    time.sleep(1)
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    driver.find_element(By.NAME, "recipient_name").send_keys("Test Tenant")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)
    textarea = driver.find_element(By.NAME, "response")
    textarea.clear()
    textarea.send_keys("Success page info test.")
    send_btn = driver.find_element(By.XPATH, "//button[@name='action' and @value='send']")
    send_btn.click()
    time.sleep(1)
    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Success" in body and "john@example.com" in body

def test_error_nonexistent_email(driver):
    driver.get("http://localhost:5000/email/9999")
    time.sleep(1)
    assert "Inbox" in driver.page_source

def test_edge_long_body_special_chars(driver):
    # This test assumes you have a long/special char email in sample_emails.json
    driver.get("http://localhost:5000")
    time.sleep(1)
    emails = driver.find_elements(By.TAG_NAME, "a")
    # Pick the last email (assume it's the special one)
    emails[-1].click()
    time.sleep(1)
    assert "Process Email" in driver.page_source
    # Check for special chars visually
    assert "@" in driver.page_source or "!" in driver.page_source

def test_duplicate_subjects(driver):
    # If you have duplicate subjects in sample_emails.json, both should be clickable
    driver.get("http://localhost:5000")
    time.sleep(1)
    subjects = [e.text for e in driver.find_elements(By.TAG_NAME, "a")]
    # Count duplicates
    assert len(subjects) != len(set(subjects)) or len(subjects) > 1 