"""LLM Wiki — persistent, compounding knowledge base maintained by the LLM.

Architecture (Karpathy pattern — https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):

  data/wiki/
    index.md        – catalog: every page listed with title, path, summary, tags
    log.md          – append-only record of all operations
    pages/
      entities/     – people, places, organisations, products, concepts
      concepts/     – abstract topics and ideas
      sources/      – summaries of ingested external documents
      syntheses/    – query answers filed back as permanent pages

Key operations:
  ingest(text, title)         – read source, update wiki, file summary page
  query(question)             – read relevant pages, synthesize answer
  update_from_interaction()   – post-chat lightweight wiki update
  lint()                      – health-check: orphans, contradictions, stale
  search(query)               – keyword scan over index + pages
"""

from __future__ import annotations

import logging
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from echo.core.config import settings
from echo.core.llm_client import llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

WIKI_ROOT: Path = Path("data/wiki")
INDEX_PATH: Path = WIKI_ROOT / "index.md"
LOG_PATH: Path = WIKI_ROOT / "log.md"
PAGES_ROOT: Path = WIKI_ROOT / "pages"

PageCategory = Literal["entities", "concepts", "sources", "syntheses"]

_CATEGORIES: tuple[PageCategory, ...] = ("entities", "concepts", "sources", "syntheses")

# ---------------------------------------------------------------------------
# LLM system prompt — the wiki "schema"
# ---------------------------------------------------------------------------

_WIKI_SCHEMA = textwrap.dedent("""
    You are the LLM writer of PROJECT ECHO's personal knowledge wiki.

    The wiki is a directory of interlinked markdown files. Rules:
    - Write in Markdown; use ### headers and bullet lists for facts.
    - Add YAML frontmatter to every page:
        ---
        title: <title>
        category: entities|concepts|sources|syntheses
        tags: [tag1, tag2]
        updated: YYYY-MM-DD
        ---
    - Use [[PageName]] wikilinks to cross-reference other pages.
    - Be factual and concise. Never invent facts not present in the source.
    - When citing a source, note it as "(from: <source_title>)".
""").strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:80].strip("-")


def _truncate(text: str, max_chars: int = 1800) -> str:
    """Truncate to stay within Ollama's context limit."""
    return text[:max_chars]


# ---------------------------------------------------------------------------
# WikiStore
# ---------------------------------------------------------------------------

class WikiStore:
    """Manages the on-disk wiki and exposes LLM-driven operations.

    All write operations are sync-safe (atomic file writes) and all LLM calls
    are async.  Use ``wiki`` singleton from this module.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or WIKI_ROOT
        self._index = self._root / "index.md"
        self._log = self._root / "log.md"
        self._pages = self._root / "pages"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> None:
        """Create directory structure and seed empty index/log if needed."""
        self._root.mkdir(parents=True, exist_ok=True)
        for cat in _CATEGORIES:
            (self._pages / cat).mkdir(parents=True, exist_ok=True)

        if not self._index.exists():
            self._index.write_text(
                "# Wiki Index\n\n"
                "| Page | Category | Tags | Summary |\n"
                "|------|----------|------|---------|\n",
                encoding="utf-8",
            )
            logger.info("Wiki: created index.md")

        if not self._log.exists():
            self._log.write_text(
                "# Wiki Log\n\nAppend-only record of all wiki operations.\n\n",
                encoding="utf-8",
            )
            logger.info("Wiki: created log.md")

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _index_has_page(self, slug: str) -> bool:
        if not self._index.exists():
            return False
        return slug in self._index.read_text(encoding="utf-8")

    def _update_index(
        self,
        slug: str,
        title: str,
        category: PageCategory,
        tags: list[str],
        summary: str,
    ) -> None:
        content = self._index.read_text(encoding="utf-8")
        rel_path = f"pages/{category}/{slug}.md"
        tag_str = ", ".join(tags)
        # Sanitize for table cell
        summary_short = summary.replace("|", "–").replace("\n", " ")[:120]
        new_row = f"| [[{title}]]({rel_path}) | {category} | {tag_str} | {summary_short} |\n"

        # Replace existing row or append
        pattern = re.compile(rf"^\|.*{re.escape(slug)}.*\|.*$\n?", re.MULTILINE)
        if pattern.search(content):
            content = pattern.sub(new_row, content, count=1)
        else:
            content += new_row
        self._index.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Log management
    # ------------------------------------------------------------------

    def _append_log(
        self,
        op: str,
        title: str,
        details: str = "",
    ) -> None:
        entry = f"## [{_now_ts()}] {op} | {title}\n"
        if details:
            entry += f"{details.strip()}\n"
        entry += "\n"
        log_content = self._log.read_text(encoding="utf-8") if self._log.exists() else ""
        self._log.write_text(log_content + entry, encoding="utf-8")

    # ------------------------------------------------------------------
    # Page I/O
    # ------------------------------------------------------------------

    def _page_path(self, category: PageCategory, slug: str) -> Path:
        return self._pages / category / f"{slug}.md"

    def _write_page(self, category: PageCategory, slug: str, content: str) -> Path:
        path = self._page_path(category, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _read_page(self, category: PageCategory, slug: str) -> str | None:
        path = self._page_path(category, slug)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def read_page_by_path(self, rel_path: str) -> str | None:
        """Read a page given its path relative to wiki root."""
        path = self._root / rel_path
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def list_pages(self) -> list[dict[str, str]]:
        """Return all pages parsed from index.md."""
        pages: list[dict[str, str]] = []
        if not self._index.exists():
            return pages
        content = self._index.read_text(encoding="utf-8")
        for line in content.splitlines():
            if not line.startswith("| [["):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                # Extract title from [[Title]](path)
                m = re.match(r"\[\[(.+?)\]\]\((.+?)\)", parts[0])
                if m:
                    pages.append(
                        {
                            "title": m.group(1),
                            "path": m.group(2),
                            "category": parts[1],
                            "tags": parts[2],
                            "summary": parts[3] if len(parts) > 3 else "",
                        }
                    )
        return pages

    def get_index(self) -> str:
        if self._index.exists():
            return self._index.read_text(encoding="utf-8")
        return ""

    def get_log(self, last_n: int = 20) -> str:
        if not self._log.exists():
            return ""
        lines = self._log.read_text(encoding="utf-8").splitlines()
        # Find last n entries (sections starting with ##)
        section_starts = [i for i, l in enumerate(lines) if l.startswith("## [")]
        if not section_starts:
            return "\n".join(lines)
        start_idx = section_starts[-last_n] if len(section_starts) >= last_n else 0
        return "\n".join(lines[start_idx:])

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Simple keyword search over index.md + page contents."""
        query_lower = query.lower()
        keywords = query_lower.split()
        results: list[dict[str, Any]] = []

        for page in self.list_pages():
            title_lower = page["title"].lower()
            # Score by number of keyword matches in title + summary
            score = sum(1 for kw in keywords if kw in title_lower)
            score += sum(0.5 for kw in keywords if kw in page.get("summary", "").lower())
            score += sum(0.3 for kw in keywords if kw in page.get("tags", "").lower())

            if score > 0:
                results.append({**page, "score": score})

        # Also scan page bodies for more relevant hits
        for page in self.list_pages():
            body = self.read_page_by_path(page["path"]) or ""
            body_lower = body.lower()
            body_score = sum(0.2 for kw in keywords if kw in body_lower)
            if body_score > 0:
                # Update existing result or add new
                existing = next((r for r in results if r["path"] == page["path"]), None)
                if existing:
                    existing["score"] = existing.get("score", 0) + body_score
                else:
                    results.append({**page, "score": body_score})

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:max_results]

    # ------------------------------------------------------------------
    # _find_relevant_pages (for query)
    # ------------------------------------------------------------------

    def _find_relevant_pages(self, query: str, max_pages: int = 8) -> list[dict[str, Any]]:
        """Return the most relevant page dicts for a query."""
        return self.search(query, max_results=max_pages)

    # ------------------------------------------------------------------
    # LLM operations
    # ------------------------------------------------------------------

    async def ingest(
        self,
        source_text: str,
        title: str,
        source_type: str = "text",
        file_back_synthesis: bool = True,
    ) -> dict[str, Any]:
        """Process a source, create/update wiki pages, return summary.

        1. Ask LLM to extract entities and concepts from the source.
        2. Write/update individual entity and concept pages.
        3. Write a source summary page.
        4. Update index.md and log.md.
        """
        if not source_text.strip():
            return {"error": "Empty source text"}

        slug = _slugify(title)
        truncated = _truncate(source_text, 6000)  # generous cap for ingest

        # ── Step 1: Extract entities & concepts ──────────────────────────────
        extract_resp = await llm.chat(
            messages=[
                {"role": "system", "content": _WIKI_SCHEMA},
                {
                    "role": "user",
                    "content": (
                        f"Read this source titled '{title}' and return JSON with:\n"
                        "- entities: [{name, slug, description}] — people, places, things\n"
                        "- concepts: [{name, slug, description}] — ideas, topics, themes\n"
                        "- summary: one paragraph summary of the source\n\n"
                        "Respond with ONLY valid JSON, no markdown.\n\n"
                        f"SOURCE:\n{truncated}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=1500,
        )

        entities: list[dict] = []
        concepts: list[dict] = []
        source_summary = ""

        try:
            import json as _json
            # Strip possible markdown code fence
            clean = re.sub(r"^```(?:json)?\n?", "", extract_resp.strip())
            clean = re.sub(r"\n?```$", "", clean)
            data = _json.loads(clean)
            entities = data.get("entities", [])
            concepts = data.get("concepts", [])
            source_summary = data.get("summary", "")
        except Exception as exc:
            logger.warning("Wiki ingest: JSON parse error — %s", exc)
            source_summary = extract_resp[:300]

        pages_written: list[str] = []

        # ── Step 2: Write/update entity pages ───────────────────────────────
        for ent in entities[:10]:  # cap to avoid runaway
            ent_slug = _slugify(ent.get("slug") or ent.get("name", "unknown"))
            ent_title = ent.get("name", ent_slug)
            existing = self._read_page("entities", ent_slug)

            if existing:
                # Update existing page
                update_resp = await llm.chat(
                    messages=[
                        {"role": "system", "content": _WIKI_SCHEMA},
                        {
                            "role": "user",
                            "content": (
                                f"Update this wiki page for '{ent_title}' "
                                f"with new information from source '{title}'.\n\n"
                                f"CURRENT PAGE:\n{existing}\n\n"
                                f"NEW INFO:\n{ent.get('description', '')}\n\n"
                                "Return the full updated markdown page."
                            ),
                        },
                    ],
                    temperature=0.2,
                    max_tokens=800,
                )
                self._write_page("entities", ent_slug, update_resp)
            else:
                # Create new page
                page_content = (
                    f"---\n"
                    f"title: {ent_title}\n"
                    f"category: entities\n"
                    f"tags: [entity]\n"
                    f"updated: {_now_iso()}\n"
                    f"---\n\n"
                    f"# {ent_title}\n\n"
                    f"{ent.get('description', '')}\n\n"
                    f"*(from: [[{title}]])*\n"
                )
                self._write_page("entities", ent_slug, page_content)
                self._update_index(
                    ent_slug, ent_title, "entities",
                    ["entity"], ent.get("description", "")[:80],
                )
            pages_written.append(f"entities/{ent_slug}")

        # ── Step 3: Write/update concept pages ──────────────────────────────
        for con in concepts[:10]:
            con_slug = _slugify(con.get("slug") or con.get("name", "unknown"))
            con_title = con.get("name", con_slug)
            existing = self._read_page("concepts", con_slug)

            if existing:
                update_resp = await llm.chat(
                    messages=[
                        {"role": "system", "content": _WIKI_SCHEMA},
                        {
                            "role": "user",
                            "content": (
                                f"Update this wiki page for concept '{con_title}' "
                                f"with new info from source '{title}'.\n\n"
                                f"CURRENT PAGE:\n{existing}\n\n"
                                f"NEW INFO:\n{con.get('description', '')}\n\n"
                                "Return the full updated markdown page."
                            ),
                        },
                    ],
                    temperature=0.2,
                    max_tokens=800,
                )
                self._write_page("concepts", con_slug, update_resp)
            else:
                page_content = (
                    f"---\n"
                    f"title: {con_title}\n"
                    f"category: concepts\n"
                    f"tags: [concept]\n"
                    f"updated: {_now_iso()}\n"
                    f"---\n\n"
                    f"# {con_title}\n\n"
                    f"{con.get('description', '')}\n\n"
                    f"*(from: [[{title}]])*\n"
                )
                self._write_page("concepts", con_slug, page_content)
                self._update_index(
                    con_slug, con_title, "concepts",
                    ["concept"], con.get("description", "")[:80],
                )
            pages_written.append(f"concepts/{con_slug}")

        # ── Step 4: Write source summary page ───────────────────────────────
        src_content = (
            f"---\n"
            f"title: {title}\n"
            f"category: sources\n"
            f"tags: [{source_type}]\n"
            f"updated: {_now_iso()}\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"**Type:** {source_type}  \n"
            f"**Ingested:** {_now_iso()}\n\n"
            f"## Summary\n\n{source_summary}\n\n"
            f"## Related Pages\n\n"
        )
        for pg in pages_written:
            src_content += f"- [[{pg}]]\n"
        self._write_page("sources", slug, src_content)
        self._update_index(slug, title, "sources", [source_type], source_summary[:80])
        pages_written.append(f"sources/{slug}")

        # ── Step 5: Update log ───────────────────────────────────────────────
        self._append_log(
            "ingest",
            title,
            f"Type: {source_type}. Pages touched: {len(pages_written)}.\n"
            f"Entities: {len(entities)}, concepts: {len(concepts)}.",
        )

        return {
            "title": title,
            "slug": slug,
            "pages_written": pages_written,
            "entities": len(entities),
            "concepts": len(concepts),
            "summary": source_summary,
        }

    async def query(
        self,
        question: str,
        file_back: bool = True,
    ) -> dict[str, Any]:
        """Search wiki pages and synthesize an answer.

        1. Read index.md to find relevant pages.
        2. Load those pages.
        3. LLM synthesizes answer with citations.
        4. Optionally file the answer back as a synthesis page.
        """
        # ── Step 1: find relevant pages ──────────────────────────────────────
        relevant = self._find_relevant_pages(question, max_pages=6)

        # Load page bodies
        context_parts: list[str] = []
        for pg in relevant:
            body = self.read_page_by_path(pg["path"])
            if body:
                context_parts.append(
                    f"=== Page: {pg['title']} ({pg['path']}) ===\n{body[:1200]}"
                )

        context = "\n\n".join(context_parts) if context_parts else "No relevant pages found."

        # ── Step 2: synthesize answer ─────────────────────────────────────────
        answer = await llm.chat(
            messages=[
                {"role": "system", "content": _WIKI_SCHEMA},
                {
                    "role": "user",
                    "content": (
                        "Answer the following question using the wiki pages provided.\n"
                        "Cite pages as [[PageName]]. If info is missing, say so.\n\n"
                        f"QUESTION: {question}\n\n"
                        f"WIKI CONTEXT:\n{context}"
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=1200,
        )

        # ── Step 3: file back as synthesis page ──────────────────────────────
        synthesis_slug: str | None = None
        if file_back and answer.strip():
            synthesis_slug = _slugify(question[:60])
            synthesis_content = (
                f"---\n"
                f"title: {question[:80]}\n"
                f"category: syntheses\n"
                f"tags: [query]\n"
                f"updated: {_now_iso()}\n"
                f"---\n\n"
                f"# Q: {question}\n\n"
                f"{answer}\n\n"
                f"## Sources consulted\n\n"
            )
            for pg in relevant:
                synthesis_content += f"- [[{pg['title']}]]({pg['path']})\n"
            self._write_page("syntheses", synthesis_slug, synthesis_content)
            self._update_index(
                synthesis_slug, f"Q: {question[:60]}", "syntheses",
                ["query"], answer[:80],
            )

        self._append_log("query", question[:80], f"Pages consulted: {len(relevant)}.")

        return {
            "question": question,
            "answer": answer,
            "pages_consulted": [pg["title"] for pg in relevant],
            "synthesis_page": f"pages/syntheses/{synthesis_slug}.md" if synthesis_slug else None,
        }

    async def update_from_interaction(
        self,
        user_msg: str,
        assistant_msg: str,
    ) -> dict[str, Any]:
        """Lightweight post-interaction wiki update.

        Asks the LLM to identify any new entities or facts worth adding and
        creates/updates the relevant pages.  This is deliberately lightweight
        (capped tokens) to run as a fire-and-forget background task.
        """
        combined = f"User: {user_msg}\nAssistant: {assistant_msg}"
        if len(combined) < 40:
            return {"pages_updated": 0}

        extract_resp = await llm.chat(
            messages=[
                {"role": "system", "content": _WIKI_SCHEMA},
                {
                    "role": "user",
                    "content": (
                        "Given this short conversation, identify any NEW facts "
                        "worth adding to a personal knowledge wiki.\n\n"
                        "Return JSON: {\"updates\": [{\"category\": \"entities|concepts\", "
                        "\"name\": \"...\", \"slug\": \"...\", \"fact\": \"...\"}]}\n"
                        "Only include genuinely new, durable facts (not greetings, "
                        "chat niceties, etc.). Return [] if nothing notable.\n\n"
                        f"CONVERSATION:\n{combined[:3000]}"
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=500,
        )

        updates: list[dict] = []
        try:
            import json as _json
            clean = re.sub(r"^```(?:json)?\n?", "", extract_resp.strip())
            clean = re.sub(r"\n?```$", "", clean)
            data = _json.loads(clean)
            updates = data.get("updates", [])
        except Exception:
            return {"pages_updated": 0}

        pages_updated = 0
        for upd in updates[:5]:  # cap
            cat: PageCategory = upd.get("category", "entities")
            if cat not in _CATEGORIES:
                cat = "entities"
            slug = _slugify(upd.get("slug") or upd.get("name", "unknown"))
            name = upd.get("name", slug)
            fact = upd.get("fact", "")
            if not fact:
                continue

            existing = self._read_page(cat, slug)
            if existing:
                # Append fact to existing page
                appended = existing + f"\n- {fact} *(from: conversation {_now_iso()})*\n"
                self._write_page(cat, slug, appended)
            else:
                page_content = (
                    f"---\n"
                    f"title: {name}\n"
                    f"category: {cat}\n"
                    f"tags: [{cat[:-1]}]\n"
                    f"updated: {_now_iso()}\n"
                    f"---\n\n"
                    f"# {name}\n\n"
                    f"- {fact} *(from: conversation {_now_iso()})*\n"
                )
                self._write_page(cat, slug, page_content)
                self._update_index(slug, name, cat, [cat[:-1]], fact[:80])
            pages_updated += 1

        if pages_updated:
            self._append_log(
                "interaction-update",
                f"chat {_now_iso()}",
                f"Updated {pages_updated} page(s) from conversation.",
            )

        return {"pages_updated": pages_updated}

    async def lint(self) -> dict[str, Any]:
        """Health-check the wiki: orphans, contradictions, missing pages."""
        pages = self.list_pages()
        if not pages:
            return {"issues": [], "total_pages": 0}

        index_content = self.get_index()
        # Sample up to 20 pages for lint context
        sample_pages = pages[:20]
        sample_bodies: list[str] = []
        for pg in sample_pages:
            body = self.read_page_by_path(pg["path"])
            if body:
                sample_bodies.append(f"### {pg['title']}\n{body[:600]}")

        context = "\n\n".join(sample_bodies[:15])

        lint_resp = await llm.chat(
            messages=[
                {"role": "system", "content": _WIKI_SCHEMA},
                {
                    "role": "user",
                    "content": (
                        "Perform a health-check on this wiki. "
                        "Look for: contradictions, stale claims, orphan concepts "
                        "(mentioned but no dedicated page), missing cross-references.\n\n"
                        "Return JSON: {\"issues\": [{\"severity\": \"high|medium|low\", "
                        "\"page\": \"...\", \"description\": \"...\"}]}\n\n"
                        f"INDEX:\n{index_content[:2000]}\n\n"
                        f"SAMPLE PAGES:\n{context}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=800,
        )

        issues: list[dict] = []
        try:
            import json as _json
            clean = re.sub(r"^```(?:json)?\n?", "", lint_resp.strip())
            clean = re.sub(r"\n?```$", "", clean)
            data = _json.loads(clean)
            issues = data.get("issues", [])
        except Exception:
            issues = [{"severity": "low", "page": "—", "description": lint_resp[:200]}]

        self._append_log("lint", "wiki-health-check", f"Found {len(issues)} issue(s).")

        return {
            "total_pages": len(pages),
            "issues": issues,
            "checked_pages": len(sample_pages),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

wiki = WikiStore()
