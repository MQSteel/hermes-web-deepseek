"""DeepSeek Search & Fetch API provider for Hermes.

官方文档：https://api-docs.deepseek.com/guides/search
端点：
  POST https://api.deepseek.com/v1/tools/search
  POST https://api.deepseek.com/v1/tools/fetch
认证：Bearer <DEEPSEEK_API_KEY>

计费（2026-10-27 查证）：
  每 1000 次成功请求 ¥5 = ¥0.005/次
  2026-11-01 00:00 起对 Server 端工具调用开始收费

优势 vs 博查（¥0.036/次）：
  · 便宜约 7 倍
  · 支持 extract（抓网页转 Markdown），博查只有 search
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"


def _get_api_key() -> str:
    from agent.web_search_provider import get_provider_env
    key = get_provider_env("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError(
            "DEEPSEEK_API_KEY not set. Get one at https://platform.deepseek.com"
        )
    return key


def _base_url() -> str:
    from agent.web_search_provider import get_provider_env
    url = (
        get_provider_env("DEEPSEEK_SEARCH_BASE_URL")
        or os.environ.get("DEEPSEEK_SEARCH_BASE_URL")
        or DEFAULT_BASE_URL
    )
    return url.rstrip("/")


def _post(path: str, payload: Dict[str, Any], timeout: int = 45) -> Dict[str, Any]:
    """POST to DeepSeek tools API and return parsed JSON."""
    import httpx

    url = _base_url() + path
    headers = {
        "Authorization": "Bearer " + _get_api_key(),
        "Content-Type": "application/json",
    }
    logger.info("DeepSeek API request to %s", url)
    resp = httpx.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _normalize_search(response: Dict[str, Any]) -> Dict[str, Any]:
    """Map DeepSeek {results:[...]} → Hermes {success, data:{web:[...]}}.

    DeepSeek 字段 → Hermes 字段：
      title       → title
      url         → url
      summary     → description（优先，信息量大于 snippet）
      snippet     → description（summary 为空时兜底）
      date        → date
      site_name   → （拼到 description 前缀，标注来源站）
    """
    web_results: List[Dict[str, Any]] = []
    try:
        for i, item in enumerate(response.get("results") or []):
            desc = (item.get("summary") or item.get("snippet") or "").strip()
            site = (item.get("site_name") or "").strip()
            if site and desc:
                desc = f"[{site}] {desc}"
            web_results.append(
                {
                    "title": item.get("title", "") or "",
                    "url": item.get("url", "") or "",
                    "description": desc,
                    "position": i + 1,
                    "date": item.get("date") or "",
                }
            )
    except Exception as e:
        logger.warning("DeepSeek response parse error: %s", e)
    return {"success": True, "data": {"web": web_results}}


class DeepseekSearchProvider(WebSearchProvider):
    """DeepSeek 官方搜索 + 抓取 provider。"""

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def display_name(self) -> str:
        return "DeepSeek Search"

    def is_available(self) -> bool:
        from agent.web_search_provider import get_provider_env
        return bool(
            get_provider_env("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        )

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5, **kwargs: Any) -> Dict[str, Any]:
        try:
            logger.info("DeepSeek search: %r (limit=%d)", query, limit)
            raw = _post(
                "/v1/tools/search",
                {
                    "query": query,
                    "count": min(max(limit, 1), 20),
                    "need_content": False,
                },
            )
            return _normalize_search(raw)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.warning("DeepSeek search error: %s", exc)
            return {"success": False, "error": "DeepSeek search failed: " + str(exc)}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """逐个抓取 URL，返回 Markdown 正文。"""
        results: List[Dict[str, Any]] = []
        for u in urls:
            try:
                logger.info("DeepSeek fetch: %s", u)
                d = _post("/v1/tools/fetch", {"url": u}, timeout=60)
                results.append(
                    {
                        "url": u,
                        "title": d.get("title", "") or "",
                        "content": d.get("content", "") or "",
                    }
                )
            except Exception as exc:
                logger.warning("DeepSeek fetch failed for %s: %s", u, exc)
                results.append(
                    {"url": u, "title": "", "content": "", "error": str(exc)}
                )
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "DeepSeek Search",
            "badge": "paid",
            "tag": "官方内置搜索 + 网页抓取，¥0.005/次",
            "env_vars": [
                {
                    "key": "DEEPSEEK_API_KEY",
                    "prompt": "DeepSeek API key",
                    "url": "https://platform.deepseek.com/api_keys",
                },
            ],
        }
