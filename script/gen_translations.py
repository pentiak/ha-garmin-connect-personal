"""Write translations/en.json from strings.json.

Core resolves `[%key:...%]` references at build time. A custom integration is loaded
from translations/en.json as is, so the references must be resolved here. Common
strings come from the installed `homeassistant` package.

Run after every change to strings.json:
    .venv/bin/python -I script/gen_translations.py
"""

import json
from pathlib import Path
import re
from typing import Any

import homeassistant

DOMAIN = "garmin_connect_personal"
INTEGRATION = Path(__file__).parent.parent / "custom_components" / DOMAIN
REFERENCE = re.compile(r"\[%key:([a-z0-9_:]+)%\]")


def main() -> None:
    """Write `translations/en.json` with every reference resolved."""
    strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
    common = json.loads(
        (Path(homeassistant.__file__).parent / "strings.json").read_text(
            encoding="utf-8"
        )
    )
    roots = {"common": common["common"], "component": {DOMAIN: strings}}

    def lookup(path: str) -> str:
        node: Any = roots
        for part in path.split("::"):
            node = node[part]
        if not isinstance(node, str):
            raise SystemExit(f"{path} is not a string")
        return resolve(node)

    def resolve(value: str) -> str:
        return REFERENCE.sub(lambda match: lookup(match.group(1)), value)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: walk(value) for key, value in node.items()}
        return resolve(node) if isinstance(node, str) else node

    target = INTEGRATION / "translations" / "en.json"
    target.write_text(json.dumps(walk(strings), indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {target}")


if __name__ == "__main__":
    main()
