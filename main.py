# ============================
# main.py — Railway/Headless (Rev. Sahra • helpers uyumlu)
# - Helpers (Zara/Bershka) birincil kaynak
# - Opsiyonel DOM teyidi (REQUIRE_DOM_CONFIRM)
# - JSON/TEXT fallback sadece helpers boş dönerse
# - Yalnızca EŞLEŞEN bedenler bildirimi (sade mesaj)
# - Always-notify / edge-only + Cooldown
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

import shutil
import platform
import sys, types

# --- [HOTFIX] pygame STUB (headless'ta import kalsın diye) ---
if 'pygame' not in sys.modules:
    pygame_stub = types.ModuleType('pygame')
    pygame_stub.mixer = types.SimpleNamespace(init=lambda *a, **k: None)
    pygame_stub.music = types.SimpleNamespace(load=lambda *a, **k: None, play=lambda *a, **k: None)
    sys.modules['pygame'] = pygame_stub
# --- HOTFIX SONU ---

# Helpers (Zara/Bershka)
try:
    from scraperHelpers import check_stock_zara, check_stock_bershka
except ModuleNotFoundError:
    from scraperHelpers import check_stock_zara, check_stock_bershka

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# -----------------------------
# CONFIG
# -----------------------------
with open("config.json", "r", encoding="utf-8") as config_file:
    config = json.load(config_file)

urls_to_check     = config["urls"]
sleep_min_seconds = config.get("sleep_min_seconds", 30)
sleep_max_seconds = config.get("sleep_max_seconds", 90)

last_status  = {item["url"]: None for item in urls_to_check}  # YOK/VAR edge takibi
next_allowed = {item["url"]: 0 for item in urls_to_check}     # cooldown epoch sn

# -----------------------------
# ENV
# -----------------------------
load_dotenv()

BOT_API  = os.getenv("BOT_API", "").strip()
CHAT_ID  = os.getenv("CHAT_ID", "").strip()

TELEGRAM_ENABLED = bool(BOT_API and CHAT_ID)
TELEGRAM_TEST_ON_START = os.getenv("TELEGRAM_TEST_ON_START", "false").strip().lower() in ("1","true","yes","on")
TELEGRAM_DIAG = os.getenv("TELEGRAM_DIAG", "0").strip().lower() in ("1","true","yes","on")

ALWAYS_NOTIFY_ON_TRUE = os.getenv("ALWAYS_NOTIFY_ON_TRUE", "0").strip().lower() in ("1","true","yes","on")
NOTIFY_EMPTY_RAW      = os.getenv("NOTIFY_EMPTY_RAW", "0").strip().lower() in ("1","true","yes","on")
COOLDOWN_SECONDS      = int(os.getenv("COOLDOWN_SECONDS", "0"))
PER_URL_DELAY         = int(os.getenv("PER_URL_DELAY", "2"))
REQUIRE_DOM_CONFIRM   = os.getenv("REQUIRE_DOM_CONFIRM", "1").strip().lower() in ("1","true","yes","on")

log.info("TELEGRAM_ENABLED: %s", TELEGRAM_ENABLED)

# -----------------------------
# TELEGRAM
# -----------------------------
def send_telegram_message(text: str, parse_mode: str | None = None) -> bool:
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
        return r.ok
    except Exception as e:
        log.exception("[TG] İstisna: %s", e)
        return False

def telegram_diag() -> None:
    if not TELEGRAM_DIAG or not TELEGRAM_ENABLED:
        return
    try:
        me = requests.get(f"https://api.telegram.org/bot{BOT_API}/getMe", timeout=10)
        log.info("[TG-DIAG] getMe %s %s", me.status_code, me.text[:500])
        gc = requests.get(f"https://api.telegram.org/bot{BOT_API}/getChat", params={"chat_id": CHAT_ID}, timeout=10)
        log.info("[TG-DIAG] getChat %s %s", gc.status_code, gc.text[:500])
        ok = send_telegram_message("🔔 Telegram DIAG: bot ayakta (Railway).")
        log.info("[TG-DIAG] test send ok=%s", ok)
    except Exception as e:
        log.exception("[TG-DIAG] İstisna: %s", e)

# -----------------------------
# DIAG / DRIVER
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
    # Anti-bot
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    env_chrome = os.getenv("CHROME_BIN", "")
    if env_chrome and os.path.isfile(env_chrome) and os.access(env_chrome, os.X_OK):
        chrome_options.binary_location = env_chrome
        log.info("[DEBUG] binary_location set: %s", env_chrome)

    log.info("[DEBUG] Using SELENIUM MANAGER")
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass
    log.info("[DEBUG] ChromeDriver READY (Selenium Manager)")
    return driver

# -----------------------------
# PARSING / FALLBACK
# -----------------------------
def _clean_size_token(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace("/", " ")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip()
    if " " in s:
        s = s.split()[0]
    return s

def normalize_found(res):
    def norm_list(lst):
        out, seen = [], set()
        for x in lst:
            t = _clean_size_token(str(x))
            if t and t not in seen:
                seen.add(t); out.append(t)
        return out
    if isinstance(res, (list, tuple, set)):
        return norm_list(res)
    if isinstance(res, str):
        t = _clean_size_token(res)
        return [t] if t else []
    if res is True:
        return ["ANY"]
    return []

SIZE_TOKEN_RE = re.compile(r"\b(3[0-9]|[1-9][0-9]|xxs|xs|s|m|l|xl|xxl|xxxl)\b", re.I)

def fallback_sizes_from_text(text: str) -> list[str]:
    tokens, uniq, seen = SIZE_TOKEN_RE.findall(text or ""), [], set()
    for t in tokens:
        u = str(t).strip().upper()
        if u and u not in seen:
            seen.add(u); uniq.append(u)
    return uniq

def zara_get_enabled_sizes(driver) -> list[str]:
    selectors = [
        "[data-qa='size-selector'] button",
        ".product-size-selector button",
        ".size-selector button",
        "li.size button",
        "button.size",
        "button[aria-label*='Beden']",
        "button[aria-label*='Size']",
        "button[aria-label*='Talla']",
    ]
    sizes = []

    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
        time.sleep(1.5)
    except Exception:
        pass

    for sel in selectors:
        try:
            btns = driver.find_elements("css selector", sel)
            for b in btns:
                txt = (b.text or "").strip() or (b.get_attribute("aria-label") or "").strip()
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true")
                if txt and not disabled:
                    sizes.append(txt)
        except Exception:
            pass

    return normalize_found(sizes)

def extract_sizes_with_fallback(driver) -> list[str]:
    
    # 1) DOM generic (enabled butonlar)
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
                txt = (b.text or "").strip() or (b.get_attribute("aria-label") or "").strip()
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true")
                if txt and not disabled:
                    found.append(txt)
            if found:
                return normalize_found(found)
        time.sleep(1.0)

    # 2) JSON içi arama (sadece stock=true olanlar)
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

        # Sadece inStock=true olan bedenleri al
        for m in re.finditer(r'"(size|name|sizeCode|value|sizeId)"\s*:\s*"([^"]{1,12})".{0,500}?"(availability|inStock)"\s*:\s*(true|"inStock"|"available")',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))
        
        # Zara özel data-qa-action kontrolü
        for m in re.finditer(r'"(size|name|sizeCode|value|sizeId)"\s*:\s*"([^"]{1,12})".{0,500}?"data-qa-action"\s*:\s*"[^"]*size-in-stock[^"]*"',
                             blob, re.IGNORECASE | re.DOTALL):
            sizes.add(m.group(2))

    if sizes:
        return normalize_found(list(sizes))

    # 3) TEXT
    return fallback_sizes_from_text(driver.page_source or "")

# Genel: DOM'da gerçekten aktif (enabled) butonlardan beden listesi
def get_enabled_size_buttons(driver) -> list[str]:
    """Sayfada aktif (seçilebilir) beden butonlarını döndürür. Tüm mağazalar için geçerlidir."""
    selectors = [
        "[data-qa='size-selector'] button",
        ".product-size-selector button",
        ".size-selector button",
        "li.size button",
        "button.size",
        "button[aria-label*='Beden']",
        "button[aria-label*='Size']",
        "button[aria-label*='Talla']",
    ]
    sizes = []

    try:
        # Sayfanın orta-altına kaydır
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
        time.sleep(1.5)  # bedenlerin yüklenmesini bekle
    except Exception:
        pass

    for sel in selectors:
        try:
            btns = driver.find_elements("css selector", sel)
            for b in btns:
                txt = (b.text or "").strip() or (b.get_attribute("aria-label") or "").strip()
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true")
                if txt and not disabled:
                    sizes.append(txt)
        except Exception:
            pass

    return normalize_found(sizes)


# -----------------------------
# KARAR & BİLDİRİM
# -----------------------------
def _norm_size(x: str) -> str:
    return (x or "").strip().casefold()

def _norm_list(xs):
    return sorted({_norm_size(x) for x in xs or []})

def decide_and_notify(url: str,
                      wanted_sizes: list[str],
                      found_sizes: list[str],
                      was_available: bool | None,
                      always_notify_on_true: bool,
                      now_ts: int,
                      cooldown_seconds: int) -> bool:
    """wanted boş DEĞİLSE: yalnızca intersection varsa bildir; wanted boşsa found boş değilse bildir."""
    w = _norm_list(wanted_sizes)
    f = _norm_list(found_sizes)

    if w:
        intersection = sorted(set(w).intersection(set(f)))
        now_available = len(intersection) > 0
    else:
        intersection = f[:]
        now_available = len(f) > 0

    log.info("[-DECIDE-] wanted=%s found=%s -> intersect=%s now=%s was=%s",
             w, f, intersection, now_available, was_available)

    if not now_available:
        return False

    if now_ts < next_allowed.get(url, 0):
        log.info("[NOTIFY] cooldown aktif -> atlanıyor (url=%s)", url)
        return False

    should_send = always_notify_on_true or (was_available in (None, False))
    if not should_send:
        log.info("[NOTIFY] atlandı: already True & always_notify_on_true=False")
        return False

    # Mesaj: yalnızca eşleşen bedenleri yaz (wanted varsa)
    if w:
        match_disp = ", ".join(sorted({x.upper() for x in intersection}))
    else:
        match_disp = ", ".join(sorted({x.upper() for x in f}))

    msg = f"🛍️ {match_disp} beden stokta!!!!\nLink: {url}"
    ok = send_telegram_message(msg)

    if ok and cooldown_seconds > 0:
        next_allowed[url] = now_ts + cooldown_seconds
        log.info("[NOTIFY] cooldown set: url=%s until=%s (+%ss)", url, next_allowed[url], cooldown_seconds)
    return ok

# -----------------------------
# OVERLAY
# -----------------------------
def dismiss_overlays(driver):
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
# MAIN LOOP
# -----------------------------
if __name__ == "__main__":
    if TELEGRAM_TEST_ON_START and TELEGRAM_ENABLED:
        send_telegram_message("✅ Bot çalıştı – Railway başlangıç testi.")

    diag()
    telegram_diag()

    while True:
        driver = build_driver()
        try:
            for item in urls_to_check:
                url   = item.get("url")
                store = item.get("store")
                sizes = item.get("sizes", [])  # takip edilen bedenler (boş=herhangi)

                log.info("--------------------------------")
                log.info("[DEBUG] GET %s / Sizes=%s", url, sizes)

                try:
                    driver.get(url)
                    dismiss_overlays(driver)

                    try:
                        WebDriverWait(driver, 20).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                    except Exception:
                        log.warning("[WARN] readyState wait timed out")

                    # 1) Helpers (birincil)
                    if store == "zara":
                        raw = check_stock_zara(driver, sizes)
                    elif store == "bershka":
                        raw = check_stock_bershka(driver, sizes)
                    else:
                        log.warning("Unknown store, skipping: %s", store)
                        continue

                    if raw is None:
                        log.warning("[SCRAPER] helper returned None (error-like), treating as empty")
                        raw = []

                    found_sizes = normalize_found(raw)
                    log.info("[SCRAPER RAW] store=%s found=%s", store, found_sizes)
                    
                    # 2) DOM teyidi (REQUIRE_DOM_CONFIRM kontrolü ile)
                    enabled_dom_sizes = []
                    if REQUIRE_DOM_CONFIRM:
                        if store == "zara":
                            enabled_dom_sizes = zara_get_enabled_sizes(driver)
                        elif store == "bershka":
                            # Bershka için dom kontrolü için aynı genel fonksiyonu kullan
                            enabled_dom_sizes = get_enabled_size_buttons(driver)
                        else:
                            enabled_dom_sizes = get_enabled_size_buttons(driver)
                        
                        log.info("[DOM-CONFIRM] enabled_dom_sizes=%s", enabled_dom_sizes)
                        
                        # DOM'da aktif beden varsa, helpers sonucunu filtrele
                        if enabled_dom_sizes:
                            upper_dom = {x.upper() for x in enabled_dom_sizes}
                            found_sizes = [s for s in found_sizes if s.upper() in upper_dom]
                            log.info("[DOM-CONFIRM] Filtrelenmiş found_sizes=%s", found_sizes)

                    # 3) Fallback (sadece helpers boşsa)
                    if not found_sizes:
                        log.info("[FALLBACK] Helpers boş → fallback deneniyor")
                        json_text_sizes = extract_sizes_with_fallback(driver)
                        if json_text_sizes:
                            found_sizes = normalize_found(json_text_sizes)
                            log.info("[FALLBACK] Raw fallback sizes -> %s", found_sizes)
                            
                            # DOM teyidi açık ve DOM verisi varsa → filtrele
                            if REQUIRE_DOM_CONFIRM and enabled_dom_sizes:
                                upper_dom = {x.upper() for x in enabled_dom_sizes}
                                found_sizes = [s for s in found_sizes if s.upper() in upper_dom]
                                log.info("[DOM-CONFIRM] Fallback filtrelenmiş: %s", found_sizes)
                            
                            # DOM teyidi açık ama DOM boş → şüpheli veri, KULLANMA!
                            elif REQUIRE_DOM_CONFIRM and not enabled_dom_sizes:
                                log.warning("[DOM-CONFIRM] Fallback sonucu var ama DOM boş! Fallback iptal edildi (yanlış pozitif riski).")
                                found_sizes = []  # ❌ KULLANMA! Yanlış pozitif riski
                                if NOTIFY_EMPTY_RAW:
                                    send_telegram_message(f"⚠️ DOM doğrulaması başarısız, fallback reddedildi:\n{url}")

                    # 4) Durum belirleme ve loglama
                    was_in_stock = last_status.get(url)
                    
                    # Eşleşen bedenleri hesapla
                    # Eğer wanted_sizes varsa, sadece onlarla eşleşenleri kullan
                    # Eğer wanted_sizes boşsa, tüm found_sizes'ı kullan
                    if sizes:
                        upper_sizes = {s.upper() for s in sizes}
                        matched = [s for s in found_sizes if s.upper() in upper_sizes]
                    else:
                        matched = found_sizes[:]
                    
                    currently_in_stock = bool(matched)
                    
                    log.info("[FINAL] wanted_sizes=%s", sizes)
                    log.info("[FINAL] found_sizes=%s", found_sizes)
                    log.info("[FINAL] enabled_dom_sizes=%s", enabled_dom_sizes)
                    log.info("[FINAL] matched=%s", matched)
                    log.info("[FINAL] was=%s now=%s", was_in_stock, currently_in_stock)

                    # 5) Opsiyonel uyarı (helpers boşsa)
                    now_ts = int(time.time())
                    if NOTIFY_EMPTY_RAW and not found_sizes:
                        send_telegram_message(f"⚠️ Parser boş döndü (muhtemel DOM değişimi):\n{url}")

                    # 6) Bildirim kararı
                    sent = decide_and_notify(
                        url=url,
                        wanted_sizes=sizes,
                        found_sizes=matched,  # Her zaman matched kullan
                        was_available=was_in_stock,
                        always_notify_on_true=ALWAYS_NOTIFY_ON_TRUE,
                        now_ts=now_ts,
                        cooldown_seconds=COOLDOWN_SECONDS
                    )

                    # 7) Durum güncelle
                    last_status[url] = currently_in_stock
                    
                    if not currently_in_stock:
                        log.info("No stock for %s @ %s", (', '.join(sizes) if sizes else '(any)'), url)

                except Exception as e:
                    log.exception("[ERROR] URL %s hata: %s", url, e)

                log.info("[DEBUG] Per-URL delay: %ss", PER_URL_DELAY)
                time.sleep(PER_URL_DELAY)

        finally:
            log.info("Closing the browser…")
            try:
                driver.quit()
            except Exception:
                pass

            sleep_time = random.randint(sleep_min_seconds, sleep_max_seconds)
            log.info("Sleeping for %d minutes and %d seconds…", sleep_time // 60, sleep_time % 60)
            time.sleep(sleep_time)
