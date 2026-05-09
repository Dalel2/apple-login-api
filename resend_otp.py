import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def resend_otp(driver, method="iphone"):
    """
    This function clicks on the 'Resend code' button on the Apple page.
    method: "iphone" or "sms"
    """
    try:
        # Wait for the page to fully load
        time.sleep(2)
        
        # Selectors based on method
        if method == "sms":
            # For SMS, we need to open alternative options first if necessary
            try:
                # Look for the "Alternative options" or "Access problem" button
                alt_options_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#alt-options-btn .text"))
                )
                alt_options_btn.click()
                time.sleep(1)
            except (TimeoutException, NoSuchElementException):
                # If the button doesn't exist, continue
                pass
            
            # Now look for the button to send via SMS
            selectors = [
                (By.CSS_SELECTOR, ".popup-tooltip__divided-element:nth-child(1) .si-link > span"),
                (By.XPATH, "//button[contains(., 'Resend code via SMS')]"),
                (By.XPATH, "//button[contains(., 'Send SMS')]"),
                (By.XPATH, "//button[contains(., 'Send SMS')]"),
                (By.XPATH, "//button[contains(., 'Resend code') and contains(., 'SMS')]"),
                (By.XPATH, "//span[contains(., 'Resend code via SMS')]"),
                (By.XPATH, "//span[contains(., 'Send SMS')]")
            ]
        else:
            # For iPhone, directly look for the resend button
            selectors = [
                (By.CSS_SELECTOR, "#resend-code-link > .text"),
                (By.XPATH, "//button[contains(., 'Resend code to') and contains(., 'iPhone')]"),
                (By.XPATH, "//button[contains(., 'Send code to iPhone')]"),
                (By.XPATH, "//button[contains(., 'Resend code')]"),
                (By.XPATH, "//span[contains(., 'Resend code to') and contains(., 'iPhone')]"),
                (By.XPATH, "//span[contains(., 'Send code to iPhone')]"),
                (By.XPATH, "//span[contains(., 'Resend code')]")
            ]

        # Try each selector
        for by, selector in selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    time.sleep(2)
                    return True
            except (TimeoutException, NoSuchElementException):
                continue
        
        return False
        
    except Exception as e:
        print(f"Error in resend_otp: {e}")
        return False