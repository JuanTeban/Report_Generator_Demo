import os
from collections import defaultdict
from scraper import (
    connect_to_browser,
    create_requests_session,
    get_defect_links,
    process_defect_attachments,
    find_or_collect_defect_by_id   # <— NUEVO
)
from config import DOWNLOAD_FOLDER, DOWNLOAD_FOLDER_TICKETS

# ------------------------
# Configuración de carpetas
# ------------------------
def ensure_download_folders():
    """Asegura que las carpetas de descarga existan."""
    folders = [DOWNLOAD_FOLDER, DOWNLOAD_FOLDER_TICKETS]
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f"✅ Carpeta configurada: {folder}")

# ------------------------
# Selección de MODO
# ------------------------
def select_mode():
    print("\n=== MODO DE DESCARGA ===")
    print("  1) Descargar por RESPONSABLE (actual)")
    print("  2) Descargar por TICKET (ID)  [NUEVO]")
    while True:
        choice = input("Elige 1 o 2 (Enter para cancelar): ").strip()
        if not choice:
            return None
        if choice in ("1", "2"):
            return choice
        print("❌ Opción inválida. Intenta de nuevo.")

# ------------------------
# Selección por DEFECTOS (ya existente)
# ------------------------
def select_defects_to_process(all_defects):
    if not all_defects:
        print("No se encontraron defectos para procesar.")
        return []
    print("\n--- SELECCIÓN DE DEFECTOS ---")
    print("Se encontraron los siguientes defectos:")
    for i, defect in enumerate(all_defects, 1):
        print(f"  {i}: {defect['text']}")
    while True:
        print("\n¿Cuáles deseas procesar?")
        user_input = input("Ingresa los números separados por comas (ej: 1,3,8), 'todos' o Enter para cancelar: ")
        choice = user_input.strip().lower()
        if not choice:
            print("Proceso cancelado por el usuario.")
            return []
        if choice == 'todos':
            return all_defects
        try:
            idxs = [int(x.strip()) - 1 for x in choice.split(',')]
            out = []
            for idx in idxs:
                if 0 <= idx < len(all_defects):
                    out.append(all_defects[idx])
                else:
                    raise ValueError()
            return out
        except ValueError:
            print("❌ Entrada inválida. Asegúrate de ingresar sólo números separados por comas.")

# --- Selección por RESPONSABLE (ya existente) ---
def select_responsables_to_process(all_defects):
    if not all_defects:
        print("No se encontraron defectos para procesar.")
        return []
    buckets = defaultdict(list)
    for it in all_defects:
        buckets[it.get("responsable") or "SIN_RESPONSABLE"].append(it)
    responsables = sorted(buckets.keys(), key=lambda k: (k == "SIN_RESPONSABLE", k.lower()))
    print("\n--- SELECCIÓN POR RESPONSABLE ---")
    for i, r in enumerate(responsables, 1):
        print(f"  {i}: {r}  ({len(buckets[r])} defectos)")
    while True:
        choice = input("\n¿De cuáles responsables descargar? (ej: 1,3)  'todos' o Enter para cancelar: ").strip().lower()
        if not choice:
            print("Proceso cancelado por el usuario.")
            return []
        if choice == "todos":
            out = []
            for r in responsables:
                out.extend(buckets[r])
            return out
        try:
            idxs = [int(x.strip())-1 for x in choice.split(",")]
            out = []
            for idx in idxs:
                if 0 <= idx < len(responsables):
                    out.extend(buckets[responsables[idx]])
                else:
                    raise ValueError()
            return out
        except Exception:
            print("❌ Entrada inválida. Intenta de nuevo.")

# ------------------------
# NUEVO: Selección por TICKET
# ------------------------
def ask_ticket_ids():
    """
    Pide IDs de tickets: '8000002052,1515' o @ruta.txt (uno por línea).
    Devuelve lista de strings con IDs.
    """
    print("\n--- SELECCIÓN POR TICKET (ID) ---")
    inp = input("Ingresa IDs separados por coma (ej: 1515,8000002052) o '@archivo.txt': ").strip()
    if not inp:
        print("Proceso cancelado por el usuario.")
        return []
    ids = []
    if inp.startswith("@"):
        path = inp[1:].strip('" ')
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    t = line.strip()
                    if t:
                        ids.append(t)
        except Exception as e:
            print(f"❌ No pude leer '{path}': {e}")
            return []
    else:
        ids = [x.strip() for x in inp.split(",") if x.strip()]
    # dedup conservando orden
    seen, out = set(), []
    for t in ids:
        if t not in seen:
            out.append(t); seen.add(t)
    print(f"✅ {len(out)} ticket(s) ingresados: {', '.join(out)}")
    return out

def run_scraper():
    # Asegurar que las carpetas de descarga existan
    ensure_download_folders()
    
    driver = None
    try:
        driver = connect_to_browser()
        session = create_requests_session(driver)

        mode = select_mode()
        if mode is None:
            print("Sin acción. Saliendo.")
            return

        if mode == "1":
            # Flujo original por responsable
            all_defect_links = get_defect_links(driver)
            defects_to_process = select_responsables_to_process(all_defect_links)
            if not defects_to_process:
                print("No hay defectos seleccionados. Finalizando.")
                return
            print(f"\n✅ Se procesarán {len(defects_to_process)} defectos seleccionados (por responsable).")
            for i, defect in enumerate(defects_to_process, 1):
                print(f"\n--- Procesando {i}/{len(defects_to_process)} ---")
                process_defect_attachments(driver, session, defect, DOWNLOAD_FOLDER, path_strategy="by_responsable")
            print("\n🎉 Proceso completado exitosamente.")
            return

        # ---------------- MODO 2: por ticket (ID) ----------------
        ticket_ids = ask_ticket_ids()
        if not ticket_ids:
            return

        # Primero recolectamos todo lo visible (ahorra tiempo); luego buscamos faltantes
        all_defect_links = get_defect_links(driver)
        defects_to_process = []

        for tid in ticket_ids:
            d = find_or_collect_defect_by_id(driver, tid, all_defect_links)
            if d:
                defects_to_process.append(d)
            else:
                print(f"❌ No encontré el ticket {tid} en la tabla (ni con filtro).")

        if not defects_to_process:
            print("No hay tickets válidos para procesar. Finalizando.")
            return

        print(f"\n✅ Se procesarán {len(defects_to_process)} ticket(s) seleccionados.")
        for i, defect in enumerate(defects_to_process, 1):
            print(f"\n--- Procesando {i}/{len(defects_to_process)} [Ticket] ---")
            process_defect_attachments(driver, session, defect, DOWNLOAD_FOLDER_TICKETS, path_strategy="by_ticket")

        print("\n🎉 Proceso completado exitosamente (modo por ticket).")

    except Exception as e:
        print(f"❌ Ocurrió un error general en el proceso: {e}")
    finally:
        if driver:
            print("👋 El bot ha terminado. El navegador principal se mantendrá abierto.")

if __name__ == "__main__":
    run_scraper()
