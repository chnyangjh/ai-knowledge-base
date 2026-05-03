#!/usr/bin/env python3
"""
MCP Server for AI Knowledge Base.

Provides tools to search and retrieve locally stored knowledge articles
via the Model Context Protocol (JSON-RPC 2.0 over stdio).

Protocol lifecycle:
  Client → initialize       → Server (returns capabilities)
  Client → notifications/*   → Server (no response)
  Client → tools/list        → Server (returns tool definitions)
  Client → tools/call        → Server (returns tool result)
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ARTICLES_DIR = SCRIPT_DIR / "knowledge" / "articles"

# ── Data Loading ────────────────────────────────────────────────────────────

_articles_cache: list[dict[str, Any]] | None = None


def _load_articles() -> list[dict[str, Any]]:
    """Load and normalise all articles from the knowledge base (cached)."""
    global _articles_cache
    if _articles_cache is not None:
        return _articles_cache

    articles: list[dict[str, Any]] = []
    if not ARTICLES_DIR.is_dir():
        _articles_cache = articles
        return articles

    for json_file in sorted(ARTICLES_DIR.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if "items" in data and isinstance(data["items"], list):
            for item in data["items"]:
                name = item.get("name", "")
                articles.append({
                    "id": name.replace("/", "_").replace(" ", "_"),
                    "title": name,
                    "summary": item.get("summary", ""),
                    "tags": item.get("suggested_tags", []),
                    "source": data.get("source", ""),
                    "score": item.get("score", 0),
                    "score_reason": item.get("score_reason", ""),
                    "technical_highlights": item.get("technical_highlights", []),
                    "url": item.get("url", ""),
                })
        elif "id" in data:
            articles.append(data)

    _articles_cache = articles
    return articles


# ── Tool Implementations ────────────────────────────────────────────────────

def _search_articles(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    articles = _load_articles()
    kw = keyword.lower()
    matched = []
    for a in articles:
        title = (a.get("title") or "").lower()
        summary = (a.get("summary") or "").lower()
        if kw in title or kw in summary:
            matched.append({
                "id": a.get("id", ""),
                "title": a.get("title", ""),
                "summary": a.get("summary", ""),
                "tags": a.get("tags", []),
                "source": a.get("source", ""),
                "score": a.get("score", 0),
                "url": a.get("url", a.get("source_url", "")),
            })
    matched.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
    return matched[:limit]


def _get_article(article_id: str) -> dict[str, Any] | None:
    for a in _load_articles():
        if a.get("id") == article_id:
            return a
    return None


def _knowledge_stats() -> dict[str, Any]:
    articles = _load_articles()
    source_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    total_score = 0

    for a in articles:
        source_counter[a.get("source", "unknown")] += 1
        for tag in a.get("tags", []):
            tag_counter[tag] += 1
        total_score += a.get("score", 0) or 0

    n = len(articles)
    return {
        "total_articles": n,
        "avg_score": round(total_score / n, 2) if n else 0,
        "source_distribution": dict(source_counter.most_common()),
        "top_tags": tag_counter.most_common(20),
    }


# ── Tool Definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_articles",
        "description": (
            "搜索本地知识库中的文章。按关键词在标题和摘要中进行匹配，"
            "返回按评分排序的结果列表。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "搜索关键词（大小写不敏感）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限（默认 5）",
                    "default": 5,
                },
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "get_article",
        "description": (
            "根据文章 ID 获取完整内容，包括关键点、技术亮点、标签、"
            "元信息等全部字段。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "文章的唯一标识符（ID）",
                },
            },
            "required": ["article_id"],
        },
    },
    {
        "name": "knowledge_stats",
        "description": (
            "返回知识库的统计信息，包括文章总数、平均评分、"
            "各来源分布、热门标签（Top 20）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

_TOOL_MAP = {
    "search_articles": lambda args: _search_articles(
        args.get("keyword", ""), args.get("limit", 5)
    ),
    "get_article": lambda args: _get_article(args.get("article_id", "")),
    "knowledge_stats": lambda args: _knowledge_stats(),
}


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> str:
    """Run a tool and return JSON-serialised result."""
    fn = _TOOL_MAP.get(name)
    if fn is None:
        raise ValueError(f"Unknown tool: {name}")
    result = fn(arguments)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── JSON-RPC 2.0 Transport ──────────────────────────────────────────────────

def _send(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_error(request_id: Any, code: int, message: str) -> None:
    _send({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    })


def _log(msg: str) -> None:
    print(f"[mcp_knowledge] {msg}", file=sys.stderr, flush=True)


def _handle_initialize(req_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "knowledge-base-server", "version": "1.0.0"},
    }


def _handle_tools_list(req_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    return {"tools": TOOLS}


def _handle_tools_call(req_id: Any, params: dict[str, Any]) -> dict[str, Any] | None:
    name = params.get("name", "")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}

    if name not in _TOOL_MAP:
        _send_error(req_id, -32602, f"Unknown tool: {name}")
        return None

    try:
        text = _dispatch_tool(name, arguments)
    except Exception as e:
        _log(f"Tool error ({name}): {e}")
        return {
            "content": [{"type": "text", "text": str(e)}],
            "isError": True,
        }

    return {"content": [{"type": "text", "text": text}]}


_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


def process_request(line: str) -> None:
    raw = line.strip()
    if not raw:
        return

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        _send_error(None, -32700, "Parse error")
        return

    req_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})
    if not isinstance(params, dict):
        params = {}

    if req_id is None:
        _log(f"Notification: {method}")
        return

    handler = _HANDLERS.get(method)
    if handler is None:
        _send_error(req_id, -32601, f"Method not found: {method}")
        return

    try:
        result = handler(req_id, params)
    except Exception as e:
        _log(f"Handler error ({method}): {e}")
        _send_error(req_id, -32603, str(e))
        return

    if result is not None:
        _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def main() -> None:
    _log("Starting knowledge base MCP server...")
    _log(f"Articles directory: {ARTICLES_DIR}")
    n = len(_load_articles())
    _log(f"Loaded {n} articles")
    _log("Ready")

    for line in sys.stdin:
        try:
            process_request(line)
        except Exception as e:
            _log(f"Unhandled error: {e}")


if __name__ == "__main__":
    main()
