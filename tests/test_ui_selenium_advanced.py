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

def test_navigate_back_to_inbox(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    email_links = driver.find_elements(By.TAG_NAME, "a")
    email_links[0].click()
    time.sleep(1)
    back_link = driver.find_element(By.LINK_TEXT, "Back to Inbox")
    back_link.click()
    time.sleep(1)
    assert "Inbox" in driver.page_source

def test_send_email_action(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    email_links = driver.find_elements(By.TAG_NAME, "a")
    email_links[1].click()
    time.sleep(1)
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    driver.find_element(By.NAME, "recipient_name").send_keys("Test Tenant")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)
    textarea = driver.find_element(By.NAME, "response")
    textarea.clear()
    textarea.send_keys("This is a send test response.")
    send_btn = driver.find_element(By.XPATH, "//button[@name='action' and @value='send']")
    send_btn.click()
    time.sleep(1)
    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Success" in body and "Sended" in body or "Sended".lower() in body.lower() or "sent" in body.lower()

def test_nonexistent_email(driver):
    driver.get("http://localhost:5000/email/9999")
    time.sleep(1)
    # Should redirect to inbox and flash message
    assert "Inbox" in driver.page_source

def test_missing_fields(driver):
    driver.get("http://localhost:5000")
    time.sleep(1)
    email_links = driver.find_elements(By.TAG_NAME, "a")
    email_links[2].click()
    time.sleep(1)
    # Only fill one field
    driver.find_element(By.NAME, "your_name").send_keys("Test Manager")
    # Try to submit without recipient_name
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(1)
    # Should still be on the form page
    assert "Generate Response" in driver.page_source 