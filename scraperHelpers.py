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
      - SADECE gerçekten tıklanabilir (enabled) butonlar "stok var" sayılır.
      - Eşleşme case-insensitive yapılır.
    """
    try:
        # Sayfayı biraz kaydır (bedenlerin yüklenmesi için)
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.35);")
            time.sleep(1.5)
        except Exception:
            pass

        # AGGRESİF SELECTOR'LAR - Tüm olası Zara yapıları
        button_selectors = [
            # Modern Zara
            "button[data-qa-action*='in-stock']",
            "button[data-qa-action*='low-on-stock']", 
            "[data-qa='size-selector'] button:not([aria-disabled='true']):not([disabled])",
            ".size-selector-sizes button:not([aria-disabled='true'])",
            "[data-qa-qualifier*='size'] button:not([disabled])",
            
            # Genel buton selectorlar (enabled olanları filtrele)
            "button.size:not([disabled]):not([aria-disabled='true'])",
            "li button:not([disabled])",
            ".product-detail-size button:not([disabled])",
            
            # Data attribute'ları ile
            "button[data-qa*='size']:not([disabled])",
            "button[aria-label*='Size']:not([aria-disabled='true'])",
            "button[aria-label*='Beden']:not([aria-disabled='true'])",
        ]
        
        buttons = []
        for sel in button_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                if found:
                    buttons = found
                    break
            except Exception:
                continue

        # Eğer hala bulamadıysak, daha genel arama
        if not buttons:
            # Scroll daha aşağıya
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
                time.sleep(1.5)
                # Tüm butonları al ve kendimiz filtreleyelim
                all_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
                buttons = []
                for btn in all_buttons:
                    txt = _safe_text(btn).upper()
                    cls = (btn.get_attribute("class") or "").lower()
                    aria_disabled = (btn.get_attribute("aria-disabled") or "").lower()
                    
                    # Beden pattern'i kontrol et (S, M, L, XS, XL veya sayı 28-50)
                    is_size = False
                    if txt and len(txt) <= 3:
                        if txt in ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']:
                            is_size = True
                        elif txt.isdigit() and 28 <= int(txt) <= 50:
                            is_size = True
                    
                    if is_size:
                        disabled = ("disabled" in cls) or (aria_disabled == "true") or (btn.get_attribute("disabled") is not None)
                        if not disabled:
                            buttons.append(btn)
            except Exception:
                pass

        if not buttons:
            return []

        # İstenen bedenleri normalize et (case-insensitive)
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))

        in_stock = []
        for b in buttons:
            try:
                size_label = _safe_text(b).upper()
                if not size_label:
                    continue

                # Eğer takip listesi verilmişse, önce onlarla filtrele
                if wanted and (size_label not in wanted):
                    continue

                # Buton disabled mı kontrol et
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                qa = (b.get_attribute("data-qa-action") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true") or (b.get_attribute("disabled") is not None)

                # Stok kontrolü: Sadece disabled OLMAYAN + (data-qa-action'da "in-stock" varsa VEYA boş yoksa)
                # Muhafazakâr yaklaşım: Disabled değilse ve data-qa-action'da "in-stock" VEYA boş değilse
                if not disabled:
                    # Eğer qa-action varsa, kontrol et
                    if qa and ("in-stock" in qa or "low-on-stock" in qa):
                        in_stock.append(size_label)
                    elif not qa:
                        # qa-action yoksa, sadece disabled değilse kabul et (daha riskli)
                        in_stock.append(size_label)

            except StaleElementReferenceException:
                continue
            except Exception:
                continue

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
