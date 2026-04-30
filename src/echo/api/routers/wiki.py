"""Wiki router — /api/wiki.

Implements the Karpathy LLM Wiki pattern:
  POST /api/wiki/ingest          – process a source document, update wiki
  POST /api/wiki/ingest_files    – upload one or more files (.txt/.md/.pdf)
  POST /api/wiki/query           – ask a question, synthesize from wiki pages
  GET  /api/wiki/pages           – list all wiki pages
  GET  /api/wiki/page            – read a single page
  GET  /api/wiki/search          – keyword search
  GET  /api/wiki/index           – return raw index.md
  GET  /api/wiki/log             – return recent log entries
  POST /api/wiki/lint            – health-check (orphans, contradictions)
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from echo.api.schemas import (
    WikiIngestRequest,
    WikiIngestResponse,
    WikiLintResponse,
    WikiPageItem,
    WikiQueryRequest,
    WikiQueryResponse,
    WikiSearchResponse,
    WikiGraphResponse,
)
from echo.memory.wiki import wiki

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wiki", tags=["wiki"])


@router.post("/ingest", response_model=WikiIngestResponse)
async def ingest_source(body: WikiIngestRequest) -> WikiIngestResponse:
    """Ingest a source document into the wiki.

    The LLM extracts entities and concepts, creates/updates pages,
    and files a source summary page.
    """
    result = await wiki.ingest(
        source_text=body.source_text,
        title=body.title,
        source_type=body.source_type,
        file_back_synthesis=body.file_back_synthesis,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return WikiIngestResponse(**result)


def _extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from uploaded file bytes based on extension."""
    fname = filename.lower()
    if fname.endswith(".pdf"):
        try:
            import pypdf  # noqa: PLC0415
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(p for p in pages if p.strip())
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Impossibile leggere PDF '{filename}': {exc}") from exc
    # .txt / .md / plain text
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=422, detail=f"Encoding non riconosciuto per '{filename}'")


@router.post("/ingest_files", response_model=list[WikiIngestResponse])
async def ingest_files(
    files: list[UploadFile] = File(..., description="Uno o più file .txt/.md/.pdf"),
    source_type: str = Query(default="document", description="Tipo sorgente: text/article/paper/book/document"),
) -> list[WikiIngestResponse]:
    """Upload and ingest one or more files (.txt, .md, .pdf) into the wiki.

    Each file is processed independently: the LLM extracts entities and
    concepts and creates/updates wiki pages.  Results are returned in order.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Nessun file ricevuto.")

    _ALLOWED_EXT = {".txt", ".md", ".pdf"}
    results: list[WikiIngestResponse] = []

    for upload in files:
        fname = upload.filename or "untitled"
        ext = "." + fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in _ALLOWED_EXT:
            raise HTTPException(
                status_code=415,
                detail=f"Tipo non supportato: '{fname}'. Usa .txt, .md o .pdf.",
            )

        data = await upload.read()
        if len(data) > 10 * 1024 * 1024:  # 10 MB cap
            raise HTTPException(status_code=413, detail=f"File '{fname}' supera 10 MB.")

        text = _extract_text(fname, data)
        if not text.strip():
            raise HTTPException(status_code=422, detail=f"Il file '{fname}' non contiene testo estraibile.")

        # Use filename stem as title
        title = fname.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()

        logger.info("Wiki ingest_files: processing '%s' (%d chars)", fname, len(text))
        result = await wiki.ingest(
            source_text=text,
            title=title,
            source_type=source_type,
            file_back_synthesis=True,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=f"Errore su '{fname}': {result['error']}")
        results.append(WikiIngestResponse(**result))

    return results


@router.post("/query", response_model=WikiQueryResponse)
async def query_wiki(body: WikiQueryRequest) -> WikiQueryResponse:
    """Ask a question; LLM synthesizes an answer from relevant wiki pages."""
    result = await wiki.query(question=body.question, file_back=body.file_back)
    return WikiQueryResponse(**result)


@router.get("/pages", response_model=WikiSearchResponse)
async def list_pages() -> WikiSearchResponse:
    """Return all pages listed in the wiki index."""
    pages = wiki.list_pages()
    return WikiSearchResponse(
        query="",
        results=[WikiPageItem(**p) for p in pages],
    )


@router.get("/page", response_model=dict)
async def get_page(path: str = Query(..., description="Relative path, e.g. pages/entities/lorenzo.md")) -> dict:
    """Read a single wiki page by its relative path."""
    content = wiki.read_page_by_path(path)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Page not found: {path}")
    return {"path": path, "content": content}


@router.get("/search", response_model=WikiSearchResponse)
async def search_wiki(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=10, ge=1, le=50),
) -> WikiSearchResponse:
    """Keyword search over wiki index and page bodies."""
    results = wiki.search(q, max_results=limit)
    return WikiSearchResponse(
        query=q,
        results=[WikiPageItem(**r) for r in results],
    )


@router.get("/index")
async def get_index() -> dict:
    """Return the raw index.md content."""
    return {"content": wiki.get_index()}


@router.get("/log")
async def get_log(last: int = Query(default=20, ge=1, le=200)) -> dict:
    """Return the last N log entries."""
    return {"content": wiki.get_log(last_n=last)}


@router.post("/lint", response_model=WikiLintResponse)
async def lint_wiki() -> WikiLintResponse:
    """LLM health-check: find contradictions, orphans, missing cross-refs."""
    result = await wiki.lint()
    return WikiLintResponse(**result)


@router.get("/graph", response_model=WikiGraphResponse)
async def get_wiki_graph() -> WikiGraphResponse:
    """Return nodes + wikilink edges for 3D graph visualisation."""
    result = wiki.graph()
    return WikiGraphResponse(**result)
