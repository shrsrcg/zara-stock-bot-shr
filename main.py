# ============================
# main.py — Railway/Headless
# Sade: BOT_API/CHAT_ID, anti-bot, uzun bekleme+scroll, JSON fallback, net loglar
# ============================
import json
import time
import random
import os
import re
import requests
import logging

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# Teşhis yardımcıları
import shutil
import platform

# --- [HOTFIX] pygame STUB (headless'ta import kalsın diye) ---
import sys, types
if 'pygame' not in sys.modules:
    pygame_stub = types.ModuleType('pygame')
    pygame_stub.mixer = types.SimpleNamespace(init=lambda *a, **k: None)
    pygame_stub.music = types.SimpleNamespace(load=lambda *a, **k: None, play=lambda *a, **k: None)
    sys.modules['pygame'] = pygame_stub
# --- HOTFIX SONU ---

# Helper import (scraperHelpers.py içinde)
try:
    from scraperHelpers import check_stock_zara, check_stock_bershka
except ModuleNotFoundError:
    from scraperHelpers import check_stock_zara, check_stock_bershka


# -----------------------------
# 1) CONFIG YÜKLEME
# -----------------------------
with open("config.json", "r") as config_file:
    config = json.load(config_file)

urls_to_check     = config["urls"]
sleep_min_seconds = config.get("sleep_min_seconds", 30)
sleep_max_seconds = config.get("sleep_max_seconds", 90)

# YOK→VAR bildirim için son durum
last_status = {item["url"]: None for item in urls_to_check}


# -----------------------------
# 2) ENV / TELEGRAM
# -----------------------------
load_dotenv()  # .env varsa da okusun (Railway Variables önceliklidir)

# Standart: BOT_API + CHAT_ID
BOT_API  = os.getenv("BOT_API")
CHAT_ID  = os.getenv("CHAT_ID")
TELEGRAM_TEST_ON_START = os.getenv("TELEGRAM_TEST_ON_START", "True").strip().lower() == "true"

TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
print("TELEGRAM_ENABLED:", TELEGRAM_ENABLED)


# -----------------------------
# 3) TELEGRAM GÖNDERİM
# -----------------------------
def send_telegram_message(message: str):
    """
    VS sürümündeki gibi: data=payload (JSON değil), kısa timeout.
    """
    if not TELEGRAM_ENABLED:
        print("⚠️ Telegram message skipped (missing BOT_API or CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        r = requests.post(url, data=payload, timeout=10)
        print("[TG]", r.status_code, r.text[:200])
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[TG] send error: {e}")


# -----------------------------
# 4) TEŞHİS/DRIVER YARDIMCILARI
# -----------------------------
def find_on_path(name: str):
    return shutil.which(name)

def diag():
    print("=== DIAG START ===")
    print("[DEBUG] Python:", platform.python_version())
    print("[DEBUG] OS:", platform.platform())
    print("[DEBUG] PATH:", os.getenv("PATH"))
    print("[DEBUG] CHROME_BIN env:", os.getenv("CHROME_BIN"))
    print("[DEBUG] CHROMEDRIVER_PATH env:", os.getenv("CHROMEDRIVER_PATH"))
    print("[DEBUG] which chromium:", find_on_path("chromium"))
    print("[DEBUG] which google-chrome:", find_on_path("google-chrome"))
    print("[DEBUG] which chrome:", find_on_path("chrome"))
    print("[DEBUG] which chromedriver:", find_on_path("chromedriver"))
    print("=== DIAG END ===")

def build_driver():
    """
    Selenium Manager kullanır (chromedriver kendisi halleder).
    Anti-bot ayarları + webdriver izini gizleme.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument("--lang=tr-TR")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    # Anti-bot flags
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    env_chrome = os.getenv("CHROME_BIN", "")
    if env_chrome and os.path.isfile(env_chrome) and os.access(env_chrome, os.X_OK):
        chrome_options.binary_location = env_chrome
        print("[DEBUG] binary_location set:", env_chrome)

    print("[DEBUG] Using SELENIUM MANAGER")
    driver = webdriver.Chrome(options=chrome_options)

    # webdriver izini gizle
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    print("[DEBUG] ChromeDriver READY (Selenium Manager)")
    return driver


# -----------------------------
# 5) NORMALİZASYON + FALLBACK PARSER
# -----------------------------
def _clean_size_token(s: str) -> str:
    # "S / 36", "S(ONLINE)" vb. sadeleştir → "S" veya "36"
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("/", " ")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip()
    if " " in s:
        s = s.split()[0]
    return s

def normalize_found(res):
    def norm_list(lst):
        out = []
        for x in lst:
            t = _clean_size_token(str(x))
            if t:
                out.append(t)
        return list(dict.fromkeys(out))  # unique & order

    if isinstance(res, (list, tuple, set)):
        return norm_list(res)
    if isinstance(res, str):
        t = _clean_size_token(res)
        return [t] if t else []
    if res is True:
        return ["ANY"]
    return []

def extract_sizes_from_dom_or_json(driver):
    """
    1) DOM'daki beden butonlarını dene (scroll + farklı seçiciler + 30sn ısrar).
    2) Olmazsa script içi JSON'dan 'inStock' olanları çek.
    Dönen: ['S','M','34',...] ya da [].
    """
    # --- 1) DOM yolu ---
    selector_groups = [
        "[data-qa='size-selector'] button, .product-size-selector button, .size-selector button, li.size button, button.size",
        "button[aria-label*='Beden'], button[aria-label*='Size'], button[aria-label*='Talla']",
    ]

    deadline = time.time() + 30  # 30 sn'ye kadar ısrar et
    while time.time() < deadline:
        try:
            # biraz aşağı kaydır
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.35);")
        except Exception:
            pass
        for sel in selector_groups:
            btns = driver.find_elements("css selector", sel)
            found = []
            for b in btns:
                txt = (b.text or "").strip()
                if not txt:
                    try:
                        txt = (b.get_attribute("aria-label") or "").strip()
                    except Exception:
                        pass
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true")
                if txt and not disabled:
                    found.append(txt)
            if found:
                return normalize_found(found)
        time.sleep(1.0)

    # --- 2) JSON yolu ---
    sizes = set()
    scripts = driver.find_elements("css selector", "script")
    for s in scripts:
        try:
            blob = s.get_attribute("innerHTML") or ""
        except Exception:
            blob = ""
        if not blob:
            continue
        if not any(k in blob for k in ["sizes", "availability", "variants", "skus", "inStock", "stock"]):
            continue

        # "size/name":"S" yakınında inStock
        for m in re.finditer(r'"(size|name)"\s*:\s*"([^"]{1,6})".{0,120}?"(availability|inStock)"\s*:\s*(true|"inStock")',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))
        # "value/sizeCode" varyantı
        for m in re.finditer(r'"(value|sizeCode|sizeId)"\s*:\s*"([^"]{1,6})".{0,120}?"(availability|inStock)"\s*:\s*(true|"inStock")',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))

    return normalize_found(list(sizes))


# -----------------------------
# 6) ANA DÖNGÜ
# -----------------------------
if __name__ == "__main__":
    # Başlangıç testi (istemiyorsan Railway'de TELEGRAM_TEST_ON_START=False yap)
    if TELEGRAM_TEST_ON_START and TELEGRAM_ENABLED:
        send_telegram_message("✅ Bot çalıştı – Railway başlangıç testi.")

    diag()

    while True:
        driver = build_driver()
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")
                sizes = item.get("sizes", [])

                print("--------------------------------")
                print(f"[DEBUG] GET {url} / Sizes={sizes}")

                try:
                    driver.get(url)

                    # Cookie/popup kapat
                    try:
                        selectors = [
                            "button#onetrust-accept-btn-handler",
                            "button[data-qa='privacy-accept']",
                            "button[aria-label*='Kabul']",
                            ".ot-sdk-container #onetrust-accept-btn-handler",
                        ]
                        for sel in selectors:
                            els = driver.find_elements("css selector", sel)
                            if els:
                                try:
                                    els[0].click()
                                except Exception:
                                    pass
                                time.sleep(0.5)
                                break
                    except Exception as _e:
                        print("[COOKIE] ignore:", _e)

                    # readyState=complete
                    try:
                        WebDriverWait(driver, 20).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        print("[WARN] readyState wait timed out")

                    # 1) Scraper ham sonuç
                    if store == "zara":
                        raw = check_stock_zara(driver, sizes)
                    elif store == "bershka":
                        raw = check_stock_bershka(driver, sizes)
                    else:
                        print("Unknown store, skipping:", store)
                        continue

                    print(f"[SCRAPER RAW] store={store} raw={raw!r}")

                    # 2) DOM fallback (butonlardan)
                    fallback_btn = []
                    try:
                        btns = driver.find_elements(
                            "css selector",
                            "[data-qa='size-selector'] button, .size-selector button, .product-size-selector button, button.size, li.size button"
                        )
                        for b in btns:
                            txt = (b.text or "").strip()
                            cls = (b.get_attribute("class") or "").lower()
                            aria = (b.get_attribute("aria-disabled") or "").lower()
                            disabled = ("disabled" in cls) or (aria == "true")
                            if txt and not disabled:
                                fallback_btn.append(txt)
                    except Exception as _e:
                        print(f"[FALLBACK BTN] error: {_e}")

                    # 3) Normalize (önce scraper → boşsa DOM → hâlâ boşsa JSON)
                    found_sizes = normalize_found(raw)
                    if not found_sizes and fallback_btn:
                        print(f"[FALLBACK BTN] available -> {fallback_btn}")
                        found_sizes = normalize_found(fallback_btn)
                    if not found_sizes:
                        json_sizes = extract_sizes_from_dom_or_json(driver)
                        if json_sizes:
                            print(f"[FALLBACK JSON] sizes -> {json_sizes}")
                            found_sizes = json_sizes

                    # 4) Durum & log
                    currently_in_stock = bool(found_sizes)
                    was_in_stock       = last_status.get(url)
                    print(f"DEBUG found_sizes={found_sizes} was={was_in_stock} now={currently_in_stock}")

                    # 5) Eşleşen bedenleri çıkar (takip edilenlerle)
                    upper_sizes = [x.upper() for x in sizes]
                    matched = [s for s in found_sizes if s.upper() in upper_sizes]
                    to_announce = matched if matched else found_sizes

                    # 6) Bildirim: ilk VAR veya YOK→VAR
                    if currently_in_stock and to_announce:
                        if len(to_announce) == 1:
                            msg_sizes = f"{to_announce[0]} beden stokta!!!!"
                        else:
                            msg_sizes = f"{', '.join(to_announce)} beden stokta!!!!"
                        message = f"🛍️{msg_sizes}\nLink: {url}"

                        should_notify = (was_in_stock is None and currently_in_stock) or (was_in_stock is False and currently_in_stock)
                        print("ALERT:", message)
                        if should_notify:
                            send_telegram_message(message)
                    else:
                        print(f"No stock for {', '.join(sizes) if sizes else '(no sizes provided)'} @ {url}")

                    # 7) Son durumu güncelle
                    last_status[url] = currently_in_stock

                except Exception as e:
                    print(f"[ERROR] URL {url} hata: {e}")

                # URL'ler arası gecikme (nazik tarama)
                per_url_delay = int(os.getenv("PER_URL_DELAY", "2"))
                print(f"[DEBUG] Per-URL delay: {per_url_delay}s")
                time.sleep(per_url_delay)

        finally:
            print("Closing the browser…")
            try:
                driver.quit()
            except Exception:
                pass

            # Tur arası bekleme (config.json'dan)
            sleep_time = random.randint(sleep_min_seconds, sleep_max_seconds)
            print(f"Sleeping for {sleep_time // 60} minutes and {sleep_time % 60} seconds…")
            time.sleep(sleep_time)
