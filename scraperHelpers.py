# ============================
# scraperHelpers.py (REVIZE)
# Sahra: Bu dosyada PYGAME YOK. Tüm fonksiyonlar headless/worker'a uygun.
# Dönüş tiplerini tutarlı yaptık: stok varsa LIST[str] (ör. ["S","M"]),
# yoksa boş liste [] döner. Hata olursa None dönüyoruz.
# ============================

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
# Sahra: Aşağıdakiler bu dosyada kullanılmıyordu, SİLDİM (gereksiz bağımlılık yaratıyor)
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium import webdriver
# from webdriver_manager.chrome import ChromeDriverManager

import time

# ------------------------------------------------------------
# ZARA: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_zara(driver, sizes_to_check):
    """
    Sahra:
    - Girdi: driver, sizes_to_check (örn: ["S","M","L"])
    - Çıktı: stokta bulunan bedenlerin listesi. Örn: ["M","L"].
             Hiç yoksa [], hata olursa None.
    - Not: "Add to cart" tıklamaya GEREK YOK. Beden listesi üzerinden okuyoruz.
    """
    try:
        wait = WebDriverWait(driver, 30)

        # 1) Çerez (cookie) popup'ı varsa kapat
        try:
            accept = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            accept.click()
            # print("ZARA: Cookie kapatıldı.")
        except TimeoutException:
            # print("ZARA: Cookie zaten yok/kapalı.")
            pass

        # 2) Beden listesinin DOM'a gelmesini bekle
        # Not: Zara sınıf adları zamanla değişebilir; iki olası sınıfı deniyoruz.
        locators = [
            (By.CSS_SELECTOR, ".size-selector-sizes"),
            (By.CSS_SELECTOR, "[data-qa-qualifier='size-selector-sizes']"),  # alternatif
        ]
        found_container = False
        for loc in locators:
            try:
                wait.until(EC.presence_of_element_located(loc))
                found_container = True
                break
            except TimeoutException:
                continue

        if not found_container:
            # print("ZARA: Beden konteyneri bulunamadı.")
            return []

        # 3) Tüm beden satırlarını al
        # Ör. her bir li için label ve button bilgisi var
        size_items = driver.find_elements(By.CSS_SELECTOR, ".size-selector-sizes .size-selector-sizes-size")
        if not size_items:
            size_items = driver.find_elements(By.CSS_SELECTOR, "[data-qa-qualifier='size-selector-sizes'] .size-selector-sizes-size")

        # 4) İstediğimiz bedenleri karşılaştır, stokta olanları topla
        in_stock = []  # ← çıktı listemiz
        wanted = set([s.strip() for s in sizes_to_check]) if sizes_to_check else set()

        for li in size_items:
            try:
                # Label: görünen beden yazısı
                label_el = li.find_element(By.CSS_SELECTOR, "[data-qa-qualifier='size-selector-sizes-size-label']")
                size_label = label_el.text.strip()

                # İstediğimiz bedenlerden değilse pas geç
                if wanted and (size_label not in wanted):
                    continue

                # Buton: stok durumunu attribute'larından anlayacağız
                button = li.find_element(By.CSS_SELECTOR, ".size-selector-sizes-size__button")

                # "Benzer ürünler" gösteriyorsa stok yok demektir
                try:
                    similar_txt_el = button.find_element(By.CSS_SELECTOR, ".size-selector-sizes-size__action")
                    if "Benzer ürünler" in similar_txt_el.text.strip():
                        # print(f"ZARA: {size_label} stok YOK (benzer ürünler).")
                        continue
                except NoSuchElementException:
                    pass  # bu alan yoksa normal devam

                # Stok bilgisini veren attribute'lar:
                # - data-qa-action: "size-in-stock" | "size-low-on-stock" | "size-out-of-stock"
                # - disabled/aria-disabled
                qa_action = button.get_attribute("data-qa-action") or ""
                aria_dis  = (button.get_attribute("aria-disabled") or "").lower() == "true"
                disabled  = button.get_attribute("disabled") is not None

                # "in-stock" varyantları → stok var
                if ("size-in-stock" in qa_action) or ("size-low-on-stock" in qa_action):
                    in_stock.append(size_label)
                else:
                    # Bazen qa_action boş olabilir; o durumda disable değilse stok olabilir (temkinli yaklaşım)
                    if not aria_dis and not disabled and qa_action == "":
                        # print(f"ZARA: {size_label} muhtemelen stok VAR (fallback).")
                        in_stock.append(size_label)
                    # else:
                    #     print(f"ZARA: {size_label} stok YOK.")

            except (NoSuchElementException, StaleElementReferenceException) as e:
                # print(f"ZARA: Eleman okunamadı: {e}")
                continue

        # Sahra: Tutarlı dönüş (liste). Boş liste → stok yok.
        return in_stock

    except Exception as e:
        print(f"[check_stock_zara] Hata: {e}")
        return None


# ------------------------------------------------------------
# BERSHKA: link-bazlı beden kontrolü
# ------------------------------------------------------------
def check_stock_bershka(driver, sizes_to_check):
    """
    Sahra:
    - Girdi: driver, sizes_to_check (örn: ["XS","S","M"])
    - Çıktı: stokta bulunan bedenlerin listesi. Örn: ["S","M"].
             Hiç yoksa [], hata olursa None.
    """
    try:
        wait = WebDriverWait(driver, 25)

        # 1) Çerez popup'ını kapat
        try:
            accept = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            accept.click()
        except Exception:
            pass

        # 2) Beden listesini bekle
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul[data-qa-anchor='productDetailSize']")))

        # 3) Dinamik class güncellemelerine 1-2 sn tolerans
        time.sleep(2)

        buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-qa-anchor='sizeListItem']")
        in_stock = []
        wanted = set([s.strip() for s in sizes_to_check]) if sizes_to_check else set()

        for btn in buttons:
            try:
                label_el = btn.find_element(By.CSS_SELECTOR, "span.text__label")
                size_label = label_el.text.strip()

                if wanted and (size_label not in wanted):
                    continue

                # "is-disabled" yoksa tıklanabilir → stok var
                cls = btn.get_attribute("class") or ""
                if "is-disabled" not in cls:
                    in_stock.append(size_label)
                # else: stok yok

            except Exception:
                continue

        return in_stock

    except Exception as e:
        print(f"[check_stock_bershka] Hata: {e}")
        return None


# ------------------------------------------------------------
# ROSSMMAN: basit stok kontrol (isteğe bağlı; dönüş True/False)
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

        # "Sepete Ekle" butonu bulunabiliyorsa stok olabilir
        try:
            button = driver.find_element(By.XPATH, "//button[@type='submit' and contains(., 'Sepete Ekle')]")
            if button:
                # driver.execute_script("arguments[0].click();", button)  # istersen tıkla
                return True
        except Exception:
            return False

        return False
    except Exception:
        return None


# ------------------------------------------------------------
# WATSONS: sonuç sayısı kontrolü (örnek düzeltme)
# ------------------------------------------------------------
def watsonsChecker(driver):
    """
    True → listede ürün var,
    False → '0 ürün' veya liste yok,
    None  → hata.
    """
    try:
        wait = WebDriverWait(driver, 20)
        # presence_of_all_elements_located locator TUPLE ister:
        elems = wait.until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "product-grid-manager__view-mount"))
        )

        # elems bir liste; metin kontrolü yapmak için birleştiriyoruz
        combined_text = " ".join([e.text.strip() for e in elems if e.text]).lower()
        if "0 ürün" in combined_text or "0 urun" in combined_text:
            return False
        return True
    except TimeoutException:
        # Liste hiç gelmediyse yok sayalım
        return False
    except Exception:
        return None
