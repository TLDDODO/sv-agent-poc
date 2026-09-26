"""Load agent role definitions ("skills") from the skills/ folder.

Each skill is a markdown file documenting a role; the actual prompt is the text
after a `===PROMPT===` marker. If the file is missing, the caller's inline default
is used, so the code never breaks if skills/ is absent.
"""
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def load_skill(name: str, default: str = "") -> str:
    try:
        text = (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
    except Exception:
        return default
    if "===PROMPT===" in text:
        return text.split("===PROMPT===", 1)[1].strip()
    return text.strip() or default
