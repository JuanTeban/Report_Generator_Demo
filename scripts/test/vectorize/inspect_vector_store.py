#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script a mejorar, lo pruebo y sale un resultado que no es coherente. :c 

Inspector robusto de ChromaDB (no escribe archivos)

- Compatible con versiones donde `get()` NO acepta "ids" en `include`.
- Normaliza respuestas (listas/ndarrays) para evitar errores booleanos.
- Imprime:
  * conteo, dimensión de embedding,
  * distribución de tipos (heurística por metadatos),
  * claves de metadatos presentes y top valores,
  * stats simples de documentos y embeddings,
  * muestra por elemento con metadatos completos.
"""

import argparse
import logging
import math
import statistics
from datetime import datetime
from pathlib import Path
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

try:
    import app  # type: ignore
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

import chromadb

from app.config.settings_etl import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTIONS,
)

log = logging.getLogger("chroma_inspector")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


def to_seq(x: Any) -> List[Any]:
    """Convierte None/ndarray/iterable en lista normal y segura."""
    if x is None:
        return []
    try:
        if hasattr(x, "tolist"):
            return x.tolist()
        return list(x)
    except Exception:
        return [x]

def preview_text(text: Any, max_len: int = 220) -> Tuple[str, int]:
    t = "" if text is None else str(text)
    length = len(t)
    if length <= max_len:
        return t.replace("\n", " "), length
    return (t[:max_len].replace("\n", " ") + "..."), length

def chunks(total: int, page_size: int) -> Iterable[Tuple[int, int]]:
    if total <= 0:
        return
    offset = 0
    while offset < total:
        limit = min(page_size, total - offset)
        yield offset, limit
        offset += limit

def vector_norm(v: List[float]) -> float:
    s = 0.0
    for val in v:
        fv = float(val)
        s += fv * fv
    return math.sqrt(s)

def detect_embedding_dim(sample_embeddings: Any) -> int:
    seq = to_seq(sample_embeddings)
    if len(seq) == 0:
        return 0
    first = to_seq(seq[0])
    return len(first)

# --------------------- acceso a colección ------------------------

def iter_documents(collection: Any, total_count: int, page_size: int, with_embeddings: bool) -> Iterable[Dict[str, Any]]:
    # ¡NO incluyas "ids"! (IDs vienen siempre)
    includes = ["documents", "metadatas"]
    if with_embeddings:
        includes.append("embeddings")

    for offset, limit in chunks(total_count, page_size):
        batch = collection.get(include=includes, limit=limit, offset=offset)

        ids  = to_seq(batch.get("ids"))           # vienen aunque no los pidas
        docs = to_seq(batch.get("documents"))
        metas = to_seq(batch.get("metadatas"))
        embs = to_seq(batch.get("embeddings")) if with_embeddings else []

        n = min(len(ids), len(docs), len(metas), len(embs) if with_embeddings else len(ids))
        for i in range(n):
            yield {
                "id": ids[i],
                "document": docs[i],
                "metadata": metas[i] if i < len(metas) and metas[i] else {},
                "embedding": (embs[i] if with_embeddings and i < len(embs) else None),
            }

def collect_metadata_schema_and_distribution(collection: Any, total_count: int, page_size: int = 1000):
    all_keys: Set[str] = set()
    presence: Dict[str, int] = defaultdict(int)
    content_types: Dict[str, int] = defaultdict(int)
    value_counts: Dict[str, Counter[Any]] = defaultdict(Counter)
    examples: Dict[str, List[Any]] = defaultdict(list)

    for row in iter_documents(collection, total_count, page_size, with_embeddings=False):
        md = row["metadata"] or {}

        # claves y presencia
        for k, v in md.items():
            all_keys.add(k)
            presence[k] += 1
            if isinstance(v, (str, int, float, bool)):
                value_counts[k][v] += 1
            if len(examples[k]) < 5:
                examples[k].append(v if not isinstance(v, (list, dict)) else str(v)[:200])

        # heurística de tipo de contenido
        et = md.get("element_type")
        rt = md.get("rule_type")
        tn = md.get("table_name")
        src = md.get("source")
        typ = md.get("type")
        if et:
            key = f"element:{et}"
        elif rt:
            key = f"rule:{rt}"
        elif tn:
            key = f"table:{tn}"
        elif src:
            key = f"source:{src}"
        elif typ:
            key = f"type:{typ}"
        else:
            key = "unknown"
        content_types[key] += 1

    return sorted(all_keys), dict(presence), dict(content_types), value_counts, examples

def collect_doc_stats(collection: Any, total_count: int, page_size: int = 1000, cap: Optional[int] = None) -> Dict[str, Any]:
    lengths: List[int] = []
    limit_total = min(total_count, cap) if cap else total_count
    for row in iter_documents(collection, limit_total, page_size, with_embeddings=False):
        doc = row["document"]
        lengths.append(len(doc) if isinstance(doc, str) else 0)
    if not lengths:
        return {"avg": None, "min": None, "p50": None, "p90": None, "max": None}
    sl = sorted(lengths)
    def pct(p: float): 
        idx = max(0, min(len(sl) - 1, int(round(p * (len(sl) - 1)))))
        return sl[idx]
    return {
        "avg": round(statistics.fmean(lengths), 2),
        "min": sl[0],
        "p50": pct(0.5),
        "p90": pct(0.9),
        "max": sl[-1],
    }

def collect_embedding_stats(collection: Any, total_count: int, page_size: int = 1000, cap: Optional[int] = None) -> Dict[str, Any]:
    norms: List[float] = []
    zeros = 0
    nanv = 0
    infv = 0
    dim = 0
    limit_total = min(total_count, cap) if cap else total_count

    for row in iter_documents(collection, limit_total, page_size, with_embeddings=True):
        emb = row["embedding"]
        if emb is None:
            continue
        if not dim:
            dim = len(to_seq(emb))
        # NaN/Inf check
        has_nan = False
        has_inf = False
        s = 0.0
        for val in to_seq(emb):
            fv = float(val)
            if math.isnan(fv): has_nan = True
            if math.isinf(fv): has_inf = True
            s += fv * fv
        if has_nan: nanv += 1
        if has_inf: infv += 1
        nrm = math.sqrt(s)
        norms.append(nrm)
        if nrm == 0.0: zeros += 1

    if not norms:
        return {"dim": dim, "count": 0, "min": None, "avg": None, "max": None, "p01": None, "p99": None, "zeros": 0, "nan": 0, "inf": 0}

    ns = sorted(norms)
    def pct(p: float): 
        idx = max(0, min(len(ns) - 1, int(round(p * (len(ns) - 1)))))
        return ns[idx]

    return {
        "dim": dim, "count": len(ns),
        "min": ns[0], "avg": statistics.fmean(ns), "max": ns[-1],
        "p01": pct(0.01), "p99": pct(0.99),
        "zeros": zeros, "nan": nanv, "inf": infv
    }

# ------------------------- inspección -----------------------------

def inspect_collection(col_name: str, col: Any, args: Any) -> None:
    try:
        count = col.count()
    except Exception as e:
        print(f"Estado: error  (detalle: {e})")
        return

    if count == 0:
        print("Estado: empty")
        return

    # dim
    sample = col.get(include=["embeddings"], limit=1)
    emb_dim = detect_embedding_dim(sample.get("embeddings"))

    print(f"Estado: active")
    print(f"Elementos (count)         : {count}")
    print(f"Embedding dim             : {emb_dim}")

    # stats documentos
    ds = collect_doc_stats(col, count, page_size=args.page_size, cap=args.doc_stats_cap)
    print("\nTamaño de documentos:")
    print(f"  avg: {ds['avg']}, min: {ds['min']}, p50: {ds['p50']}, p90: {ds['p90']}, max: {ds['max']}")

    # metadatos + distribución
    keys, presence, dist, vcounts, examples = collect_metadata_schema_and_distribution(col, count, page_size=args.page_size)
    print("\nDistribución de contenido:")
    total = max(1, count)
    for k, v in sorted(dist.items(), key=lambda x: (-x[1], x[0])):
        pct = (v / total) * 100.0
        print(f"  - {k:<40} {v:>8} ({pct:5.1f}%)")

    if keys:
        print("\nClaves de metadatos (todas):")
        for k in keys:
            pres = presence.get(k, 0)
            pct = (pres / total) * 100.0
            print(f"  • {k}  [{pres}/{total} = {pct:.1f}%]")
            top = vcounts.get(k)
            if top:
                for val, cnt in top.most_common(args.top_values):
                    p, _ = preview_text(val, 80)
                    pc = (cnt / total) * 100.0
                    print(f"      - {p!r}  {cnt} ({pc:.1f}%)")
            ex = examples.get(k) or []
            if ex:
                exs = ", ".join(repr(preview_text(e, 50)[0]) for e in ex)
                print(f"      ejemplos: {exs}")

    # stats embeddings
    es = collect_embedding_stats(col, count, page_size=args.page_size, cap=args.embedding_stats_cap)
    print("\nStats de embeddings:")
    print(f"  dim={es['dim']}, evaluados={es['count']}, min={es['min']}, avg={es['avg']}, max={es['max']}, p01={es['p01']}, p99={es['p99']}, zeros={es['zeros']}, NaN={es['nan']}, Inf={es['inf']}")

    # muestra
    print("\nMuestra (primeros {n} elementos):".format(n=min(args.sample, count)))
    taken = 0
    for row in iter_documents(col, min(args.sample, count), page_size=min(args.sample, count), with_embeddings=args.show_embeddings):
        taken += 1
        doc_prev, doc_len = preview_text(row["document"], 300)
        print(f"\n  -- Elemento #{taken} --")
        print(f"     id           : {row['id']}")
        print(f"     doc.length   : {doc_len}")
        print(f"     doc.preview  : {doc_prev}")
        md = row["metadata"] or {}
        if md:
            print("     metadatos    :")
            for k in sorted(md.keys()):
                val_prev, _ = preview_text(md[k], 160)
                print(f"        - {k}: {val_prev}")
        else:
            print("     metadatos    : {}")
        if args.show_embeddings:
            emb = row.get("embedding")
            if emb is None:
                print("     embedding    : None")
            else:
                ev = to_seq(emb)
                head = ", ".join(f"{float(x):.4f}" for x in ev[:args.vector_preview])
                tail = "" if len(ev) <= args.vector_preview else ", ..."
                print(f"     embedding    : dim={len(ev)}  [{head}{tail}]")

# ----------------------------- CLI --------------------------------

def main():
    parser = argparse.ArgumentParser(description="Inspección robusta del almacén de vectores (ChromaDB) - No escribe archivos")
    parser.add_argument("--collection", type=str, default=None, help="Nombre exacto de la colección a inspeccionar")
    parser.add_argument("--sample", type=int, default=5, help="Elementos de la muestra")
    parser.add_argument("--page-size", type=int, default=1000, help="Tamaño de página para la paginación")
    parser.add_argument("--top-values", type=int, default=5, help="Top-k valores por clave de metadatos")
    parser.add_argument("--embedding-stats-cap", type=int, default=10000, help="Máximo de elementos para stats de embeddings")
    parser.add_argument("--doc-stats-cap", type=int, default=20000, help="Máximo de elementos para stats de documentos")
    parser.add_argument("--show-embeddings", action="store_true", help="Mostrar preview de embeddings en la muestra")
    parser.add_argument("--vector-preview", type=int, default=8, help="Cuántos valores del vector mostrar por ítem si --show-embeddings")
    parser.add_argument("--verbose", action="store_true", help="Logs detallados")
    args = parser.parse_args()

    setup_logging(args.verbose)

    print("\n" + "="*100)
    print("INSPECCIÓN AVANZADA DE CHROMADB (sin archivos)")
    print("="*100)
    print(f"Directorio de vectores        : {VECTOR_STORE_DIR}")
    print(f"Fecha                         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not VECTOR_STORE_DIR.exists():
        print(f"\nERROR: No existe el directorio de vectores: {VECTOR_STORE_DIR}")
        raise SystemExit(1)

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
    existing = client.list_collections()
    print(f"Colecciones totales encontradas: {len(existing)}")
    for c in existing:
        print(f"  - {c.name}")

    targets: List[str]
    if args.collection:
        targets = [args.collection]
    else:
        configured = set(CHROMA_COLLECTIONS.values()) if CHROMA_COLLECTIONS else set()
        existing_names = {c.name for c in existing}
        targets = sorted(configured | existing_names)

    print("\n" + "="*100)
    print("RESUMEN DETALLADO POR COLECCIÓN")
    print("="*100)

    active = 0
    total_vectors = 0

    for name in targets:
        print("\n" + "-"*100)
        print(f"COLECCIÓN: {name}")
        print("-"*100)
        try:
            col = client.get_collection(name=name)
        except Exception as e:
            print(f"Estado: not_found  (detalle: {e})")
            continue

        try:
            inspect_collection(name, col, args)
            cnt = col.count()
            if cnt > 0:
                active += 1
                total_vectors += cnt
        except Exception as e:
            print(f"Estado: error  (detalle: {e})")

    print("\n" + "="*100)
    print("RESUMEN FINAL")
    print("="*100)
    print(f"Colecciones activas           : {active}/{len(targets)}")
    print(f"Total elementos vectorizados  : {total_vectors}")
    print(f"Directorio                    : {VECTOR_STORE_DIR}")
    print("\nNota: Esta herramienta NO genera archivos. Toda la información se ha mostrado en consola.\n")

if __name__ == "__main__":
    main()
