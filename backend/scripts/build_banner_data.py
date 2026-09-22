"""Fetches banner phase history (start/end dates + featured 5-star slugs) from
paimon.moe's GitHub source (src/data/banners.js, src/data/bannersDual.js) and
builds a static per-gacha_type phase list, for resolving won_fiftyfifty at
read-time (see db.py resolve_won_fiftyfifty). No runtime network fetch - this
script is run manually and its output is checked in.

Usage: venv/Scripts/python.exe scripts/build_banner_data.py
"""
import json
import re
import urllib.request
from pathlib import Path

OUT_PATH = Path(__file__).parent.parent / "data" / "banner_data.json"

BANNERS_URL = "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/data/banners.js"
DUAL_URL = "https://raw.githubusercontent.com/MadeBaruna/paimon-moe/main/src/data/bannersDual.js"

# banners.js section name -> this app's gacha_type. beginners/standard have no
# rate-up concept and are intentionally omitted (won_fiftyfifty is always
# null for gacha_type 100/200, see db.py).
SECTION_TO_GACHA_TYPE = {
    "characters": "301",
    "weapons": "302",
    "chronicled": "500",
}

# Matches one phase object's body, anchored at line-start so consecutive
# blocks (no blank line between a "}," and the next "{") don't share a
# newline character - a naive "\n    {...\n    },\n" pattern silently
# consumes the boundary newline and skips every other block in an array of
# back-to-back objects (caught while parsing bannersDual.js, where each
# window is exactly 2 adjacent blocks).
BLOCK_RE = re.compile(r"^    \{\n(.*?)\n^    \},?$", re.DOTALL | re.MULTILINE)
START_RE = re.compile(r"start:\s*'([^']+)'")
END_RE = re.compile(r"end:\s*'([^']+)'")
FEATURED_RE = re.compile(r"featured:\s*\[(.*?)\]", re.DOTALL)


def _parse_blocks(text: str) -> list[dict]:
    phases = []
    for block in BLOCK_RE.findall(text):
        start_m, end_m, featured_m = START_RE.search(block), END_RE.search(block), FEATURED_RE.search(block)
        if not (start_m and end_m and featured_m):
            continue
        featured = re.findall(r"'([^']+)'", featured_m.group(1))
        phases.append({"start": start_m.group(1), "end": end_m.group(1), "featured": featured})
    return phases


def _extract_section(text: str, key: str) -> str:
    """Slice out a top-level `  <key>: [ ... ]` section's body from banners.js.
    Section boundaries are 2-space indented; phase objects inside are 4-space
    indented, so a 2-space-indented closing `],` can't be mistaken for one."""
    start_m = re.search(rf"^  {key}: \[\n", text, re.MULTILINE)
    if not start_m:
        raise ValueError(f"section {key!r} not found")
    end_m = re.search(r"^  \],?$", text[start_m.end():], re.MULTILINE)
    if not end_m:
        raise ValueError(f"closing bracket for section {key!r} not found")
    return text[start_m.end():start_m.end() + end_m.start()]


def build_single_phases(banners_text: str) -> dict:
    return {
        gacha_type: _parse_blocks(_extract_section(banners_text, section))
        for section, gacha_type in SECTION_TO_GACHA_TYPE.items()
    }


def build_dual_windows(dual_text: str) -> list[dict]:
    """bannersDual.js is a dict of {window_name: [phase_a, phase_b]}, both
    phases sharing the same start/end but different featured characters
    (HoYoverse's dual concurrent character-banner mechanic). This app's
    historical import coerces both banners' pulls onto gacha_type 301 without
    keeping track of which one a pull belonged to (see the code "400" -> "301"
    coercion comment in scripts/import_paimon_backup.py) - so here we union
    both phases' featured lists into one window, and a pull's item counts as
    a win if it matches EITHER concurrent banner's rate-up. This can't
    perfectly attribute which specific banner a pull was on, but correctly
    answers "did the rate-up land", which is what won_fiftyfifty is for."""
    blocks = _parse_blocks(dual_text)
    if len(blocks) % 2 != 0:
        raise ValueError(f"expected an even number of dual-banner phase blocks, got {len(blocks)}")
    windows = []
    for i in range(0, len(blocks), 2):
        a, b = blocks[i], blocks[i + 1]
        if (a["start"], a["end"]) != (b["start"], b["end"]):
            raise ValueError(f"dual-banner pair date mismatch: {a} vs {b}")
        windows.append({
            "start": a["start"],
            "end": a["end"],
            "featured": sorted(set(a["featured"]) | set(b["featured"])),
        })
    return windows


def main():
    banners_text = urllib.request.urlopen(BANNERS_URL).read().decode("utf-8")
    dual_text = urllib.request.urlopen(DUAL_URL).read().decode("utf-8")

    data = build_single_phases(banners_text)
    data["301_dual"] = build_dual_windows(dual_text)

    for key, phases in data.items():
        print(f"{key}: {len(phases)} phases")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"Wrote banner data to {OUT_PATH}")


if __name__ == "__main__":
    main()
