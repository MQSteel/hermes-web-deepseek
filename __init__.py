"""DeepSeek web search plugin — user-installed.

Mirrors the ``plugins/web/xai/`` layout: ``provider.py`` holds the provider
class, ``__init__.py::register(ctx)`` registers an instance with the plugin
context so it lands in ``agent.web_search_registry``.
"""

from __future__ import annotations

from .provider import DeepseekSearchProvider


def register(ctx) -> None:
    """Register the DeepSeek search provider with the plugin context."""
    ctx.register_web_search_provider(DeepseekSearchProvider())
