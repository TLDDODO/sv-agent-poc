"""Export the FastAPI schema to docs/openapi.json (import it into Dify as a Custom Tool).

    python scripts/export_openapi.py            # write docs/openapi.json
    python scripts/export_openapi.py --check    # exit 1 if the file is out of date
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from api.main import app  # noqa: E402

OUT = ROOT / "docs" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = render()
    if args.check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("docs/openapi.json is up to date" if ok else "docs/openapi.json is OUT OF DATE")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
