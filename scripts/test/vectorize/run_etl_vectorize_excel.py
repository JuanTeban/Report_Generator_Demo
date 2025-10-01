import asyncio
import argparse
import logging
from pathlib import Path
import sys
from typing import Optional

# Ensure project root is on sys.path when running as a script
try:
    import app  # type: ignore
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.core.etl.excels import ingest as _ingest_mod
from app.core.etl.excels import knowledge_base as _kb_mod
from app.core.etl.excels import vectorize as _vec_mod
from app.config import settings_etl as etl_settings
from typing import Callable, Awaitable, cast, TypedDict


class IngestResult(TypedDict, total=False):
    success: bool


class KnowledgeBaseResult(TypedDict, total=False):
    success: bool
    markdown_file: Optional[str]


class VectorizeResult(TypedDict, total=False):
    success: bool


ingest_excel_files = cast(Callable[[], Awaitable[IngestResult]], _ingest_mod.ingest_excel_files)  # type: ignore[reportUnknownVariableType]
build_knowledge_base = cast(Callable[[], Awaitable[KnowledgeBaseResult]], _kb_mod.build_knowledge_base)  # type: ignore[reportUnknownVariableType]
vectorize_markdown_file = cast(Callable[[Path], Awaitable[VectorizeResult]], _vec_mod.vectorize_markdown_file)  # type: ignore[reportUnknownVariableType]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


async def ensure_dirs() -> None:
    etl_settings.DATA_STORE_PATH.mkdir(parents=True, exist_ok=True)
    etl_settings.DUCKDB_DATA_DIR.mkdir(parents=True, exist_ok=True)
    etl_settings.KNOWLEDGE_BASE_DIR.mkdir(parents=True, exist_ok=True)
    etl_settings.DATA_LOG_PATH.mkdir(parents=True, exist_ok=True)
    etl_settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    etl_settings.UPLOADS_EXCEL_DIR.mkdir(parents=True, exist_ok=True)

async def run(args: argparse.Namespace) -> int:
    logger = logging.getLogger("test_runner")
    await ensure_dirs()

    step: str = args.step
    force: bool = args.force
    markdown_arg: Optional[str] = args.markdown

    if step in ("ingest", "all"):
        logger.info("Running: ingest_excel_files()")
        ingest_result: IngestResult = await ingest_excel_files()
        logger.info(f"Ingest result: {ingest_result}")
        if not ingest_result.get("success") and not force:
            logger.error("Ingest step failed. Use --force to continue anyway.")
            return 1

    markdown_path: Optional[str] = None
    if step in ("kb", "all"):
        logger.info("Running: build_knowledge_base()")
        kb_result: KnowledgeBaseResult = await build_knowledge_base()
        logger.info(f"KB result: {kb_result}")
        if not kb_result.get("success") and not force:
            logger.error("KB step failed. Use --force to continue anyway.")
            return 1
        markdown_path = kb_result.get("markdown_file")

    if step in ("vectorize", "all"):
        if not markdown_path:
            if markdown_arg:
                markdown_path = markdown_arg
            else:
                kbase_dir = etl_settings.KNOWLEDGE_BASE_DIR
                md_files = sorted(kbase_dir.glob("database_embedding_*.md"))
                markdown_path = str(md_files[-1]) if md_files else None
        if not markdown_path:
            logger.error("No markdown file found to vectorize. Provide --markdown path or run KB step first.")
            return 1
        logger.info(f"Running: vectorize_markdown_file({markdown_path})")
        assert isinstance(markdown_path, str)
        vec_result: VectorizeResult = await vectorize_markdown_file(Path(markdown_path))
        logger.info(f"Vectorize result: {vec_result}")
        if not vec_result.get("success") and not force:
            logger.error("Vectorize step failed.")
            return 1

    logger.info("All requested steps completed successfully.")
    return 0


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Run ETL -> KB -> Vectorize pipeline for testing")
    parser.add_argument("--step", choices=["ingest", "kb", "vectorize", "all"], default="all")
    parser.add_argument("--markdown", type=str, default=None, help="Path to markdown file for vectorization")
    parser.add_argument("--force", action="store_true", help="Continue on errors")
    args = parser.parse_args()

    exit_code = asyncio.run(run(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()


