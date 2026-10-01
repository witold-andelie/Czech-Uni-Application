from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_no_control_characters_in_ingestion_source() -> None:
    """A backspace written where a regex meant \b silently breaks the pattern.

    Three edits on 2026-10-01 left a literal U+0008 in regexes, so "\bbenefit"
    and the advantage heading never matched and nothing failed.
    """
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if any(ord(char) < 32 and char not in "\t" for char in line):
                offenders.append(f"{path.relative_to(SRC)}:{number}")
    assert offenders == []
