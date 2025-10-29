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
        wait = WebDriverWait(driver, 60)  # ÇALIŞAN KOD: 60 saniye
        
        # Cookie popup'ı kapat
        try:
            print("[DEBUG] Cookie popup kontrol ediliyor...")
            accept_cookies_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            accept_cookies_button.click()
            print("[DEBUG] Cookie popup kapatıldı")
            time.sleep(1)
        except TimeoutException:
            print("[DEBUG] Cookie popup bulunamadı veya zaten kapalı")
        
        # ÇALIŞAN KOD: Scroll YOK! Direkt Add to Cart'a geç
        
        # "Add to Cart" butonuna tıkla (ÇALIŞAN KOD MANTIĞI - AYNISI)
        try:
            print("[DEBUG] 'Add to Cart' butonu bekleniyor...")
            add_to_cart_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[data-qa-action='add-to-cart']")))
            
            # Overlay varsa kaldır (ÇALIŞAN KOD MANTIĞI)
            overlays = driver.find_elements(By.CLASS_NAME, "zds-backdrop")
            if overlays:
                print("[DEBUG] Overlay bulundu, kaldırılıyor...")
                driver.execute_script("arguments[0].remove();", overlays[0])
            
            # JavaScript ile tıkla (overlay bypass - ÇALIŞAN KOD MANTIĞI)
            driver.execute_script("arguments[0].click();", add_to_cart_button)
            print("[DEBUG] 'Add to Cart' butonuna tıklandı")
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e:
            print(f"[DEBUG] 'Add to Cart' butonu bulunamadı veya tıklanamadı: {e}")
            return None  # ÇALIŞAN KOD: None döndür
        
        # Size selector'ın görünmesini bekle (ÇALIŞAN KOD MANTIĞI)
        print("[DEBUG] Size selector bekleniyor...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "size-selector-sizes")))

        # Find size elements (ÇALIŞAN KOD MANTIĞI - AYNISI)
        size_elements = driver.find_elements(By.CLASS_NAME, "size-selector-sizes-size")
        print(f"[DEBUG] {len(size_elements)} size element bulundu (.size-selector-sizes-size)")
        
        # ÇALIŞAN KOD: Her bedeni kontrol et ve eşleşeni bul
        in_stock = []
        
        for li in size_elements:
            try:
                # ÇALIŞAN KOD: Direkt text strip (case-sensitive kontrolü yapmıyor)
                size_label = li.find_element(By.CSS_SELECTOR, "div[data-qa-qualifier='size-selector-sizes-size-label']").text.strip()
                print(f"[DEBUG] Size element bulundu: '{size_label}'")
                
                # ÇALIŞAN KOD: Direkt string karşılaştırma (sizes_to_check içinde mi?)
                # Ama biz link bazlı çalışıyoruz, o yüzden normalize ediyoruz
                size_label_normalized = size_label.upper()
                wanted = set(x.strip().upper() for x in (sizes_to_check or []))
                
                if not wanted or size_label_normalized in wanted:
                    button = li.find_element(By.CLASS_NAME, "size-selector-sizes-size__button")

                    # Check if the button contains "Benzer ürünler" text (ÇALIŞAN KOD MANTIĞI)
                    try:
                        similar_products_text = button.find_element(By.CLASS_NAME, "size-selector-sizes-size__action").text.strip()
                        if "Benzer ürünler" in similar_products_text:
                            print(f"[DEBUG] ❌ Beden '{size_label}' - Benzer ürünler gösteriliyor (stok yok)")
                            continue
                    except NoSuchElementException:
                        pass  # No "Benzer ürünler" text found, proceed with normal check

                    # Check stock status (ÇALIŞAN KOD MANTIĞI)
                    qa_action = button.get_attribute("data-qa-action") or ""
                    print(f"[DEBUG] Beden '{size_label}' - data-qa-action: '{qa_action}'")
                    
                    if qa_action in ["size-in-stock", "size-low-on-stock"]:
                        print(f"[DEBUG] ✅ Beden '{size_label}' stokta!")
                        in_stock.append(size_label_normalized)  # Normalize edilmiş halini kaydet
                    else:
                        print(f"[DEBUG] ❌ Beden '{size_label}' stokta değil (qa-action: {qa_action})")
                        
            except Exception as e:
                print(f"[DEBUG] Size element işlenirken hata: {e}")
                continue
        
        if in_stock:
            print(f"[DEBUG] ✅ Toplam {len(in_stock)} beden stokta: {in_stock}")
            return in_stock
        else:
            wanted = set(x.strip().upper() for x in (sizes_to_check or []))
            print(f"[DEBUG] İstenen bedenler stokta değil: {list(wanted)}")
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


# ------------------------------------------------------------
# H&M: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_hm(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["XS","S","M"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : None
    Notlar :
      - aria-label içinde "stokta" varsa stok var
      - aria-label içinde "stokta yok" varsa stok yok
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)
        
        # Cookie popup kontrolü (gerekirse)
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] H&M cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-testid^='sizebutton-'], div[role='radio'][aria-label*='beden']")))
            print("[DEBUG] H&M size selector görüldü")
            time.sleep(1)
        except TimeoutException:
            print("[DEBUG] H&M size selector görünmedi")
            return []
        
        # Size elementlerini bul
        size_selectors = [
            "div[data-testid^='sizebutton-']",
            "div[role='radio'][aria-label*='beden']",
            "li div[role='radio']"
        ]
        
        size_elements = []
        for sel in size_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                if found:
                    print(f"[DEBUG] H&M {len(found)} size element bulundu (selector: {sel})")
                    size_elements = found
                    break
            except:
                continue
        
        if not size_elements:
            print("[DEBUG] H&M size element bulunamadı")
            return []
        
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        in_stock = []
        
        for element in size_elements:
            try:
                # Size text'i bul (div[dir="ltr"] içinde veya textContent'te)
                try:
                    size_text_elem = element.find_element(By.CSS_SELECTOR, "div[dir='ltr']")
                    size_label = size_text_elem.text.strip().upper()
                except:
                    # Fallback: direkt textContent
                    size_label = element.text.strip().upper()
                
                if not size_label:
                    continue
                
                # Normalize (trim whitespace)
                size_label = size_label.replace("\xa0", " ").strip().upper()
                
                # İstenen beden kontrolü
                if not wanted or size_label in wanted:
                    # aria-label kontrolü ile stok durumu tespit et
                    aria_label = element.get_attribute("aria-label") or ""
                    aria_label_lower = aria_label.lower()
                    
                    # H&M stok kontrolü: aria-label içinde "stokta" varsa stok var
                    # "stokta yok" veya "benzer ürünleri görmek" varsa stok yok
                    if "stokta yok" in aria_label_lower or "benzer ürünleri görmek" in aria_label_lower:
                        print(f"[DEBUG] ❌ H&M beden '{size_label}' stokta değil (aria-label: {aria_label[:50]})")
                        continue
                    elif "stokta" in aria_label_lower:
                        print(f"[DEBUG] ✅ H&M beden '{size_label}' stokta!")
                        in_stock.append(size_label)
                    else:
                        # aria-label belirsizse, disabled kontrolü yap
                        if element.get_attribute("aria-disabled") == "true":
                            print(f"[DEBUG] ❌ H&M beden '{size_label}' disabled")
                            continue
                        else:
                            print(f"[DEBUG] ✅ H&M beden '{size_label}' stokta (belirsiz ama disabled değil)")
                            in_stock.append(size_label)
                            
            except Exception as e:
                print(f"[DEBUG] H&M size element işlenirken hata: {e}")
                continue
        
        if in_stock:
            print(f"[DEBUG] ✅ H&M toplam {len(in_stock)} beden stokta: {in_stock}")
        else:
            print(f"[DEBUG] H&M istenen bedenler stokta değil: {list(wanted)}")
        
        return in_stock
        
    except Exception as e:
        print(f"[DEBUG] check_stock_hm genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []


# ------------------------------------------------------------
# MANGO: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_mango(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["XS","S","M"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : None
    Notlar :
      - SizeItemContent_notAvailable__2WJ__ class'ı varsa stok YOK
      - SizeItem_selectable__J5zws class'ı varsa stok VAR
      - "notify-availability" veya "beni haberdar et" popup'ı varsa stok YOK
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)
        
        # Cookie popup kontrolü (gerekirse)
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie'], button[class*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] Mango cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "button.sizeitem_sizeitem__7vipk, li.sizeslist_listitem__usajg")))
            print("[DEBUG] Mango size selector görüldü")
            time.sleep(1.5)  # Dinamik class güncellemeleri için bekle
        except TimeoutException:
            print("[DEBUG] Mango size selector görünmedi")
            return []
        
        # Size elementlerini bul (button elementlerini al, tekrar edenleri filtrele)
        size_selectors = [
            "li.sizeslist_listitem__usajg button.sizeitem_sizeitem__7vipk",
            "button.sizeitem_sizeitem__7vipk",
            "button[id^='pdp.productinfo.sizeselector.size']"
        ]
        
        size_elements = []
        seen_texts = set()
        
        for sel in size_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                if found:
                    # Tekrar edenleri filtrele
                    for el in found:
                        try:
                            size_text_elem = el.find_element(By.CSS_SELECTOR, "span.textactionm_classname__8mcjk")
                            size_text = size_text_elem.text.strip().upper()
                            if size_text and size_text not in seen_texts:
                                seen_texts.add(size_text)
                                size_elements.append(el)
                        except:
                            # Fallback: direkt textContent
                            size_text = el.text.strip().upper()
                            if size_text and size_text not in seen_texts:
                                seen_texts.add(size_text)
                                size_elements.append(el)
                    
                    if size_elements:
                        print(f"[DEBUG] Mango {len(size_elements)} benzersiz size element bulundu (selector: {sel})")
                        break
            except:
                continue
        
        if not size_elements:
            print("[DEBUG] Mango size element bulunamadı")
            return []
        
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        in_stock = []
        
        for button in size_elements:
            try:
                # Size text'i bul
                try:
                    size_text_elem = button.find_element(By.CSS_SELECTOR, "span.textactionm_classname__8mcjk")
                    size_label = size_text_elem.text.strip().upper()
                except:
                    size_label = button.text.strip().upper()
                
                if not size_label:
                    continue
                
                # İstenen beden kontrolü
                if not wanted or size_label in wanted:
                    # Class kontrolü ile stok durumu tespit et
                    class_attr = button.get_attribute("class") or ""
                    class_lower = class_attr.lower()
                    
                    # Mango stok kontrolü:
                    # - SizeItemContent_notAvailable__2WJ__ varsa → stok YOK
                    # - SizeItem_selectable__J5zws varsa → stok VAR
                    # - "notify-availability" veya popup varsa → stok YOK
                    
                    html_lower = (button.get_attribute("outerHTML") or "").lower()
                    
                    if "notavailable" in class_lower or "not-available" in class_lower:
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (notAvailable class)")
                        continue
                    elif "notify-availability" in html_lower or "beni haberdar et" in html_lower:
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (notify popup)")
                        continue
                    elif "selectable" in class_lower and "notavailable" not in class_lower:
                        print(f"[DEBUG] ✅ Mango beden '{size_label}' stokta!")
                        in_stock.append(size_label)
                    elif button.get_attribute("disabled") or button.get_attribute("aria-disabled") == "true":
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' disabled")
                        continue
                    else:
                        # Belirsiz durum - selectable class var mı kontrol et
                        try:
                            parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                            parent_class = (parent_li.get_attribute("class") or "").lower()
                            if "selectable" in parent_class or "selectable" in class_lower:
                                print(f"[DEBUG] ✅ Mango beden '{size_label}' stokta (belirsiz ama selectable)")
                                in_stock.append(size_label)
                            else:
                                print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (belirsiz)")
                        except:
                            print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (belirsiz)")
                        
            except Exception as e:
                print(f"[DEBUG] Mango size element işlenirken hata: {e}")
                continue
        
        if in_stock:
            print(f"[DEBUG] ✅ Mango toplam {len(in_stock)} beden stokta: {in_stock}")
        else:
            print(f"[DEBUG] Mango istenen bedenler stokta değil: {list(wanted)}")
        
        return in_stock
        
    except Exception as e:
        print(f"[DEBUG] check_stock_mango genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []
