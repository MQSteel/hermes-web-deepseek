# hermes-web-deepseek

> DeepSeek Search & Fetch provider plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent)
>
> 给 Hermes Agent 用的 DeepSeek 搜索 + 网页抓取插件

## 为什么用它

| | 单价 | 说明 |
|---|---|---|
| 博查 Bocha | ¥0.036 / 次 | 只有 search，不支持 extract |
| **DeepSeek** | **¥0.005 / 次** | **search + extract 都有，便宜 7 倍** |

DeepSeek 的 Search API 用自家搜索引擎，中文效果好；Fetch API 能把网页转成 Markdown。

## 安装

```bash
# 1. 克隆到正确位置（注意必须有 web/ 这一层目录）
git clone https://github.com/<your-name>/hermes-web-deepseek \
  ~/.hermes/plugins/web/deepseek

# 2. 启用插件
hermes plugins enable web/deepseek

# 3. 配置（两处都要写，见下方「配置」）
hermes config set web.backend deepseek
hermes config set web.search.api_key '${DEEPSEEK_API_KEY}'
hermes config set tools.web.backend deepseek
hermes config set tools.web.search.provider deepseek

# 4. 确保 .env 里有 key
echo 'DEEPSEEK_API_KEY=sk-xxxxxxxx' >> ~/.hermes/.env

# 5. 重启
hermes gateway restart
```

## 配置（重要：Hermes 有两套配置读取路径）

Hermes 的两个模块读**不同位置**的配置，两处都必须写：

```yaml
# ~/.hermes/config.yaml

# ① 顶层 —— tools/web_tools.py 的 _load_web_config() 读这里
web:
  backend: deepseek
  search:
    api_key: ${DEEPSEEK_API_KEY}
    default_count: 5

# ② tools 下 —— agent/web_search_registry.py 读这里
tools:
  web:
    backend: deepseek
    search:
      provider: deepseek
      api_key: ${DEEPSEEK_API_KEY}
      base_url: ''
      default_count: 5
```

**漏掉顶层的 `web:` 段会静默 fallback 到 DuckDuckGo**（表现为 `DDGS search timed out after 30s`）。

## 验证

```bash
# 不用重启就能测：检查最终决策函数返回什么
cd ~/.hermes/hermes-agent && python3 - <<'EOF'
import sys, os
sys.path.insert(0, os.path.expanduser('~/.hermes/hermes-agent'))
from hermes_cli.plugins import get_plugin_manager
get_plugin_manager().discover_and_load(force=True)
from tools.web_tools import _get_search_backend
print("search backend =", _get_search_backend())   # 应该输出 deepseek
EOF
```

然后在 Hermes 里搜一次，返回结果的 `description` 会带 `[站点名]` 前缀。

## 它能做什么

```python
# search
POST https://api.deepseek.com/v1/tools/search
{"query": "...", "count": 5, "need_content": false}
→ {"results": [{title, url, site_name, summary, snippet, content, date, authority, rerank_score}]}

# fetch / extract
POST https://api.deepseek.com/v1/tools/fetch
{"url": "..."}
→ {"content": "markdown", "title": "标题"}
```

## 计费

- **¥5 / 1000 次成功请求 = ¥0.005 / 次**
- 2026-11-01 00:00（北京时间）起对 Server 端工具调用开始收费，此前免费
- 同一个 `DEEPSEEK_API_KEY` 既用于聊天也用于搜索

## 踩坑记录

写这个插件时踩了 5 个坑，全部记录在 [PITFALLS.md](PITFALLS.md)：

1. 插件目录必须是 `~/.hermes/plugins/web/<name>/`（少一层 `web/` 不加载）
2. `__init__.py` 必须实现 `register(ctx)` 函数
3. `plugins.enabled` 里要用路径派生 key `web/deepseek`，不是 `web-deepseek`
4. `provider.py` 要继承 `WebSearchProvider` 并实现 search/extract
5. **配置要写两处**（顶层 `web:` + `tools.web:`），这是最坑的

## 兼容性

- Hermes Agent: 2026-10 之后版本（`web_search_registry` 存在的版本）
- Python: 3.9+
- 依赖：`httpx`（Hermes 自带）

## License

MIT
