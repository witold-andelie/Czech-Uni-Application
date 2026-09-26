"""Title-matching helpers for live per-candidate source verification.

Pure, offline-safe logic shared by the CLI verifier and its unit tests:
normalisation, PDF text extraction and the trilingual title matching rules.
No network access happens in this module.

Matching boundaries (kept deliberately conservative):
- A contiguous normalised title hit is the strongest evidence.
- Tolerant passes collapse hyphen/dash spacing and slash spacing, because
  official pages render "pracovnice/ Akademický" for a title spelled
  "pracovnice/Akademický".
- Czech dual-gender spellings ("ODBORNÝ/NÁ PRACOVNÍK/CE", "Odborný/asistentka")
  collapse to the masculine stem on both sides, so a reviewed title spelled
  "Odborný pracovník" still matches the page's dual-gender form.
- Gender markers appended to a title ("M/Ž", "(m/f)") are boilerplate that pages
  place, inflect or omit; they are stripped from the needle only, never from
  the page text.
- A distinctive 40+ character substring proves the announcement text is really
  on the page without over-matching short fragments.
- Titles often append an employer/department clause ("... (PRF JU)",
  "Department: ...") that the page may not render; a stable core block is
  accepted only when the block itself is at least 12 characters.
- A non-match is never rewritten into a pass; the caller records it as-is.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from typing import Any

LOCALES = ("zh-CN", "en", "cs")
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")
SLASH_SPACING = re.compile(r"\s*/\s*")
# Dual-gender infix: "Odborný/ná", "pracovník/ce", "m/ž". Only short suffixes
# collapse, so full alternatives ("pracovník/pracovnice") stay intact.
GENDER_SLASH = re.compile(r"([^\s/]{2,})/[^\s/]{1,3}(?=[\s,.;:)\-]|$)")
# Title-level gender marker: "M/Ž", "(m/f)", "MŽ".
GENDER_MARKER = re.compile(r"\(?\b(?:m/ž|mž|m/f|f/m|ž/m)\b\)?", re.I)
# Block separators inside a title: semicolons, brackets, pipes and spaced
# slash-separated alternatives ("A / B"). A bare "/" stays inside a block
# because "m/ž" and "pracovnice/Akademický" are single tokens.
BLOCK_SPLIT = re.compile(r"\s*(?:;|\(|\)|\||\s/\s)\s*")
DEPARTMENT_CLAUSE = re.compile(r"\s*(?:department:|for the department)\s+", re.I)
MIN_NEEDLE_CHARS = 8
MIN_BLOCK_CHARS = 12
MIN_SUBSTRING_CHARS = 40


def norm(text: Any) -> str:
    """Normalise page or title text for matching (case, dashes, spacing, NFC)."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFC", text)
    text = TAG.sub(" ", text)
    text = (
        text.replace(" ", " ")
        .replace("‑", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("／", "/")
        .replace("（", "(")
        .replace("）", ")")
    )
    text = html.unescape(text)
    return WS.sub(" ", text).strip().lower()


def norm_title(value: Any) -> str:
    return norm(value).replace("“", '"').replace("”", '"').replace("'", "'")


def strip_gender_marker(needle: str) -> str:
    """Drop title-level gender markers ("M/Ž", "(m/f)") from a title needle."""
    if not needle:
        return ""
    return WS.sub(" ", GENDER_MARKER.sub(" ", needle)).strip()


def _gender_collapse(text: str) -> str:
    """Collapse dual-gender infixes: "Odborný/ná pracovník/ce" -> "Odborný pracovník"."""
    return GENDER_SLASH.sub(r"\1", text) if text else text


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def extract_pdf_text(payload: bytes) -> str:
    """Extract PDF text with pypdf, falling back to PyMuPDF for scanned-flavour files."""
    text_parts: list[str] = []
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(payload))
        for page in reader.pages[:40]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
    except Exception as exc:  # pragma: no cover - pypdf flavor drift
        text_parts.append(f"__pypdf error: {exc}")
    if not "".join(text_parts).strip():
        try:
            import fitz  # type: ignore

            with fitz.open(stream=payload, filetype="pdf") as doc:
                for page in doc[:40]:
                    text_parts.append(page.get_text() or "")
        except Exception as exc:  # pragma: no cover - fitz flavor drift
            text_parts.append(f"__pymupdf error: {exc}")
    return "\n".join(text_parts)


def _hay_variants(text: str) -> set[str]:
    """Tolerant renderings of the same page text."""
    variants = {text}
    variants.add(WS.sub(" ", text.replace("-", " ")).strip())
    variants.add(text.replace(" ", ""))
    variants.add(SLASH_SPACING.sub("/", text))
    variants.add(SLASH_SPACING.sub("/", text.replace(" ", "")))
    collapsed = _gender_collapse(text)
    if collapsed != text:
        variants.add(collapsed)
        variants.add(_gender_collapse(SLASH_SPACING.sub("/", text)))
        variants.add(_gender_collapse(text.replace(" ", "")))
    return {variant for variant in variants if variant}


def _needle_variants(needle: str) -> list[str]:
    """Needle renderings tried in order, most faithful first."""
    variants: list[str] = []
    for base in (needle, SLASH_SPACING.sub("/", needle)):
        for candidate in (base, _gender_collapse(base)):
            if candidate and candidate not in variants:
                variants.append(candidate)
    return variants


def _title_blocks(needle: str) -> list[str]:
    """Split a title at natural separators into stable blocks.

    Many official titles append a department/employer clause (for example
    "DevOps & Software Engineer Department: Department of Cybernetics" or
    "Odborný asistent ... (M/Ž) (PRF JU)"). The page may render only the core
    phrase, so matching a distinctive block of the title is honest evidence the
    announcement is present without requiring the appended clause.
    """
    piece_text = DEPARTMENT_CLAUSE.sub(" | ", needle)
    if " | " in piece_text:
        pieces = piece_text.split(" | ")
    else:
        pieces = BLOCK_SPLIT.split(needle)
    return [p.strip() for p in pieces if len(p.strip()) >= MIN_BLOCK_CHARS]


def _match_variant(hay: str, needle: str) -> tuple[str, int] | None:
    """Return (matched text, index in one haystack variant) or None when absent."""
    if not needle or not hay:
        return None
    variants = _hay_variants(hay)
    # Strongest evidence: the whole title appears verbatim (after normalisation).
    for candidate in _needle_variants(needle):
        hits = [h.find(candidate) for h in variants if candidate in h]
        hits = [i for i in hits if i >= 0]
        if hits:
            return candidate, min(hits)
    # Transcribed titles may interpose words ("in the area of ..."). Requiring a
    # distinctive 40+ char substring proves the announcement text is really on
    # the page without over-matching short fragments.
    for candidate in _needle_variants(needle):
        words = candidate.split(" ")
        for lo in range(len(words)):
            for hi in range(len(words), lo, -1):
                sub = " ".join(words[lo:hi])
                if not (MIN_SUBSTRING_CHARS <= len(sub) <= len(candidate)):
                    continue
                hits = [h.find(sub) for h in variants if sub in h]
                hits = [i for i in hits if i >= 0]
                if hits:
                    return sub, min(hits)
    # Core phrase blocks ("DevOps & Software Engineer") may render without the
    # appended department clause; a stable block on the page is accepted.
    for block in _title_blocks(_gender_collapse(SLASH_SPACING.sub("/", needle))):
        hits = [h.find(block) for h in variants if block in h]
        hits = [i for i in hits if i >= 0]
        if hits:
            return block, min(hits)
    return None


def _find_needle(hay: str, needle: str) -> bool:
    return _match_variant(hay, needle) is not None


def _context_snippet(base: str, matched: str) -> str:
    """Page context around a match, quoted from the normalised page text.

    A match may be found in a collapsed variant ("odborný pracovník" for a page
    spelling "odborný/ná pracovník/ce"), so the snippet is located in the page
    text itself: the longest word run that still appears there, falling back to
    the first word. Evidence therefore quotes the page, not the variant.
    """
    words = [word for word in matched.split(" ") if word]
    if not base or not words:
        return matched[:200]
    for start in range(len(words)):
        run = words[start:]
        pattern = r"\s+".join(re.escape(word) for word in run)
        found = re.search(pattern, base)
        if found:
            return base[max(0, found.start() - 60):found.start() + len(matched) + 60]
    found = re.search(re.escape(words[0]), base)
    if found:
        return base[max(0, found.start() - 60):found.start() + len(matched) + 60]
    return matched[:200]


def title_matches(body_text: str, titles: list[dict[str, Any]]) -> dict[str, Any]:
    """Check whether at least one trilingual title appears in the body text."""
    hay = norm(body_text)
    candidates: list[tuple[str, str, str]] = []
    for item in titles:
        nt = norm_title(item.get("title"))
        if len(nt) < MIN_NEEDLE_CHARS:
            continue
        # Gender markers are page boilerplate; drop them from the needle so a
        # page that omits or relocates "M/Ž" still counts as a match. The page
        # text itself is never rewritten.
        needle = strip_gender_marker(nt)
        if len(needle) < MIN_NEEDLE_CHARS:
            needle = nt
        candidates.append((needle, item.get("title"), item.get("locale")))
    candidates.sort(key=lambda item: -len(item[0]))
    for needle, original, locale in candidates:
        found = _match_variant(hay, needle)
        if found is None:
            continue
        matched_text, _index = found
        return {
            "matched": True,
            "matchedLocale": locale,
            "matchedNeedleSnippet": original[:120],
            "contextSnippet": _context_snippet(hay, matched_text)[:200],
        }
    return {"matched": False}
