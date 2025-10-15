# ============================
# main.py (REVIZE EDILMIS)
# ============================

import json
import time
import random
import os
import requests
# import pygame  # ← HEADLESS ortamda gerekli değil, çıkarıldı

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait

# ↓↓↓ EKLENDI: PATH üstünden program bulmak ve küçük yardımcılar için
import shutil
import platform

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
# (KALDIRILDI) Ses/Pygame bölümü
# Neden? Headless Railway ortamında ses çalma gereksiz ve pygame çoğu zaman çakışır.
# Eğer ileride masaüstünde lokal denemede sesi geri istersen, bu bloğu geri ekleyebiliriz.
# -----------------------------

# -----------------------------
# Telegram helper
# -----------------------------
def send_telegram_message(message: str):
    """Telegram'a basit metin mesajı gönderen yardımcı fonksiyon."""
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
# Kullanışlı: env bool okuma
# -----------------------------
def getenv_bool(name: str, default: bool=False) -> bool:
    """Ortam değişkenlerini 1/true/yes/on → True olarak okumak için yardımcı."""
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")

# -----------------------------
# Chrome / Driver ayarları
# -----------------------------
USE_SYSTEM_CHROME = getenv_bool("USE_SYSTEM_CHROME", False)

def find_on_path(name: str):
    """PATH üzerinde verilen programın tam yolunu döndürür. Örn: chromedriver."""
    return shutil.which(name)  # bulunamazsa None döner

def exists_file(p: str) -> bool:
    """Verilen yol geçerli ve çalıştırılabilir bir dosya mı?"""
    return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)

def diag():
    """Teşhis amaçlı: ortamı hızlıca raporla (loglarda görürsün)."""
    print("=== DIAG START ===")
    print("[DEBUG] Python:", platform.python_version())
    print("[DEBUG] OS:", platform.platform())
    print("[DEBUG] PATH:", os.getenv("PATH"))
    print("[DEBUG] USE_SYSTEM_CHROME:", os.getenv("USE_SYSTEM_CHROME"))
    print("[DEBUG] CHROME_BIN env:", os.getenv("CHROME_BIN"))
    print("[DEBUG] CHROMEDRIVER_PATH env:", os.getenv("CHROMEDRIVER_PATH"))
    print("[DEBUG] which chromium:", find_on_path("chromium"))
    print("[DEBUG] which google-chrome:", find_on_path("google-chrome"))
    print("[DEBUG] which chrome:", find_on_path("chrome"))
    print("[DEBUG] which chromedriver:", find_on_path("chromedriver"))
    print("=== DIAG END ===")

def build_driver():
    """Sistem Chrome/Driver varsa onu kullanır; yoksa webdriver_manager ile indirir."""
    chrome_options = Options()

    # Headless + konteyner güvenli bayraklar
    chrome_options.add_argument("--headless=new")                # ← yeni headless
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")                  # ← container'da şart
    chrome_options.add_argument("--disable-dev-shm-usage")       # ← /dev/shm küçük
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--remote-debugging-port=9222")  # ← headless kararlılık
    chrome_options.add_argument("--lang=tr-TR")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    if USE_SYSTEM_CHROME:
        # ↓↓↓ ÖNEMLI: ENV boşsa bile literal string'e düşmeyelim; önce PATH dene
        env_chrome = os.getenv("CHROME_BIN", "")
        env_driver = os.getenv("CHROMEDRIVER_PATH", "")

        CHROME_BIN = env_chrome or find_on_path("chromium") or find_on_path("google-chrome") or find_on_path("chrome")
        CHROMEDRIVER_PATH = env_driver or find_on_path("chromedriver")

        print("[DEBUG] Using SYSTEM chrome")
        print("[DEBUG] CHROME_BIN:", CHROME_BIN)
        print("[DEBUG] CHROMEDRIVER_PATH:", CHROMEDRIVER_PATH)

        # Eğer driver bulunamadıysa ya da dosya değilse güvenle webdriver_manager'a düş
        if not CHROME_BIN or not CHROMEDRIVER_PATH or not exists_file(CHROMEDRIVER_PATH):
            print("[WARN] System chromedriver bulunamadı -> webdriver_manager fallback")
            # NOT: Burada binary_location'ı set etmeyip, indirilen driver ile açacağız
            service = Service(ChromeDriverManager().install())
        else:
            chrome_options.binary_location = CHROME_BIN            # ← sistem chromium yolunu ver
            service = Service(CHROMEDRIVER_PATH)                   # ← sistem chromedriver'ı kullan
    else:
        print("[DEBUG] Using WEBDRIVER_MANAGER")
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
    """
    Helper: check_stock_* fonksiyonlarının döndürdüğünü tek tipe çevirir.
    - Liste/tuple/set ise string'lere çevir.
    - String ise boş değilse tek elemanlı liste yap.
    - True ise 'ANY' ekle.
    - Diğer durumlarda boş liste dön.
    """
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
if __name__ == "__main__":
    # ← Teşhis bloğunu ilk turda bir kez çalıştır; loglarda ortamı gör.
    diag()

    while True:
        driver = build_driver()  # ← Her tur yeni, temiz driver aç
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")

                print("--------------------------------")
                print(f"[DEBUG] GET {url}")
                try:
                    driver.get(url)

                    # Sayfa tam yüklensin (readyState=complete)
                    try:
                        WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        print("[WARN] readyState wait timed out")

                    # Mağaza türüne göre scraper çağır
                    if store == "zara":
                        # ← scraperHelpers.check_stock_zara(driver, sizes_to_check)
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
                            # Headless ortam: ses çalma çıkarıldı; sadece Telegram
                            send_telegram_message(message)
                    else:
                        print(f"No stock for {', '.join(sizes_to_check)} @ {url}")

                    # Son durum kaydı
                    last_status[url] = currently_in_stock

                except Exception as e:
                    print(f"[ERROR] URL {url} hata: {e}")

        finally:
            print("Closing the browser…")
            try:
                driver.quit()
            except Exception:
                pass

            # Tur arası bekleme
            sleep_time = random.randint(sleep_min_seconds, sleep_max_seconds)
            print(f"Sleeping for {sleep_time // 60} minutes and {sleep_time % 60} seconds…")
            time.sleep(sleep_time)
