import json
import time
import random
import os
import requests
import pygame

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait

from scraperHelpers import check_stock_zara, check_stock_bershka

# -----------------------------
# Config yükle
# -----------------------------
with open("config.json", "r") as config_file:
    config = json.load(config_file)

urls_to_check       = config["urls"]
sizes_to_check      = config["sizes_to_check"]
sleep_min_seconds   = config["sleep_min_seconds"]
sleep_max_seconds   = config["sleep_max_seconds"]

# -----------------------------
# Env / Telegram
# -----------------------------
load_dotenv()
BOT_API  = os.getenv("BOT_API")
CHAT_ID  = os.getenv("CHAT_ID")

TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
print("TELEGRAM_ENABLED:", TELEGRAM_ENABLED)

# -----------------------------
# Ses (Railway için güvenli)
# -----------------------------

import os
import pygame

DISABLE_SOUND = os.getenv("DISABLE_SOUND", "0") == "1"

try:
    if not DISABLE_SOUND:
        pygame.mixer.init()
        print("Sound: enabled")
    else:
        print("Sound: disabled by env")
except Exception as e:
    print(f"Sound init failed, disabling sound: {e}")
    DISABLE_SOUND = True

def play_sound(sound_file: str):
    if DISABLE_SOUND:
        return
    try:
        pygame.mixer.music.load(sound_file)
        pygame.mixer.music.play()
    except Exception as e:
        print(f"[WARN] play_sound error: {e}")

# -----------------------------
# Telegram helper
# -----------------------------
def send_telegram_message(message: str):
    if not TELEGRAM_ENABLED:
        print("⚠️ Telegram message skipped (missing BOT_API or CHAT_ID).")
        return
    url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=12)
        print("[TG]", r.status_code, r.text[:120])
        r.raise_for_status()
    except Exception as e:
        print(f"[TG] send error: {e}")

# -----------------------------
# Chrome / Driver ayarları
# -----------------------------
USE_SYSTEM_CHROME = os.getenv("USE_SYSTEM_CHROME", "0") == "1"

def build_driver():
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    import os

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--remote-debugging-port=9222")

    if USE_SYSTEM_CHROME:
        CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium")
        CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        chrome_options.binary_location = CHROME_BIN
        print("[DEBUG] Using SYSTEM chrome")
        print("[DEBUG] CHROME_BIN:", CHROME_BIN)
        print("[DEBUG] CHROMEDRIVER_PATH:", CHROMEDRIVER_PATH)
        service = Service(CHROMEDRIVER_PATH)
    else:
        print("[DEBUG] Using WEBDRIVER_MANAGER")
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())

    print("[DEBUG] Starting ChromeDriver init…")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("[DEBUG] ChromeDriver READY")
    return driver

# -----------------------------
# Basit durum takibi (ilk VAR ve YOK→VAR'ta bildir)
# -----------------------------
last_status = {item["url"]: None for item in urls_to_check}

def normalize_found(res):
    # helper, check_stock_* dönüşlerini tek tipe toplar
    if isinstance(res, (list, tuple, set)):
        return [str(x) for x in res if str(x).strip()]
    if isinstance(res, str):
        return [res] if res.strip() else []
    if res is True:
        return ["ANY"]
    return []

# -----------------------------
# Döngü
# -----------------------------
while True:
    driver = build_driver()
    try:
        for item in urls_to_check:
            url   = item.get("url")
            store = item.get("store")

            print("--------------------------------")
            print(f"[DEBUG] GET {url}")
            try:
                driver.get(url)
                # sayfa tam yüklensin
                try:
                    WebDriverWait(driver, 15).until(
                        lambda d: d.execute_script("return document.readyState") == "complete"
                    )
                except Exception:
                    print("[WARN] readyState wait timed out")

                if store == "zara":
                    raw = check_stock_zara(driver, sizes_to_check)
                elif store == "bershka":
                    raw = check_stock_bershka(driver, sizes_to_check)
                else:
                    print("Unknown store, skipping:", store)
                    continue

                found_sizes = normalize_found(raw)
                currently_in_stock = bool(found_sizes)
                was_in_stock       = last_status.get(url)

                print(f"DEBUG found_sizes={found_sizes} was={was_in_stock} now={currently_in_stock}")

                should_notify = (
                    (was_in_stock is None and currently_in_stock) or  # ilk turda VAR
                    (was_in_stock is False and currently_in_stock)     # YOK→VAR
                )

                if currently_in_stock:
                    msg_sizes = ", ".join(found_sizes)
                    message = f"🛍️ Stok VAR: {msg_sizes}\n{url}"
                    print("ALERT:", message)
                    if should_notify:
                        play_sound('Crystal.mp3')
                        send_telegram_message(message)
                else:
                    print(f"No stock for {', '.join(sizes_to_check)} @ {url}")

                last_status[url] = currently_in_stock

            except Exception as e:
                print(f"[ERROR] URL {url} hata: {e}")

    finally:
        print("Closing the browser…")
        try:
            driver.quit()
        except Exception:
            pass

        # Sleep
        sleep_time = random.randint(sleep_min_seconds, sleep_max_seconds)
        print(f"Sleeping for {sleep_time // 60} minutes and {sleep_time % 60} seconds…")
        time.sleep(sleep_time)
