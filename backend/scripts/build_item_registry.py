"""Fetches the full character/weapon roster from paimon.moe's GitHub source
(src/data/characters.js, src/data/weaponList.js) and builds a static
name -> {slug, rarity} lookup, keyed separately per item_type, for resolving
icon URLs at read-time (see db.py resolve_icon_url). No runtime network
fetch - this script is run manually and its output is checked in.

Usage: venv/Scripts/python.exe scripts/build_item_registry.py
"""
import json
import re
import urllib.request
from pathlib import Path

OUT_PATH = Path(__file__).parent.parent / "data" / "paimon_item_data.json"

SOURCES = {
    "Character": "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/data/characters.js",
    "Weapon": "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/data/weaponList.js",
}

# Matches a top-level "  <slug>: {" or "  '<slug>': {" entry line (2-space
# indent only - nested object/array keys inside ascension/stats etc. are
# indented further). Slugs with a hyphen (e.g. winged-spear) are quoted since
# they aren't valid bare JS identifiers, so both forms need matching.
TOP_LEVEL_KEY = re.compile(r"^  '?([a-zA-Z0-9_-]+)'?: \{$", re.MULTILINE)
NAME_RE = re.compile(r"""name:\s*['"](.+?)['"],""")
RARITY_RE = re.compile(r"rarity:\s*(\d+),")


def parse_slugs(js_text: str) -> dict:
    """slug -> {name, rarity}, parsed from a paimon.moe data/*.js module."""
    matches = list(TOP_LEVEL_KEY.finditer(js_text))
    out = {}
    for i, m in enumerate(matches):
        slug = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(js_text)
        block = js_text[start:end]
        name_m = NAME_RE.search(block)
        rarity_m = RARITY_RE.search(block)
        if not name_m or not rarity_m:
            continue  # not an item entry (e.g. a helper object) - skip
        out[slug] = {"name": name_m.group(1), "rarity": int(rarity_m.group(1))}
    return out


def main():
    registry = {}
    for item_type, url in SOURCES.items():
        text = urllib.request.urlopen(url).read().decode("utf-8")
        slugs = parse_slugs(text)
        for slug, info in slugs.items():
            registry[slug] = {"name": info["name"], "rarity": info["rarity"], "type": item_type}
        print(f"{item_type}: {len(slugs)} entries")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote {len(registry)} total entries to {OUT_PATH}")


if __name__ == "__main__":
    main()
