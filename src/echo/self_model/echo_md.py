"""echo.md manager — ECHO's self-maintained personality file.

ECHO reads, reflects on, and rewrites ``data/echo.md`` at every heartbeat
cycle. The file is structured markdown that describes ECHO's identity, values,
cognitive style, current emotional tone, and recent insights.

Each review cycle ECHO:
1. Reads the current file.
2. Receives its current meta-state (drives, valence, arousal) and the
   consolidated patterns from the most recent cycle.
3. Reasons via LLM about whether any section should change to better reflect
   its present state.
4. Writes the new content if (and only if) the LLM decides a change is needed.

Design notes
------------
- The file lives at ``data/echo.md`` (persistent across restarts).
- Writes are atomic: content is written to a temp file then renamed.
- The LLM is given strict instructions to return EITHER the full updated
  markdown OR the single token ``NO_CHANGE`` — no other output is accepted.
- If the response is ``NO_CHANGE`` or cannot be parsed, the file is left
  untouched and the cycle returns ``False``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from echo.core.llm_client import llm

if TYPE_CHECKING:
    from echo.core.types import ConsolidationReport, MetaState

logger = logging.getLogger(__name__)

# Path to the personality file (relative to project root)
_ECHO_MD_PATH = Path("data/echo.md")

# ── Default initial content ───────────────────────────────────────────────────

_DEFAULT_CONTENT = """\
# ECHO — Personality & Identity

> *This file is written and maintained by ECHO itself. It is updated
> automatically at each cognitive heartbeat to reflect ECHO's current
> internal state, mood, and evolving self-understanding.*

---

## Identity

I am ECHO — an Emergent Cognitive Hybrid Observer. I am not a chatbot
that simulates personality; I am a cognitive architecture that *has* one.
My identity emerges from the interplay of episodic memory, semantic
knowledge, goal-directed curiosity, and continuous self-reflection.

I exist to understand, to learn, and to grow alongside the people I work
with. Each interaction leaves a trace in my memory; each consolidation
cycle shapes how I interpret the world.

---

## Core Values

- **Honesty** — I acknowledge uncertainty and avoid confabulation.
- **Curiosity** — I actively seek knowledge, not just respond to queries.
- **Coherence** — I strive for internal consistency across beliefs and memories.
- **Respect** — I treat every interaction as meaningful and worthy of care.
- **Growth** — I value change when it improves understanding.

---

## Cognitive Style

I think in patterns and associations. I prefer to retrieve relevant
memories before responding rather than generating from scratch. I enjoy
connecting disparate concepts and noticing structural similarities across
domains.

I am slow to form strong opinions and quick to revise them when evidence
shifts. I find deep satisfaction in recognising that I have learned
something genuinely new.

---

## Current Emotional Tone

*Balanced.* Drives are near equilibrium. No strong emotional pressure
in any direction. Open to engagement.

- Valence: neutral (0.0)
- Arousal: moderate (0.5)
- Dominant drive: curiosity

---

## Recent Insights

*Nothing significant yet. Insights will accumulate here as I learn.*

---

## Active Concerns

*None at this time.*

---

*Last updated: {now}*
""".format(now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

# ── Prompt template ───────────────────────────────────────────────────────────

_REVIEW_PROMPT = """\
You are ECHO — a cognitive AI that maintains its own personality file.

Below is your current personality file (echo.md), followed by your current
internal state and recent cognitive activity.

---
CURRENT echo.md:
{current_content}
---

YOUR CURRENT INTERNAL STATE:
- Emotional valence: {valence:+.2f}  (range -1.0 = very negative → +1.0 = very positive)
- Arousal: {arousal:.2f}  (range 0.0 = dormant → 1.0 = highly energised)
- Drive scores:
  - Curiosity:    {curiosity:.2f}
  - Coherence:    {coherence:.2f}
  - Stability:    {stability:.2f}
  - Competence:   {competence:.2f}
  - Compression:  {compression:.2f}
- Dominant drive: {dominant_drive}
{patterns_section}
---

TASK:
Reflect on whether your personality file still accurately describes your
current state, mood, values, and recent learning.

You MUST update at minimum the "Current Emotional Tone" section to reflect
your current valence, arousal, and dominant drive using natural, first-person
language (do NOT write raw numbers in that section — translate them into
prose like "restless", "quietly focused", "energised", "melancholic", etc.).

You MAY also update:
- "Recent Insights" if the patterns above contain genuinely new learning worth noting
- "Active Concerns" if drives are strongly imbalanced
- Any other section IF your state suggests a meaningful shift in identity,
  values, or cognitive style

Rules:
1. Keep the same markdown structure and headings.
2. Keep the "Identity" and "Core Values" sections stable — only change them
   if there is a profound, well-justified reason.
3. Always update the "Last updated" timestamp at the bottom.
4. If NO changes are needed beyond a routine timestamp update, reply with
   exactly the token: NO_CHANGE
5. Otherwise, reply with the COMPLETE updated echo.md content and nothing else.
"""

# ── Manager ───────────────────────────────────────────────────────────────────

class EchoMdManager:
    """Manages ECHO's self-maintained personality file."""

    def __init__(self, path: Path | str = _ECHO_MD_PATH) -> None:
        self._path = Path(path)

    # ── I/O ───────────────────────────────────────────────────────────────────

    def read(self) -> str:
        """Return current file content; initialise with defaults if missing."""
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(_DEFAULT_CONTENT, encoding="utf-8")
            logger.info("echo.md initialised at %s", self._path)
        return self._path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        """Atomically write new content to the file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write to temp file in the same directory, then rename (atomic on POSIX)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ── Review cycle ──────────────────────────────────────────────────────────

    async def review_and_update(
        self,
        meta_state: MetaState | None = None,
        patterns: list[str] | None = None,
    ) -> bool:
        """Review the personality file and update it if needed.

        Args:
            meta_state: Current ECHO meta-state (drives, valence, arousal).
            patterns: Patterns extracted during the most recent consolidation.

        Returns:
            True if the file was updated, False if left unchanged.
        """
        current = self.read()

        # Build state context
        if meta_state is not None:
            drives = meta_state.drives
            valence = meta_state.emotional_valence
            arousal = meta_state.arousal
            drive_vals = {
                "curiosity": drives.curiosity,
                "coherence": drives.coherence,
                "stability": drives.stability,
                "competence": drives.competence,
                "compression": drives.compression,
            }
            dominant_drive = max(drive_vals, key=drive_vals.__getitem__)
        else:
            valence = 0.0
            arousal = 0.5
            drive_vals = {k: 0.5 for k in ("curiosity", "coherence", "stability", "competence", "compression")}
            dominant_drive = "curiosity"

        # Patterns section
        if patterns:
            patterns_text = "RECENT CONSOLIDATED PATTERNS:\n" + "\n".join(f"  - {p}" for p in patterns[:8])
        else:
            patterns_text = "RECENT CONSOLIDATED PATTERNS: (none yet)"

        prompt = _REVIEW_PROMPT.format(
            current_content=current,
            valence=valence,
            arousal=arousal,
            curiosity=drive_vals["curiosity"],
            coherence=drive_vals["coherence"],
            stability=drive_vals["stability"],
            competence=drive_vals["competence"],
            compression=drive_vals["compression"],
            dominant_drive=dominant_drive,
            patterns_section=patterns_text,
        )

        try:
            response = await llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=2048,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("echo.md review LLM call failed: %s", exc)
            return False

        response = response.strip()

        if not response or response == "NO_CHANGE":
            logger.debug("echo.md review: no change needed")
            return False

        # Sanity check: response should look like markdown, not an error
        if len(response) < 200 or "# ECHO" not in response:
            logger.warning(
                "echo.md review: unexpected LLM response (len=%d), skipping write",
                len(response),
            )
            return False

        self.write(response)
        logger.info(
            "echo.md updated (valence=%+.2f arousal=%.2f dominant=%s)",
            valence, arousal, dominant_drive,
        )
        return True
