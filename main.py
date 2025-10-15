# ============================
# main.py  —  Railway/Headless
# Sahra için: Kodun içine bol açıklama eklenmiştir.
# ============================
import json
import time
import random
import os
import requests

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
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
# Önce doğru olanı (scraperHelpers.py, büyük H) dene; olmazsa küçük h'li dosyaya düş.
try:
    from scraperHelpers import check_stock_zara, check_stock_bershka
except ModuleNotFoundError:
    from scraperhelpers import check_stock_zara, check_stock_bershka


# -----------------------------
# 1) CONFIG YÜKLEME
# -----------------------------
# Sahra: Burada config.json dosyasını okuyoruz. Yeni yapıda "her URL için ayrı beden listesi" var.
# Aşağıda örnek config.json şablonu verdim. Ona göre düzenlersen, kod link-bazlı beden arar.
with open("config.json", "r") as config_file:
    config = json.load(config_file)

# Eski global "sizes_to_check" kaldırıldı. Artık her URL için "sizes" alanı var.
urls_to_check       = config["urls"]
sleep_min_seconds   = config.get("sleep_min_seconds", 30)  # Sahra: varsayılanları güvenceye aldım
sleep_max_seconds   = config.get("sleep_max_seconds", 90)


# -----------------------------
# 2) ENV / TELEGRAM
# -----------------------------
load_dotenv()  # Sahra: .env varsa oradan da BOT_API/CHAT_ID alır (Railway Variables önceliklidir)

BOT_API  = os.getenv("BOT_API")
CHAT_ID  = os.getenv("CHAT_ID")

TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
print("TELEGRAM_ENABLED:", TELEGRAM_ENABLED)


# -----------------------------
# 3) TELEGRAM GÖNDERİM YARDIMCISI
# -----------------------------
def send_telegram_message(message: str):
    """
    Sahra: Telegram'a metin mesajı göndermek için tek nokta.
    BOT_API/CHAT_ID yoksa sessizce atlar; hata vermez.
    """
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
# 4) ORTAM/DRIVER YARDIMCILARI
# -----------------------------
def getenv_bool(name: str, default: bool=False) -> bool:
    """
    Sahra: Railway'de boolean env değerlerini çeşitli şekillerde True kabul etmek için.
    Örn: 1, true, yes, on hepsi True olur.
    """
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")

USE_SYSTEM_CHROME = getenv_bool("USE_SYSTEM_CHROME", False)  # Railway Variables'ta 1 yapmıştık.

def find_on_path(name: str):
    """PATH üzerinde verilen programın tam yolunu döndürür. Örn: chromedriver."""
    return shutil.which(name)  # bulunamazsa None döner

def exists_file(p: str) -> bool:
    """Verilen yol geçerli ve çalıştırılabilir bir dosya mı?"""
    return bool(p) and os.path.isfile(p) and os.access(p, os.X_OK)

def diag():
    """
    Sahra: Bu fonksiyon sadece teşhis amaçlı. Deploy loglarında ortamı hızlıca görebilmemiz için.
    İlk turda bir kez çalıştırıyoruz.
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
    Sahra: Sistem Chrome/Driver varsa onu kullanır; yoksa webdriver_manager ile indirir.
    Railway'de:
      - NIXPACKS_PKGS = "chromium chromium-driver fonts-liberation"
      - CHROME_BIN = "/usr/bin/chromium"
      - USE_SYSTEM_CHROME = "1"
    ayarlıysa sistemdekileri bulur.
    """
    chrome_options = Options()

    # Headless + konteyner güvenli bayraklar (bunlar şart)
    chrome_options.add_argument("--headless=new")                # yeni headless mod (stabil)
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")                  # container'da şart
    chrome_options.add_argument("--disable-dev-shm-usage")       # /dev/shm küçük, çakılmasın
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--remote-debugging-port=9222")  # headless kararlılığı artırır
    chrome_options.add_argument("--lang=tr-TR")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    if USE_SYSTEM_CHROME:
        # ENV'lerden oku; boş ise PATH'te ara (literal stringe düşmeyelim)
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
            # Not: binary_location set etmeden de çalışır; ama varsa set etmek iyi olur
            if CHROME_BIN:
                chrome_options.binary_location = CHROME_BIN  # sistem chromium'u belirt
            service = Service(ChromeDriverManager().install())
        else:
            chrome_options.binary_location = CHROME_BIN
            service = Service(CHROMEDRIVER_PATH)
    else:
        print("[DEBUG] Using WEBDRIVER_MANAGER")
        service = Service(ChromeDriverManager().install())

    print("[DEBUG] Starting ChromeDriver init…")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    print("[DEBUG] ChromeDriver READY")
    return driver


# -----------------------------
# 6) DURUM TAKİBİ ve NORMALİZASYON
# -----------------------------
# Sahra: Bildirimleri "ilk kez VAR" ve "YOK→VAR geçişinde" atmak için son durumları tutuyoruz.
last_status = {item["url"]: None for item in urls_to_check}

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
    # Sahra: İlk turda ortamı bir raporla (loglarda göreceğiz)
    diag()

    while True:
        # Her turda temiz bir driver aç (sayfa çakılmalarına karşı daha stabil)
        driver = build_driver()
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")
                sizes = item.get("sizes", [])  # ← ÖNEMLI: Link bazlı beden listesi

                print("--------------------------------")
                print(f"[DEBUG] GET {url} / Sizes={sizes}")

                try:
                    driver.get(url)

                    # Sayfa tam yüklensin (readyState=complete)
                    try:
                        WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        print("[WARN] readyState wait timed out")

                    # Mağaza türüne göre ilgili scraper'ı çağır
                    if store == "zara":
                        # Sahra: scraperHelpers içinde check_stock_zara(driver, sizes) olmalı
                        raw = check_stock_zara(driver, sizes)
                    elif store == "bershka":
                        raw = check_stock_bershka(driver, sizes)
                    else:
                        print("Unknown store, skipping:", store)
                        continue

                    # Dönüşü normalize et
                    found_sizes = normalize_found(raw)
                    currently_in_stock = bool(found_sizes)
                    was_in_stock       = last_status.get(url)

                    print(f"DEBUG found_sizes={found_sizes} was={was_in_stock} now={currently_in_stock}")

                    # Bildirim kriteri: ilk kez VAR veya YOK→VAR geçişi
                    should_notify = (
                        (was_in_stock is None and currently_in_stock) or  # ilk turda VAR
                        (was_in_stock is False and currently_in_stock)     # YOK→VAR
                    )

                    if currently_in_stock:
                        msg_sizes = ", ".join(found_sizes)
                        message = f"🛍️ Stok VAR: {msg_sizes}\n{url}"
                        print("ALERT:", message)
                        if should_notify:
                            send_telegram_message(message)
                    else:
                        # Sahra: Burada log ile bedenleri ve URL'i görürsün
                        print(f"No stock for {', '.join(sizes) if sizes else '(no sizes provided)'} @ {url}")

                    # Son durum kaydı
                    last_status[url] = currently_in_stock

                except Exception as e:
                    print(f"[ERROR] URL {url} hata: {e}")

                # ----------------------------------------------------------
                # Sahra: Aynı domaini art arda çok hızlı vurmamak için
                # URL'ler arası minik gecikme (varsayılan 1–2 sn).
                per_url_delay = int(os.getenv("PER_URL_DELAY", "2"))  # ← Railway/ENV’den yönetilebilir
                print(f"[DEBUG] Per-URL delay: {per_url_delay}s")      # ← Logda net gör
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
