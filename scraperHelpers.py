from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, StaleElementReferenceException
import time
import re

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
        
        # Cookie popup kontrolü (önce cookie'yi kapat)
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie'], button[class*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] H&M cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Sayfayı kaydır ve dinamik içerik yüklenmesini bekle
        try:
            # İlk scroll
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
            time.sleep(1.5)
            # İkinci scroll (daha fazla aşağı)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
            time.sleep(1.5)
            # Üçüncü scroll (tam aşağı ve geri yukarı - lazy load tetikleme)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.7);")
            time.sleep(2)
            # Yukarı kaydır (size selector genelde yukarıda)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.2);")
            time.sleep(1.5)
            print("[DEBUG] H&M scroll işlemleri tamamlandı")
        except Exception as e:
            print(f"[DEBUG] H&M scroll hatası: {e}")
        
        # JavaScript ile DOM hazır mı kontrol et ve beklenen elementleri kontrol et
        try:
            driver.execute_script("""
                // Sayfanın tam yüklendiğinden emin ol
                if (document.readyState !== 'complete') {
                    return false;
                }
                // sizebutton içeren elementler var mı kontrol et
                var sizeElements = document.querySelectorAll('div[id^="sizebutton-"], div[data-testid^="sizebutton-"]');
                return sizeElements.length > 0;
            """)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle - daha fazla alternatif selector ve uzun süre
        size_elements = []
        wait_selectors = [
            "div[data-testid^='sizebutton-']",
            "div[id^='sizebutton-']",
            "div[role='radio'][aria-label*='beden']",
            "li div[role='radio']",
            "div[data-testid*='size']",
            "*[aria-label*='beden:']",
            "li[role='radio']",
            "div[tabindex='0'][role='radio']"
        ]
        
        selector_found = False
        for wait_sel in wait_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel)))
                print(f"[DEBUG] H&M size selector görüldü (wait selector: {wait_sel})")
                selector_found = True
                # Element'lerin tam yüklenmesi için daha uzun bekle
                time.sleep(3)
                break
            except TimeoutException:
                continue
        
        if not selector_found:
            print("[DEBUG] H&M wait selector bulunamadı, yine de size element aramaya devam ediliyor...")
            time.sleep(2)  # Yine de biraz bekle
        
        # Size elementlerini bul - ANALİZ SONUÇLARINA GÖRE: li > div[id="sizebutton-0"] formatında
        # ÖNEMLİ: Tüm selector'ları birleştirip tek seferde arama yap (tüm bedenleri bulmak için)
        size_selectors = [
            # Öncelik 1: Analiz sonuçlarına göre li içinde olmalı
            "li > div[id^='sizebutton-'], li > div[data-testid^='sizebutton-']",
            "li > div[id^='sizeButton-'], li > div[data-testid^='sizeButton-']",  # Case variation
            "li > div[id*='sizebutton'], li > div[data-testid*='sizebutton']",  # Partial match
            # Öncelik 2: Direkt div (li olmadan da olabilir)
            "div[id^='sizebutton-'], div[data-testid^='sizebutton-']",
            "div[id^='sizeButton-'], div[data-testid^='sizeButton-']",  # Case variation
            "div[id*='sizebutton'], div[data-testid*='sizebutton']",  # Partial match
            # Öncelik 3: role='radio' olanlar (tüm varyasyonlar)
            "div[role='radio'][aria-label*='beden'], div[role='radio'][aria-label*='Beden']",
            "div[role='radio'][aria-label*='BEDEN']",
            "li div[role='radio']",
            "div[role='radio']",
            # Öncelik 4: Genel selector'lar
            "div[data-testid*='size'], div[data-testid*='Size']",
            "*[aria-label*='beden:'], *[aria-label*='Beden:']",
            "li > div[tabindex='0']",
            "div[tabindex='0'][role='radio']",
            # Son çare: tüm li elementleri içinde arama
            "li > div"
        ]
        
        # Tüm selector'lardan elementleri topla (tek seferde)
        all_found_elements = []
        seen_element_ids = set()  # Duplicate element'leri önlemek için
        
        for sel in size_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                print(f"[DEBUG] H&M selector '{sel}' ile {len(found)} element bulundu")
                for el in found:
                    # Element'in unique ID'sini oluştur
                    el_id = el.get_attribute("id") or el.get_attribute("data-testid") or ""
                    el_html = el.get_attribute("outerHTML")[:100] if el.get_attribute("outerHTML") else ""
                    
                    # Daha önce görmüş mü kontrol et (duplicate önleme)
                    el_key = f"{el.tag_name}_{el_id}_{el_html[:50]}"
                    if el_key not in seen_element_ids:
                        seen_element_ids.add(el_key)
                        all_found_elements.append(el)
                        print(f"[DEBUG] H&M yeni element eklendi: {el.tag_name}, id: {el_id}")
            except Exception as e:
                print(f"[DEBUG] H&M selector '{sel}' hatası: {e}")
                continue
        
        print(f"[DEBUG] H&M toplam {len(all_found_elements)} element toplandı (tüm selector'lardan)")
        
        # Şimdi tüm elementleri filtrele
        seen_size_labels = set()
        filtered = []
        
        for el in all_found_elements:
            try:
                # İç div[dir="ltr"] elementi bul (analiz sonuçlarına göre bu içeride beden text'i var)
                text = None
                try:
                    text_elem = el.find_element(By.CSS_SELECTOR, "div[dir='ltr']")
                    text = text_elem.text.strip().replace("\xa0", " ").strip().upper()
                except:
                    # Fallback 1: direkt textContent
                    try:
                        text = el.text.strip().replace("\xa0", " ").strip().upper()
                    except:
                        pass
                
                # Fallback 2: aria-label'dan çıkar
                if not text or len(text) == 0:
                    try:
                        aria_label = el.get_attribute("aria-label") or ""
                        # "s beden: stokta" formatından "s" çıkar
                        match = re.search(r'^(\w+)\s*beden', aria_label, re.IGNORECASE)
                        if match:
                            text = match.group(1).strip().upper()
                    except:
                        pass
                
                if text and (text in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL'] or (text.isdigit() and 28 <= int(text) <= 50)):
                    # Tekrar edenleri filtrele
                    if text not in seen_size_labels:
                        seen_size_labels.add(text)
                        filtered.append(el)
                        print(f"[DEBUG] H&M beden bulundu: '{text}' (element: {el.tag_name}, id: {el.get_attribute('id')}, testid: {el.get_attribute('data-testid')}, aria-label: {(el.get_attribute('aria-label') or '')[:50]})")
            except Exception as inner_e:
                print(f"[DEBUG] H&M element işlenirken hata: {inner_e}")
                continue
        
        if filtered:
            print(f"[DEBUG] H&M toplam {len(filtered)} benzersiz size element bulundu: {sorted(seen_size_labels)}")
            size_elements = filtered
        else:
            print(f"[DEBUG] H&M hiçbir element filtrelemeden geçemedi")

        if not size_elements:
            print("[DEBUG] H&M size element bulunamadı - tüm selector'lar denendi")
            # Debug: sayfanın HTML'ini kontrol et
            try:
                page_text = driver.page_source
                page_lower = page_text.lower()
                if "sizebutton" in page_lower:
                    # Kaç tane sizebutton var?
                    count_id = page_text.count("id=\"sizebutton-")
                    count_testid = page_text.count("data-testid=\"sizebutton-")
                    print(f"[DEBUG] H&M HTML'de 'sizebutton' kelimesi var (id count: {count_id}, testid count: {count_testid}) ama selector bulamadı")
                    # İlk 2000 karakteri logla
                    size_section = page_text.find("sizebutton")
                    if size_section > 0:
                        start = max(0, size_section - 500)
                        end = min(len(page_text), size_section + 500)
                        print(f"[DEBUG] H&M sizebutton çevresi (ilk görünen): {page_text[start:end][:200]}...")
                else:
                    print("[DEBUG] H&M HTML'de 'sizebutton' kelimesi yok")
                    # Belki başka bir format var?
                    if "aria-label" in page_lower and "beden" in page_lower:
                        print("[DEBUG] H&M HTML'de 'aria-label' ve 'beden' kelimesi var, belki farklı format")
                    if "role=\"radio\"" in page_lower:
                        radio_count = page_text.count("role=\"radio\"")
                        print(f"[DEBUG] H&M HTML'de {radio_count} tane role='radio' elementi var")
            except Exception as debug_e:
                print(f"[DEBUG] H&M debug hatası: {debug_e}")
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
                    # H&M stok kontrolü - Analiz sonuçlarına göre:
                    # aria-label="... stokta. beden seç." → stok VAR
                    # aria-label="... stokta yok. benzer ürünleri görmek..." → stok YOK
                    
                    aria_label = element.get_attribute("aria-label") or ""
                    aria_label_lower = aria_label.lower()
                    
                    # Analiz sonuçlarına göre: "stokta yok" veya "benzer ürünleri görmek" varsa stok yok
                    if "stokta yok" in aria_label_lower or "benzer ürünleri görmek" in aria_label_lower:
                        print(f"[DEBUG] ❌ H&M beden '{size_label}' stokta değil (aria-label: {aria_label[:80]})")
                        continue
                    # "stokta. beden seç." varsa stok var
                    elif "stokta" in aria_label_lower and "beden seç" in aria_label_lower:
                        print(f"[DEBUG] ✅ H&M beden '{size_label}' stokta! (aria-label: {aria_label[:50]})")
                        in_stock.append(size_label)
                    # Sadece "stokta" varsa ama "stokta yok" yoksa
                    elif "stokta" in aria_label_lower:
                        print(f"[DEBUG] ✅ H&M beden '{size_label}' stokta! (aria-label: {aria_label[:50]})")
                        in_stock.append(size_label)
                    else:
                        # aria-label belirsizse, disabled kontrolü yap
                        if element.get_attribute("aria-disabled") == "true":
                            print(f"[DEBUG] ❌ H&M beden '{size_label}' disabled (aria-label yok)")
                            continue
                        else:
                            # Belirsiz durum - varsayılan olarak stokta değil
                            print(f"[DEBUG] ❌ H&M beden '{size_label}' stokta değil (aria-label belirsiz: {aria_label[:50]})")

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
        
        # Sayfayı kaydır (lazy-load için)
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
            time.sleep(2)
        except:
            pass
        
        # Cookie popup kontrolü (gerekirse)
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie'], button[class*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] Mango cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle - daha fazla alternatif
        wait_selectors = [
            "button.sizeitem_sizeitem__7vipk",
            "li.sizeslist_listitem__usajg",
            "button[id^='pdp.productinfo.sizeselector.size']",
            "button[class*='sizeitem']",
            "li[class*='sizeslist'] button",
            "ul[class*='sizes'] button",
            "button[aria-controls*='size']"
        ]
        
        selector_found = False
        for wait_sel in wait_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel)))
                print(f"[DEBUG] Mango size selector görüldü (wait selector: {wait_sel})")
                selector_found = True
                time.sleep(2.5)  # Dinamik class güncellemeleri için daha uzun bekle
                break
            except TimeoutException:
                continue
        
        if not selector_found:
            print("[DEBUG] Mango size selector görünmedi - tüm wait selector'lar denendi")
            # Devam et, belki selector'lar farklı
        
        # Size elementlerini bul (button elementlerini al, tekrar edenleri filtrele)
        # CSS modules class'ları case-sensitive olabilir, o yüzden daha geniş selector'lar kullan
        size_selectors = [
            "li.sizeslist_listitem__usajg button.sizeitem_sizeitem__7vipk",
            "button.sizeitem_sizeitem__7vipk",
            "button[class*='sizeitem']",
            "li[class*='sizeslist'] button[class*='sizeitem']",
            "button[id^='pdp.productinfo.sizeselector.size']",
            "ul[class*='sizes'] button",
            "button[aria-controls*='size']",
            "li button[class*='size']"
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
                    # Mango stok kontrolü - Analiz sonuçlarına göre:
                    # Button'un içindeki span'de "notavailable" varsa → stok YOK
                    # Button'da "selectable" varsa → stok VAR
                    
                    class_attr = button.get_attribute("class") or ""
                    class_lower = class_attr.lower()
                    html_lower = (button.get_attribute("outerHTML") or "").lower()
                    
                    # İç span'de notavailable var mı kontrol et
                    try:
                        inner_spans = button.find_elements(By.CSS_SELECTOR, "span[class*='notavailable'], span[class*='not-available']")
                        if inner_spans:
                            inner_class = (inner_spans[0].get_attribute("class") or "").lower()
                            if "notavailable" in inner_class:
                                print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (iç span'de notAvailable: {inner_class[:50]})")
                                continue
                    except:
                        pass
                    
                    # Button'un HTML'inde notavailable var mı kontrol et
                    if "notavailable" in html_lower or "not-available" in html_lower:
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (HTML'de notAvailable)")
                        continue
                    
                    # notify-availability popup kontrolü
                    if "notify-availability" in html_lower or "beni haberdar et" in html_lower:
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (notify popup)")
                        continue
                    
                    # selectable class kontrolü (button level)
                    if "selectable" in class_lower:
                        print(f"[DEBUG] ✅ Mango beden '{size_label}' stokta! (selectable class)")
                        in_stock.append(size_label)
                        continue
                    
                    # Parent li'de selectable var mı?
                    try:
                        parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                        parent_class = (parent_li.get_attribute("class") or "").lower()
                        if "selectable" in parent_class:
                            print(f"[DEBUG] ✅ Mango beden '{size_label}' stokta! (parent li'de selectable)")
                            in_stock.append(size_label)
                            continue
                    except:
                        pass
                    
                    # Disabled kontrolü
                    if button.get_attribute("disabled") or button.get_attribute("aria-disabled") == "true":
                        print(f"[DEBUG] ❌ Mango beden '{size_label}' disabled")
                        continue
                    
                    # Belirsiz durum - varsayılan olarak stokta değil
                    print(f"[DEBUG] ❌ Mango beden '{size_label}' stokta değil (belirsiz, selectable yok)")
                        
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
