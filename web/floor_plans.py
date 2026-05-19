"""SNEC NECC per-hall floor plan images (served at /floor_plans/)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOOR_PLANS_DIR = ROOT / "floor_plans"

# Hall code in DB / user text → image filename on disk
HALL_FILE_ALIASES: dict[str, str] = {
    "GC": "GC_central_plaza.jpg",
    "OVERVIEW": "00_overview_NECC_clover.jpg",
    "NECC": "00_overview_NECC_clover.jpg",
}

NAV_MAP_KEYWORDS = re.compile(
    r"floor\s*plan|booth\s*map|展位图|平面图|layout|wayfind|navigate|"
    r"direction|walking\s+route|how\s+to\s+get|which\s+entrance|"
    r"venue\s+map|clover|leaf\s+[abcd]|metro.*hall|展馆|怎么走|地图|"
    r"where\s+is\s+hall|hall\s+map|show\s+me\s+the\s+map",
    re.I,
)


def _normalize_hall(hall: str) -> str:
    return (hall or "").strip().upper().replace(" ", "")


def _filename_for_hall(hall: str) -> str | None:
    key = _normalize_hall(hall)
    if not key:
        return None
    if key in HALL_FILE_ALIASES:
        fn = HALL_FILE_ALIASES[key]
    else:
        fn = f"{key}.jpg"
    return fn if (FLOOR_PLANS_DIR / fn).is_file() else None


def list_floor_plan_catalog() -> list[dict[str, str]]:
    """All image files under floor_plans/ → {hall, label, url, filename}."""
    if not FLOOR_PLANS_DIR.is_dir():
        return []

    items: list[dict[str, str]] = []
    for path in sorted(FLOOR_PLANS_DIR.iterdir()):
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        name = path.name
        url = f"/floor_plans/{name}"
        if name.startswith("00_overview"):
            hall, label = "OVERVIEW", "NECC four-leaf clover overview"
        elif name.startswith("GC"):
            hall, label = "GC", "Central plaza (GC) between halls"
        else:
            hall = path.stem.upper()
            label = f"Hall {hall} booth layout"
        items.append({"hall": hall, "label": label, "url": url, "filename": name})
    return items


def hall_url(hall: str) -> str | None:
    fn = _filename_for_hall(hall)
    if not fn or not (FLOOR_PLANS_DIR / fn).is_file():
        return None
    return f"/floor_plans/{fn}"


def wants_floor_plan_context(message: str) -> bool:
    return bool(NAV_MAP_KEYWORDS.search(message or ""))


def halls_for_floor_plans(
    message: str,
    anchor_halls: list[str],
    explicit_halls: list[str],
) -> list[str]:
    """Halls whose maps should be highlighted for this question."""
    halls: set[str] = set()
    for h in explicit_halls + anchor_halls:
        key = _normalize_hall(h)
        if key:
            halls.add(key)

    if wants_floor_plan_context(message) and not halls:
        halls.add("OVERVIEW")

    if re.search(r"\boverview\b|whole\s+venue|nec+c|四叶草|clover", message or "", re.I):
        halls.add("OVERVIEW")

    if re.search(r"\bcentral\s+plaza\b|\bGC\b", message or "", re.I):
        halls.add("GC")

    # Stable order: overview first, then numeric halls
    order = ["OVERVIEW", "GC"]

    def sort_key(h: str) -> tuple:
        if h in order:
            return (0, order.index(h))
        return (1, h)

    return sorted(halls, key=sort_key)


def format_floor_plans_for_prompt(
    message: str,
    anchor_halls: list[str],
    explicit_halls: list[str],
) -> str:
    catalog = list_floor_plan_catalog()
    if not catalog:
        return "(Floor plan images not found in floor_plans/ folder.)"

    relevant = halls_for_floor_plans(message, anchor_halls, explicit_halls)
    catalog_lines = [f"- **{c['hall']}** — {c['label']}: `{c['url']}`" for c in catalog]

    share_lines: list[str] = []
    for hall in relevant:
        url = hall_url(hall)
        if not url:
            continue
        label = next((c["label"] for c in catalog if c["hall"] == hall), f"Hall {hall}")
        share_lines.append(f"- **{label}** — use in answer: `![{label}]({url})`")

    if wants_floor_plan_context(message) and "OVERVIEW" not in relevant:
        url = hall_url("OVERVIEW")
        if url:
            share_lines.insert(
                0,
                f"- **NECC overview** — use for venue-wide directions: `![NECC overview]({url})`",
            )

    share_block = (
        "\n".join(share_lines)
        if share_lines
        else "- (No specific hall resolved — pick maps from the catalog that match the user's halls.)"
    )

    return f"""
=== FLOOR PLAN CATALOG (official NECC hall maps — relative image URLs) ===
When helping with **directions, wayfinding, hall layout, or booth map** questions, **show the relevant map(s)** using Markdown images, e.g. `![Hall 8.2H](/floor_plans/8.2H.jpg)`. User can click to view full size.

{chr(10).join(catalog_lines)}

=== FLOOR PLANS FOR THIS QUESTION (prefer these in your reply) ===
{share_block}
""".strip()
