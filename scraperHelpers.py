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
            # Birden fazla scroll yap
            for scroll_ratio in [0.25, 0.35, 0.45]:
                driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {scroll_ratio});")
                time.sleep(2)  # Her scroll sonrası bekle
        except Exception:
            pass

        # ZARA SELECTOR STRATEJİSİ: Önce size selector container'ını bul, sonra içindeki butonları al
        # Bu yaklaşım yanlış butonları (renk, görsel vb.) seçmeyi engeller
        
        buttons = []
        
        # 1) Size selector container'larını bul
        size_container_selectors = [
            "[data-qa='size-selector']",
            ".size-selector-sizes",
            "[data-qa-qualifier*='size']",
            ".product-detail-size",
            "ul[class*='size']",
            "div[class*='size-selector']",
        ]
        
        size_container = None
        for container_sel in size_container_selectors:
            try:
                containers = driver.find_elements(By.CSS_SELECTOR, container_sel)
                if containers:
                    print(f"[DEBUG] Size container bulundu: '{container_sel}' ({len(containers)} adet)")
                    size_container = containers[0]  # İlkini al
                    break
            except:
                continue
        
        # 2) Container varsa içindeki butonları al, yoksa genel arama yap
        if size_container:
            # Container içinde spesifik selector'lar dene
            container_button_selectors = [
                "button[data-qa-action='size-in-stock']",
                "button[data-qa-action*='in-stock']",
                "button[data-qa-action*='low-on-stock']",
                "li.size-selector-sizes-size--enabled button",
                "button:not([aria-disabled='true']):not([disabled])",
                "button",
            ]
            
            for sel in container_button_selectors:
                try:
                    found = size_container.find_elements(By.CSS_SELECTOR, sel)
                    if found:
                        # Text ile filtrele - sadece gerçek bedenleri al
                        filtered = []
                        for btn in found:
                            txt = _safe_text(btn).strip().upper()
                            # Beden pattern kontrolü
                            if txt and len(txt) <= 3:
                                if txt in ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'] or (txt.isdigit() and 28 <= int(txt) <= 50):
                                    filtered.append(btn)
                        
                        if filtered:
                            print(f"[DEBUG] Container içinde '{sel}' ile {len(filtered)} beden butonu bulundu")
                            buttons = filtered
                            break
                except:
                    continue
        else:
            # Container bulunamadı - spesifik size selector'ları dene (sayfa genelinde)
            button_selectors = [
                "button[data-qa-action='size-in-stock']",
                "button[data-qa-action*='in-stock']",
                "li.size-selector-sizes-size--enabled button",
                "[data-qa='size-selector'] button",
                ".size-selector-sizes button",
            ]
            
            for sel in button_selectors:
                try:
                    found = driver.find_elements(By.CSS_SELECTOR, sel)
                    if found:
                        # Text ile filtrele
                        filtered = []
                        for btn in found:
                            txt = _safe_text(btn).strip().upper()
                            if txt and len(txt) <= 3:
                                if txt in ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'] or (txt.isdigit() and 28 <= int(txt) <= 50):
                                    filtered.append(btn)
                        
                        if filtered:
                            print(f"[DEBUG] Genel selector '{sel}' ile {len(filtered)} beden butonu bulundu")
                            buttons = filtered
                            break
                except:
                    continue

        # Eğer hala bulamadıysak, daha genel arama
        if not buttons:
            print("[DEBUG] Selector'lar başarısız, genel arama başlatılıyor")
            # Scroll daha aşağıya
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
                time.sleep(1.5)
                # Tüm butonları al ve kendimiz filtreleyelim
                all_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
                print(f"[DEBUG] Sayfada toplam {len(all_buttons)} buton var")
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
                        print(f"[DEBUG] Beden bulundu: {txt}, disabled={disabled}")
                        if not disabled:
                            buttons.append(btn)
                print(f"[DEBUG] Genel aramada {len(buttons)} enabled beden bulundu")
            except Exception as e:
                print(f"[DEBUG] Genel arama hatası: {e}")

        if not buttons:
            return []

        # İstenen bedenleri normalize et (case-insensitive)
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))

        in_stock = []
        print(f"[DEBUG] Toplam {len(buttons)} buton işlenecek, wanted={wanted}")
        for idx, b in enumerate(buttons):
            try:
                size_label = _safe_text(b).upper()
                print(f"[DEBUG] Buton #{idx+1}: text='{size_label}' (raw: {b.text[:50] if b.text else 'NONE'})")
                if not size_label:
                    print(f"[DEBUG] Buton #{idx+1}: size_label boş, atlanıyor")
                    continue

                # Eğer takip listesi verilmişse, önce onlarla filtrele
                if wanted and (size_label not in wanted):
                    print(f"[DEBUG] Buton #{idx+1}: '{size_label}' wanted listesinde değil, atlanıyor")
                    continue

                # Buton özelliklerini topla
                cls = (b.get_attribute("class") or "").lower()
                aria = (b.get_attribute("aria-disabled") or "").lower()
                qa = (b.get_attribute("data-qa-action") or "").lower()
                disabled = ("disabled" in cls) or (aria == "true") or (b.get_attribute("disabled") is not None)
                
                # HTML içeriğini kontrol et (coming soon için)
                try:
                    html_raw = b.get_attribute("outerHTML") or ""
                    html_lower = html_raw.lower()
                except:
                    html_lower = ""
                
                # Coming soon kontrolü (kazak M bedeni için)
                is_coming_soon = (
                    "coming" in html_lower or 
                    "yakında" in html_lower or 
                    "coming" in cls or
                    "coming-soon" in cls
                )
                
                # Stok kontrolü - ChatGPT analizi + kazak analizi sonrası güncellendi
                # Öncelik: data-qa-action="size-in-stock" → kesin stokta
                # İkinci: class="size-selector-sizes-size--enabled" → stokta
                # Red: Coming soon veya disabled → stokta değil
                # Son çare: disabled değilse kabul et
                
                is_in_stock = False
                
                # 0) ÖNCE RED KONTROLÜ - Coming soon veya disabled → kesinlikle stokta değil
                if is_coming_soon:
                    print(f"[DEBUG] ❌ Beden '{size_label}' coming soon - stokta değil")
                    is_in_stock = False
                
                # 1) ChatGPT'nin bulduğu: data-qa-action="size-in-stock" → kesin stokta
                elif qa and ("size-in-stock" in qa or "in-stock" in qa or "low-on-stock" in qa):
                    is_in_stock = True
                    print(f"[DEBUG] ✅ Beden '{size_label}' stokta (data-qa-action={qa})")
                    
                # 2) Enabled class var mı? (ayakkabı için)
                elif "size-selector-sizes-size--enabled" in cls:
                    is_in_stock = True
                    print(f"[DEBUG] ✅ Beden '{size_label}' stokta (enabled class)")
                    
                # 3) Explicit disabled işaretleri varsa → stokta değil
                elif "out-of-stock" in qa or "disabled" in qa:
                    is_in_stock = False
                    print(f"[DEBUG] ❌ Beden '{size_label}' disabled/out-of-stock")
                    
                # 4) Qa-action yoksa → disabled değilse kabul et (dikkatli)
                elif not qa and not disabled:
                    # Güvenlik: Çok genel olmasın, en azından size pattern'i doğrula
                    is_in_stock = True
                    print(f"[DEBUG] ⚠️ Beden '{size_label}' qa-action yok ama disabled değil - kabul edildi")
                else:
                    is_in_stock = False
                
                if is_in_stock:
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
