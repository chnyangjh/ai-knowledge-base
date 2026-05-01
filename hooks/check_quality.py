#!/usr/bin/env python3
"""Quality scoring engine for knowledge base articles.

Performs 5-dimension quality scoring (weighted total 100 pts):
  1. Summary quality (25 pts) -- length + tech keyword bonus
  2. Technical depth (25 pts) -- based on score field (1-10 -> 0-25)
  3. Format compliance (20 pts) -- id, title, source_url, status, timestamp
  4. Tag precision (15 pts) -- count + standard list validation
  5. Buzzword detection (15 pts) -- penalty for buzzwords

Usage:
    python hooks/check_quality.py <json_file>
    python hooks/check_quality.py "knowledge/articles/**/*.json"
    python hooks/check_quality.py *.json

Exit code: 1 if any article scores below C grade (< 60), 0 otherwise.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ============================================================================
# Constants
# ============================================================================

_CHINESE_BUZZWORDS: frozenset[str] = frozenset(
    {
        "赋能",
        "抓手",
        "闭环",
        "打通",
        "全链路",
        "底层逻辑",
        "颗粒度",
        "对齐",
        "拉通",
        "沉淀",
        "强大的",
        "革命性的",
    }
)

_ENGLISH_BUZZWORDS: frozenset[str] = frozenset(
    {
        "groundbreaking",
        "revolutionary",
        "game-changing",
        "cutting-edge",
        "best-in-class",
        "world-class",
        "next-generation",
        "synergy",
        "paradigm shift",
        "disruptive",
        "state-of-the-art",
    }
)

_VALID_TAGS: frozenset[str] = frozenset(
    {
        "llm",
        "agent",
        "framework",
        "research",
        "paper",
        "news",
        "tool",
        "library",
        "model",
        "education",
        "tutorial",
        "finance",
        "trading",
        "quantitative",
        "collaboration",
        "automation",
        "voice",
        "synthesis",
        "accessibility",
        "domain",
        "platform",
        "productivity",
        "configuration",
        "autonomous",
        "learning",
        "memory",
        "claude",
        "efficiency",
        "evolution",
        "ai",
        "optimization",
    }
)

_TECH_KEYWORDS: frozenset[str] = frozenset(
    {
        "llm",
        "agent",
        "model",
        "training",
        "inference",
        "neural",
        "transformer",
        "fine-tuning",
        "fine tuning",
        "prompt",
        "embedding",
        "rag",
        "vector",
        "deep learning",
        "machine learning",
        "ai",
        "gpt",
        "bert",
        "diffusion",
        "reinforcement",
        "token",
        "context",
        "attention",
        "chain-of-thought",
        "reasoning",
        "knowledge graph",
        "langgraph",
        "langchain",
        "openai",
        "claude",
        "gemini",
        "llama",
        "mistral",
        "multimodal",
        "nlp",
        "generation",
        "encoder",
        "decoder",
        "autoregressive",
        "zero-shot",
        "few-shot",
        "hallucination",
        "alignment",
        "safety",
        "benchmark",
        "evaluation",
        "mcp",
        "rag",
        "graphrag",
        "workflow",
    }
)

_SUMMARY_FULL_CHARS: int = 50
_SUMMARY_BASE_CHARS: int = 20
_SCORE_DIM_MAX: int = 25
_FORMAT_DIM_MAX: int = 20
_TAGS_DIM_MAX: int = 15
_BUZZ_DIM_MAX: int = 15
_TOTAL_MAX: int = _SCORE_DIM_MAX * 2 + _FORMAT_DIM_MAX + _TAGS_DIM_MAX + _BUZZ_DIM_MAX


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    name: str
    score: float
    max_score: int
    details: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    """Complete quality report for a single article."""

    file_path: Path
    title: str
    total_score: float
    max_total: int
    dimensions: list[DimensionScore]
    grade: str
    issues: list[str] = field(default_factory=list)


# ============================================================================
# Dimension Scoring Functions
# ============================================================================


def _score_summary(data: dict[str, Any]) -> DimensionScore:
    """Score summary quality.

    Rules:
        - >= 50 chars: 20 base pts
        - >= 20 chars: 10 + proportional pts
        - < 20 chars: proportional 0-10 pts
        - Tech keyword bonus: +1 per keyword found (max +5)

    Max score: 25.
    """
    details: list[str] = []
    summary: str = (data.get("summary") or "").strip()

    if not summary:
        return DimensionScore("摘要质量", 0.0, _SCORE_DIM_MAX, ["摘要缺失"])

    length: int = len(summary)

    if length >= _SUMMARY_FULL_CHARS:
        base_score: float = 20.0
        details.append(f"长度 {length} 字 (满分基准)")
    elif length >= _SUMMARY_BASE_CHARS:
        ratio: float = (length - _SUMMARY_BASE_CHARS) / (
            _SUMMARY_FULL_CHARS - _SUMMARY_BASE_CHARS
        )
        base_score = 10.0 + ratio * 10.0
        details.append(f"长度 {length} 字 (基本分)")
    else:
        ratio = length / _SUMMARY_BASE_CHARS
        base_score = ratio * 10.0
        details.append(f"长度 {length} 字 (不足基本分)")

    summary_lower: str = summary.lower()
    kw_hits: list[str] = sorted(
        {kw for kw in _TECH_KEYWORDS if kw in summary_lower}
    )
    kw_count: int = len(kw_hits)

    if kw_count > 0:
        bonus: float = min(kw_count * 1.0, 5.0)
        base_score = min(base_score + bonus, float(_SCORE_DIM_MAX))
        details.append(
            f"技术关键词 {kw_count} 个 (+{bonus:.1f}): {', '.join(kw_hits[:5])}"
            + ("..." if kw_count > 5 else "")
        )
    else:
        details.append("未检测到技术关键词")

    return DimensionScore(
        "摘要质量", round(base_score, 1), _SCORE_DIM_MAX, details
    )


def _score_technical(data: dict[str, Any]) -> DimensionScore:
    """Score technical depth based on the ``score`` field.

    The ``score`` field should be an integer from 1 to 10.
    Mapping: 1 -> 0, 10 -> 25 (linear interpolation).
    Searches both top-level and nested ``metadata`` dict.
    """
    raw_score: Any = data.get("score")
    if raw_score is None:
        metadata = data.get("metadata")
        if isinstance(metadata, dict):
            raw_score = metadata.get("score")

    if raw_score is None:
        return DimensionScore("技术深度", 0.0, _SCORE_DIM_MAX, ["缺少 score 字段"])

    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        return DimensionScore(
            "技术深度",
            0.0,
            _SCORE_DIM_MAX,
            [f"score 类型无效 ({type(raw_score).__name__})"],
        )

    if raw_score < 1 or raw_score > 10:
        return DimensionScore(
            "技术深度",
            0.0,
            _SCORE_DIM_MAX,
            [f"score 超出范围 1-10 (当前: {raw_score})"],
        )

    mapped: float = (raw_score - 1) / 9 * _SCORE_DIM_MAX
    return DimensionScore(
        "技术深度",
        round(mapped, 1),
        _SCORE_DIM_MAX,
        [f"score={raw_score} -> {mapped:.1f}/{_SCORE_DIM_MAX}"],
    )


def _score_format(data: dict[str, Any]) -> DimensionScore:
    """Score format compliance.

    Five required fields, each worth 4 pts:
        id, title, source_url (or ``url``), status, timestamp
    """
    details: list[str] = []
    score: int = 0

    checks: list[tuple[str, bool]] = [
        ("id", bool(data.get("id"))),
        ("title", bool(data.get("title") or data.get("name"))),
        (
            "source_url",
            bool(data.get("source_url") or data.get("url")),
        ),
        ("status", bool(data.get("status"))),
        (
            "timestamp",
            bool(
                data.get("collected_at")
                or data.get("analyzed_at")
                or data.get("published_at")
            ),
        ),
    ]

    for name, passed in checks:
        if passed:
            score += 4
            details.append(f"{name}: OK")
        else:
            details.append(f"{name}: MISSING")

    return DimensionScore("格式规范", float(score), _FORMAT_DIM_MAX, details)


def _score_tags(data: dict[str, Any]) -> DimensionScore:
    """Score tag precision.

    Rules:
        - No tags or not a list: 0
        - 1-3 *all valid* tags: full marks (15)
        - 1-3 valid but mixed with non-standard: 12
        - 4+ tags: 10
        - All invalid: 3
    """
    details: list[str] = []
    tags: Any = data.get("tags") or data.get("suggested_tags") or []

    if not isinstance(tags, list):
        return DimensionScore("标签精度", 0.0, _TAGS_DIM_MAX, ["tags 字段不是列表"])

    if len(tags) == 0:
        return DimensionScore("标签精度", 0.0, _TAGS_DIM_MAX, ["无标签"])

    valid: list[str] = [t for t in tags if t in _VALID_TAGS]
    invalid: list[str] = [t for t in tags if t not in _VALID_TAGS]
    valid_count: int = len(valid)
    invalid_count: int = len(invalid)
    total_count: int = len(tags)

    if valid_count >= 1 and invalid_count == 0 and total_count <= 3:
        score: float = 15.0
        details.append(f"{total_count} 个标签，全部合法")
    elif valid_count >= 1 and total_count <= 3 and invalid_count > 0:
        score = 12.0
        details.append(
            f"{total_count} 个标签，合法 {valid_count} / 非标准 {invalid_count}"
        )
        details.append(f"非标准标签: {', '.join(invalid)}")
    elif valid_count >= 4:
        score = 10.0
        details.append(f"{total_count} 个标签，数量偏多 (建议 1-3)")
        if invalid_count > 0:
            details.append(f"非标准标签: {', '.join(invalid)}")
    elif valid_count >= 1:
        score = 8.0
        details.append(f"{total_count} 个标签，合法 {valid_count} / 非标准 {invalid_count}")
    elif valid_count == 0 and invalid_count > 0:
        score = 3.0
        details.append(f"{total_count} 个标签，全为非标准标签")
        details.append(f"非标准标签: {', '.join(invalid)}")
    else:
        score = 6.0
        details.append(f"{total_count} 个标签，合法 {valid_count}")

    return DimensionScore("标签精度", score, _TAGS_DIM_MAX, details)


def _score_buzzwords(data: dict[str, Any]) -> DimensionScore:
    """Score buzzword detection.

    Scans ``summary`` and ``content`` fields for buzzwords from Chinese
    and English blacklists.  Each hit deducts 3 pts (max deduction 15).
    """
    details: list[str] = []

    text_parts: list[str] = []
    for field_name in ("summary", "content"):
        value: Any = data.get(field_name)
        if isinstance(value, str) and value.strip():
            text_parts.append(value)

    if not text_parts:
        return DimensionScore(
            "空洞词检测", float(_BUZZ_DIM_MAX), _BUZZ_DIM_MAX, ["无可检测文本"]
        )

    combined: str = " ".join(text_parts)

    found_chinese: list[str] = sorted(
        {bw for bw in _CHINESE_BUZZWORDS if bw in combined}
    )
    found_english: list[str] = sorted(
        {
            bw
            for bw in _ENGLISH_BUZZWORDS
            if bw in combined.lower()
        }
    )

    total_found: int = len(found_chinese) + len(found_english)
    penalty: float = min(total_found * 3.0, float(_BUZZ_DIM_MAX))
    score: float = max(float(_BUZZ_DIM_MAX) - penalty, 0.0)

    if found_chinese:
        details.append(f"中文空洞词: {', '.join(found_chinese)}")
    if found_english:
        details.append(f"英文空洞词: {', '.join(found_english)}")
    if not found_chinese and not found_english:
        details.append("未检测到空洞词")

    return DimensionScore(
        "空洞词检测", round(score, 1), _BUZZ_DIM_MAX, details
    )


# ============================================================================
# Scoring Pipeline
# ============================================================================

_DIMENSION_SCORERS: list[tuple[str, int, Any]] = [
    ("摘要质量", _SCORE_DIM_MAX, _score_summary),
    ("技术深度", _SCORE_DIM_MAX, _score_technical),
    ("格式规范", _FORMAT_DIM_MAX, _score_format),
    ("标签精度", _TAGS_DIM_MAX, _score_tags),
    ("空洞词检测", _BUZZ_DIM_MAX, _score_buzzwords),
]


def _compute_grade(total: float) -> str:
    """Map total score to letter grade."""
    if total >= 80:
        return "A"
    if total >= 60:
        return "B"
    return "C"


def _extract_articles(data: Any) -> list[dict[str, Any]]:
    """Extract individual article dicts from parsed JSON.

    Handles three structural forms:
        - Single article dict
        - Flat list of dicts
        - Dict with ``"items"`` key containing a list of dicts
    """
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items: Any = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [data]
    return []


def analyze_file(file_path: Path) -> list[QualityReport]:
    """Analyze all articles in a single JSON file.

    Returns a list of :class:`QualityReport`, one per article found.
    If the file is unreadable or contains no articles, a single error
    report is returned with grade ``C``.
    """
    try:
        raw: str = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            QualityReport(
                file_path=file_path,
                title="<读取错误>",
                total_score=0.0,
                max_total=_TOTAL_MAX,
                dimensions=[],
                grade="C",
                issues=[f"无法读取文件: {exc}"],
            )
        ]

    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [
            QualityReport(
                file_path=file_path,
                title="<JSON 解析错误>",
                total_score=0.0,
                max_total=_TOTAL_MAX,
                dimensions=[],
                grade="C",
                issues=[f"JSON 解析失败: {exc}"],
            )
        ]

    articles: list[dict[str, Any]] = _extract_articles(data)
    if not articles:
        return [
            QualityReport(
                file_path=file_path,
                title="<无内容>",
                total_score=0.0,
                max_total=_TOTAL_MAX,
                dimensions=[],
                grade="C",
                issues=["未找到有效的文章条目"],
            )
        ]

    reports: list[QualityReport] = []
    for idx, article in enumerate(articles):
        dims: list[DimensionScore] = []
        for _name, _max, scorer_fn in _DIMENSION_SCORERS:
            dims.append(scorer_fn(article))

        total: float = sum(d.score for d in dims)
        grade: str = _compute_grade(total)

        title: str = (
            article.get("title")
            or article.get("name")
            or f"条目 #{idx + 1}"
        )

        reports.append(
            QualityReport(
                file_path=file_path,
                title=title,
                total_score=round(total, 1),
                max_total=_TOTAL_MAX,
                dimensions=dims,
                grade=grade,
            )
        )

    return reports


# ============================================================================
# File Discovery
# ============================================================================


def _collect_files(raw_args: list[str]) -> list[Path]:
    """Resolve file paths from CLI arguments, expanding glob patterns."""
    files: list[Path] = []
    seen: set[Path] = set()

    for raw in raw_args:
        path: Path = Path(raw)
        has_glob: bool = any(c in raw for c in ("*", "?", "["))

        if has_glob:
            matches: list[Path] = (
                list(Path.cwd().glob(raw))
                if not path.is_absolute()
                else list(Path().glob(raw))
            )
            for match in sorted(matches):
                if match.is_file() and match.suffix == ".json" and match not in seen:
                    files.append(match)
                    seen.add(match)
        elif path.is_file():
            if path not in seen:
                files.append(path)
                seen.add(path)
        elif path.is_dir():
            for match in sorted(path.glob("**/*.json")):
                if match not in seen:
                    files.append(match)
                    seen.add(match)
        else:
            print(f"Warning: '{raw}' not found, skipping", file=sys.stderr)

    return files


# ============================================================================
# Output Rendering
# ============================================================================


def _bar_chars() -> tuple[str, str]:
    """Return (filled_char, empty_char) safe for current stdout encoding."""
    try:
        stdout_enc: str = sys.stdout.encoding or "ascii"
        "█░".encode(stdout_enc)
        return "█", "░"
    except (UnicodeEncodeError, UnicodeDecodeError):
        return "#", "-"


def _render_bar(score: float, maximum: float, width: int = 20) -> str:
    """Render a horizontal bar proportional to score/maximum."""
    if maximum <= 0:
        return "[--------------------]    0%"
    filled_char, empty_char = _bar_chars()
    filled: int = int(width * score / maximum)
    pct: int = round(score / maximum * 100)
    bar: str = filled_char * filled + empty_char * (width - filled)
    return f"[{bar}] {pct:3d}%"


def _print_report(report: QualityReport, show_file: bool = True) -> None:
    """Pretty-print a single quality report."""
    print()
    if show_file:
        try:
            file_rel: str = str(report.file_path.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            file_rel = str(report.file_path)
        print(f"  File: {file_rel}")
    print(f"  Title: {report.title}")
    print(
        f"  Total: {report.total_score}/{report.max_total}  "
        f"{_render_bar(report.total_score, report.max_total)}  "
        f"Grade: {report.grade}"
    )
    print(f"  {'-' * 54}")

    for dim in report.dimensions:
        print(
            f"  {dim.name:<6s}  {dim.score:>5.1f}/{dim.max_score:<3} "
            f"{_render_bar(dim.score, dim.max_score, 14)}"
        )
        for detail in dim.details:
            print(f"         -> {detail}")

    for issue in report.issues:
        print(f"  !! {issue}")


# ============================================================================
# Main
# ============================================================================


def main() -> int:
    """Entry point.

    Collects files, analyzes each, renders a progress indicator and final
    report.  Exit code 1 if any article is grade C, 0 otherwise.
    """
    parser = argparse.ArgumentParser(
        description="5-dimension quality scoring for knowledge base articles.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="JSON file paths or glob patterns (e.g. *.json, knowledge/**/*.json)",
    )
    args_ns = parser.parse_args()

    files: list[Path] = _collect_files(args_ns.files)
    if not files:
        print("Error: no JSON files found", file=sys.stderr)
        return 1

    print(f"\nFound {len(files)} JSON file(s).  Analyzing...")

    all_reports: list[QualityReport] = []
    for i, fp in enumerate(files):
        reports: list[QualityReport] = analyze_file(fp)
        all_reports.extend(reports)

        article_label: str = (
            f"{len(reports)} article(s)" if reports else "no articles"
        )
        if sys.stdout.isatty():
            print(
                f"\r  {_render_bar(i + 1, len(files), 28)}  "
                f"File {i + 1}/{len(files)} ({article_label})",
                end="",
            )
            sys.stdout.flush()
        else:
            print(
                f"  [{i + 1}/{len(files)}] {fp.name} -- {article_label}"
            )

    if sys.stdout.isatty():
        print()

    if not all_reports:
        print("\nNo articles found to score.")
        return 1

    # ---- Report header ----
    print()
    print("=" * 60)
    print("         KNOWLEDGE ARTICLE QUALITY REPORT")
    print("=" * 60)

    first_file: Path | None = None
    for report in all_reports:
        show_file: bool = (
            first_file is None or report.file_path != first_file
        )
        _print_report(report, show_file=show_file)
        first_file = report.file_path

    # ---- Summary ----
    grades: list[str] = [r.grade for r in all_reports]
    a_count: int = grades.count("A")
    b_count: int = grades.count("B")
    c_count: int = grades.count("C")

    avg_score: float = (
        sum(r.total_score for r in all_reports) / len(all_reports)
        if all_reports
        else 0.0
    )

    print()
    print("=" * 60)
    print("              SUMMARY")
    print("=" * 60)
    print(f"  Total articles:    {len(all_reports)}")
    print(f"  Average score:     {avg_score:.1f}")
    print(f"  A grade (>=80):    {a_count}")
    print(f"  B grade (60-79):   {b_count}")
    print(f"  C grade (<60):     {c_count}")
    print()

    if c_count > 0:
        print(f"  !! {c_count} article(s) scored below C threshold.")
        print()

    return 1 if c_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
