from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
import time

def _safe_text(el):
    """Element text'ini güvenli şekilde al (StaleElementReferenceException için)"""
    try:
        return el.text or ""
    except StaleElementReferenceException:
        return ""


# ------------------------------------------------------------
# ZARA: link-bazlı beden kontrolü (ÇALIŞAN KOD MANTIĞI)
# ------------------------------------------------------------
def check_stock_zara(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["S","M","L"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : None
    Notlar :
      - ÇALIŞAN KOD MANTIĞI: Önce "Add to Cart" butonuna tıklıyor, sonra size selector açılıyor
      - SADECE gerçekten tıklanabilir (enabled) butonlar "stok var" sayılır.
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)
        
        # Cookie popup'ı kapat
        try:
            accept_cookies_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            accept_cookies_button.click()
            print("[DEBUG] Cookie popup kapatıldı")
            time.sleep(1)
        except TimeoutException:
            print("[DEBUG] Cookie popup bulunamadı veya zaten kapalı")
        
        # Sayfayı kaydır
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
            time.sleep(1)
        except Exception:
            pass
        
        # "Add to Cart" butonuna tıkla (ÇALIŞAN KOD MANTIĞI)
        try:
            add_to_cart_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-qa-action='add-to-cart']")))
            
            # Overlay varsa kaldır
            overlays = driver.find_elements(By.CLASS_NAME, "zds-backdrop")
            if overlays:
                print("[DEBUG] Overlay bulundu, kaldırılıyor...")
                driver.execute_script("arguments[0].remove();", overlays[0])
            
            # JavaScript ile tıkla (overlay bypass)
            driver.execute_script("arguments[0].click();", add_to_cart_button)
            print("[DEBUG] 'Add to Cart' butonuna tıklandı")
            time.sleep(2)  # Size selector'ın açılması için bekle
        except (TimeoutException, NoSuchElementException) as e:
            print(f"[DEBUG] 'Add to Cart' butonu bulunamadı veya tıklanamadı: {e}")
            # Add to Cart bulunamazsa devam et, belki size selector zaten açık
        
        # Size selector'ın görünmesini bekle
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "size-selector-sizes")))
            print("[DEBUG] Size selector container görüldü")
            time.sleep(1)  # Element'lerin tam yüklenmesi için
        except TimeoutException:
            print("[DEBUG] Size selector container görünmedi, alternatif yöntem deneniyor...")

        # ÇALIŞAN KOD MANTIĞI: .size-selector-sizes-size class'ını kullan
        # Her size elementi bir <li> ve içinde label ve button var
        
        in_stock = []
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        
        # ÇALIŞAN KOD SELECTOR'LARI:
        try:
            size_elements = driver.find_elements(By.CLASS_NAME, "size-selector-sizes-size")
            print(f"[DEBUG] Çalışan kod mantığı: {len(size_elements)} size element bulundu (.size-selector-sizes-size)")
            
            for li in size_elements:
                try:
                    # Beden label'ını bul
                    size_label_elem = li.find_element(By.CSS_SELECTOR, "div[data-qa-qualifier='size-selector-sizes-size-label']")
                    size_label = size_label_elem.text.strip().upper()
                    print(f"[DEBUG] Size element bulundu: '{size_label}'")
                    
                    if not wanted or size_label in wanted:
                        # Button'u bul
                        button = li.find_element(By.CLASS_NAME, "size-selector-sizes-size__button")
                        
                        # "Benzer ürünler" kontrolü (stok yok)
                        try:
                            similar_products_elem = button.find_element(By.CLASS_NAME, "size-selector-sizes-size__action")
                            if "Benzer ürünler" in similar_products_elem.text:
                                print(f"[DEBUG] ❌ Beden '{size_label}' - Benzer ürünler gösteriliyor (stok yok)")
                                continue
                        except NoSuchElementException:
                            pass  # "Benzer ürünler" yoksa devam et
                        
                        # Stok durumunu kontrol et
                        qa_action = button.get_attribute("data-qa-action") or ""
                        print(f"[DEBUG] Beden '{size_label}' - data-qa-action: '{qa_action}'")
                        
                        if qa_action in ["size-in-stock", "size-low-on-stock"]:
                            print(f"[DEBUG] ✅ Beden '{size_label}' stokta!")
                            in_stock.append(size_label)
                        else:
                            print(f"[DEBUG] ❌ Beden '{size_label}' stokta değil (qa-action: {qa_action})")
                            
                except NoSuchElementException as e:
                    print(f"[DEBUG] Size element işlenirken hata (label/button bulunamadı): {e}")
                    continue
                except Exception as e:
                    print(f"[DEBUG] Size element işlenirken hata: {e}")
                    continue
            
            if in_stock:
                print(f"[DEBUG] ✅ Toplam {len(in_stock)} beden stokta: {in_stock}")
                return in_stock
            else:
                print(f"[DEBUG] İstenen bedenler stokta değil: {list(wanted)}")
                return []
                
        except Exception as e:
            print(f"[DEBUG] Çalışan kod mantığı hatası: {e}")
            import traceback
            print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
            return []
    
    except Exception as e:
        print(f"[DEBUG] check_stock_zara genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []
    
    return []


# ------------------------------------------------------------
# BERSHKA: link-bazlı beden kontrolü
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

        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        in_stock = []

        for sel in button_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                if not buttons:
                    continue

                print(f"[DEBUG] {len(buttons)} Bershka beden butonu bulundu (selector: {sel})")

                for button in buttons:
                    try:
                        size_label_elem = button.find_element(By.CSS_SELECTOR, "span.text__label")
                        size_label = size_label_elem.text.strip().upper()

                        if not wanted or size_label in wanted:
                            # Class'ın stabilize olmasını bekle
                            def class_stabilized(driver):
                                cls = button.get_attribute("class")
                                return "is-disabled" in cls or "is-disabled" not in cls

                            WebDriverWait(driver, 5).until(class_stabilized)

                            class_attr = button.get_attribute("class")
                            if "is-disabled" in class_attr:
                                print(f"[DEBUG] ❌ Bershka beden '{size_label}' stokta değil (is-disabled)")
                            else:
                                print(f"[DEBUG] ✅ Bershka beden '{size_label}' stokta!")
                                in_stock.append(size_label)
                    except NoSuchElementException:
                        continue
                    except Exception as e:
                        print(f"[DEBUG] Bershka button işlenirken hata: {e}")
                        continue

                if in_stock:
                    return in_stock
            except Exception as e:
                print(f"[DEBUG] Bershka selector '{sel}' hatası: {e}")
                continue

        if not in_stock:
            print(f"[DEBUG] İstenen Bershka bedenler stokta değil: {list(wanted)}")
        
        return in_stock

    except Exception as e:
        print(f"[DEBUG] check_stock_bershka genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []
