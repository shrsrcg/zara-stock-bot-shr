# ============================
# scraperHelpers.py (REVIZE v2)
# Headless/worker uyumlu; yalancı pozitifleri azaltır.
# Dönüş:
#   - stok varsa: List[str]  (ör. ["S","M"])
#   - stok yoksa: []
#   - hata:      None
# ============================

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

import time


# ----------------------------
# Yardımcı: güvenli text okuma
# ----------------------------
def _safe_text(el):
    try:
        t = (el.text or "").strip()
        if t:
            return t
        t = (el.get_attribute("innerText") or "").strip()
        if t:
            return t
        t = (el.get_attribute("aria-label") or "").strip()
        return t or ""
    except Exception:
        return ""


# ------------------------------------------------------------
# ZARA: link-bazlı beden kontrolü (muhafazakâr)
# ------------------------------------------------------------
def check_stock_zara(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["S","M","L"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : None
    Notlar :
      - SADECE gerçekten tıklanabilir (enabled) + QA action'ı "in-stock"/"low-on-stock"
        olan bedenler "stok var" sayılır.
      - 'qa_action' boşsa ARTIK stok varsaymıyoruz (yalancı pozitifleri engeller).
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)

        # Beden konteynerini bekle (çeşitli varyantlar)
        container_locators = [
            (By.CSS_SELECTOR, ".size-selector-sizes"),
            (By.CSS_SELECTOR, "[data-qa-qualifier='size-selector-sizes']"),
            (By.CSS_SELECTOR, "[data-qa='size-selector']"),
        ]

        found_container = False
        for loc in container_locators:
            try:
                wait.until(EC.presence_of_element_located(loc))
                found_container = True
                break
            except TimeoutException:
                continue
        if not found_container:
            return []

        # Buton havuzu (farklı şablonlar için geniş seçim)
        button_selectors = [
            "[data-qa='size-selector'] button",
            ".size-selector-sizes .size-selector-sizes-size__button",
            ".size-selector button",
            "li.size button",
            "button.size",
        ]
        buttons = []
        for sel in button_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                if buttons:
                    break
            except Exception:
                continue

        if not buttons:
            return []

        # İstenen bedenleri normalize et (case-insensitive)
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))

        in_stock = []
        for b in buttons:
            try:
                size_label = _safe_text(b).upper()
                if not size_label:
                    # bazı şablonlarda label ayrı bir span'da
                    try:
                        lab = b.find_element(By.CSS_SELECTOR, "[data-qa-qualifier='size-selector-sizes-size-label']")
                        size_label = _safe_text(lab).upper()
                    except Exception:
                        pass

                if not size_label:
                    continue

                # Eğer takip listesi verilmişse, önce onlarla filtrele
                if wanted and (size_label not in wanted):
                    continue

                cls  = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                qa   = (b.get_attribute("data-qa-action") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true") or (b.get_attribute("disabled") is not None)

                # Net pozitif sinyaller:
                qa_in = ("size-in-stock" in qa) or ("size-low-on-stock" in qa)

                # Muhafazakâr koşul:
                # - Buton tıklanabilir olacak
                # - data-qa-action içinde "size-in-stock" veya "size-low-on-stock" olacak
                # Aksi takdirde, fallback aşamasında bile "stok var" demeyeceğiz.
                if (not disabled) and qa_in:
                    in_stock.append(size_label)

            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        # Tutarlı dönüş
        return in_stock

    except Exception as e:
        print(f"[check_stock_zara] Hata: {e}")
        return None


# ------------------------------------------------------------
# BERSHKA: link-bazlı beden kontrolü (muhafazakâr)
# ------------------------------------------------------------
def check_stock_bershka(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["XS","S","M"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : None
    Notlar :
      - 'is-disabled' sınıfı veya aria-disabled=true olan butonlar stok YOK.
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)

        # Beden listesi container
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul[data-qa-anchor='productDetailSize']")))
        except TimeoutException:
            # Bazı sayfalarda farklı kökler olabiliyor, kısa tolerans
            time.sleep(1)

        # Dinamik class güncellemelerine küçük tolerans
        time.sleep(1.5)

        button_selectors = [
            "button[data-qa-anchor='sizeListItem']",
            "ul[data-qa-anchor='productDetailSize'] button",
        ]
        buttons = []
        for sel in button_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                if buttons:
                    break
            except Exception:
                continue

        if not buttons:
            return []

        wanted = set(x.strip().upper() for x in (sizes_to_check or []))

        in_stock = []
        for btn in buttons:
            try:
                # Label
                size_label = ""
                try:
                    size_label = _safe_text(btn.find_element(By.CSS_SELECTOR, "span.text__label")).upper()
                except NoSuchElementException:
                    size_label = _safe_text(btn).upper()

                if not size_label:
                    continue

                if wanted and (size_label not in wanted):
                    continue

                cls  = (btn.get_attribute("class") or "").lower()
                aria = (btn.get_attribute("aria-disabled") or "").lower()
                disabled = ("is-disabled" in cls) or (aria == "true") or (btn.get_attribute("disabled") is not None)

                if not disabled:
                    in_stock.append(size_label)

            except StaleElementReferenceException:
                continue
            except Exception:
                continue

        return in_stock

    except Exception as e:
        print(f"[check_stock_bershka] Hata: {e}")
        return None


# ------------------------------------------------------------
# Rossmann: örnek (bool döner)
# ------------------------------------------------------------
def rossmannStockCheck(driver):
    """
    True → stok var (Sepete Ekle tıklanabilir),
    False → stok yok,
    None  → hata.
    """
    try:
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "product-add-form")))
        try:
            button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(., 'Sepete Ekle')]")
            return bool(button)
        except Exception:
            return False
    except Exception:
        return None


# ------------------------------------------------------------
# Watsons: örnek (bool döner)
# ------------------------------------------------------------
def watsonsChecker(driver):
    """
    True → listede ürün var,
    False → '0 ürün' veya liste yok,
    None  → hata.
    """
    try:
        wait = WebDriverWait(driver, 20)
        elems = wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, "product-grid-manager__view-mount")))
        combined_text = " ".join([(_safe_text(e)).lower() for e in elems if _safe_text(e)])
        if "0 ürün" in combined_text or "0 urun" in combined_text:
            return False
        return True
    except TimeoutException:
        return False
    except Exception:
        return None
