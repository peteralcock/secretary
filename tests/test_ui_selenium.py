import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options

# You may need to adjust this if using Firefox or another browser
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

def test_end_to_end_ui():
    driver = webdriver.Chrome(options=chrome_options)
    driver.get("http://localhost:5000")
    time.sleep(1)

    # Click the first email link
    email_links = driver.find_elements(By.TAG_NAME, "a")
    assert email_links, "No email links found on inbox page"
    email_links[0].click()
    time.sleep(1)

    # Fill in the name fields and submit
    your_name = driver.find_element(By.NAME, "your_name")
    recipient_name = driver.find_element(By.NAME, "recipient_name")
    your_name.send_keys("Test Manager")
    recipient_name.send_keys("Test Tenant")
    driver.find_element(By.TAG_NAME, "button").click()
    time.sleep(2)

    # Edit the response and submit as draft
    textarea = driver.find_element(By.NAME, "response")
    textarea.clear()
    textarea.send_keys("This is a test response.")
    draft_btn = driver.find_element(By.XPATH, "//button[@name='action' and @value='draft']")
    draft_btn.click()
    time.sleep(1)

    # Check for success message
    body = driver.find_element(By.TAG_NAME, "body").text
    assert "Success" in body and "drafted" in body, "Success message not found"
    driver.quit()

if __name__ == "__main__":
    test_end_to_end_ui() 