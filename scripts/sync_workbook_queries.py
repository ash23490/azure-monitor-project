#!/usr/bin/env python3
"""Update embedded cost queries in an existing Azure Monitor workbook.

Run from repo root:
    python scripts/sync_workbook_queries.py --apply
Without --apply this prints the affected workbook tiles and changes nothing.
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERY_FILE = ROOT / "kusto-queries" / "cost-anomaly-detection.kql"
WORKBOOK = ROOT / "dashboards" / "workbook.json"
TITLES = {"Cost Anomalies Detected": 2,
          "30 Day Spend Trend": 3,
          "Top Spending Resources": 4}


def queries_by_number(text: str) -> dict[int, str]:
    pattern = r"(?m)^// QUERY (\d+):[^\n]*\n"
    matches = list(re.finditer(pattern, text))
    result = {}
    for i, match in enumerate(matches):
        ending = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[match.end():ending]
        # Trailing separator belongs to the next query, remove it.
        block = re.sub(r"(?:\n// ={10,}[ \t]*)+\s*$", "", block)
        result[int(match.group(1))] = block.strip() + "\n"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write updated workbook JSON")
    args = parser.parse_args()
    if not QUERY_FILE.exists() or not WORKBOOK.exists():
        parser.error("Run inside a full repo clone containing queries and the workbook.")
    kql = queries_by_number(QUERY_FILE.read_text(encoding="utf-8"))
    workbook = json.loads(WORKBOOK.read_text(encoding="utf-8"))
    found = set()
    for item in workbook.get("items", []):
        content = item.get("content", {})
        title = content.get("title")
        if title not in TITLES:
            continue
        query_id = TITLES[title]
        content["query"] = kql[query_id]
        if query_id == 3:
            chart = content.get("chartSettings")
            if isinstance(chart, dict):
                chart["xAxis"] = "Day"
        found.add(title)
    if found != set(TITLES):
        parser.error(f"Workbook is missing expected tiles: {set(TITLES) - found}")
    for title in sorted(found):
        print(f"Will refresh {title!r} (Query {TITLES[title]})")
    if args.apply:
        WORKBOOK.write_text(json.dumps(workbook, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Updated {WORKBOOK}")
    else:
        print("Dry run. Add --apply to save changes.")


if __name__ == "__main__":
    main()
