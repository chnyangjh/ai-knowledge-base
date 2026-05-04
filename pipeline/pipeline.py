"""四步知识库自动化流水线。

采集 -> 分析 -> 整理 -> 保存

Usage:
    python pipeline/pipeline.py --sources github,rss --limit 20
    python pipeline/pipeline.py --sources github --limit 5
    python pipeline/pipeline.py --sources rss --limit 10
    python pipeline/pipeline.py --sources github --limit 5 --dry-run
    python pipeline/pipeline.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

# Ensure project root is on sys.path for direct → python pipeline/pipeline.py ←
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from model_client import chat_with_retry, create_provider  # noqa: E402, F401

from utils.organizer import (  # noqa: E402
    deduplicate_by_url,
    generate_filename,
    normalize_entry,
    save_organized_entry,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
GITHUB_AI_QUERY = (
    "ai+OR+llm+OR+agent+OR+machine+learning+OR+deep+learning"
    "+OR+transformer+OR+rag+OR+langchain+OR+prompt+engineering"
)

RSS_FEEDS: dict[str, str] = {
    "arxiv_cs_ai": "https://arxiv.org/rss/cs.AI",
    "arxiv_cs_cl": "https://arxiv.org/rss/cs.CL",
    "hn_frontpage": "https://hnrss.org/frontpage",
}

RAW_DIR = Path("knowledge/raw")
ARTICLES_DIR = Path("knowledge/articles")

ANALYSIS_SYSTEM_PROMPT = """\
你是一个 AI 技术内容分析专家。请分析给定的技术内容，并严格按照以下 JSON 格式返回分析结果：

{
  "summary": "中文简洁摘要，200-300 字",
  "score": 1到10的整数评分（综合技术价值、创新性、实用性）,
  "score_reason": "简要评分理由",
  "tags": ["相关标签1", "标签2", "标签3", "标签4", "标签5"],
  "category": "framework|library|paper|news|tool",
  "key_points": ["关键点1", "关键点2", "关键点3"],
  "language": "zh|en"
}

只输出 JSON，不要包含任何其他文本。"""


# ---------------------------------------------------------------------------
# Step 1: Collect
# ---------------------------------------------------------------------------


def collect_github(limit: int = 20, timeout: float = 30.0) -> list[dict[str, Any]]:
    """从 GitHub Search API 采集 AI 相关仓库。

    Args:
        limit: 最大采集数。
        timeout: HTTP 请求超时秒数。

    Returns:
        仓库信息条目列表。
    """
    params = {
        "q": GITHUB_AI_QUERY,
        "sort": "stars",
        "order": "desc",
        "per_page": min(limit, 100),
    }
    headers = {"Accept": "application/vnd.github.v3+json"}
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    with httpx.Client(timeout=timeout) as client:
        response = client.get(GITHUB_SEARCH_URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

    items: list[dict[str, Any]] = []
    for repo in data.get("items", []):
        items.append(
            {
                "title": repo.get("full_name", ""),
                "url": repo.get("html_url", ""),
                "description": repo.get("description") or "",
                "language": repo.get("language") or "",
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "topics": repo.get("topics", []),
                "source": "github_search",
                "collected_at": datetime.now(UTC).isoformat(),
            }
        )

    logger.info("GitHub Search: collected %d items", len(items))
    return items


def parse_rss_xml(xml_text: str) -> list[dict[str, str]]:
    """使用正则解析 RSS / Atom XML 中的条目。

    兼容 RSS <item> 和 Atom <entry> 格式。

    Args:
        xml_text: XML 文本内容。

    Returns:
        包含 title / link / description 的字典列表。
    """
    item_blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    if not item_blocks:
        item_blocks = re.findall(r"<entry>(.*?)</entry>", xml_text, re.DOTALL)

    entries: list[dict[str, str]] = []
    for block in item_blocks:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", block, re.DOTALL)
        link_match = re.search(r"<link[^>]*>(.*?)</link>", block, re.DOTALL)
        desc_match = re.search(
            r"<description[^>]*>(.*?)</description>", block, re.DOTALL
        )

        title = _clean_xml_text(title_match.group(1)) if title_match else ""
        link = link_match.group(1).strip() if link_match else ""
        description = _clean_xml_text(desc_match.group(1)) if desc_match else ""

        if not title or not link:
            continue

        entries.append({"title": title, "link": link, "description": description})

    return entries


def _clean_xml_text(text: str) -> str:
    """清理 XML 文本：去除 CDATA / HTML 标签，解码 HTML 实体。

    Args:
        text: 带 XML / HTML 包装的原始文本。

    Returns:
        清理后的纯文本。
    """
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = text.replace("&#x27;", "'")
    return text.strip()


def collect_rss(limit: int = 20, timeout: float = 30.0) -> list[dict[str, Any]]:
    """从 RSS 源采集 AI 相关内容。

    Args:
        limit: 最大采集数。
        timeout: HTTP 请求超时秒数。

    Returns:
        内容条目列表。
    """
    all_items: list[dict[str, Any]] = []

    for feed_name, feed_url in RSS_FEEDS.items():
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(feed_url)
                response.raise_for_status()
                entries = parse_rss_xml(response.text)

            for entry in entries:
                all_items.append(
                    {
                        "title": entry["title"],
                        "url": entry["link"],
                        "description": entry["description"][:500],
                        "source": f"rss/{feed_name}",
                        "collected_at": datetime.now(UTC).isoformat(),
                    }
                )

            logger.debug("RSS '%s': parsed %d entries", feed_name, len(entries))
        except Exception as exc:
            logger.warning("Failed to fetch RSS feed '%s': %s", feed_name, exc)

    result = all_items[:limit]
    logger.info("RSS total: collected %d items", len(result))
    return result


def collect(
    sources: list[str],
    limit: int = 20,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Step 1: 执行数据采集。

    Args:
        sources: 数据源列表（github / rss）。
        limit: 采集数量上限。
        timeout: HTTP 请求超时秒数。

    Returns:
        采集到的所有条目。
    """
    items: list[dict[str, Any]] = []

    if "github" in sources:
        items.extend(collect_github(limit=limit, timeout=timeout))
    if "rss" in sources:
        items.extend(collect_rss(limit=limit, timeout=timeout))

    items = items[:limit]
    logger.info("Step 1 (Collect): total %d items from %s", len(items), sources)
    return items


def save_raw(items: list[dict[str, Any]], source_label: str = "mixed") -> Path:
    """保存原始采集数据到 knowledge/raw/。

    Args:
        items: 采集条目列表。
        source_label: 数据源标签，用于生成文件名前缀。

    Returns:
        保存的文件路径。
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = RAW_DIR / f"{source_label}-{date_str}.json"

    payload = {
        "source": source_label,
        "collected_at": datetime.now(UTC).isoformat(),
        "count": len(items),
        "items": items,
    }
    filename.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Raw data saved: %s (%d items)", filename, len(items))
    return filename


# ---------------------------------------------------------------------------
# Step 2: Analyze
# ---------------------------------------------------------------------------


def analyze_single(
    item: dict[str, Any],
    provider: str | None = None,
) -> dict[str, Any]:
    """使用 LLM 分析单条内容，提取摘要、评分、标签等。

    Args:
        item: 待分析的原始条目。
        provider: LLM 提供商名称。

    Returns:
        附加了分析结果的条目字典。
    """
    title = item.get("title", "")
    description = item.get("description", "")
    content = f"标题: {title}\n描述: {description}"

    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": content},
    ]

    response = chat_with_retry(
        messages,
        provider=provider,
        temperature=0.3,
        max_tokens=1024,
    )

    analysis: dict[str, Any] = {}
    raw_text = response.content

    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        try:
            analysis = json.loads(json_match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse LLM JSON for '%s': %s", title, exc)
            logger.debug("Raw response: %s", raw_text[:300])
    else:
        logger.warning("No JSON found in LLM response for '%s'", title)

    return {
        **item,
        "summary": analysis.get("summary", ""),
        "score": analysis.get("score"),
        "score_reason": analysis.get("score_reason", ""),
        "tags": analysis.get("tags", []),
        "category": analysis.get("category", "news"),
        "key_points": analysis.get("key_points", []),
        "language": analysis.get("language", "en"),
        "analyzed_at": datetime.now(UTC).isoformat(),
        "status": "analyzed",
    }


def analyze(
    items: list[dict[str, Any]],
    provider: str | None = None,
) -> list[dict[str, Any]]:
    """Step 2: 对全部条目调用 LLM 进行分析。

    Args:
        items: 待分析条目列表。
        provider: LLM 提供商名称。

    Returns:
        分析后的条目列表。
    """
    analyzed: list[dict[str, Any]] = []
    total = len(items)

    for i, item in enumerate(items, 1):
        title = item.get("title", "Unknown")
        logger.info("Analyzing %d/%d: %s", i, total, title)
        try:
            result = analyze_single(item, provider=provider)
            analyzed.append(result)
        except Exception as exc:
            logger.error("Analysis failed for '%s': %s", title, exc)
            analyzed.append(
                {
                    **item,
                    "status": "analysis_failed",
                    "analyzed_at": datetime.now(UTC).isoformat(),
                }
            )

    succeeded = sum(1 for a in analyzed if a.get("status") != "analysis_failed")
    logger.info("Step 2 (Analyze): %d/%d items analyzed", succeeded, total)
    return analyzed


# ---------------------------------------------------------------------------
# Step 3: Organize
# ---------------------------------------------------------------------------


def organize(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Step 3: 去重 + 格式标准化 + 校验。

    Args:
        items: 分析后的条目列表。

    Returns:
        整理后的条目列表。
    """
    unique = deduplicate_by_url(items)
    organized: list[dict[str, Any]] = []

    for item in unique:
        try:
            normalized = normalize_entry(item)
            organized.append(normalized)
        except Exception as exc:
            logger.error(
                "Normalize failed for '%s': %s",
                item.get("title", "Unknown"),
                exc,
            )

    logger.info(
        "Step 3 (Organize): %d unique -> %d normalized",
        len(unique),
        len(organized),
    )
    return organized


# ---------------------------------------------------------------------------
# Step 4: Save
# ---------------------------------------------------------------------------


def save_articles(
    items: list[dict[str, Any]],
    dry_run: bool = False,
) -> list[Path]:
    """Step 4: 将文章保存为独立 JSON 文件到 knowledge/articles/。

    Args:
        items: 整理后的条目列表。
        dry_run: 干跑模式，仅打印保存路径，不实际写入。

    Returns:
        保存（或拟定）的文件路径列表。
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    saved: list[Path] = []

    for item in items:
        if dry_run:
            filename = generate_filename(item, date_str)
            logger.info(
                "[DRY-RUN] Would save: knowledge/articles/%s", filename
            )
            saved.append(Path("knowledge/articles") / filename)
        else:
            filepath = Path(save_organized_entry(item, str(ARTICLES_DIR), date_str))
            saved.append(filepath)

    logger.info(
        "Step 4 (Save): %s %d items",
        "Would save" if dry_run else "Saved",
        len(items),
    )
    return saved


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    sources: list[str],
    limit: int = 20,
    dry_run: bool = False,
    timeout: float = 30.0,
    provider: str | None = None,
) -> dict[str, Any]:
    """执行完整的四步知识库自动化流水线。

    Args:
        sources: 数据源列表。
        limit: 采集数量上限。
        dry_run: 干跑模式，跳过最终文章保存。
        timeout: HTTP 请求超时秒数。
        provider: LLM 提供商名称。

    Returns:
        包含处理统计信息的 dict。
    """
    logger.info("=== Pipeline Start ===")
    logger.info(
        "Config: sources=%s, limit=%d, dry_run=%s",
        ",".join(sources),
        limit,
        dry_run,
    )

    # Step 1: Collect
    items = collect(sources, limit=limit, timeout=timeout)
    if not items:
        logger.warning("No items collected from %s", sources)
        return {"status": "no_items", "collected": 0, "dry_run": dry_run}

    save_raw(items, source_label="+".join(sources))

    # Step 2: Analyze
    analyzed = analyze(items, provider=provider)

    # Step 3: Organize
    organized = organize(analyzed)

    # Step 4: Save
    saved = save_articles(organized, dry_run=dry_run)

    stats = {
        "status": "completed",
        "collected": len(items),
        "analyzed": len(analyzed),
        "organized": len(organized),
        "saved": len(saved),
        "dry_run": dry_run,
    }
    logger.info(
        "=== Pipeline Complete: "
        "collected=%d, analyzed=%d, organized=%d, saved=%d ===",
        stats["collected"],
        stats["analyzed"],
        stats["organized"],
        stats["saved"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI 入口函数。"""
    parser = argparse.ArgumentParser(
        description="四步知识库自动化流水线：采集 -> 分析 -> 整理 -> 保存",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python pipeline/pipeline.py --sources github,rss --limit 20
  python pipeline/pipeline.py --sources github --limit 5
  python pipeline/pipeline.py --sources rss --limit 10
  python pipeline/pipeline.py --sources github --limit 5 --dry-run
  python pipeline/pipeline.py --verbose""",
    )
    parser.add_argument(
        "--sources",
        default="github,rss",
        help="数据源，逗号分隔 (默认: github,rss)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="最大采集条目数 (默认: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干跑模式：采集和分析均执行，但不保存最终文章文件",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出 DEBUG 级别详细日志",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP 请求超时秒数 (默认: 30)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM 提供商: deepseek / qwen / openai",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    source_list = [s.strip().lower() for s in args.sources.split(",")]
    stats = run_pipeline(
        sources=source_list,
        limit=args.limit,
        dry_run=args.dry_run,
        timeout=args.timeout,
        provider=args.provider,
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
