from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
import hashlib
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from types import SimpleNamespace

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.config.settings_etl import UPLOADS_MULTIMODAL_DIR, DATA_LOG_PATH, CHROMA_COLLECTIONS
from app.core.ia.vision import get_vision_provider
from .vectorize import vectorize_content, prepare_metadata, prepare_solution_metadata, IngestionResult

log = logging.getLogger(__name__)
MULTIMODAL_LOG_FILE = DATA_LOG_PATH / "multimodal_ingestion_log.json"

TMP_DIR = (DATA_LOG_PATH / "tmp_images")
TMP_DIR.mkdir(parents=True, exist_ok=True)

HEADING_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)*)[.)\s]+(.+?)(?:\s+\d+)?\s*$",
    re.IGNORECASE
)
SKIP_TOKENS = {"confidencial", "cb consultores chile.", "grupo epm", "grupo saesa"}

SECTION_KEYWORDS = {
    "1": ["control de la plantilla", "control de versiones", "historial de cambios"],
    "2": ["descripción y evidencia", "evidencia hallazgo", "descripción hallazgo"],
    "3": ["respuesta consultoría", "respuesta consultoria", "solución"]
}

def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))

def _norm(s: str) -> str:
    s2 = _strip_accents(str(s or ""))
    s2 = re.sub(r"\s+", "_", s2.strip().lower())
    s2 = re.sub(r"[^a-z0-9_\-\.]+", "", s2)
    return s2

def _digits(s: str) -> str:
    m = re.search(r"\d+", str(s or ""))
    return m.group(0) if m else ""

def _content_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

def _is_footer_or_disclaimer(text: str) -> bool:
    s = " ".join((text or "").lower().split())
    return (
        not s
        or s.startswith("página ")
        or s.startswith("pagina ")
        or any(tok in s for tok in SKIP_TOKENS)
    )

def _detect_heading(line: str) -> Tuple[Optional[str], Optional[str]]:
    clean_line = re.sub(r'\s+', ' ', line.strip())
    m = HEADING_RE.match(clean_line)
    return (m.group(1), m.group(2).strip()) if m else (None, None)

def _infer_section_from_content(text: str, is_marker_check: bool = False) -> Optional[str]:
    text_lower = _strip_accents(text.lower())
    
    matches = []
    for section, keywords in SECTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matches.append(section)
    
    if not matches:
        return None
    
    if is_marker_check:
        words = [w for w in text.split() if w.strip()]
        word_count = len(words)
        
        if word_count < 10 and len(matches) == 1:
            return matches[0]
        return None
    
    return matches[0]

def _page_of(el) -> Optional[int]:
    try:
        p = getattr(getattr(el, "metadata", None), "page_number", None)
        return int(p) if p is not None else None
    except Exception:
        return None

def _get_section_parent(path: str) -> str:
    if not path or path == "title":
        return path
    parts = path.split(".")
    return parts[0] if parts else path

def _extract_metadata_from_path(file_path: Path) -> Dict[str, str]:
    """
    Extrae metadata desde la estructura del path:
    by_responsable/{Responsable}/{ID_Caso-Descripcion}/{Fecha}/{Archivo}
    by_ticket/{Responsable}/{ID_Caso-Descripcion}/{Fecha}/{Archivo}
    
    Retorna:
    - responsable_original: Nombre sin normalizar (ej: "Alvaro_Arturo_Cortes_Barreto_(92)")
    - responsable_clean: Nombre limpio (ej: "Alvaro Arturo Cortes Barreto")
    - defecto_id_digits: ID limpio (ej: "8000001239")
    - defecto_original: Carpeta completa (ej: "8000001239-H1_TX_1272_No_despliega_información")
    - tipo_organizacion: "by_responsable" o "by_ticket"
    """
    result = {
        "responsable_original": "",
        "responsable_clean": "",
        "defecto_id_digits": "",
        "defecto_original": "",
        "tipo_organizacion": ""
    }
    
    try:
        parts = file_path.parts
        
        if "by_responsable" in parts:
            result["tipo_organizacion"] = "by_responsable"
            idx = parts.index("by_responsable")
        elif "by_ticket" in parts:
            result["tipo_organizacion"] = "by_ticket"
            idx = parts.index("by_ticket")
        else:
            return result
        
        if idx + 1 < len(parts):
            responsable_raw = parts[idx + 1]
            result["responsable_original"] = responsable_raw
            
            responsable_clean = re.sub(r'_?\(\d+\)$', '', responsable_raw)
            responsable_clean = responsable_clean.replace('_', ' ') 
            result["responsable_clean"] = responsable_clean.strip()
        
        if idx + 2 < len(parts):
            caso_dir = parts[idx + 2]
            result["defecto_original"] = caso_dir
            
            match = re.match(r'^(\d+)', caso_dir)
            if match:
                result["defecto_id_digits"] = match.group(1)
    
    except Exception as e:
        log.warning(f"Error extrayendo metadata del path {file_path}: {e}")
    
    return result

def _extract_business_metadata(elements: List[Any]) -> Dict[str, str]:
    """
    Extrae módulo y proyecto desde las tablas de metadata del documento.
    Busca en las primeras tablas campos como:
    - "Nombre de Proyecto", "Proyecto"
    - "Sistema y/o Módulo", "Módulo", "Frente"
    """
    result = {
        "proyecto": "",
        "modulo": ""
    }
    
    try:
        for el in elements[:20]:
            et = type(el).__name__
            if "Table" not in et:
                continue 
            text = str(el).lower()
            

            if not result["proyecto"]:
                patterns_proyecto = [
                    r'nombre\s+de\s+proyecto[:\s]+([^\n|]+)',
                    r'proyecto[:\s]+([^\n|]+)',
                ]
                for pattern in patterns_proyecto:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        proyecto = match.group(1).strip()
                        proyecto = re.sub(r'\s*\|\s*', '', proyecto)
                        proyecto = proyecto.strip()
                        if proyecto and len(proyecto) > 2:
                            result["proyecto"] = proyecto
                            break
            
            if not result["modulo"]:
                patterns_modulo = [
                    r'sistema\s+y/o\s+m[óo]dulo[:\s]+([^\n|]+)',
                    r'm[óo]dulo[:\s]+([^\n|]+)',
                    r'frente[:\s]+([^\n|]+)',
                ]
                for pattern in patterns_modulo:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        modulo = match.group(1).strip()
                        modulo = re.sub(r'\s*\|\s*', '', modulo)
                        modulo = modulo.strip()
                        if modulo and len(modulo) > 2:
                            result["modulo"] = modulo
                            break
            
            if result["proyecto"] and result["modulo"]:
                break
    
    except Exception as e:
        log.warning(f"Error extrayendo metadata de negocio: {e}")
    
    return result

def _extract_id_reporte_from_path(file_path: Path) -> Optional[str]:
    """Mantener para compatibilidad, pero _extract_metadata_from_path es más completo"""
    try:
        caso_dir = file_path.parent.parent.name
        m = re.match(r"^(\d{6,})\b", caso_dir)
        if m:
            return m.group(1)
    except Exception:
        pass
    for p in reversed(file_path.parents):
        name = p.name
        m2 = re.match(r"^(\d{6,})\b", name)
        if m2:
            return m2.group(1)
    return None

def _extract_image_bytes(el) -> bytes | None:
    data = getattr(getattr(el, "metadata", None), "image", None) or getattr(el, "image", None)
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    try:
        from PIL import Image as PILImage
        if isinstance(data, PILImage.Image):
            buf = io.BytesIO()
            data.convert("RGB").save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except Exception:
        pass
    path = getattr(getattr(el, "metadata", None), "image_path", None)
    if path and Path(path).exists():
        return Path(path).read_bytes()
    return None

def _materialize_image(el) -> Path | None:
    raw = _extract_image_bytes(el)
    if not raw:
        return None
    name = f"{uuid.uuid4().hex}.jpg"
    out = TMP_DIR / name
    out.write_bytes(raw)
    return out

def _docx_inline_images_as_elements(docx_path: Path) -> list:
    out = []
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            media_files = [n for n in zf.namelist() if n.startswith("word/media/")]
            for mf in media_files:
                raw = zf.read(mf)
                meta = SimpleNamespace(image=raw, image_path=None, page_number=None)
                class ImageElement:
                    def __init__(self, metadata):
                        self.metadata = metadata
                    def __str__(self):
                        return "[IMAGEN]"
                out.append(ImageElement(meta))
    except Exception:
        log.exception("Fallo extrayendo imágenes inline del DOCX")
    return out

def partition_file(path: Path) -> List[Any]:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            from unstructured.partition.pdf import partition_pdf
            return partition_pdf(
                filename=str(path),
                strategy="hi_res",
                infer_table_structure=True,
                extract_image_block_types=["Image"],
                extract_image_block_to_payload=True,
            )
        elif ext == ".docx":
            from unstructured.partition.docx import partition_docx
            els = partition_docx(filename=str(path), extract_images_in_docx=True)
            has_img = any("Image" in type(e).__name__ for e in els)
            if not has_img:
                injected = _docx_inline_images_as_elements(path)
                if injected:
                    els = els + injected
            return els
        else:
            from unstructured.partition.auto import partition
            return partition(filename=str(path))
    except Exception:
        log.exception("partition_file error")
        return []

def _element_to_markdown(el: Any) -> str:
    et = type(el).__name__
    if "Table" in et:
        html = getattr(getattr(el, "metadata", None), "text_as_html", None) or str(el)
        try:
            return md(html, heading_style="ATX").strip()
        except Exception:
            return BeautifulSoup(html, "lxml").get_text(separator=" | ", strip=True)
    return str(el).strip()

async def _describe_images_async(images: List[Any]) -> List[str]:
    if not images:
        return []
    provider = get_vision_provider()
    prompt = (
        "Describe de forma objetiva y estructurada el contenido de esta imagen. "
        "Tu regla más importante es transcribir todo el texto de forma literal y precisa. "
        "No hagas suposiciones ni interpretaciones."
    )
    out: List[str] = []
    for el in images:
        try:
            img_path = _materialize_image(el)
            if not img_path:
                continue
            res = await provider.analyze_image_async(img_path, prompt)
            text = (res.get("response") or "").strip() if res.get("success") else ""
            out.append(f"[IMAGEN] {text if text else 'Descripción no disponible.'}")
        except Exception as e:
            log.error(f"Error al procesar imagen con el proveedor de visión: {e}")
            out.append("[IMAGEN] Error de procesamiento")
    return out

async def process_document_by_section_async(elements: List[Any]) -> Tuple[List[str], List[Dict]]:
    """
    Nueva estrategia:
    1. Detectar encabezados en TOC/índice
    2. Asignar elementos por contenido (no por posición)
    3. Las tablas con títulos de sección marcan los límites
    """
    
    section_titles = {}
    toc_elements = []
    
    print("\n" + "="*80)
    print("FASE 1: DETECCIÓN DE ENCABEZADOS EN TOC")
    print("="*80)
    
    for idx, el in enumerate(elements):
        et = type(el).__name__
        txt = str(el).strip()
        
        if et in ["Header", "Footer", "PageBreak"] or _is_footer_or_disclaimer(txt):
            continue
            
        path, title = _detect_heading(txt)
        if path and title:
            parent = _get_section_parent(path)
            if parent not in section_titles or path == parent:
                section_titles[parent] = title
            toc_elements.append(idx)
            print(f"  TOC #{idx}: [{parent}] {title} (tipo={et})")
    
    print(f"\nSecciones detectadas: {section_titles}")
    
    # Paso 2: Asignar elementos a secciones por contenido
    sections = {sec: {"path": sec, "title": title, "els": [], "pages": set()} 
                for sec, title in section_titles.items()}
    
    print("\n" + "="*80)
    print("FASE 2: ASIGNACIÓN DE ELEMENTOS A SECCIONES")
    print("="*80)
    
    current_section = None
    last_content_section = None 
    
    for idx, el in enumerate(elements):
        et = type(el).__name__
        txt = str(el).strip()
        
        if idx in toc_elements or et in ["Header", "Footer", "PageBreak"] or _is_footer_or_disclaimer(txt):
            continue
        
        if "Image" in et:
            target_section = last_content_section or current_section
            if target_section:
                sections[target_section]["els"].append(el)
                p = _page_of(el)
                if p:
                    sections[target_section]["pages"].add(p)
                print(f"  Elemento #{idx} ({et}): ASIGNADO A ÚLTIMA SECCIÓN DE CONTENIDO -> {target_section}")
            else:
                print(f"  Elemento #{idx} ({et}): IGNORADO (sin sección de contenido previa)")
            continue
        
        potential_section = _infer_section_from_content(txt, is_marker_check=False)
        is_pure_marker = "Table" in et and _infer_section_from_content(txt, is_marker_check=True)
        
        if potential_section and potential_section in sections and potential_section != current_section:
            current_section = potential_section
            print(f"  Elemento #{idx} ({et}): CAMBIO DE SECCIÓN DETECTADO -> {current_section}")
            if is_pure_marker:
                continue
        
        if current_section:
            sections[current_section]["els"].append(el)
            p = _page_of(el)
            if p:
                sections[current_section]["pages"].add(p)
            print(f"  Elemento #{idx} ({et}): -> sección {current_section}")
            if not is_pure_marker:
                last_content_section = current_section
        else:
            print(f"  Elemento #{idx} ({et}): IGNORADO (sin sección activa)")
    
    print("\n" + "="*80)
    print("RESUMEN DE SECCIONES")
    print("="*80)
    for sec, data in sections.items():
        print(f"  Sección {sec}: {len(data['els'])} elementos")
    
    chunks: List[str] = []
    metas: List[Dict] = []
    
    print("\n" + "="*80)
    print("FASE 3: GENERACIÓN DE CHUNKS")
    print("="*80)
    
    for sec_key in sorted(sections.keys()):
        sec = sections[sec_key]
        path = sec["path"]
        title = sec["title"]
        els = sec["els"]
        
        if not els:
            print(f"\n>>> Sección {path}: SIN ELEMENTOS, saltando...")
            continue
            
        pages = sorted(sec["pages"]) if sec["pages"] else []
        page_range = [pages[0], pages[-1]] if pages else None
        group_id = f"sec:{path}"
        order = 1
        
        print(f"\n>>> Procesando sección {path}: {title} ({len(els)} elementos)")
        
        def _mk_meta(ctype: str, content: str) -> Dict:
            return {
                "section_path": path,
                "section_title": title,
                "section_title_norm": _norm(title),
                "chunk_type": ctype,
                "group_id": group_id,
                "order_in_group": order,
                "within_section_index": order,
                "page_range": page_range,
                "image_count": content.count("[IMAGEN]"),
                "table_count": content.count("| ---"),
                "content_sha": _content_sha(content),
            }
        
        if path == "1":
            print("  -> Regla SECCIÓN 1 (todo junto)")
            text_parts: List[str] = []
            table_parts: List[str] = []
            image_buf: List[Any] = []
            
            for e in els:
                et = type(e).__name__
                if "Image" in et:
                    image_buf.append(e)
                elif "Table" in et:
                    md_table = _element_to_markdown(e)
                    if md_table and "control de la plantilla" not in md_table.lower():
                        table_parts.append(md_table)
                else:
                    tx = str(e).strip()
                    if tx:
                        text_parts.append(tx)
            
            img_descs = await _describe_images_async(image_buf)
            content_parts = []
            if text_parts:
                content_parts.append("\n\n".join(text_parts))
            if table_parts:
                content_parts.append("\n\n".join(table_parts))
            if img_descs:
                content_parts.append("\n\n".join(img_descs))
            
            final = "\n\n".join([p for p in content_parts if p]).strip()
            if final:
                ctype = "mixed" if img_descs else "text"
                chunks.append(final)
                metas.append(_mk_meta(ctype, final))
                print(f"  -> Chunk creado: {len(final)} chars")
            continue
        
        if path == "2":
            print("  -> Regla SECCIÓN 2 (pasos)")
            step_buffer = {"text": [], "tables": [], "images": []}
            has_evidence = False
            
            async def flush_step():
                nonlocal order, step_buffer, has_evidence
                if not any([step_buffer["text"], step_buffer["tables"], step_buffer["images"]]):
                    return
                
                img_descs = await _describe_images_async(step_buffer["images"])
                parts = []
                if step_buffer["text"]:
                    parts.append("\n\n".join(step_buffer["text"]))
                if step_buffer["tables"]:
                    parts.append("\n\n".join(step_buffer["tables"]))
                if img_descs:
                    parts.append("\n\n".join(img_descs))
                
                final = "\n\n".join([p for p in parts if p]).strip()
                if final:
                    ctype = "mixed" if img_descs else "text"
                    chunks.append(final)
                    metas.append(_mk_meta(ctype, final))
                    print(f"  -> Paso {order} creado: {len(final)} chars")
                    order += 1
                
                step_buffer = {"text": [], "tables": [], "images": []}
                has_evidence = False
            
            for e in els:
                et = type(e).__name__
                
                if "Image" in et:
                    step_buffer["images"].append(e)
                    has_evidence = True
                elif "Table" in et:
                    md_table = _element_to_markdown(e)
                    if md_table:
                        step_buffer["tables"].append(md_table)
                        has_evidence = True
                else:
                    tx = str(e).strip()
                    if not tx:
                        continue
                    
                    if has_evidence and step_buffer["text"]:
                        await flush_step()
                    
                    step_buffer["text"].append(tx)
            
            await flush_step()
            continue
        
        print("  -> Regla ESTÁNDAR")
        text_buf: List[str] = []
        table_buf: List[str] = []
        img_buf: List[Any] = []
        
        for e in els:
            et = type(e).__name__
            if "Image" in et:
                img_buf.append(e)
            elif "Table" in et:
                md_table = _element_to_markdown(e)
                if md_table and _infer_section_from_content(md_table) != path:
                    table_buf.append(md_table)
            else:
                tx = str(e).strip()
                if tx:
                    text_buf.append(tx)
        
        img_descs = await _describe_images_async(img_buf)
        parts = []
        if text_buf:
            parts.append("\n\n".join(text_buf))
        if table_buf:
            parts.append("\n\n".join(table_buf))
        if img_descs:
            parts.append("\n\n".join(img_descs))
        
        final = "\n\n".join([p for p in parts if p]).strip()
        if final:
            ctype = "mixed" if img_descs else "text"
            chunks.append(final)
            metas.append(_mk_meta(ctype, final))
            print(f"  -> Chunk creado: {len(final)} chars")
    
    print(f"\n{'='*80}")
    print(f"TOTAL CHUNKS GENERADOS: {len(chunks)}")
    print("="*80 + "\n")
    
    return chunks, metas

def _save_log(data: Dict):
    MULTIMODAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MULTIMODAL_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _files_in(d: Path) -> List[Path]:
    files: List[Path] = []
    for it in d.iterdir():
        if it.is_dir():
            files.extend(fp for fp in it.iterdir() if fp.is_file() and not fp.name.startswith("~$"))
        elif it.is_file() and not it.name.startswith("~$"):
            files.append(it)
    return files

async def _process_dir(root: Path, responsable: Optional[str], defecto: Optional[str], meta_preparer, collection_name: str) -> Dict[str, int]:
    processed_files = 0
    successful_files = 0
    total_chunks = 0
    successful_chunks = 0

    responsables = [responsable] if responsable else [d.name for d in root.iterdir() if d.is_dir()]
    for r in responsables:
        rdir = root / r
        if not rdir.is_dir():
            continue
        casos = [d.name for d in rdir.iterdir() if d.is_dir()]
        for caso in casos:
            cdir = rdir / caso
            if not cdir.is_dir():
                continue
            fechas = [d.name for d in cdir.iterdir() if d.is_dir()]
            for fecha in fechas:
                fdir = cdir / fecha
                if not fdir.is_dir():
                    continue
                files = _files_in(fdir)
                for f in files:
                    processed_files += 1
                    try:
                        path_meta = _extract_metadata_from_path(f)
                        
                        elements = partition_file(f)
                        
                        business_meta = _extract_business_metadata(elements)
                        
                        grouped_chunks, partial_metas = await process_document_by_section_async(elements)
                        if not grouped_chunks:
                            continue

                        id_reporte = path_meta.get("defecto_id_digits") or _extract_id_reporte_from_path(f) or ""
                        responsable_norm = _norm(path_meta.get("responsable_clean") or r)
                        document_id = f"{responsable_norm}::{id_reporte or 'na'}::{Path(f).stem}"

                        final_metas = []
                        for i, meta in enumerate(partial_metas):
                            raw = {
                                "element_type": meta.get("chunk_type", ""),
                                "responsable": path_meta.get("responsable_clean") or r,
                                "responsable_norm": responsable_norm,
                                "responsable_original": path_meta.get("responsable_original", ""),
                                
                                "defecto": defecto or path_meta.get("defecto_original", ""),
                                "defecto_original": path_meta.get("defecto_original", ""),
                                "defect_id_digits": id_reporte,
                                
                                "modulo": business_meta.get("modulo", ""),
                                "proyecto": business_meta.get("proyecto", ""),
                                
                                "source_file": f.name,
                                "chunk_index": i,
                                "id_reporte": id_reporte,
                                "document_id": document_id,
                                "tipo_organizacion": path_meta.get("tipo_organizacion", ""),
                                
                                **{k: v for k, v in meta.items() if k not in {"element_type"}},
                            }
                            final_metas.append(meta_preparer(raw))

                        vc = await vectorize_content(grouped_chunks, final_metas, collection_name)
                        total_chunks += len(grouped_chunks)
                        successful_chunks += vc
                        if vc == len(grouped_chunks):
                            successful_files += 1
                    except Exception:
                        log.exception("Error procesando archivo %s", f)
                        continue

    return {
        "processed_files": processed_files,
        "successful_files": successful_files,
        "total_chunks": total_chunks,
        "successful_chunks": successful_chunks,
    }

async def ingest_evidence_tree(responsable: Optional[str] = None, defecto: Optional[str] = None) -> IngestionResult:
    root = UPLOADS_MULTIMODAL_DIR.resolve()
    result = await _process_dir(root, responsable, defecto, prepare_metadata, CHROMA_COLLECTIONS["multimodal_evidence"])
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "type": "multimodal_evidence",
        "root_path": str(root),
        "responsable": responsable or "*",
        "defecto": defecto or "*",
        "results": result,
    }
    _save_log(log_data)
    return IngestionResult(responsable=responsable or "*", defecto=defecto or "*", log_file=str(MULTIMODAL_LOG_FILE), **result)

async def ingest_solutions_tree(responsable: Optional[str] = None, defecto: Optional[str] = None) -> IngestionResult:
    root = UPLOADS_MULTIMODAL_DIR.resolve()
    result = await _process_dir(root, responsable, defecto, prepare_solution_metadata, CHROMA_COLLECTIONS["historical_solutions"])
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "type": "historical_solutions",
        "root_path": str(root),
        "responsable": responsable or "*",
        "defecto": defecto or "*",
        "results": result,
    }
    _save_log(log_data)
    return IngestionResult(responsable=responsable or "*", defecto=defecto or "*", log_file=str(MULTIMODAL_LOG_FILE), **result)