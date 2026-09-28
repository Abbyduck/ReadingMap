"""Report every raw category annotation found in source reading-list JSON files."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "source_data" / "reading_lists"
OUTPUT_PATH = ROOT / "docs" / "category_raw_values.md"


def category_values(value):
    if isinstance(value, list):
        for item in value:
            yield from category_values(item)
    elif isinstance(value, dict):
        raw = value.get("value_text")
        if value.get("annotation_type") == "category" and isinstance(raw, str) and raw.strip():
            yield raw.strip()
        for item in value.values():
            yield from category_values(item)


def main() -> None:
    totals: Counter[str] = Counter()
    sources: dict[str, Counter[str]] = defaultdict(Counter)
    files = sorted(SOURCE_ROOT.glob("*.json"), key=lambda path: path.name.casefold())

    for path in files:
        document = json.loads(path.read_text(encoding="utf-8"))
        list_title = str((document.get("list") or {}).get("title") or path.stem)
        source_label = f"{list_title} (`{path.name}`)"
        for raw_category in category_values(document):
            totals[raw_category] += 1
            sources[raw_category][source_label] += 1

    lines = [
        "# 来源书单 raw category 真实统计",
        "",
        "> 此文件由 `scripts/report_raw_categories.py` 从 `source_data/reading_lists/*.json` 生成。",
        "> 仅统计 `annotation_type = category` 且 `value_text` 非空的真实记录；未进行 KEEP / MERGE / DROP 判断。",
        "",
        f"- 来源 JSON：{len(files)} 份",
        f"- category 出现次数：{sum(totals.values())} 次",
        f"- 不同 raw category：{len(totals)} 种",
        "",
        "| raw category | 次数 | 来源书单 / 文件（该来源内次数） |",
        "|---|---:|---|",
    ]
    ordered = sorted(totals, key=lambda value: (-totals[value], value.casefold()))
    for raw_category in ordered:
        source_text = "<br>".join(
            f"{label} × {count}"
            for label, count in sorted(sources[raw_category].items(), key=lambda row: (-row[1], row[0].casefold()))
        )
        escaped_value = raw_category.replace("|", "\\|")
        lines.append(f"| {escaped_value} | {totals[raw_category]} | {source_text} |")

    lines.extend([
        "",
        "## 人工清洗状态",
        "",
        "本报告故意不自动填写 KEEP / MERGE / DROP。后续人工清洗应以本表中的 66 个真实值为输入，",
        "需要临时映射时写入 `scripts/category_mapping.json`，不要建立正式 alias 表。",
        "",
    ])
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} ({sum(totals.values())} rows, {len(totals)} unique values)")


if __name__ == "__main__":
    main()
