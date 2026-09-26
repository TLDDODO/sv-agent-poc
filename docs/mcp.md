# MCP 服务器 / MCP server

把 Interface Adjudicator 发布成 [MCP](https://modelcontextprotocol.io) 服务器,让 Claude Desktop、Dify 等客户端直接调用。
Publishes the agent as an MCP server (official MCP Python SDK, `mcp>=2`). It calls the same functions as the web
client and the FastAPI; no logic is copied.

## 工具 / Tools

| tool | 作用 / what it does | 需要模型密钥? / needs `DEEPSEEK_API_KEY`? |
|---|---|---|
| `list_cases` | 预设案例(FAT10–MAD2 和基准蛋白对;不返回任何答案)/ preset cases, no answers | no |
| `get_evidence` | FAT10–MAD2 的真实证据:MD 接触占有率、文献预期区域、一致性检查;每条证据标 `live` / `cited` / `pending` / real evidence, labelled | no |
| `run_adjudication` | 运行调查 agent(预设案例或两个 UniProt 号)。返回 `conclusion`(中英文)、带标签的 `evidence`、`usage`(耗时与成本)/ runs the agent; returns conclusion, labelled evidence, time and cost | **yes** |

其他蛋白对没有独立的 `get_evidence`(证据只在 agent 运行内、在过滤掉答案结构之后取得),会返回 `status: pending`。
FAT10–MAD2 的结论不变:MD 界面(C 端区域)与文献/NMR(UBL1 6–81)矛盾,系统只报告矛盾,不判断哪一方正确。

## 启动 / Start

先在仓库根目录安装依赖:`pip install -r requirements.txt`。

**stdio(Claude Desktop 用 / for Claude Desktop):**

```powershell
python -m mcp_server
```

**streamable HTTP(Dify 用 / for Dify),默认只监听本机 / localhost only by default:**

```powershell
python -m mcp_server --transport http            # http://127.0.0.1:8765/mcp
python -m mcp_server --transport http --port 9000
```

Docker 容器里的 Dify 用 `host.docker.internal` 访问本机;服务器会校验 `Host` 头,需要显式放行(见 `docs/dify_setup.md`):

```powershell
python -m mcp_server --transport http --allow-host host.docker.internal:8765
```

`--host 0.0.0.0` 会让局域网可访问;服务没有内置认证,除非你清楚后果,不要这样做。
The server has no built-in authentication; keep it on localhost.

## Windows 上的 Claude Desktop 配置 / Claude Desktop config on Windows

编辑 `%APPDATA%\Claude\claude_desktop_config.json`(不存在就新建),按你的路径修改后保存并重启 Claude Desktop:

```json
{
  "mcpServers": {
    "interface-adjudicator": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
      "args": ["-m", "mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\sv-agent-poc",
        "DEEPSEEK_API_KEY": "<your key>"
      }
    }
  }
}
```

- `command` 用 `python` 的完整路径(`where python` 可查),需已安装本仓库的依赖。
- 没有 `DEEPSEEK_API_KEY` 时 `list_cases` 和 `get_evidence` 仍可用,`run_adjudication` 会返回清楚的错误。
- 密钥只放在这个本机配置里,不要提交到仓库。

## 验证过什么 / What was verified

- 离线测试(`tests/test_m1_mcp.py`):进程内 MCP 客户端 + 假 LLM,列出三个工具并成功调用;错误(无密钥、错误案例)以工具错误返回;默认只监听 `127.0.0.1`;运行过程中的 `print` 不会写到 stdout(否则会破坏 stdio 协议)。
- 手动检查(本机,输出没有保存,不是可复查的记录):用 MCP 客户端分别连接了 stdio(`python -m mcp_server`)和 HTTP(`http://127.0.0.1:8765/mcp`),都列出了三个工具。
- **没有验证**:在 Claude Desktop 里的实际使用(本环境没有该应用),上面的 JSON 配置示例(反斜杠已按 JSON 转义成 `\`)按其文档格式书写,未在 Claude Desktop 中实测;Dify 侧见 `docs/dify_setup.md`。
