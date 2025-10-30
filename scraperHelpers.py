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
      - 'is-disabled' sınıfı olan butonlar stok YOK
      - aria-description="yakında stokta olacak!" = stok YOK
      - aria-description="az sayıda kaldı!" veya boş = stok VAR
      - Eşleşme case-insensitive yapılır.
    """
    try:
        wait = WebDriverWait(driver, 25)

        # Cookie popup kontrolü
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie'], button[class*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] Bershka cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass

        # Sayfayı kaydır (lazy-load için)
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.4);")
            time.sleep(1.5)
        except:
            pass

        # Beden listesi container - Analiz sonuçlarına göre UL container YOK, direkt butonları bulabiliriz
        wait_selectors = [
            "button[data-qa-anchor='sizeListItem']",  # camelCase
            "button[data-qa-anchor='sizelistitem']",  # küçük harf (analiz sonuçlarına göre)
            "ul[data-qa-anchor='productDetailSize']",  # Container (varsa)
            "button[role='button'][aria-label*='beden']"  # Fallback
        ]

        selector_found = False
        for wait_sel in wait_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel)))
                print(f"[DEBUG] Bershka size selector görüldü (wait selector: {wait_sel})")
                selector_found = True
                time.sleep(2)  # Element'lerin tam yüklenmesi için
                break
            except TimeoutException:
                continue

        if not selector_found:
            print("[DEBUG] Bershka wait selector bulunamadı, yine de size element aramaya devam ediliyor...")
            time.sleep(2)

        # Dinamik class güncellemelerine küçük tolerans
        time.sleep(1)

        # Analiz sonuçlarına göre: button[data-qa-anchor="sizelistitem"] (küçük harf) formatında
        button_selectors = [
            "button[data-qa-anchor='sizelistitem']",  # EN ÖNEMLİ: Küçük harf (analiz sonuçlarına göre)
            "button[data-qa-anchor='sizeListItem']",  # camelCase (fallback)
            "ul[data-qa-anchor='productDetailSize'] button",  # Container içinden
            "button[role='button'][aria-label*='beden']"  # Genel fallback
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
                        # Beden text'ini bul - analiz sonuçlarına göre span.text__label içinde
                        try:
                            size_label_elem = button.find_element(By.CSS_SELECTOR, "span.text__label")
                            size_label = size_label_elem.text.strip().upper()
                        except NoSuchElementException:
                            # Fallback: button text'inden al
                            size_label = button.text.strip().upper()
                            # "32" gibi rakamları filtrele
                            if not size_label or not (size_label in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL'] or (size_label.isdigit() and 28 <= int(size_label) <= 50)):
                                continue

                        if not wanted or size_label in wanted:
                            # Class kontrolü - analiz sonuçlarına göre: "is-disabled" class'ı varsa stok YOK
                            class_attr = button.get_attribute("class") or ""
                            
                            # Aria-description kontrolü - ek kontrol
                            aria_desc = (button.get_attribute("aria-description") or "").lower()
                            
                            # Stok durumu belirleme
                            if "is-disabled" in class_attr.lower():
                                print(f"[DEBUG] ❌ Bershka beden '{size_label}' stokta değil (is-disabled class)")
                                continue
                            elif "yakında stokta olacak" in aria_desc:
                                print(f"[DEBUG] ❌ Bershka beden '{size_label}' stokta değil (aria-description: yakında stokta)")
                                continue
                            else:
                                print(f"[DEBUG] ✅ Bershka beden '{size_label}' stokta! (class: {class_attr[:50]}, aria-desc: {aria_desc[:30]})")
                                in_stock.append(size_label)
                    except NoSuchElementException:
                        continue
                    except Exception as e:
                        print(f"[DEBUG] Bershka button işlenirken hata: {e}")
                        continue

                if in_stock:
                    print(f"[DEBUG] ✅ Bershka toplam {len(in_stock)} beden stokta: {in_stock}")
                    return in_stock
            except Exception as e:
                print(f"[DEBUG] Bershka selector '{sel}' hatası: {e}")
                continue

        if not in_stock:
            print(f"[DEBUG] Bershka istenen bedenler stokta değil: {list(wanted)}")
        
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
        wait = WebDriverWait(driver, 5)  # Optimize: 25'ten 5'e düşürüldü
        
        # Cookie popup kontrolü (önce cookie'yi kapat)
        try:
            cookie_button = driver.find_elements(By.CSS_SELECTOR, "button[id*='onetrust'], button[id*='cookie'], button[class*='cookie']")
            if cookie_button:
                cookie_button[0].click()
                print("[DEBUG] H&M cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Sayfa yüklenmesini bekle - DOM tam yüklenene kadar bekle
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # Sayfa yüklenmesi için ek bekleme
            time.sleep(2)
            
            # HTML uzunluğu kontrolü - eğer çok kısaysa sayfa tam yüklenmemiş demektir
            html_length = len(driver.page_source)
            if html_length < 1000:  # 1000 karakterden azsa problem var
                print(f"[DEBUG] H&M sayfa HTML çok kısa ({html_length} karakter), daha uzun bekleniyor...")
                time.sleep(5)  # Ekstra bekleme
                html_length = len(driver.page_source)
                print(f"[DEBUG] H&M sayfa HTML uzunluğu (yeniden kontrol): {html_length} karakter")
                # Hâlâ kısa ise refresh dene (bazı sayfalarda ilk yüklemede içerik gelmiyor)
                if html_length < 1000:
                    try:
                        print("[DEBUG] H&M sayfa yenileniyor (refresh)")
                        driver.refresh()
                        WebDriverWait(driver, 10).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        time.sleep(3)
                        html_length = len(driver.page_source)
                        print(f"[DEBUG] H&M sayfa HTML uzunluğu (refresh sonrası): {html_length} karakter")
                        # Çok nadir: refresh de yetmezse aynı URL'e yeniden git (hard reload)
                        if html_length < 1000:
                            try:
                                current_url = driver.current_url
                                print("[DEBUG] H&M hard reload (navigate current_url)")
                                driver.get(current_url)
                                WebDriverWait(driver, 10).until(
                                    lambda d: d.execute_script("return document.readyState") == "complete"
                                )
                                time.sleep(3)
                                html_length = len(driver.page_source)
                                print(f"[DEBUG] H&M sayfa HTML uzunluğu (hard reload sonrası): {html_length} karakter")
                            except Exception:
                                pass
                    except Exception as _:
                        pass
            
            print("[DEBUG] H&M sayfa yüklendi")
        except:
            print("[DEBUG] H&M sayfa yükleme beklemesi timeout oldu, devam ediliyor...")
        
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
            time.sleep(2)  # Biraz daha uzun bekle
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
        
        # Size selector'ın yüklenmesini bekle - Optimize: Öncelikli selector'lar
        size_elements = []
        wait_selectors = [
            "div[data-testid^='sizeButton-']",  # EN ÖNEMLİ: Büyük B formatı
            "div[id^='sizeButton-']",  # Büyük B formatı (fallback)
            "*[aria-label*='beden']",  # Genel fallback
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
            print("[DEBUG] H&M wait selector bulunamadı, debug'a geçiliyor...")
            time.sleep(1)  # Optimize: 2'den 1'e düşürüldü
        
        # Size elementlerini bul - ANALİZ SONUÇLARINA GÖRE: li > div[id="sizeButton-0"] formatında
        # ÖNEMLİ NOT: ID formatı büyük harfle başlıyor: sizeButton-0 (sizebutton-0 değil!)
        # ÖNEMLİ: Tüm selector'ları birleştirip tek seferde arama yap (tüm bedenleri bulmak için)
        size_selectors = [
            # Öncelik 1: Analiz sonuçlarına göre - li içinde ve BÜYÜK HARF: sizeButton-
            "li > div[id^='sizeButton-'], li > div[data-testid^='sizeButton-']",  # EN ÖNEMLİ: Büyük B formatı
            "li > div[id^='sizebutton-'], li > div[data-testid^='sizebutton-']",  # Küçük b (fallback)
            "li > div[id*='sizeButton'], li > div[data-testid*='sizeButton']",  # Partial match (büyük B)
            "li > div[id*='sizebutton'], li > div[data-testid*='sizebutton']",  # Partial match (küçük b)
            # Öncelik 2: Direkt div (li olmadan da olabilir) - BÜYÜK HARF ÖNCELİKLİ
            "div[id^='sizeButton-'], div[data-testid^='sizeButton-']",  # Büyük B formatı
            "div[id^='sizebutton-'], div[data-testid^='sizebutton-']",  # Küçük b (fallback)
            "div[id*='sizeButton'], div[data-testid*='sizeButton']",  # Partial match (büyük B)
            # Öncelik 3: role='radio' olanlar (tüm varyasyonlar) - Analiz sonuçlarına göre parent: LI
            "li > div[role='radio'][aria-label*='Beden']",  # Büyük B ile başlayan (stokta olanlar)
            "li > div[role='radio'][aria-label*='beden']",  # Küçük b ile (stokta olmayanlar)
            "div[role='radio'][aria-label*='Beden']",  # Direkt div (büyük B)
            "div[role='radio'][aria-label*='beden']",  # Direkt div (küçük b)
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
                # Sayfanın tam yüklenmesini bekle (optimize: daha kısa)
                time.sleep(1)
                
                page_text = driver.page_source
                page_lower = page_text.lower()
                
                print(f"[DEBUG] H&M sayfa HTML uzunluğu: {len(page_text)} karakter")
                try:
                    nd_scripts = driver.find_elements(By.CSS_SELECTOR, "script#__NEXT_DATA__")
                    print(f"[DEBUG] H&M __NEXT_DATA__ script sayısı: {len(nd_scripts)}")
                except Exception:
                    pass
                
                # Büyük harf formatını kontrol et (analiz sonuçlarına göre: sizeButton-)
                count_id_capital = page_text.count("id=\"sizeButton-")
                count_testid_capital = page_text.count("data-testid=\"sizeButton-")
                count_id_lower = page_text.count("id=\"sizebutton-")
                count_testid_lower = page_text.count("data-testid=\"sizebutton-")
                
                if count_id_capital > 0 or count_testid_capital > 0:
                    print(f"[DEBUG] H&M HTML'de 'sizeButton-' (büyük B) formatı var (id: {count_id_capital}, testid: {count_testid_capital}) ama selector bulamadı")
                elif count_id_lower > 0 or count_testid_lower > 0:
                    print(f"[DEBUG] H&M HTML'de 'sizebutton-' (küçük b) formatı var (id: {count_id_lower}, testid: {count_testid_lower}) ama selector bulamadı")
                elif "sizebutton" in page_lower:
                    print(f"[DEBUG] H&M HTML'de 'sizebutton' kelimesi var (farklı format) ama selector bulamadı")
                else:
                    print("[DEBUG] H&M HTML'de 'sizebutton' veya 'sizeButton' kelimesi yok")
                
                # Belki başka bir format var?
                try:
                    if "aria-label" in page_lower and "beden" in page_lower:
                        print("[DEBUG] H&M HTML'de 'aria-label' ve 'beden' kelimesi var, belki farklı format")
                        # Aria-label içinde beden geçen element sayısını kontrol et
                        aria_beden_elements = driver.find_elements(By.CSS_SELECTOR, "*[aria-label*='beden'], *[aria-label*='Beden']")
                        print(f"[DEBUG] H&M aria-label'da 'beden' geçen {len(aria_beden_elements)} element var")
                        if aria_beden_elements:
                            # İlk birkaç elementin aria-label'ını göster (optimize: 5'ten 3'e)
                            for i, el in enumerate(aria_beden_elements[:3]):
                                try:
                                    aria_val = el.get_attribute("aria-label") or ""
                                    el_tag = el.tag_name
                                    el_id = el.get_attribute("id") or ""
                                    print(f"[DEBUG] H&M örnek aria-label[{i}]: tag={el_tag}, id={el_id[:50]}, aria-label={aria_val[:100]}")
                                    
                                    # Bu element beden text'i içeriyor mu kontrol et
                                    if aria_val and ("S " in aria_val or "M " in aria_val or "L " in aria_val or "XL " in aria_val):
                                        el_text = el.text.strip()[:50]
                                        print(f"[DEBUG] H&M potansiyel beden elementi [{i}]: text={el_text}")
                                except Exception as e:
                                    print(f"[DEBUG] H&M aria-label element[{i}] işlenirken hata: {e}")
                    else:
                        print("[DEBUG] H&M HTML'de 'aria-label' ve 'beden' birlikte geçmiyor")
                except Exception as e:
                    print(f"[DEBUG] H&M aria-label kontrol hatası: {e}")
                    import traceback
                    print(f"[DEBUG] H&M aria-label hata detayı: {traceback.format_exc()}")
                
                try:
                    if "role=\"radio\"" in page_lower or "role='radio'" in page_lower:
                        radio_count = page_text.count("role=\"radio\"") + page_text.count("role='radio'")
                        print(f"[DEBUG] H&M HTML'de {radio_count} tane role='radio' elementi var")
                        # Role radio olan elementleri kontrol et
                        radio_elements = driver.find_elements(By.CSS_SELECTOR, "[role='radio'], [role=\"radio\"]")
                        print(f"[DEBUG] H&M {len(radio_elements)} role='radio' elementi bulundu")
                        if radio_elements:
                            # Optimize: 5'ten 3'e düşürüldü
                            for i, el in enumerate(radio_elements[:3]):
                                try:
                                    aria_val = el.get_attribute("aria-label") or ""
                                    el_id = el.get_attribute("id") or ""
                                    el_tag = el.tag_name
                                    el_text = el.text.strip()[:50]
                                    print(f"[DEBUG] H&M örnek radio[{i}]: tag={el_tag}, id={el_id[:50]}, text={el_text}, aria-label={aria_val[:80]}")
                                except Exception as e:
                                    print(f"[DEBUG] H&M radio element[{i}] işlenirken hata: {e}")
                    else:
                        print("[DEBUG] H&M HTML'de 'role=radio' bulunamadı")
                except Exception as e:
                    print(f"[DEBUG] H&M role='radio' kontrol hatası: {e}")
                    import traceback
                    print(f"[DEBUG] H&M role='radio' hata detayı: {traceback.format_exc()}")
                
                # Son çare: Tüm li elementlerini kontrol et
                try:
                    all_lis = driver.find_elements(By.CSS_SELECTOR, "li")
                    print(f"[DEBUG] H&M sayfada toplam {len(all_lis)} li elementi var")
                    if all_lis:
                        # Optimize: 10'dan 5'e düşürüldü
                        for i, li in enumerate(all_lis[:5]):
                            try:
                                li_text = li.text.strip()[:100]
                                li_class = li.get_attribute("class") or ""
                                li_aria = li.get_attribute("aria-label") or ""
                                if "S" in li_text or "M" in li_text or "beden" in li_text.lower() or "beden" in li_aria.lower():
                                    print(f"[DEBUG] H&M potansiyel li[{i}]: class={li_class[:50]}, aria-label={li_aria[:80]}, text={li_text}")
                            except:
                                pass
                except Exception as e:
                    print(f"[DEBUG] H&M li element kontrol hatası: {e}")
                    
                # JSON fallback: __NEXT_DATA__ içinden varyantları parse et (H&M Next.js sayfaları)
                try:
                    import json
                    script_elems = driver.find_elements(By.CSS_SELECTOR, "script#__NEXT_DATA__")
                    if script_elems:
                        raw_json = script_elems[0].get_attribute("innerHTML") or script_elems[0].get_attribute("textContent") or ""
                        data = json.loads(raw_json)
                        wanted = set(x.strip().upper() for x in (sizes_to_check or []))

                        def collect_sizes(obj, acc):
                            try:
                                if isinstance(obj, dict):
                                    # A few common H&M keys: variants, articles, variantSizes, sizes
                                    keys = obj.keys()
                                    # Heuristic: an entry with a size-like name/code and availability flag/value
                                    size_value = (obj.get('size') or obj.get('name') or obj.get('sizeName') or obj.get('code') or obj.get('title'))
                                    avail = obj.get('inStock')
                                    if avail is None:
                                        avail = obj.get('available')
                                    if avail is None:
                                        avail = obj.get('availability')
                                    if avail is None and 'stock' in obj:
                                        try:
                                            avail = (int(obj.get('stock') or 0) > 0)
                                        except:
                                            pass
                                    if isinstance(size_value, str):
                                        label = size_value.strip().upper().replace("\xa0", " ")
                                        if (label in ['XXS','XS','S','M','L','XL','XXL'] or (label.isdigit() and 28 <= int(label) <= 50)):
                                            if avail is True or (isinstance(avail, str) and avail.upper() in ['IN_STOCK','AVAILABLE','OK']):
                                                acc.add(label)
                                    for v in obj.values():
                                        collect_sizes(v, acc)
                                elif isinstance(obj, list):
                                    for it in obj:
                                        collect_sizes(it, acc)
                            except Exception:
                                pass

                        parsed_in_stock = set()
                        collect_sizes(data, parsed_in_stock)
                        parsed_in_stock_list = sorted(parsed_in_stock)
                        if parsed_in_stock_list:
                            print(f"[DEBUG] H&M JSON fallback ile stoklar: {parsed_in_stock_list}")
                            if wanted:
                                parsed_in_stock_list = [s for s in parsed_in_stock_list if s in wanted]
                            if parsed_in_stock_list:
                                return parsed_in_stock_list
                    else:
                        # Bazı sayfalarda __NEXT_DATA__ window üzerinde tutulabiliyor
                        try:
                            raw = driver.execute_script("return window.__NEXT_DATA__ ? JSON.stringify(window.__NEXT_DATA__) : null;")
                            if raw:
                                data = json.loads(raw)
                                wanted = set(x.strip().upper() for x in (sizes_to_check or []))
                                def collect_sizes(obj, acc):
                                    try:
                                        if isinstance(obj, dict):
                                            size_value = (obj.get('size') or obj.get('name') or obj.get('sizeName') or obj.get('code') or obj.get('title'))
                                            avail = obj.get('inStock')
                                            if avail is None:
                                                avail = obj.get('available')
                                            if avail is None:
                                                avail = obj.get('availability')
                                            if avail is None and 'stock' in obj:
                                                try:
                                                    avail = (int(obj.get('stock') or 0) > 0)
                                                except:
                                                    pass
                                            if isinstance(size_value, str):
                                                label = size_value.strip().upper().replace("\xa0", " ")
                                                if (label in ['XXS','XS','S','M','L','XL','XXL'] or (label.isdigit() and 28 <= int(label) <= 50)):
                                                    if avail is True or (isinstance(avail, str) and avail.upper() in ['IN_STOCK','AVAILABLE','OK']):
                                                        acc.add(label)
                                            for v in obj.values():
                                                collect_sizes(v, acc)
                                        elif isinstance(obj, list):
                                            for it in obj:
                                                collect_sizes(it, acc)
                                    except Exception:
                                        pass
                                parsed_in_stock = set()
                                collect_sizes(data, parsed_in_stock)
                                parsed_in_stock_list = sorted(parsed_in_stock)
                                if parsed_in_stock_list:
                                    print(f"[DEBUG] H&M JSON (window.__NEXT_DATA__) stoklar: {parsed_in_stock_list}")
                                    if wanted:
                                        parsed_in_stock_list = [s for s in parsed_in_stock_list if s in wanted]
                                    if parsed_in_stock_list:
                                        return parsed_in_stock_list
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[DEBUG] H&M JSON fallback hatası: {e}")

                # Network fallback: performance loglarından JSON response parse et
                try:
                    import json
                    try:
                        perf_logs = driver.get_log('performance')
                    except Exception:
                        perf_logs = []
                    candidate_req_ids = []
                    for entry in perf_logs[-120:]:
                        try:
                            msg = json.loads(entry.get('message', '{}')).get('message', {})
                            if msg.get('method') == 'Network.responseReceived':
                                params = msg.get('params', {})
                                resp = params.get('response', {})
                                mime = (resp.get('mimeType') or '').lower()
                                url = (resp.get('url') or '').lower()
                                if ('json' in mime) or any(k in url for k in ['json', 'variant', 'product', 'article']):
                                    candidate_req_ids.append(params.get('requestId'))
                        except Exception:
                            continue

                    parsed_sizes = set()
                    for rid in candidate_req_ids[-15:]:
                        if not rid:
                            continue
                        body = None
                        try:
                            body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': rid})
                        except Exception:
                            body = None
                        if not body or not body.get('body'):
                            continue
                        try:
                            data = json.loads(body['body'])
                        except Exception:
                            continue

                        def collect_sizes(obj, acc):
                            try:
                                if isinstance(obj, dict):
                                    size_value = (obj.get('size') or obj.get('name') or obj.get('sizeName') or obj.get('code') or obj.get('title'))
                                    avail = obj.get('inStock')
                                    if avail is None:
                                        avail = obj.get('available')
                                    if avail is None:
                                        avail = obj.get('availability')
                                    if avail is None and 'stock' in obj:
                                        try:
                                            avail = (int(obj.get('stock') or 0) > 0)
                                        except Exception:
                                            pass
                                    if isinstance(size_value, str):
                                        label = size_value.strip().upper().replace("\xa0", " ")
                                        if (label in ['XXS','XS','S','M','L','XL','XXL'] or (label.isdigit() and 28 <= int(label) <= 50)):
                                            if avail is True or (isinstance(avail, str) and str(avail).upper() in ['IN_STOCK','AVAILABLE','OK']):
                                                acc.add(label)
                                    for v in obj.values():
                                        collect_sizes(v, acc)
                                elif isinstance(obj, list):
                                    for it in obj:
                                        collect_sizes(it, acc)
                            except Exception:
                                pass

                        collect_sizes(data, parsed_sizes)

                    parsed_list = sorted(parsed_sizes)
                    if parsed_list:
                        print(f"[DEBUG] H&M Network fallback stoklar: {parsed_list}")
                        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
                        if wanted:
                            parsed_list = [s for s in parsed_list if s in wanted]
                        if parsed_list:
                            return parsed_list
                except Exception as e:
                    print(f"[DEBUG] H&M network fallback hatası: {e}")

            except Exception as debug_e:
                print(f"[DEBUG] H&M debug hatası: {debug_e}")
                import traceback
                print(f"[DEBUG] H&M debug hata detayı: {traceback.format_exc()}")
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


# ------------------------------------------------------------
# STRADIVARIUS: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_stradivarius(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["XS","S","M"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : []
    Notlar :
      - li > button[data-cy="product-normal-size-button"] yapısında
      - disabled attribute varsa → stok YOK
      - data-cy="grid-product-size-stock-none" varsa → stok YOK
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
                print("[DEBUG] Stradivarius cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle
        wait_selectors = [
            "button[data-cy='product-normal-size-button']",
            "li button[data-cy='product-normal-size-button']",
            "button[id*='size-button-']",
            "li[aria-label]"
        ]
        
        selector_found = False
        for wait_sel in wait_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel)))
                print(f"[DEBUG] Stradivarius size selector görüldü (wait selector: {wait_sel})")
                selector_found = True
                time.sleep(2)  # Element'lerin tam yüklenmesi için
                break
            except TimeoutException:
                continue
        
        if not selector_found:
            print("[DEBUG] Stradivarius size selector görünmedi - tüm wait selector'lar denendi")
            time.sleep(2)  # Yine de biraz bekle
        
        # Size elementlerini bul - Analiz sonuçlarına göre: li > button[data-cy="product-normal-size-button"]
        size_selectors = [
            "li button[data-cy='product-normal-size-button']",  # EN ÖNEMLİ: Analiz sonuçlarına göre
            "button[data-cy='product-normal-size-button']",  # Direkt button
            "li button[id*='size-button-']",  # ID ile
            "button[id*='size-button-']",  # Direkt ID
            "li[aria-label] button"  # li aria-label ile
        ]
        
        size_elements = []
        seen_size_labels = set()
        
        for sel in size_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                print(f"[DEBUG] Stradivarius selector '{sel}' ile {len(found)} element bulundu")
                if found:
                    for button in found:
                        try:
                            size_label = None
                            # Beden text'i bul - analiz sonuçlarına göre div.sc-hoLldG içinde
                            try:
                                # Önce div.sc-hoLldG içinde ara
                                size_div = button.find_element(By.CSS_SELECTOR, "div.sc-hoLldG, div[class*='hoLldG']")
                                size_label = size_div.text.strip().upper()
                                if not size_label:
                                    raise NoSuchElementException("Empty text in div.sc-hoLldG")
                            except (NoSuchElementException, Exception) as e1:
                                # Fallback 1: li'nin aria-label'ından
                                try:
                                    parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                                    aria_label_raw = parent_li.get_attribute("aria-label") or ""
                                    if aria_label_raw:
                                        # "XS beden" veya "32 beden" formatından sadece beden kısmını al
                                        import re
                                        match = re.search(r'^(\w+)\s*beden', aria_label_raw.strip(), re.IGNORECASE)
                                        if match:
                                            size_label = match.group(1).strip().upper()
                                        else:
                                            size_label = aria_label_raw.strip().upper()
                                except Exception as e2:
                                    # Fallback 2: direkt button text
                                    button_text = button.text.strip().upper()
                                    if button_text:
                                        size_label = button_text
                            
                            # Debug: bulunan text'i göster
                            # Fallback 3: Button ID'sinden beden çıkar (örn: product-451624756-size-button-l -> "l")
                            if not size_label:
                                try:
                                    button_id = button.get_attribute("id") or ""
                                    if button_id and "-size-button-" in button_id:
                                        # ID formatı: product-XXX-size-button-XXS veya product-XXX-size-button-35
                                        parts = button_id.split("-size-button-")
                                        if len(parts) > 1:
                                            size_from_id = parts[-1].strip().upper()
                                            # Geçerli beden formatı mı kontrol et
                                            if size_from_id in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'] or (size_from_id.isdigit() and 28 <= int(size_from_id) <= 50):
                                                size_label = size_from_id
                                                print(f"[DEBUG] Stradivarius beden text bulundu (button id): '{size_label}'")
                                except:
                                    pass
                            
                            if not size_label:
                                button_html = (button.get_attribute("outerHTML") or "")[:150]
                                print(f"[DEBUG] Stradivarius button text bulunamadı (html: {button_html}...)")
                                continue
                            
                            # Text temizleme: gereksiz karakterleri kaldır
                            size_label = size_label.replace("\xa0", " ").strip().upper()
                            
                            # Beden formatı kontrolü (daha esnek)
                            is_valid_size = False
                            if size_label in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']:
                                is_valid_size = True
                            elif size_label.isdigit() and 28 <= int(size_label) <= 50:
                                is_valid_size = True
                            elif len(size_label) <= 3:  # Kısa text'ler de geçerli olabilir (38, 40, vs)
                                try:
                                    int(size_label)
                                    if 28 <= int(size_label) <= 50:
                                        is_valid_size = True
                                except:
                                    pass
                            
                            if is_valid_size:
                                # Tekrar edenleri filtrele
                                if size_label not in seen_size_labels:
                                    seen_size_labels.add(size_label)
                                    size_elements.append(button)
                                    print(f"[DEBUG] Stradivarius beden bulundu: '{size_label}' (button id: {button.get_attribute('id')})")
                            else:
                                print(f"[DEBUG] Stradivarius geçersiz beden formatı: '{size_label}'")
                        except Exception as inner_e:
                            print(f"[DEBUG] Stradivarius button işlenirken hata: {inner_e}")
                            continue
                    
                    if size_elements:
                        print(f"[DEBUG] Stradivarius {len(size_elements)} benzersiz size element bulundu (selector: {sel})")
                        break
            except Exception as e:
                print(f"[DEBUG] Stradivarius selector '{sel}' hatası: {e}")
                continue
        
        if not size_elements:
            print("[DEBUG] Stradivarius size element bulunamadı")
            return []

        # Birden fazla bölümde (öneri carouselleri, popuplar vb.) aynı selector'lar olabilir.
        # Ana ürünün beden listesini seçmek için, butonları en yakın container'a göre gruplayıp
        # sayfada en üstte yer alan (y konumu en küçük) ve en az 3 beden içeren grubu seçeceğiz.
        try:
            container_to_buttons = {}
            container_to_y = {}
            for btn in list(size_elements):
                container = None
                try:
                    # Önce UL container'ı dene
                    container = btn.find_element(By.XPATH, "./ancestor::ul[1]")
                except Exception:
                    pass
                if container is None:
                    try:
                        # Sonra div içinde product-size geçen sınıfı olan container'ı dene
                        container = btn.find_element(By.XPATH, "./ancestor::div[contains(@class,'product-size')][1]")
                    except Exception:
                        pass
                # Hiçbiri bulunamazsa, bir üst div'e bağla (gevşek fallback)
                if container is None:
                    try:
                        container = btn.find_element(By.XPATH, "./ancestor::div[1]")
                    except Exception:
                        continue

                key = container
                if key not in container_to_buttons:
                    container_to_buttons[key] = []
                    try:
                        container_to_y[key] = container.location.get('y', 999999)
                    except Exception:
                        container_to_y[key] = 999999
                container_to_buttons[key].append(btn)

            # Uygun container'ı seç: en az 3 farklı beden içersin ve sayfada en yukarıda olsun
            def count_unique_sizes(buttons_list):
                uniq = set()
                for b in buttons_list:
                    try:
                        txt = (b.text or "").strip().upper()
                        if txt:
                            uniq.add(txt)
                    except Exception:
                        continue
                return len(uniq)

            selected_container = None
            best_y = 999999
            for cont, btns in container_to_buttons.items():
                uniq_count = count_unique_sizes(btns)
                y = container_to_y.get(cont, 999999)
                if uniq_count >= 3 and y < best_y:
                    best_y = y
                    selected_container = cont

            if selected_container is not None:
                size_elements = container_to_buttons[selected_container]
                print(f"[DEBUG] Stradivarius ana beden container seçildi: y={best_y}, buton sayısı={len(size_elements)}")
            else:
                print("[DEBUG] Stradivarius uygun bir ana container bulunamadı, tüm bulunan elementler kullanılacak")
        except Exception as e:
            print(f"[DEBUG] Stradivarius container gruplama hatası: {e}")
        
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        in_stock = []
        
        for button in size_elements:
            try:
                size_label = None
                # Beden text'ini tekrar al
                try:
                    size_div = button.find_element(By.CSS_SELECTOR, "div.sc-hoLldG, div[class*='hoLldG']")
                    size_label = size_div.text.strip().upper()
                    if size_label:  # Boş olmadığından emin ol
                        print(f"[DEBUG] Stradivarius beden text bulundu (div.sc-hoLldG): '{size_label}'")
                except:
                    pass
                
                # Fallback 1: aria-label
                if not size_label:
                    try:
                        parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                        aria_label_raw = parent_li.get_attribute("aria-label") or ""
                        if aria_label_raw:
                            # "XS beden" formatından beden çıkar
                            import re
                            match = re.search(r'^(\w+)\s*beden', aria_label_raw.strip(), re.IGNORECASE)
                            if match:
                                size_label = match.group(1).strip().upper()
                            else:
                                size_label = aria_label_raw.strip().upper()
                        if size_label:
                            print(f"[DEBUG] Stradivarius beden text bulundu (aria-label): '{size_label}'")
                    except:
                        pass
                
                # Fallback 2: button text
                if not size_label:
                    try:
                        size_label = button.text.strip().upper()
                        if size_label:
                            print(f"[DEBUG] Stradivarius beden text bulundu (button text): '{size_label}'")
                    except:
                        pass
                
                # Fallback 3: Button ID'sinden beden çıkar (örn: product-451624756-size-button-l -> "l")
                if not size_label:
                    try:
                        button_id = button.get_attribute("id") or ""
                        if button_id and "-size-button-" in button_id:
                            # ID formatı: product-XXX-size-button-XXS veya product-XXX-size-button-35
                            parts = button_id.split("-size-button-")
                            if len(parts) > 1:
                                size_from_id = parts[-1].strip().upper()
                                # Geçerli beden formatı mı kontrol et
                                if size_from_id in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'] or (size_from_id.isdigit() and 28 <= int(size_from_id) <= 50):
                                    size_label = size_from_id
                                    print(f"[DEBUG] Stradivarius beden text bulundu (button id): '{size_label}'")
                    except:
                        pass
                
                if not size_label:
                    print(f"[DEBUG] Stradivarius beden text bulunamadı, button id: {button.get_attribute('id')}")
                    continue
                
                # İstenen beden kontrolü
                if not wanted or size_label in wanted:
                    print(f"[DEBUG] Stradivarius beden '{size_label}' istenenler arasında, stok kontrol ediliyor...")
                    # Stradivarius stok kontrolü - Analiz sonuçlarına göre:
                    # 1. disabled attribute varsa → stok YOK
                    # 2. data-cy="grid-product-size-stock-none" varsa → stok YOK
                    # 3. "benzer ürünleri görüntüle" text'i varsa → stok YOK
                    # 4. "bana haber ver" veya "stok olmayınca bana haber ver" text'i varsa → stok YOK
                    # 5. Yoksa → stok VAR
                    
                    is_disabled = button.get_attribute("disabled") is not None
                    html_lower = (button.get_attribute("outerHTML") or "").lower()
                    button_text = (button.text or "").lower()
                    button_class_lower = (button.get_attribute("class") or "").lower()
                    
                    # data-cy="grid-product-size-stock-none" kontrolü
                    has_stock_none = "grid-product-size-stock-none" in html_lower or "stock-none" in html_lower
                    
                    # "benzer ürünleri görüntüle" kontrolü
                    has_similar_products = "benzer ürünleri görüntüle" in button_text or "benzer ürünleri görüntüle" in html_lower or "benzer ürün" in button_text
                    
                    # "bana haber ver" veya "stok olmayınca bana haber ver" kontrolü
                    has_notify_me = "bana haber ver" in button_text or "bana haber ver" in html_lower or "stok olmayınca bana haber ver" in button_text or "stok olmayınca bana haber ver" in html_lower
                    
                    # Parent li'de de kontrol et
                    try:
                        parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                        parent_html = (parent_li.get_attribute("outerHTML") or "").lower()
                        parent_text = (parent_li.text or "").lower()
                        parent_class_lower = (parent_li.get_attribute("class") or "").lower()
                        if "benzer ürünleri görüntüle" in parent_text or "benzer ürün" in parent_text:
                            has_similar_products = True
                        if "bana haber ver" in parent_text or "stok olmayınca bana haber ver" in parent_text:
                            has_notify_me = True
                        if "grid-product-size-stock-none" in parent_html or "stock-none" in parent_html:
                            has_stock_none = True
                    except:
                        pass

                    # Class tabanlı durum sezgileri (kXgBpS = OOS, lbblEr = in-stock) - saha çıktısından
                    has_oos_by_class = ("kxgbps" in button_class_lower) or ("kxgbps" in parent_html) or ("kxgbps" in (parent_class_lower if 'parent_class_lower' in locals() else ""))
                    has_instock_by_class = ("lbblEr".lower() in button_class_lower) or ("lbblEr".lower() in parent_html)
                    
                    print(f"[DEBUG] Stradivarius beden '{size_label}' - disabled={is_disabled}, stock-none={has_stock_none}, similar_products={has_similar_products}, notify_me={has_notify_me}, oosByClass={has_oos_by_class}, inByClass={has_instock_by_class}")
                    
                    if is_disabled:
                        print(f"[DEBUG] ❌ Stradivarius beden '{size_label}' stokta değil (disabled attribute)")
                        continue
                    elif has_stock_none:
                        print(f"[DEBUG] ❌ Stradivarius beden '{size_label}' stokta değil (data-cy='grid-product-size-stock-none')")
                        continue
                    elif has_oos_by_class:
                        print(f"[DEBUG] ❌ Stradivarius beden '{size_label}' stokta değil (class heuristic)")
                        continue
                    elif has_similar_products:
                        print(f"[DEBUG] ❌ Stradivarius beden '{size_label}' stokta değil ('benzer ürünleri görüntüle' text'i bulundu)")
                        continue
                    elif has_notify_me:
                        print(f"[DEBUG] ❌ Stradivarius beden '{size_label}' stokta değil ('bana haber ver' text'i bulundu)")
                        continue
                    else:
                        print(f"[DEBUG] ✅ Stradivarius beden '{size_label}' stokta!")
                        in_stock.append(size_label)
                else:
                    print(f"[DEBUG] Stradivarius beden '{size_label}' istenenler arasında değil (wanted: {list(wanted)})")
                        
            except Exception as e:
                print(f"[DEBUG] Stradivarius button işlenirken hata: {e}")
                import traceback
                print(f"[DEBUG] Stradivarius hata detayı: {traceback.format_exc()}")
                continue
        
        if in_stock:
            print(f"[DEBUG] ✅ Stradivarius toplam {len(in_stock)} beden stokta: {in_stock}")
        else:
            print(f"[DEBUG] Stradivarius istenen bedenler stokta değil: {list(wanted)}")
        
        return in_stock
        
    except Exception as e:
        print(f"[DEBUG] check_stock_stradivarius genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []


# ------------------------------------------------------------
# OYSHO: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_oysho(driver, sizes_to_check):
    """
    Girdi  : driver, sizes_to_check (örn: ["XS","S","M"])
    Çıktı  : stokta bulunan bedenler (list[str]); yoksa [].
    Hata   : []
    Notlar :
      - li.product-size-selector__size-item > button[data-testid="product-size-selector-item"] yapısında
      - Beden text'i button içindeki span'de
      - disabled attribute varsa → stok YOK
      - aria-disabled="true" varsa → stok YOK
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
                print("[DEBUG] Oysho cookie popup kapatıldı")
                time.sleep(1)
        except:
            pass
        
        # Size selector'ın yüklenmesini bekle
        wait_selectors = [
            "button[data-testid='product-size-selector-item']",
            "li.product-size-selector__size-item button",
            "button.oy-button.product-size-selector__size-button",
            "li[class*='size-item'] button"
        ]
        
        selector_found = False
        for wait_sel in wait_selectors:
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_sel)))
                print(f"[DEBUG] Oysho size selector görüldü (wait selector: {wait_sel})")
                selector_found = True
                time.sleep(2)  # Element'lerin tam yüklenmesi için
                break
            except TimeoutException:
                continue
        
        if not selector_found:
            print("[DEBUG] Oysho size selector görünmedi - tüm wait selector'lar denendi")
            time.sleep(2)  # Yine de biraz bekle
        
        # Size elementlerini bul - Analiz sonuçlarına göre: button[data-testid="product-size-selector-item"]
        size_selectors = [
            "button[data-testid='product-size-selector-item']",  # EN ÖNEMLİ: Analiz sonuçlarına göre
            "li.product-size-selector__size-item button",  # LI container'dan
            "button.oy-button.product-size-selector__size-button",  # Class ile
            "li[class*='size-item'] button"  # Genel
        ]
        
        size_elements = []
        seen_size_labels = set()
        
        for sel in size_selectors:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, sel)
                print(f"[DEBUG] Oysho selector '{sel}' ile {len(found)} element bulundu")
                if found:
                    for button in found:
                        try:
                            # Beden text'i bul - analiz sonuçlarına göre span içinde
                            try:
                                # Önce span içinde ara
                                size_span = button.find_element(By.CSS_SELECTOR, "span")
                                size_label = size_span.text.strip().upper()
                            except NoSuchElementException:
                                # Fallback: direkt button text
                                size_label = button.text.strip().upper()
                            
                            if not size_label:
                                continue
                            
                            # Text temizleme
                            size_label = size_label.replace("\xa0", " ").strip().upper()
                            
                            # Beden formatı kontrolü
                            is_valid_size = False
                            if size_label in ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']:
                                is_valid_size = True
                            elif size_label.isdigit() and 28 <= int(size_label) <= 50:
                                is_valid_size = True
                            elif len(size_label) <= 3:  # Kısa text'ler
                                try:
                                    int(size_label)
                                    if 28 <= int(size_label) <= 50:
                                        is_valid_size = True
                                except:
                                    pass
                            
                            if is_valid_size:
                                # Tekrar edenleri filtrele
                                if size_label not in seen_size_labels:
                                    seen_size_labels.add(size_label)
                                    size_elements.append(button)
                                    print(f"[DEBUG] Oysho beden bulundu: '{size_label}' (button data-testid: {button.get_attribute('data-testid')})")
                        except Exception as inner_e:
                            print(f"[DEBUG] Oysho button işlenirken hata: {inner_e}")
                            continue
                    
                    if size_elements:
                        print(f"[DEBUG] Oysho {len(size_elements)} benzersiz size element bulundu (selector: {sel})")
                        break
            except Exception as e:
                print(f"[DEBUG] Oysho selector '{sel}' hatası: {e}")
                continue
        
        if not size_elements:
            print("[DEBUG] Oysho size element bulunamadı")
            return []
        
        wanted = set(x.strip().upper() for x in (sizes_to_check or []))
        in_stock = []
        
        for button in size_elements:
            try:
                # Beden text'ini tekrar al
                try:
                    size_span = button.find_element(By.CSS_SELECTOR, "span")
                    size_label = size_span.text.strip().upper()
                except:
                    size_label = button.text.strip().upper()
                
                if not size_label:
                    continue
                
                # İstenen beden kontrolü
                if not wanted or size_label in wanted:
                    print(f"[DEBUG] Oysho beden '{size_label}' istenenler arasında, stok kontrol ediliyor...")
                    
                    # Oysho stok kontrolü - Analiz sonuçlarına göre:
                    # 1. disabled attribute varsa → stok YOK
                    # 2. aria-disabled="true" varsa → stok YOK
                    # 3. Button içinde "benzer ürünler" veya stok yok göstergesi varsa → stok YOK
                    # 4. Button'a tıklanabilir mi kontrol et (stok varsa tıklanabilir olmalı)
                    
                    is_disabled = button.get_attribute("disabled") is not None
                    aria_disabled = button.get_attribute("aria-disabled") == "true"
                    button_html = (button.get_attribute("outerHTML") or "").lower()
                    button_class = (button.get_attribute("class") or "").lower()
                    
                    # Button içinde "benzer ürünler", "stok yok", "out of stock" gibi ifadeleri kontrol et
                    has_similar_products = False
                    try:
                        # Button içindeki tüm text'i kontrol et
                        button_text = button.text.lower()
                        similar_phrases = ["benzer ürünler", "benzer ürün", "stok yok", "out of stock", "unavailable", "not available"]
                        for phrase in similar_phrases:
                            if phrase in button_text:
                                has_similar_products = True
                                print(f"[DEBUG] Oysho beden '{size_label}' - '{phrase}' text'i bulundu")
                                break
                    except:
                        pass
                    
                    # Button HTML'inde stok yok göstergeleri kontrol et
                    has_out_of_stock_indicator = False
                    out_of_stock_indicators = [
                        "out-of-stock", "outofstock", "unavailable", "not-available",
                        "no-stock", "stock-none", "disabled", "not-allowed"
                    ]
                    for indicator in out_of_stock_indicators:
                        if indicator in button_html or indicator in button_class:
                            has_out_of_stock_indicator = True
                            print(f"[DEBUG] Oysho beden '{size_label}' - '{indicator}' indicator bulundu")
                            break
                    
                    # Button'ın parent li elementinde de kontrol et
                    try:
                        parent_li = button.find_element(By.XPATH, "./ancestor::li[1]")
                        parent_class = (parent_li.get_attribute("class") or "").lower()
                        parent_html = (parent_li.get_attribute("outerHTML") or "").lower()
                        
                        for indicator in out_of_stock_indicators:
                            if indicator in parent_class or indicator in parent_html:
                                has_out_of_stock_indicator = True
                                print(f"[DEBUG] Oysho beden '{size_label}' - parent li'de '{indicator}' bulundu")
                                break
                    except:
                        pass
                    
                    # Tüm kontrolleri özetle
                    print(f"[DEBUG] Oysho beden '{size_label}' - disabled={is_disabled}, aria-disabled={aria_disabled}, similar_products={has_similar_products}, out_of_stock={has_out_of_stock_indicator}")
                    print(f"[DEBUG] Oysho beden '{size_label}' - button class: {button_class[:100]}")
                    
                    if is_disabled:
                        print(f"[DEBUG] ❌ Oysho beden '{size_label}' stokta değil (disabled attribute)")
                        continue
                    elif aria_disabled:
                        print(f"[DEBUG] ❌ Oysho beden '{size_label}' stokta değil (aria-disabled='true')")
                        continue
                    elif has_similar_products:
                        print(f"[DEBUG] ❌ Oysho beden '{size_label}' stokta değil ('benzer ürünler' text'i bulundu)")
                        continue
                    elif has_out_of_stock_indicator:
                        print(f"[DEBUG] ❌ Oysho beden '{size_label}' stokta değil (out-of-stock indicator bulundu)")
                        continue
                    else:
                        # Son kontrol: Button tıklanabilir mi? (EC.element_to_be_clickable test etmeden, sadece görünür ve enabled mı kontrol et)
                        try:
                            if not button.is_displayed():
                                print(f"[DEBUG] ❌ Oysho beden '{size_label}' stokta değil (button görünmüyor)")
                                continue
                        except:
                            pass
                        
                        print(f"[DEBUG] ✅ Oysho beden '{size_label}' stokta!")
                        in_stock.append(size_label)
                else:
                    print(f"[DEBUG] Oysho beden '{size_label}' istenenler arasında değil (wanted: {list(wanted)})")
                        
            except Exception as e:
                print(f"[DEBUG] Oysho button işlenirken hata: {e}")
                continue
        
        if in_stock:
            print(f"[DEBUG] ✅ Oysho toplam {len(in_stock)} beden stokta: {in_stock}")
        else:
            print(f"[DEBUG] Oysho istenen bedenler stokta değil: {list(wanted)}")
        
        return in_stock
        
    except Exception as e:
        print(f"[DEBUG] check_stock_oysho genel hatası: {e}")
        import traceback
        print(f"[DEBUG] Hata detayı:\n{traceback.format_exc()}")
        return []
