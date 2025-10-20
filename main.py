# ============================
# main.py  —  Railway/Headless
# Sahra için: Kodun içine bol açıklama eklenmiştir.
# ============================
import json
import time
import random
import os
import requests
import logging

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

# ↓↓↓ EKLENDI: PATH üstünden program bulmak ve teşhis (diagnostic) logları için yardımcılar
import shutil
import platform

# --- [HOTFIX 1] pygame STUB ---
# NEDEN: Başka bir dosyada (örn: scraperHelpers.py) yanlışlıkla 'import pygame' kalmış olabilir.
# Headless ortamda pygame yok; bu stub, 'pygame' adında boş bir modül enjekte eder ki çökmesin.
import sys, types  # ← sadece bu stub için kullanılıyor
if 'pygame' not in sys.modules:
    pygame_stub = types.ModuleType('pygame')
    pygame_stub.mixer = types.SimpleNamespace(
        init=lambda *a, **k: None
    )
    pygame_stub.music = types.SimpleNamespace(
        load=lambda *a, **k: None,
        play=lambda *a, **k: None
    )
    sys.modules['pygame'] = pygame_stub
# --- HOTFIX SONU ---

# Sahra: Bu helper'ları iki farklı dosya adı senaryosuna karşı güvenli import ediyoruz.
try:
    from scraperHelpers import check_stock_zara, check_stock_bershka
except ModuleNotFoundError:
    from scraperHelpers import check_stock_zara, check_stock_bershka


# -----------------------------
# 1) CONFIG YÜKLEME
# -----------------------------
# Sahra: Burada config.json dosyasını okuyoruz. Yeni yapıda "her URL için ayrı beden listesi" var.
with open("config.json", "r") as config_file:
    config = json.load(config_file)

# Eski global "sizes_to_check" kaldırıldı. Artık her URL için "sizes" alanı var.
urls_to_check       = config["urls"]
sleep_min_seconds   = config.get("sleep_min_seconds", 30)  # varsayılanları güvenceye aldım
sleep_max_seconds   = config.get("sleep_max_seconds", 90)

# Stok geçişini takip için basit bellek (YOK→VAR geçişinde bildirim)
last_status = {item["url"]: None for item in urls_to_check}


# -----------------------------
# 2) ENV / TELEGRAM
# -----------------------------
load_dotenv()  # .env varsa da okusun (Railway Variables önceliklidir)

# Not: Standart olarak BOT_API + CHAT_ID kullanıyoruz.
BOT_API  = os.getenv("BOT_API")
CHAT_ID  = os.getenv("CHAT_ID")

# Opsiyonel başlangıç testi için ortam bayrağı
TELEGRAM_TEST_ON_START = os.getenv("TELEGRAM_TEST_ON_START", "True").strip().lower() == "true"

# Telegram aktif mi?
TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
print("TELEGRAM_ENABLED:", TELEGRAM_ENABLED)

# -----------------------------
# 3) TELEGRAM GÖNDERİM YARDIMCISI
# -----------------------------
def send_telegram_message(message: str):
    """
    Eski VS sürümündekiyle aynı davranış:
    - BOT_API/CHAT_ID kullanır
    - form-data (data=...) gönderir
    - kısa timeout
    """
    if not TELEGRAM_ENABLED:
        print("⚠️ Telegram message skipped (missing BOT_API or CHAT_ID).")
        return

    url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        # ÖNEMLİ: eski kodda olduğu gibi data=... (JSON değil)
        r = requests.post(url, data=payload, timeout=10)
        print("[TG]", r.status_code, r.text[:200])
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[TG] send error: {e}")

# -----------------------------
# 4) ORTAM/DRIVER YARDIMCILARI
# -----------------------------
def getenv_bool(name: str, default: bool=False) -> bool:
    """
    Railway'de boolean env değerlerini çeşitli şekillerde True kabul etmek için.
    Örn: 1, true, yes, on hepsi True olur.
    """
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")

USE_SYSTEM_CHROME = getenv_bool("USE_SYSTEM_CHROME", False)  # İstersen kullanırsın

def find_on_path(name: str):
    """PATH üzerinde verilen programın tam yolunu döndürür. Örn: chromedriver."""
    return shutil.which(name)  # bulunamazsa None döner

def diag():
    """
    Deploy loglarında ortamı hızlıca görebilmemiz için ilk turda bir kez çalışır.
    """
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


# -----------------------------
# 5) CHROME/CHROMEDRIVER KURULUMU (HEADLESS)
# -----------------------------
def build_driver():
    """
    Selenium Manager kullan: sistemde chrome/driver olmasa da kendi indirir.
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

    # İsteğe bağlı: CHROME_BIN gerçekten geçerliyse kullan; yoksa set etme
    env_chrome = os.getenv("CHROME_BIN", "")
    if env_chrome and os.path.isfile(env_chrome) and os.access(env_chrome, os.X_OK):
        chrome_options.binary_location = env_chrome
        print("[DEBUG] binary_location set:", env_chrome)
    elif env_chrome:
        print("[WARN] CHROME_BIN var ama dosya yok/çalıştırılamıyor → yok sayılıyor")

    print("[DEBUG] Using SELENIUM MANAGER")
    driver = webdriver.Chrome(options=chrome_options)
    print("[DEBUG] ChromeDriver READY (Selenium Manager)")
    return driver


# -----------------------------
# 6) NORMALİZASYON
# -----------------------------
def normalize_found(res):
    """
    Helper: check_stock_* fonksiyonlarının döndürdüğünü tek tipe çevirir.
    - Liste/tuple/set ise string'lere çevir.
    - String ise boş değilse tek elemanlı liste yap.
    - True ise 'ANY' ekle (yani "herhangi bir boy var").
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
# 7) ANA DÖNGÜ
# -----------------------------
if __name__ == "__main__":
    # --- [STARTUP TEST MESAJI] ---
    if TELEGRAM_TEST_ON_START and TELEGRAM_ENABLED:
        send_telegram_message("✅ Bot çalıştı – Railway başlangıç testi.")
    # --- [END] ---

    # İlk turda ortam raporu
    diag()

    while True:
        # Her turda temiz bir driver aç (sayfa çakılmalarına karşı daha stabil)
        driver = build_driver()
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")
                sizes = item.get("sizes", [])  # ← ÖNEMLİ: Link bazlı beden listesi

                print("--------------------------------")
                print(f"[DEBUG] GET {url} / Sizes={sizes}")

                try:
                    driver.get(url)
                    # --- [ ZARA COOKIE/PAGE READY] ---
                    # 1) Çerez/popup kapatma (Zara farklı varyantlar kullanabiliyor)
                    try:
                        # Sık görülen Zara çerez buton seçicileri (biri tutar)
                        selectors = [
                            "button#onetrust-accept-btn-handler",
                            "button[data-qa='privacy-accept']",
                            "button[aria-label='Kabul et']",
                            "button.cookie-accept, .ot-sdk-container #onetrust-accept-btn-handler"
                        ]
                        for sel in selectors:
                            els = driver.find_elements("css selector", sel)
                            if els:
                                try: els[0].click()
                                except Exception: pass
                                time.sleep(0.5)
                                break
                    except Exception as _e:
                        print("[COOKIE] ignore:", _e)

                    # 2) Beden butonları DOM'a gelsin (maks 10 sn)
                    try:
                        WebDriverWait(driver, 10).until(
                            lambda d: d.find_elements(
                                "css selector",
                                "[data-qa='size-selector'] button, .size-selector button, .product-size-selector button, button.size, li.size button"
                            )
                        )
                    except Exception:
                        print("[WARN] size buttons not found within 10s")


                    # Sayfa tam yüklensin (readyState=complete)
                    try:
                        WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        print("[WARN] readyState wait timed out")

                    # Mağaza türüne göre ilgili scraper'ı çağır
                    # --- [ RAW LOG + FALLBACK] ---
                    print(f"[SCRAPER RAW] store={store} raw={raw!r}")

                    found_sizes = normalize_found(raw)

                    # Eğer scraper boş döndüyse hızlı bir fallback dene (Zara/Bershka common seçiciler)
                    if not found_sizes:
                        try:
                            # Genel buton seçicileri (Zara sık değişiyor)
                            btns = driver.find_elements("css selector", "[data-qa='size-selector'] button, .size-selector button, .product-size-selector button, button.size, li.size button")
                            tmp = []
                            for b in btns:
                                txt = (b.text or "").strip()
                                cls = (b.get_attribute("class") or "").lower()
                                aria = (b.get_attribute("aria-disabled") or "").lower()
                                disabled = ("disabled" in cls) or (aria == "true")
                                if txt and not disabled:
                                    tmp.append(txt)
                            if tmp:
                                print(f"[FALLBACK] available buttons -> {tmp}")
                                found_sizes = [s.strip() for s in tmp if s.strip()]
                        except Exception as _e:
                            print(f"[FALLBACK] error: {_e}")
                    

                    if store == "zara":
                        # scraperHelpers içinde check_stock_zara(driver, sizes) olmalı
                        raw = check_stock_zara(driver, sizes)
                    elif store == "bershka":
                        raw = check_stock_bershka(driver, sizes)
                        # --- [ADD - RAW LOG + FALLBACK] ---
                        print(f"[SCRAPER RAW] store={store} raw={raw!r}")

                        # İlk yorum: eski kod, butonlardan direkt beden adını topluyordu (başarılıydı)
                        # Eğer scraper boş dönerse, basit buton fallback dene:
                        fallback_sizes = []
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
                                    fallback_sizes.append(txt)
                        except Exception as _e:
                            print(f"[FALLBACK] error: {_e}")
                        # --- [END ADD] ---

                    else:
                        print("Unknown store, skipping:", store)
                        continue

                    # Dönüşü normalize et
                   # Dönüşü normalize et (önce scraper, boşsa fallback)
                    found_sizes = normalize_found(raw)
                    if not found_sizes and fallback_sizes:
                        print(f"[FALLBACK] available buttons -> {fallback_sizes}")
                        found_sizes = [s for s in fallback_sizes if s.strip()]

                    currently_in_stock = bool(found_sizes)
                    was_in_stock       = last_status.get(url)

                    print(f"DEBUG found_sizes={found_sizes} was={was_in_stock} now={currently_in_stock}")

                    # --- [STOCK NOTIFY EXACT MESSAGE] ---
                    # --- [UPDATE - MATCHED SIZES] ---
                    # İlgilenilen bedenle kesişim (config.json’daki "sizes")
                    matched = [s for s in found_sizes if (s in sizes) or (s.upper() in [x.upper() for x in sizes])]
                    if matched:
                        if len(matched) == 1:
                            msg_sizes = f"{matched[0]} beden stokta!!!!"
                        else:
                            msg_sizes = f"{', '.join(matched)} beden stokta!!!!"
                    else:
                        # matched boşsa yine de bulunduğu şekliyle yaz (fallback'ten '?' vs gelirse görürüz)
                        if len(found_sizes) == 1:
                            msg_sizes = f"{found_sizes[0]} beden stokta!!!!"
                        else:
                            msg_sizes = f"{', '.join(found_sizes)} beden stokta!!!!"
                            
                    if currently_in_stock:
                    # --- [UPDATE - MATCHED SIZES] ---
                    # config.json'daki takip edilen bedenlerle kesişimi alalım
                     upper_sizes = [x.upper() for x in sizes]
                     matched = [s for s in found_sizes if s.upper() in upper_sizes]

                    to_announce = matched if matched else found_sizes  # matched boşsa yine de görüneni basalım
                    if to_announce:
                        if len(to_announce) == 1:
                            msg_sizes = f"{to_announce[0]} beden stokta!!!!"
                        else:
                            msg_sizes = f"{', '.join(to_announce)} beden stokta!!!!"
                        message = f"🛍️{msg_sizes}\nLink: {url}"
                        # İlk turda VAR (was None) veya YOK→VAR geçişinde bildir
                        should_notify = (was_in_stock is None and currently_in_stock) or (was_in_stock is False and currently_in_stock)
                        print("ALERT:", message)
                        if should_notify:
                            send_telegram_message(message)
                    else:
                        print(f"No stock for {', '.join(sizes) if sizes else '(no sizes provided)'} @ {url}")

                    # Son durumu güncelle
                    last_status[url] = currently_in_stock

                except Exception as e:
                    print(f"[ERROR] URL {url} hata: {e}")

                # ----------------------------------------------------------
                # Aynı domaini art arda çok hızlı vurmamak için küçük gecikme
                per_url_delay = int(os.getenv("PER_URL_DELAY", "2"))  # Railway/ENV’den yönetilebilir
                print(f"[DEBUG] Per-URL delay: {per_url_delay}s")
                time.sleep(per_url_delay)
                # ----------------------------------------------------------

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
