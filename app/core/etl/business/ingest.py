import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def _read_text_any(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")

    if path.suffix.lower() == ".pdf":
        try:
            import fitz
            text_pages = []
            with fitz.open(str(path)) as doc:
                for i, page in enumerate(doc):
                    text_pages.append(f"== PÁGINA {i+1} ==\n{page.get_text()}")
            return "\n\n".join(text_pages).strip()
        except Exception as e:
            logger.warning(f"PyMuPDF falló en {path.name}: {e}. Intentando fallback con Unstructured...")
            try:
                from unstructured.partition.pdf import partition_pdf
                import warnings
                warnings.filterwarnings("ignore", message="No languages specified")
                elements = partition_pdf(str(path), strategy="auto", languages=["spa", "eng"])
                return "\n\n".join([str(elem) for elem in elements])
            except ImportError:
                logger.error("Ni PyMuPDF ni Unstructured están instalados.")
                return ""
            except Exception as e_unstructured:
                logger.error(f"Unstructured también falló: {e_unstructured}")
                return ""
    return ""

def _chunk_by_sections(text: str) -> List[Dict[str, str]]:
    sections = []
    lines = text.split('\n')
    current_section_content = []
    section_title = "Regla General"

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        is_title = (
            len(stripped_line) < 100 and
            (stripped_line.isupper() or
             stripped_line.startswith(('1.', '2.', 'I.', 'II.')) or
             any(kw in stripped_line.upper() for kw in ['REGLA', 'PROCEDIMIENTO', 'POLÍTICA']))
        )

        if is_title and current_section_content:
            content = "\n".join(current_section_content).strip()
            if len(content) > 50:
                sections.append({'title': section_title, 'content': content})
            current_section_content = []
            section_title = stripped_line
        
        current_section_content.append(stripped_line)

    if current_section_content:
        content = "\n".join(current_section_content).strip()
        if len(content) > 50:
            sections.append({'title': section_title, 'content': content})

    if not sections and len(text) > 50:
         sections.append({'title': 'Documento Completo', 'content': text})

    return sections

def ingest_business_rules(
    root_dir: Path,
    *,
    rule_type: str = "general",
    category: str = "default",
) -> Tuple[List[str], List[Dict]]:
    documents: List[str] = []
    metadatas: List[Dict] = []

    if not root_dir.exists():
        logger.warning(f"Directorio no existe: {root_dir}")
        return documents, metadatas

    for path in sorted(root_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".txt", ".md"}:
            continue

        raw_text = _read_text_any(path)
        if not raw_text:
            logger.info(f"Sin texto extraíble en: {path.name}")
            continue

        chunks = _chunk_by_sections(raw_text)
        file_hash = file_md5(path)
        
        logger.info(f"Procesando {path.name}: {len(chunks)} chunks encontrados.")

        for idx, chunk in enumerate(chunks):
            
            enriched_content = f"""TIPO: {rule_type.upper()}
CATEGORÍA: {category.upper()}
TÍTULO: {chunk['title']}
FUENTE: {path.name}

CONTENIDO:
{chunk['content']}"""
            documents.append(enriched_content)

            metadatas.append({
                "doc_type": "business",
                "rule_type": rule_type,
                "category": category,
                "title": chunk['title'],
                "source_file": str(path.name),
                "file_hash": file_hash,
                "chunk_idx": idx,
                "char_len": len(chunk['content']),
            })

    return documents, metadatas