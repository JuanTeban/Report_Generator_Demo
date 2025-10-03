import os
import re
import time
import json
import requests
from datetime import date
import unicodedata
from urllib.parse import unquote

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from config import DEBUGGER_ADDRESS, DOWNLOAD_FOLDER, DEBUG_MODE
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.common.exceptions import NoSuchElementException, JavascriptException
from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException
)
from config import DEBUGGER_ADDRESS


def connect_to_browser():
    opts = Options()
    opts.add_experimental_option("debuggerAddress", DEBUGGER_ADDRESS)
    driver = webdriver.Chrome(options=opts)
    print("✅ Conectado exitosamente al navegador existente.")
    return driver


def create_requests_session(driver):
    s = requests.Session()
    s.verify = False

    try:
        ua = driver.execute_script("return navigator.userAgent")
        if ua:
            s.headers.update({"User-Agent": ua})
    except Exception:
        pass

    for c in driver.get_cookies():
        try:
            s.cookies.set(c["name"], c["value"], domain=c.get("domain"))
        except Exception:
            s.cookies.set(c["name"], c["value"])
    print("✅ Sesión de 'requests' creada con las cookies del navegador.")
    return s


def _ui5_ok(driver) -> bool:
    try:
        return bool(driver.execute_script("return !!(window.sap && sap.ui && sap.ui.getCore);"))
    except JavascriptException:
        return False


def switch_to_app_iframe(driver):
    driver.switch_to.default_content()
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for idx, fr in enumerate(frames):
        try:
            driver.switch_to.frame(fr)
            if not _ui5_ok(driver):
                driver.switch_to.default_content()
                continue
            has_table = driver.execute_script("""
                return !!document.querySelector(
                  "[id$='--analyticalTable'],[id$='--table'],[id$='--analyticalTable-vsb']"
                );
            """)
            if has_table:
                print(f"   -> Entré al iframe #{idx} (contiene UI5 + tabla).")
                return True
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    driver.switch_to.default_content()
    if _ui5_ok(driver):
        print("   -> La app NO parece usar iframe (UI5 presente en raíz).")
        return True

    print("   -> ⚠️ No encontré un iframe con UI5; continuaré en raíz (podría fallar).")
    return False


def ui5_table_info(driver):
    if not _ui5_ok(driver):
        return None

    table_id = driver.execute_script("""
        var cand = document.querySelector("[id$='--analyticalTable']")
                 || document.querySelector("[id$='--table']");
        return cand ? cand.id : null;
    """)
    if not table_id:
        return None

    info = driver.execute_script("""
        var id = arguments[0];
        var t = sap.ui.getCore().byId(id);
        if (!t) return null;
        var meta = t.getMetadata().getName();
        var rowsBind = t.getBinding && t.getBinding("rows");
        var itemsBind = t.getBinding && t.getBinding("items");
        var total = -1;
        if (rowsBind && rowsBind.getLength) total = rowsBind.getLength();
        else if (itemsBind && itemsBind.getLength) total = itemsBind.getLength();
        var vis = t.getVisibleRowCount ? t.getVisibleRowCount() : 20;
        return {tableId:id, meta:meta, total: total, visible: vis, hasRows: !!rowsBind, hasItems: !!itemsBind};
    """, table_id)
    return info


def _safe_slug(txt: str, max_len: int = 64) -> str:
    txt = (txt or "").strip()
    txt = txt.replace("\\", "_").replace("/", "_")
    txt = re.sub(r'[<>:"|?*]+', "_", txt)
    txt = re.sub(r"\s+", "_", txt)
    txt = txt[:max_len].rstrip(" ._")
    return txt or "SIN_NOMBRE"

def extract_defect_id_from_text(txt: str) -> str:
    """Extrae el número entre paréntesis al final del texto del ítem: '... (8000002052)' -> '8000002052'."""
    if not txt:
        return ""
    m = re.search(r"\((\d+)\)\s*$", txt.strip())
    return m.group(1) if m else ""

def _ui5_try_quick_search(driver, term: str) -> bool:
    """
    Intenta escribir en un SearchField típico de UI5 (placeholder 'Buscar', role=search, etc).
    Devuelve True si pudo inyectar la búsqueda y espera el idle.
    """
    try:
        js = """
        const q = arguments[0];
        // 1) SearchField visible
        let input = document.querySelector("div.sapMSF input[type='search']") 
                 || document.querySelector("div.sapMSF input")
                 || document.querySelector("input[role='searchbox']")
                 || document.querySelector("input[placeholder*='Buscar'],input[aria-label*='Buscar']");
        if (!input) return false;
        input.focus();
        input.value = q;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter',bubbles:true}));
        input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter',bubbles:true}));
        return true;
        """
        ok = driver.execute_script(js, term)
        if ok:
            wait_ui5_global_idle(driver, timeout=30, debug=DEBUG_MODE)
        return bool(ok)
    except Exception:
        return False

def _recollect_visible_rows(driver):
    """Re-escanea la tabla visible (mismo mecanismo que harvest visible) para refrescar enlaces."""
    try:
        return driver.execute_script("""
            function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}
            function lower(s){return norm(s).toLowerCase();}
            var root = document.querySelector('div.sapUiTableCnt');
            if (!root) return [];
            var links = Array.from(root.querySelectorAll("a.sapMLnk[href*='Action-genericApp']"));
            var out = [];
            links.forEach(function(a){
                var tr = a.closest('tr');
                if (!tr) return;
                var responsable = "";
                var tds = Array.from(tr.querySelectorAll('td'));
                for (var i=0; i<tds.length; i++){
                    var td = tds[i];
                    var lbl = (td.getAttribute('headers')||'') + ' ' + (td.getAttribute('aria-labelledby')||'');
                    var headerTxt = '';
                    lbl.split(/\\s+/).forEach(function(id){
                        var el = document.getElementById(id);
                        if (el) headerTxt += ' ' + lower(el.textContent||'');
                    });
                    if (headerTxt.includes('responsable')) {
                        responsable = norm(td.innerText||td.textContent); break;
                    }
                }
                out.push({text:norm(a.textContent||''), url:a.href||'', responsable:responsable||'SIN_RESPONSABLE'});
            });
            // de-dup
            const seen = new Set(); const dedup=[];
            out.forEach(it=>{ if(it.url && !seen.has(it.url)){ dedup.push(it); seen.add(it.url);} });
            return dedup;
        """) or []
    except Exception:
        return []



def _parse_defect_text(text: str):
    if not text:
        return {"id": "SIN_ID", "title": "SIN_TITULO"}
    
    match = re.search(r'^(.*)\s\((\d+)\)\s*$', text)
    if match:
        title = match.group(1).strip()
        defect_id = match.group(2).strip()
        return {"id": defect_id, "title": title}
    
    return {"id": "SIN_ID", "title": text.strip()}


def get_defect_links(driver):
    print("🔎 Buscando la lista de defectos...")
    wait = WebDriverWait(driver, 30)

    switch_to_app_iframe(driver)
    link_sel = (By.XPATH, "//a[contains(@class,'sapMLnk') and contains(@href,'Action-genericApp')]")
    wait.until(EC.presence_of_element_located(link_sel))

    info = ui5_table_info(driver)
    if not info or not isinstance(info.get("total"), (int, float)) or info["total"] <= 0:
        print("   -> ⚠️ No hay info confiable; uso fallback con rueda.")
        return _fallback_wheel_collect(driver)

    table_id = info["tableId"]
    total = int(info["total"])
    print(f"   -> Tabla: {info['meta']}   total={total} visibles={info['visible']}")

    seen, collected = set(), []

    def harvest_visible_using_headers():
        raw_data = driver.execute_script("""
            function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}
            function lower(s){return norm(s).toLowerCase();}
            var root = document.querySelector('div.sapUiTableCnt');
            if (!root) return [];
            var out = [];

            var links = Array.from(root.querySelectorAll("a.sapMLnk[href*='Action-genericApp']"));
            links.forEach(function(a){
                var tr = a.closest('tr');
                if (!tr) return;

                var responsable = "";
                var tds = Array.from(tr.querySelectorAll('td'));
                for (var i=0; i<tds.length; i++){
                    var td = tds[i];
                    var hdrId = td.getAttribute('headers');
                    var headerTxt = '';
                    if (hdrId) {
                        var hdrEl = document.getElementById(hdrId);
                        headerTxt = lower(hdrEl ? hdrEl.textContent : '');
                    }
                    if (!headerTxt) {
                        var lb = td.getAttribute('aria-labelledby') || '';
                        lb.split(/\\s+/).forEach(function(id){
                            var el = document.getElementById(id);
                            if (el) headerTxt += ' ' + lower(el.textContent || '');
                        });
                        headerTxt = lower(headerTxt);
                    }
                    if (headerTxt.includes('responsable')) {
                        responsable = norm(td.innerText || td.textContent);
                        break;
                    }
                }

                out.push({
                    text: norm(a.textContent || ''),
                    url: a.href || '',
                    responsable: responsable || 'SIN_RESPONSABLE'
                });
            });

            var seen = new Set(), dedup = [];
            out.forEach(function(it){
                if (it.url && !seen.has(it.url)) { dedup.push(it); seen.add(it.url); }
            });
            return dedup;
        """) or []
        
        processed_data = []
        for item in raw_data:
            parsed_info = _parse_defect_text(item.get('text', ''))
            item.update(parsed_info)
            processed_data.append(item)
        return processed_data


    last_size = 0
    for i in range(total):
        driver.execute_script("""
            var t = sap.ui.getCore().byId(arguments[0]);
            if (t && t.setFirstVisibleRow) { t.setFirstVisibleRow(arguments[1]); }
        """, table_id, i)
        time.sleep(0.18)

        for it in harvest_visible_using_headers():
            if it["url"] in seen:
                continue
            collected.append(it)
            seen.add(it["url"])

        if (i + 1) % 10 == 0 or i == total - 1:
            if len(collected) != last_size:
                print(f"   -> Progreso: {i+1}/{total} (acumulados: {len(collected)})")
                last_size = len(collected)

    print(f"   -> ✅ Recopilados {len(collected)} defectos.")
    if not collected:
        print("   -> ⚠️ Nada recolectado; intento fallback con rueda.")
        return _fallback_wheel_collect(driver)

    return collected

def _find_in_collected_by_id(collected, ticket_id: str):
    """Busca en la lista recolectada por el patrón '(ID)' en el texto."""
    for it in collected or []:
        if extract_defect_id_from_text(it.get("text") or "") == ticket_id:
            return it
    return None

def find_or_collect_defect_by_id(driver, ticket_id: str, current_collected: list):
    """
    Intenta resolver un ticket ID a {text,url,responsable}:
      1) Busca en lo ya recolectado (rápido)
      2) Si no está, intenta quick search y vuelve a escanear
      3) Si aún no, usa el fallback de scroll y vuelve a buscar
    """
    # 1) directo en colección actual
    it = _find_in_collected_by_id(current_collected, ticket_id)
    if it:
        print(f"   -> Ticket {ticket_id}: encontrado en la lista visible.")
        return it

    print(f"   -> Ticket {ticket_id}: no visible. Intentando búsqueda UI5…")
    try:
        switch_to_app_iframe(driver)
    except Exception:
        pass

    # 2) quick search
    if _ui5_try_quick_search(driver, ticket_id):
        time.sleep(0.8)
        after = _recollect_visible_rows(driver)
        it = _find_in_collected_by_id(after, ticket_id)
        if it:
            print(f"   -> Ticket {ticket_id}: encontrado tras búsqueda.")
            return it

    # 3) último recurso: fallback de scroll completo
    print(f"   -> Ticket {ticket_id}: usando fallback de scroll para recolectar.")
    all_again = _fallback_wheel_collect(driver)
    it = _find_in_collected_by_id(all_again, ticket_id)
    if it:
        print(f"   -> Ticket {ticket_id}: encontrado tras fallback.")
        return it

    return None

def _fallback_wheel_collect(driver):
    print("   -> Fallback: desplazamiento con rueda sobre el contenedor de filas…")
    wait = WebDriverWait(driver, 20)
    link_sel = (By.XPATH, "//a[contains(@class,'sapMLnk') and contains(@href,'Action-genericApp')]")
    wait.until(EC.presence_of_element_located(link_sel))

    try:
        scroll_area = driver.find_element(By.CSS_SELECTOR, "div.sapUiTableCtrlScr")
    except NoSuchElementException:
        first_link = driver.find_element(*link_sel)
        scroll_area = first_link.find_element(By.XPATH, "./ancestor::*[contains(@class,'sapUiTableCnt') or contains(@class,'sapUiTable')]")

    seen, collected = set(), []

    def harvest_once():
        added = 0
        raw_rows = driver.execute_script("""
            function norm(s){return (s||'').replace(/\\s+/g,' ').trim();}
            function lower(s){return norm(s).toLowerCase();}
            var root = document.querySelector('div.sapUiTableCnt');
            if (!root) return [];
            var out = [];

            var links = Array.from(root.querySelectorAll("a.sapMLnk[href*='Action-genericApp']"));
            links.forEach(function(a){
                var tr = a.closest('tr');
                if (!tr) return;

                var responsable = "";
                var tds = Array.from(tr.querySelectorAll('td'));
                for (var i=0; i<tds.length; i++){
                    var td = tds[i];
                    var hdrId = td.getAttribute('headers');
                    var headerTxt = '';
                    if (hdrId) {
                        var hdrEl = document.getElementById(hdrId);
                        headerTxt = lower(hdrEl ? hdrEl.textContent : '');
                    }
                    if (!headerTxt) {
                        var lb = td.getAttribute('aria-labelledby') || '';
                        lb.split(/\\s+/).forEach(function(id){
                            var el = document.getElementById(id);
                            if (el) headerTxt += ' ' + lower(el.textContent || '');
                        });
                        headerTxt = lower(headerTxt);
                    }
                    if (headerTxt.includes('responsable')) {
                        responsable = norm(td.innerText || td.textContent);
                        break;
                    }
                }

                out.push({
                    text: norm(a.textContent || ''),
                    url: a.href || '',
                    responsable: responsable || 'SIN_RESPONSABLE'
                });
            });
            return out;
        """) or []

        for it in raw_rows:
            href = it.get("url") or ""
            if "Action-genericApp" not in href or href in seen:
                continue
            
            parsed_info = _parse_defect_text(it.get('text', ''))
            it.update(parsed_info)
            
            if not it.get("title"):
                continue

            collected.append(it)
            seen.add(href)
            added += 1
        return added

    harvest_once()
    stagnant = 0
    for _ in range(500):
        driver.execute_script("""
            const el = arguments[0];
            const evt = new WheelEvent('wheel', {deltaY: el.clientHeight});
            el.dispatchEvent(evt);
        """, scroll_area)
        time.sleep(0.2)
        if harvest_once() == 0:
            stagnant += 1
            if stagnant >= 8:
                break
        else:
            stagnant = 0

    print(f"   -> Fallback reunió {len(collected)} enlaces.")
    return collected


_WIN_RESERVED = {"CON","PRN","AUX","NUL",
                 "COM1","COM2","COM3","COM4","COM5","COM6","COM7","COM8","COM9",
                 "LPT1","LPT2","LPT3","LPT4","LPT5","LPT6","LPT7","LPT8","LPT9"}

def _sanitize_filename_win(name: str) -> str:
    s = (name or "").strip()
    s = s.replace("\\", "_").replace("/", "_")
    s = re.sub(r'[<>:"|?*]+', "_", s)
    s = re.sub(r"\s+", "_", s)
    base, ext = os.path.splitext(s or "archivo")
    if base.upper() in _WIN_RESERVED:
        base += "_"
    s = base + ext
    return s or "archivo.bin"


def download_file_with_requests(session, url, dir_path, fallback_name):
    dir_path = os.path.abspath(dir_path)
    os.makedirs(dir_path, exist_ok=True)
    try:
        with session.get(url, stream=True, timeout=90) as r:
            r.raise_for_status()
            cd = r.headers.get("Content-Disposition") or r.headers.get("content-disposition", "")
            m = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd or "", re.I)

            raw_name = m.group(1) if m else (fallback_name or "archivo.bin")
            raw_name = unquote(raw_name)
            raw_name = unicodedata.normalize("NFC", raw_name)
            
            fname = _sanitize_filename_win(raw_name)
            if "." not in os.path.basename(fname):
                fname += ".bin"

            fpath = os.path.join(dir_path, fname)
            
            counter = 1
            original_base, original_ext = os.path.splitext(fname)
            while os.path.exists(fpath):
                new_name = f"{original_base}({counter}){original_ext}"
                fpath = os.path.join(dir_path, new_name)
                counter += 1
            
            fname = os.path.basename(fpath)
            
            final_fpath = os.path.abspath(fpath)
            if os.name == 'nt' and len(final_fpath) > 255 and not final_fpath.startswith('\\\\?\\'):
                final_fpath = '\\\\?\\' + final_fpath

            print(f"       - [DL] {fname}")

            with open(final_fpath, "wb") as f:
                for chunk in r.iter_content(1 << 15):
                    if chunk:
                        f.write(chunk)
            print(f"       - ✅ Descargado: '{fname}'")
            return fpath
            
    except requests.RequestException as e:
        print(f"       - ❌ Error HTTP al descargar {url}: {e}")
        return None


def save_debug_screenshot(driver, name):
    if not DEBUG_MODE:
        return
    try:
        debug_folder = os.path.join(os.path.dirname(__file__), "debug")
        os.makedirs(debug_folder, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filepath = os.path.join(debug_folder, f"{name}_{timestamp}.png")
        
        driver.save_screenshot(filepath)
        print(f"   -> 📸 [DEBUG] Captura de pantalla guardada en: {filepath}")
    except Exception as e:
        print(f"   -> ⚠️ [DEBUG] No se pudo guardar la captura de pantalla: {e}")


def wait_ui5_global_idle(driver, timeout=90, stable_ms=600, poll=0.25, debug=False):
    deadline = time.time() + timeout
    last_clear = None
    while time.time() < deadline:
        try:
            busy_count = driver.execute_script("""
                var nodes = document.querySelectorAll('.sapUiLocalBusyIndicator');
                var visible = 0;
                nodes.forEach(function(n){
                    var s = window.getComputedStyle(n);
                    if (s && s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') visible++;
                });
                return visible;
            """) or 0
        except Exception:
            busy_count = 0

        if busy_count == 0:
            if last_clear is None:
                last_clear = time.time()
            if (time.time() - last_clear) * 1000 >= stable_ms:
                if debug:
                    print("   -> [DEBUG] UI5 global idle.")
                return True
        else:
            last_clear = None
        time.sleep(poll)
    if debug:
        print("   -> [DEBUG] UI5 global idle: timeout.")
    return False


def select_anexos_tab(driver, wait, debug=False):
    XPATH = ("//div[@role='tab' and (normalize-space(@title)='Anexos' "
             " or .//div[contains(@class,'sapMITBText') and normalize-space(.)='Anexos'])]")

    def is_selected(tab_el):
        try:
            sel = tab_el.get_attribute("aria-selected")
            cls = tab_el.get_attribute("class") or ""
            return sel == "true" or "sapMITBSelected" in cls
        except Exception:
            return False

    tab = wait.until(EC.presence_of_element_located((By.XPATH, XPATH)))
    content_id = tab.get_attribute("aria-controls") or "__xmlview3--idIconTabBarMulti-content"

    if is_selected(tab):
        if debug:
            print("   -> [DEBUG] 'Anexos' ya estaba seleccionado.")
        return content_id

    for attempt in range(1, 11):
        try:
            wait_ui5_global_idle(driver, timeout=20, debug=debug)

            target = None
            try:
                target = tab.find_element(By.CSS_SELECTOR, ".sapMITBTab")
            except Exception:
                target = tab

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
            try:
                ActionChains(driver).move_to_element(target).pause(0.05).click().perform()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", target)

            WebDriverWait(driver, 10).until(lambda d: is_selected(tab))
            wait_ui5_global_idle(driver, timeout=30, debug=debug)
            return content_id

        except StaleElementReferenceException:
            if debug:
                print(f"   -> [DEBUG] STALE al clicar 'Anexos' (intento {attempt}); relocalizando…")
            tab = wait.until(EC.presence_of_element_located((By.XPATH, XPATH)))
            content_id = tab.get_attribute("aria-controls") or content_id
        except TimeoutException:
            if debug:
                print(f"   -> [DEBUG] 'Anexos' no quedó seleccionado (intento {attempt}); reintento…")
        time.sleep(0.4)

    if debug:
        print("   -> [DEBUG] Fallback: no pude confirmar selección; uso content_id y seguiré.")
    return content_id


def process_defect_attachments(driver, session, defect_info, base_folder, path_strategy="by_responsable"):
    main_window = driver.current_window_handle
    driver.switch_to.new_window('tab')

    print(f"📂 Procesando defecto: {defect_info['text']}")
    print("   -> Abriendo URL del defecto. Esperando a que la página cargue...")
    try:
        driver.set_page_load_timeout(90)
        driver.get(defect_info["url"])
    except TimeoutException:
        print("   -> ❌ Timeout: La página del defecto tardó más de 90 segundos en cargar.")
        save_debug_screenshot(driver, "error_carga_inicial")
        return
    finally:
        driver.set_page_load_timeout(35)

    wait = WebDriverWait(driver, 60)

    try:
        wait.until(EC.visibility_of_element_located((
            By.XPATH, "//div[@role='tab' and contains(., 'Detalles')]"
        )))
        wait_ui5_global_idle(driver, timeout=45, debug=DEBUG_MODE)
        print("   -> ✅ Página del defecto cargada.")

        try:
            switch_to_app_iframe(driver)
        except Exception:
            pass

        print("   -> Abriendo pestaña 'Anexos' de forma robusta…")
        content_id = select_anexos_tab(driver, wait, debug=DEBUG_MODE)
        
        wait_ui5_global_idle(driver, timeout=60, debug=DEBUG_MODE)

        print("   -> Esperando a que la tabla de anexos sea poblada con filas...")
        try:
            tabla_selector = (By.XPATH, f"//tbody[contains(@id, 'CustomColumnsTable-tblBody')]/tr")
            WebDriverWait(driver, 45).until(
                EC.presence_of_element_located(tabla_selector)
            )
            print("   -> ✅ ¡Tabla poblada! Las filas de anexos ahora son visibles.")
        except TimeoutException:
            print("   -> ⚠️  La tabla de anexos está vacía o no cargó a tiempo.")
            save_debug_screenshot(driver, "timeout_tabla_vacia")
            return
            
        def get_links_multifrequency(container_id):
            return driver.execute_script("""
                const containerId = arguments[0];
                const root = containerId ? document.getElementById(containerId) : document;
                const selectors = [
                    "a.sapMLnk[href*='/documentContent'][href*='$value']",
                    "a[title^='Hacer clic para descargar fichero']",
                    "a[href*='vhp-downloaddocument-']",
                    "a.sapMListTblCell[href*='/documentContent']",
                    "a[href*='/documentContent']"
                ];
                let links = [];
                for (const selector of selectors) {
                    const found = Array.from(root.querySelectorAll(selector));
                    if (found.length) {
                        links = found;
                        break;
                    }
                }
                return links.map(a => ({
                    href: a.href || "", text: (a.textContent || "").trim(),
                    title: a.getAttribute('title') || "", id: a.id || ""
                }));
            """, container_id) or []
        
        links_info = get_links_multifrequency(content_id)

        if not links_info:
            print("   -> ⚠️  No se encontraron enlaces de descarga en la pestaña 'Anexos'.")
            save_debug_screenshot(driver, "error_extraccion_links_raro")
            return

        print(f"   -> ✅ ¡Éxito! Se encontraron {len(links_info)} enlaces de anexos.")

        title = defect_info.get("title", defect_info["text"]).strip()
        defect_id = defect_info.get("id", "SIN_ID").strip()

        responsable = (defect_info.get("responsable") or "SIN_RESPONSABLE").strip()
        responsable_dir = _safe_slug(responsable, 48)
        defect_dirname = f"{defect_id}-{_safe_slug(title, 64)}"

        defect_dir = os.path.join(
            base_folder, responsable_dir, defect_dirname, date.today().isoformat()
        )
        os.makedirs(defect_dir, exist_ok=True)
        print(f"   -> Descargando en: {os.path.abspath(defect_dir)}")

        meta = {"defect": defect_info["text"], "url": defect_info["url"], "attachments": []}
        print(f"   -> Descargando {len(links_info)} anexos…")
        for li in links_info:
            href = li.get("href") or ""
            title_attr = li.get("title") or ""
            text_attr = li.get("text") or ""
            m_title = re.search(r'Hacer clic para descargar fichero:\s*(.+)$', title_attr)
            suggested_name = m_title.group(1).strip() if m_title else (text_attr.strip() or "archivo.bin")
            saved_path = download_file_with_requests(session, href, defect_dir, suggested_name)
            if saved_path:
                meta["attachments"].append({"title": suggested_name, "href": href, "path": saved_path})

        meta_path = os.path.join(defect_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"   -> 📝 Metadata guardada en '{os.path.basename(meta_path)}'")

    except Exception as e:
        print(f"   -> ❌ Error inesperado procesando defecto: {repr(e)}")
        save_debug_screenshot(driver, "error_inesperado_defecto")
    finally:
        if DEBUG_MODE:
            print("   -> DEBUG_MODE=True: dejo la pestaña abierta para inspección.")
            return
        try:
            print("   -> Finalizando, cerrando pestaña...")
            driver.close()
            driver.switch_to.window(main_window)
        except Exception:
            pass