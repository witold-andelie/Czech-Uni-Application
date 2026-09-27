"""Regression floor for the school-owned programme page link index.

The link index (``data/sources/admissions/programme-links.json``) is a
coverage artefact, not a target: a school whose site cannot be read keeps its
rows unresolved and the card shows the university site with that label
(docs/ACCEPTANCE.md A100). What must never happen silently is a *drop* - a
school that had 107 programme pages yesterday showing none today because a
crawler change, a renamed catalogue, or a domain edit quietly lost them.

So this check compares the current index against a committed floor and fails
when any school, or the total, falls below it. The floor is a deliberate
commit: when coverage genuinely improves the floor is raised, and when the
register itself shrinks (a programme removed, so both the denominator and the
resolved count fall) the floor is revised with the reason recorded here.

It never claims that a programme has an open window, a fee, or a place; it
only guards the link index against silent regression.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LINKS = ROOT / "data" / "sources" / "admissions" / "programme-links.json"
DEFAULT_FLOOR = ROOT / "data" / "sources" / "admissions" / "programme-link-coverage-floor.json"
DEFAULT_INVENTORY = ROOT / "data" / "sources" / "browse" / "nine-hei-inventory.json"


def _resolved(payload: dict) -> tuple[dict[str, int], dict[str, int]]:
    by_school: dict[str, int] = {}
    offerings: dict[str, int] = {}
    for row in payload.get("coverage", {}).get("schools") or []:
        institution_id = str(row.get("institutionId") or "")
        if not institution_id:
            continue
        by_school[institution_id] = int(row.get("resolved") or 0)
        offerings[institution_id] = int(row.get("offerings") or 0)
    totals = payload.get("coverage", {}).get("totals") or {}
    return by_school, {
        "__total__": int(totals.get("resolved") or 0),
        "__offerings__": int(totals.get("offerings") or 0),
        **offerings,
    }


def _school_domains() -> dict[str, set[str]]:
    """The registrable domains each school owns, straight from the resolver."""
    from resolve_programme_links import allowed_domains_by_institution

    return {str(key): set(value) for key, value in allowed_domains_by_institution().items()}


def _proven_ids(payload: dict, domains: dict[str, set[str]]) -> set[str]:
    """The links the index proves and the publication gate is meant to keep."""
    from resolve_programme_links import registrable_host

    proven: set[str] = set()
    for ident, entry in (payload.get("links") or {}).items():
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "")
        if not url.startswith("https://"):
            continue
        if registrable_host(url) not in domains.get(str(entry.get("institutionId") or ""), set()):
            continue
        proven.add(str(ident))
    return proven


def _inventory_drops(payload: dict, inventory_path: Path, domains: dict[str, set[str]]) -> list[str]:
    """Links the index proves that the built inventory does not publish.

    Only compared when the inventory was built from this very index: a build
    made before the latest resolver run is simply older, not wrong. What it
    catches is a gate change that drops a school's own page for a reason no one
    said out loud.
    """
    if not inventory_path.is_file():
        return []
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    published_at = str(inventory.get("programmeLinkGeneratedAt") or "")
    if not published_at or published_at != str(payload.get("generatedAt") or ""):
        return []
    proven = _proven_ids(payload, domains)
    published = {str(ident) for ident in (inventory.get("programmeLinks") or {})}
    missing = sorted(proven - published)
    if not missing:
        return []
    label = str(inventory_path.relative_to(ROOT)) if inventory_path.is_relative_to(ROOT) else str(inventory_path)
    return [
        "PROGRAMME_LINK_DROPPED_IN_PUBLICATION: "
        f"{len(missing)} proven school-owned programme page(s) are missing from "
        f"{label}: {', '.join(missing[:10])}"
        + (" ..." if len(missing) > 10 else "")
    ]


def check(
    links_path: Path = DEFAULT_LINKS,
    floor_path: Path = DEFAULT_FLOOR,
    inventory_path: Path | None = None,
    domains: dict[str, set[str]] | None = None,
) -> tuple[bool, list[str]]:
    if not floor_path.exists():
        return True, [f"no floor committed at {floor_path.relative_to(ROOT)}; nothing to compare against"]
    floor = json.loads(floor_path.read_text(encoding="utf-8"))
    if not links_path.exists():
        # An absent index is the honest state when no source could be read.
        return True, ["the link index does not exist yet; no regression to report"]
    payload = json.loads(links_path.read_text(encoding="utf-8"))
    current, denominators = _resolved(payload)
    floor_by_school = {
        str(key): int(value) for key, value in (floor.get("resolvedBySchool") or {}).items()
    }
    errors: list[str] = []
    for institution_id, expected in sorted(floor_by_school.items()):
        found = current.get(institution_id, 0)
        if found < expected:
            errors.append(
                "PROGRAMME_LINK_REGRESSION: "
                f"{institution_id} resolved {found} programme page(s), the committed floor is {expected}"
            )
    total = denominators.get("__total__", 0)
    floor_total = int(floor.get("resolvedTotal") or 0)
    if total < floor_total:
        errors.append(
            "PROGRAMME_LINK_REGRESSION: "
            f"total resolved {total} programme page(s), the committed floor is {floor_total}"
        )
    offerings = denominators.get("__offerings__", 0)
    if not errors:
        if inventory_path is None and domains is None:
            # The default comparison, against the inventory in the tree. A test
            # that states its own domains keeps its own paths.
            inventory_path = DEFAULT_INVENTORY
        if inventory_path is not None:
            allowed = domains if domains is not None else _school_domains()
            errors.extend(_inventory_drops(payload, inventory_path, allowed))
    if not errors:
        return True, [
            f"programme page link index: {total} of {offerings} register row(s) resolved "
            f"(floor {floor_total}); unresolved rows show the university site"
        ]
    return False, errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the programme page link index against its floor")
    parser.add_argument("--links", type=Path, default=DEFAULT_LINKS)
    parser.add_argument("--floor", type=Path, default=DEFAULT_FLOOR)
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY,
        help="built inventory to compare the proven links against; empty path skips that check",
    )
    parser.add_argument("--skip-inventory", action="store_true", help="do not compare the built inventory")
    args = parser.parse_args()
    inventory = None if args.skip_inventory else args.inventory
    ok, messages = check(args.links, args.floor, inventory_path=inventory)
    for message in messages:
        print(message, flush=True)
    if not ok:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
