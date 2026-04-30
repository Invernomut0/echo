"""Wiki router — /api/wiki.

Implements the Karpathy LLM Wiki pattern:
  POST /api/wiki/ingest      – process a source document, update wiki
  POST /api/wiki/query       – ask a question, synthesize from wiki pages
  GET  /api/wiki/pages       – list all wiki pages
  GET  /api/wiki/page        – read a single page
  GET  /api/wiki/search      – keyword search
  GET  /api/wiki/index       – return raw index.md
  GET  /api/wiki/log         – return recent log entries
  POST /api/wiki/lint        – health-check (orphans, contradictions)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

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
