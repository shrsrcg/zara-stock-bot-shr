# ============================
# main.py — Railway/Headless (Rev. Sahra)
# - Headless Chrome (Selenium Manager)
# - Telegram: ayrıntılı log + diag + timeouts
# - DOM+JSON fallback parser, uzun bekleme + scroll
# - Case-insensitive beden eşleştirme
# - Edge-only veya Always-notify seçeneği
# - Cooldown (spam önleme)
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
# 0) LOGGING
# -----------------------------
# Railway loglarında daha okunur; INFO yeterli, hata/istina ayrıntılarını da gösterelim.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# -----------------------------
# 1) CONFIG YÜKLEME
# -----------------------------
with open("config.json", "r", encoding="utf-8") as config_file:
    config = json.load(config_file)

urls_to_check     = config["urls"]
sleep_min_seconds = config.get("sleep_min_seconds", 30)
sleep_max_seconds = config.get("sleep_max_seconds", 90)

# Son durum & cooldown saatleri
last_status = {item["url"]: None for item in urls_to_check}  # YOK/VAR edge takibi
next_allowed = {item["url"]: 0 for item in urls_to_check}    # cooldown zaman damgası (epoch sn)

# -----------------------------
# 2) ENV / TELEGRAM
# -----------------------------
load_dotenv()  # .env varsa da oku (Railway Variables önceliklidir)

BOT_API  = os.getenv("BOT_API", "").strip()
CHAT_ID  = os.getenv("CHAT_ID", "").strip()

TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
TELEGRAM_TEST_ON_START = os.getenv("TELEGRAM_TEST_ON_START", "false").strip().lower() in ("1","true","yes","on")
TELEGRAM_DIAG = os.getenv("TELEGRAM_DIAG", "0").strip().lower() in ("1","true","yes","on")

ALWAYS_NOTIFY_ON_TRUE = os.getenv("ALWAYS_NOTIFY_ON_TRUE", "0").strip().lower() in ("1","true","yes","on")
NOTIFY_EMPTY_RAW = os.getenv("NOTIFY_EMPTY_RAW", "0").strip().lower() in ("1","true","yes","on")
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "0"))
PER_URL_DELAY = int(os.getenv("PER_URL_DELAY", "2"))

log.info("TELEGRAM_ENABLED: %s", TELEGRAM_ENABLED)

# -----------------------------
# 3) TELEGRAM YARDIMCILAR
# -----------------------------
def send_telegram_message(text: str, parse_mode: str | None = None) -> bool:
    """
    Ayrıntılı log + timeout + hata görünürlüğü.
    """
    if not TELEGRAM_ENABLED:
        log.warning("⚠️ Telegram atlanıyor: BOT_API/CHAT_ID eksik")
        return False

    url = f"https://api.telegram.org/bot{BOT_API}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = requests.post(url, data=payload, timeout=10)
        log.info("[TG] status=%s body=%s", r.status_code, r.text[:500])
        if r.ok:
            return True
        log.error("[TG] Gönderim başarısız: %s", r.text)
        return False
    except Exception as e:
        log.exception("[TG] İstisna: %s", e)
        return False


def telegram_diag() -> None:
    """
    Token ve chat doğrulama + test mesajı (TELEGRAM_DIAG=1 ise).
    """
    if not TELEGRAM_DIAG:
        return
    if not TELEGRAM_ENABLED:
        log.warning("[TG-DIAG] BOT_API/CHAT_ID eksik")
        return
    try:
        me = requests.get(f"https://api.telegram.org/bot{BOT_API}/getMe", timeout=10)
        log.info("[TG-DIAG] getMe %s %s", me.status_code, me.text[:500])

        gc = requests.get(f"https://api.telegram.org/bot{BOT_API}/getChat",
                          params={"chat_id": CHAT_ID}, timeout=10)
        log.info("[TG-DIAG] getChat %s %s", gc.status_code, gc.text[:500])

        ok = send_telegram_message("🔔 Telegram DIAG: bot ayakta (Railway).")
        log.info("[TG-DIAG] test send ok=%s", ok)
    except Exception as e:
        log.exception("[TG-DIAG] İstisna: %s", e)

# -----------------------------
# 4) TEŞHİS / DRIVER
# -----------------------------
def find_on_path(name: str):
    return shutil.which(name)

def diag():
    log.info("=== DIAG START ===")
    log.info("[DEBUG] Python: %s", platform.python_version())
    log.info("[DEBUG] OS: %s", platform.platform())
    log.info("[DEBUG] PATH: %s", os.getenv("PATH"))
    log.info("[DEBUG] CHROME_BIN env: %s", os.getenv("CHROME_BIN"))
    log.info("[DEBUG] CHROMEDRIVER_PATH env: %s", os.getenv("CHROMEDRIVER_PATH"))
    log.info("[DEBUG] which chromium: %s", find_on_path("chromium"))
    log.info("[DEBUG] which google-chrome: %s", find_on_path("google-chrome"))
    log.info("[DEBUG] which chrome: %s", find_on_path("chrome"))
    log.info("[DEBUG] which chromedriver: %s", find_on_path("chromedriver"))
    log.info("=== DIAG END ===")

def build_driver():
    """
    Selenium Manager kullanır (chromedriver'ı kendisi halleder).
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
        log.info("[DEBUG] binary_location set: %s", env_chrome)

    log.info("[DEBUG] Using SELENIUM MANAGER")
    driver = webdriver.Chrome(options=chrome_options)

    # webdriver izini gizle
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    log.info("[DEBUG] ChromeDriver READY (Selenium Manager)")
    return driver

# -----------------------------
# 5) NORMALİZASYON + PARSER
# -----------------------------
def _clean_size_token(s: str) -> str:
    # "S / 36", "S(ONLINE)" → "S" / "36"
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("/", " ")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip()
    if " " in s:
        s = s.split()[0]
    return s

def normalize_found(res):
    """
    Çeşitli formatlardan ['S','M','34'] listesine indirger, tekilleştirir (orijinal sırayı korur).
    """
    def norm_list(lst):
        out = []
        seen = set()
        for x in lst:
            t = _clean_size_token(str(x))
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    if isinstance(res, (list, tuple, set)):
        return norm_list(res)
    if isinstance(res, str):
        t = _clean_size_token(res)
        return [t] if t else []
    if res is True:
        return ["ANY"]
    return []

SIZE_TOKEN_RE = re.compile(r"\b(3[0-9]|4[0-9]|xxs|xs|s|m|l|xl|xxl|xxxl)\b", re.I)

def fallback_sizes_from_text(text: str) -> list[str]:
    """
    Kaba fallback: sayfa metninden olası beden tokenlarını topla.
    """
    tokens = SIZE_TOKEN_RE.findall(text or "")
    uniq = []
    seen = set()
    for t in tokens:
        n = t.lower()
        if n not in seen:
            seen.add(n)
            disp = t.upper() if not t.isdigit() else t
            uniq.append(disp)
    return uniq

def extract_sizes_with_fallback(driver) -> list[str]:
    """
    1) DOM: beden butonlarını ara (birkaç selector grubu + scroll + ~30sn sabır)
    2) JSON: script içinde inStock/availability = true
    3) TEXT: kaba token çıkarımı
    """
    selector_groups = [
        "[data-qa='size-selector'] button, .product-size-selector button, .size-selector button, li.size button, button.size",
        "button[aria-label*='Beden'], button[aria-label*='Size'], button[aria-label*='Talla']",
    ]

    deadline = time.time() + 30
    while time.time() < deadline:
        try:
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

    # JSON yolu
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

        # "size/name":"S" ... "inStock":true
        for m in re.finditer(r'"(size|name)"\s*:\s*"([^"]{1,6})".{0,120}?"(availability|inStock)"\s*:\s*(true|"inStock")',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))
        # "value/sizeCode" varyantı
        for m in re.finditer(r'"(value|sizeCode|sizeId)"\s*:\s*"([^"]{1,6})".{0,120}?"(availability|inStock)"\s*:\s*(true|"inStock")',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))

    if sizes:
        return normalize_found(list(sizes))

    # TEXT fallback
    return fallback_sizes_from_text(driver.page_source or "")

# -----------------------------
# 6) KARAR & BİLDİRİM
# -----------------------------
def _norm_size(x: str) -> str:
    return (x or "").strip().casefold()  # case-insensitive karşılaştırma

def _norm_list(xs):
    return sorted({_norm_size(x) for x in xs or []})

def decide_and_notify(url: str,
                      wanted_sizes: list[str],
                      found_sizes: list[str],
                      was_available: bool | None,
                      always_notify_on_true: bool,
                      now_ts: int,
                      cooldown_seconds: int) -> bool:
    """
    - stok var mı? (wanted ∩ found != ∅; wanted boşsa found != ∅)
    - cooldown doldu mu?
    - edge-only mı / her True'da mı bildirelim?
    Döner: (mesaj gönderildi mi)
    """
    w = _norm_list(wanted_sizes)
    f = _norm_list(found_sizes)

    # Wanted boşsa 'herhangi beden' demek → stok: found non-empty
    if w:
        intersection = sorted(set(w).intersection(set(f)))
        now_available = len(intersection) > 0
    else:
        intersection = f[:]  # bilgi için
        now_available = len(f) > 0

    log.info("[-DECIDE-] wanted=%s found=%s -> intersect=%s now=%s was=%s",
             w, f, intersection, now_available, was_available)

    if not now_available:
        return False

    # Cooldown kontrolü (spam önleme)
    if now_ts < next_allowed.get(url, 0):
        log.info("[NOTIFY] cooldown aktif -> atlanıyor (url=%s)", url)
        return False

    should_send = always_notify_on_true or (was_available in (None, False))
    if not should_send:
        log.info("[NOTIFY] atlandı: already True & always_notify_on_true=False")
        return False

    # Mesaj metni
    display_wanted = wanted_sizes if wanted_sizes else ["(herhangi)"]
    display_found = found_sizes if found_sizes else ["(bilinmiyor)"]
    if intersection:
        match_disp = ", ".join(sorted({x.upper() for x in intersection}))
    else:
        # wanted boşsa intersection = tüm found; görsellik için
        match_disp = ", ".join(sorted({x.upper() for x in display_found}))

    msg = (
        "🟢 *STOK VAR*\n"
        f"URL: {url}\n"
        f"Aranan bedenler: {', '.join(display_wanted)}\n"
        f"Bulunan bedenler: {', '.join(display_found)}\n"
        f"Eşleşen: {match_disp}"
    )
    ok = send_telegram_message(msg, parse_mode="Markdown")
    if ok and cooldown_seconds > 0:
        next_allowed[url] = now_ts + cooldown_seconds
        log.info("[NOTIFY] cooldown set: url=%s until=%s (+%ss)", url, next_allowed[url], cooldown_seconds)
    return ok

# -----------------------------
# 7) YARDIMCI: Cookie/Popup kapatma
# -----------------------------
def dismiss_overlays(driver):
    """
    Yaygın cookie/popup butonları için hızlı tıklama.
    Sessizce dener, hata olsa da akışı bozmaz.
    """
    selectors = [
        "button#onetrust-accept-btn-handler",
        "button[data-qa='privacy-accept']",
        "button[aria-label*='Kabul']",
        ".ot-sdk-container #onetrust-accept-btn-handler",
        "button[aria-label*='Accept']",
    ]
    for sel in selectors:
        try:
            els = driver.find_elements("css selector", sel)
            if els:
                try:
                    els[0].click()
                    time.sleep(0.4)
                    log.info("[COOKIE] clicked: %s", sel)
                    break
                except Exception:
                    pass
        except Exception:
            pass

# -----------------------------
# 8) ANA DÖNGÜ
# -----------------------------
if __name__ == "__main__":
    # Başlangıç testi (kapalı tutuyoruz; istersen env ile aç)
    if TELEGRAM_TEST_ON_START and TELEGRAM_ENABLED:
        send_telegram_message("✅ Bot çalıştı – Railway başlangıç testi.")

    diag()
    telegram_diag()  # TELEGRAM_DIAG=1 ise token/chat doğrular + test atar

    while True:
        driver = build_driver()
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")
                sizes = item.get("sizes", [])  # takip edilen bedenler (boşsa 'herhangi')

                log.info("--------------------------------")
                log.info("[DEBUG] GET %s / Sizes=%s", url, sizes)

                try:
                    driver.get(url)

                    # Cookie/popup kapat
                    dismiss_overlays(driver)

                    # readyState=complete
                    try:
                        WebDriverWait(driver, 20).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        log.warning("[WARN] readyState wait timed out")

                    # 1) Primary scraper (senin helper fonksiyonların)
                    if store == "zara":
                        raw = check_stock_zara(driver, sizes)
                    elif store == "bershka":
                        raw = check_stock_bershka(driver, sizes)
                    else:
                        log.warning("Unknown store, skipping: %s", store)
                        continue

                    log.info("[SCRAPER RAW] store=%s raw=%r", store, raw)

                    # 2) Normalize primary
                    found_sizes = normalize_found(raw)

                    # 3) Fallback DOM/JSON (primary boş ise)
                    if not found_sizes:
                        # DOM buttons (hızlı)
                        try:
                            btns = driver.find_elements(
                                "css selector",
                                "[data-qa='size-selector'] button, .size-selector button, .product-size-selector button, button.size, li.size button"
                            )
                            fallback_btn = []
                            for b in btns:
                                txt = (b.text or "").strip()
                                cls = (b.get_attribute("class") or "").lower()
                                aria = (b.get_attribute("aria-disabled") or "").lower()
                                disabled = ("disabled" in cls) or (aria == "true")
                                if txt and not disabled:
                                    fallback_btn.append(txt)
                            if fallback_btn:
                                log.info("[FALLBACK BTN] available -> %s", fallback_btn)
                                found_sizes = normalize_found(fallback_btn)
                        except Exception as _e:
                            log.warning("[FALLBACK BTN] error: %s", _e)

                    if not found_sizes:
                        json_sizes = extract_sizes_with_fallback(driver)
                        if json_sizes:
                            log.info("[FALLBACK JSON/TEXT] sizes -> %s", json_sizes)
                            found_sizes = json_sizes

                    # 4) Durum & log
                    currently_in_stock = bool(found_sizes)
                    was_in_stock       = last_status.get(url)
                    log.info("DEBUG found_sizes=%s was=%s now=%s", found_sizes, was_in_stock, currently_in_stock)

                    # 5) Eşleşen bedenleri çıkar (takip edilenlerle)
                    #   - karşılaştırma case-insensitive yapılır
                    upper_sizes = [x.upper() for x in sizes]
                    matched = [s for s in found_sizes if s.upper() in upper_sizes] if sizes else found_sizes[:]
                    to_announce = matched if matched else (found_sizes if sizes else found_sizes)

                    # 6) Bildirim kararı
                    now_ts = int(time.time())
                    if NOTIFY_EMPTY_RAW and not found_sizes:
                        send_telegram_message(f"⚠️ Parser boş döndü (muhtemel DOM değişimi):\n{url}")

                    sent = decide_and_notify(
                        url=url,
                        wanted_sizes=sizes,
                        found_sizes=found_sizes,
                        was_available=was_in_stock,
                        always_notify_on_true=ALWAYS_NOTIFY_ON_TRUE,
                        now_ts=now_ts,
                        cooldown_seconds=COOLDOWN_SECONDS
                    )

                    if not currently_in_stock:
                        log.info("No stock for %s @ %s", (', '.join(sizes) if sizes else '(any)'), url)

                    # 7) Son durumu güncelle
                    last_status[url] = currently_in_stock

                except Exception as e:
                    log.exception("[ERROR] URL %s hata: %s", url, e)

                # URL'ler arası gecikme (nazik tarama)
                log.info("[DEBUG] Per-URL delay: %ss", PER_URL_DELAY)
                time.sleep(PER_URL_DELAY)

        finally:
            log.info("Closing the browser…")
            try:
                driver.quit()
            except Exception:
                pass

            # Tur arası bekleme (config.json'dan)
            sleep_time = random.randint(sleep_min_seconds, sleep_max_seconds)
            log.info("Sleeping for %d minutes and %d seconds…", sleep_time // 60, sleep_time % 60)
            time.sleep(sleep_time)
