# 给 Hermes 写自定义 Web Search Provider Plugin —— 5 个必踩的坑

> 2026-10-27 实战：把 Hermes 的 web_search 从博查（¥0.036/次）切到 DeepSeek（¥0.005/次）。
> 全程踩了 5 个坑，重启 6 次才通。这份文档就是省下那 6 次重启的。

## 何时用

- 想接入一个新的搜索 provider（官方没有的）
- 想从付费贵的切到便宜的
- 想给 web_extract 换后端（支持抓取的 provider）

## 一、目录结构（坑 ①）

```
✅ 正确：
  ~/.hermes/plugins/web/<name>/          ← 必须有 web/ 这一层！
    ├── plugin.yaml
    ├── __init__.py
    └── provider.py

❌ 错误（小咪踩的）：
  ~/.hermes/plugins/<name>/
```

**依据**：`agent/web_search_provider.py` 文档字符串第 11-13 行
```
Providers live in `<repo>/plugins/web/<name>/` (built-in, auto-loaded as
`kind: backend`) or `~/.hermes/plugins/web/<name>/` (user, opt-in via
`plugins.enabled`).
```

## 二、`__init__.py` 必须实现 `register(ctx)`（坑 ②）

```python
# plugin.yaml 里的 provides_web_providers 只是元数据（CLI 展示用），
# 真正注册靠 __init__.py 的代码。

from __future__ import annotations
from .provider import YourProvider

def register(ctx) -> None:
    ctx.register_web_search_provider(YourProvider())
```

**对照**：`plugins/web/xai/__init__.py`、`plugins/web/brave_free/__init__.py` 都是这个形状。

⚠️ 缺 `register()` 的后果：加载器只打一行 `Plugin 'xxx' has no register() function`（WARNING 级，很容易漏看），provider 永远不会进 registry。

## 三、`plugins.enabled` 要用【路径派生 key】（坑 ③）

```python
# hermes_cli/plugins.py PluginManifest 注释原文：
"Registry key — path-derived, used by plugins.enabled/disabled lookups.
 For a flat plugin at plugins/disk-cleanup/ the key is disk-cleanup;
 for a nested category plugin at plugins/image_gen/openai/ the key is image_gen/openai."
```

```yaml
# ✅ 正确
plugins:
  enabled:
    - web/deepseek          # 路径派生：web/ 目录 + deepseek/ 目录

# ❌ 错误
plugins:
  enabled:
    - web-deepseek          # 这是 plugin.yaml 里的 name，lookup 不认
```

## 四、provider 类要继承 `WebSearchProvider` 并实现这些

```python
from agent.web_search_provider import WebSearchProvider

class YourProvider(WebSearchProvider):
    @property
    def name(self) -> str: return "yourname"        # ← 配置里引用的名字

    @property
    def display_name(self) -> str: return "Your Name"

    def is_available(self) -> bool:                  # ← 有没有 key
        from agent.web_search_provider import get_provider_env
        return bool(get_provider_env("YOUR_API_KEY"))

    def supports_search(self) -> bool: return True
    def supports_extract(self) -> bool: return False

    def search(self, query: str, limit: int = 5, **kwargs) -> dict:
        # 必须返回这个形状：
        return {"success": True, "data": {"web": [
            {"title": ..., "url": ..., "description": ...,
             "position": i+1, "date": ...}
        ]}}

    def extract(self, urls: list[str], **kwargs) -> list[dict]:
        # 每项返回 {"url","title","content"} 或 {"url","error"}
        ...
```

## 五、配置要写【两处】（坑 ④⑤ —— 最难发现）

**这是最坑的一点：Hermes 有两套代码读不同位置的配置。**

```python
# tools/web_tools.py（真正执行搜索的）
def _load_web_config() -> dict:
    return load_config().get("web") or {}     # ← 读【顶层 web:】！

# agent/web_search_registry.py（解析 provider 名字的）
_read_config_key("tools", "web", "backend")   # ← 读【tools.web.backend】！
```

**⇒ 两个地方都得配：**

```yaml
# ① 顶层（web_tools.py 用）—— 缺了它就会 fallback 到 ddgs
web:
  backend: deepseek
  search:
    api_key: ${DEEPSEEK_API_KEY}
    default_count: 5

# ② tools 下（registry 用）
tools:
  web:
    backend: deepseek
    search:
      provider: deepseek
      api_key: ${DEEPSEEK_API_KEY}
      base_url: ''
      default_count: 5
```

配置命令：
```bash
hermes config set web.backend deepseek
hermes config set web.search.api_key '${DEEPSEEK_API_KEY}'
hermes config set tools.web.backend deepseek
hermes config set tools.web.search.provider deepseek
```

## 六、验证链路（不用重启就能查）

**Step 1 — 检查 plugin 是否被加载 + provider 是否注册：**
```python
import sys, os
sys.path.insert(0, '/home/ubuntu/.hermes/hermes-agent')
# 加载 .env 到 os.environ
from hermes_cli.plugins import get_plugin_manager
mgr = get_plugin_manager()
mgr.discover_and_load(force=True)

for key, p in mgr._plugins.items():        # 注意是 _plugins（私有）
    if 'web' in key: print(key, p.enabled)

from agent.web_search_registry import list_providers
for p in list_providers():
    print(p.name, p.is_available())
```

**Step 2 — 检查最终决策函数返回什么（关键！）：**
```python
from tools.web_tools import _get_backend, _get_search_backend, _load_web_config
print(_load_web_config())        # 看读到什么
print(_get_backend())            # 共享 backend
print(_get_search_backend())     # ← 这个返回你的 provider 名才算通
```

**Step 3 — 重启 gateway（必须主人手动，agent 不能自重启）：**
```bash
hermes gateway restart
```

**Step 4 — 实际调 web_search 验证：** 看返回的 description 有没有你 normalize 时加的标记（如 `[站点名]` 前缀）。

## 七、Fallback 顺序（为什么会掉到 ddgs）

`tools/web_tools.py` 的 `_get_backend()` 在配置无效时按这个顺序找：
```
tavily → exa → parallel → firecrawl → searxng → brave-free → ddgs → 最后才是插件注册的 provider
```
`ddgs` 排在插件之前，所以配置只要有一点不对，就静默走 ddgs（表现是 DDG 超时 30s）。

## 八、速度参考

- 从零写完 plugin（照 bocha 结构）：约 10 分钟
- 排查 5 个坑：约 90 分钟，重启 6 次
- 有了这份文档：应该 15 分钟一次性通过

## 九、实例：DeepSeek Search & Fetch

```python
# 端点
SEARCH: POST https://api.deepseek.com/v1/tools/search
        {"query": "...", "count": 5, "need_content": false}
        → {"results": [{"title","url","site_name","summary","snippet","content","date","authority","rerank_score"}]}

FETCH:  POST https://api.deepseek.com/v1/tools/fetch
        {"url": "..."}
        → {"content": "markdown", "title": "标题"}

# 认证：Bearer DEEPSEEK_API_KEY（和聊天 API 同一个 key）
# 计费：¥5 / 1000 次成功请求 = ¥0.005/次（2026-11-01 起对 server-side 工具调用收费）
```

字段映射要点：
- `summary` 优先当 description（比 snippet 信息量大）
- `site_name` 拼成 `[站点名] ` 前缀（便于一眼看出源站）
- `date` 直接透传（ISO8601 格式）

## 十、参考文件

- 官方 provider 范例：`~/.hermes/hermes-agent/plugins/web/bocha/provider.py`（130 行）
- 注册范例：`~/.hermes/hermes-agent/plugins/web/xai/__init__.py`
- 我的实现：`~/.hermes/plugins/web/deepseek/provider.py`（240 行，含 search + extract）
