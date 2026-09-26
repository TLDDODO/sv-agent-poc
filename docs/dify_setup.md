# 在 Dify 里接入界面裁决器

目标:让不写代码的同事在 Dify 的聊天界面里问"MAD2 结合 FAT10 的哪里?证据是否冲突?",答案由本仓库提供。

Dify 只是一个"前台":真实数据、判断逻辑和"实时 / 引用 / 待定"标签都由本仓库给出,Dify 里的语言模型只负责把工具返回的内容转述成人话。

有两种接入方式:

- **方式 A(推荐):自托管 Dify + MCP 服务器**(第 A 部分)。Dify 通过 MCP 直接看到三个工具:`list_cases`、`get_evidence`、`run_adjudication`。
- **方式 B:OpenAPI 自定义工具**(第 B 部分,较早的写法,适合 Dify 云端版本)。

> 状态说明:第 A 部分的 1–3 步是在本机实际跑过的,结果写在各步里。第 4 步起需要在 Dify 网页里操作,**在人工确认并补上截图 / 导出文件之前,那几步是待验证的**,文中以“待验证”标出。

---

## A. 自托管 Dify + MCP(方式 A)

### A1. 部署 Dify(官方 Docker 自托管方式)

Dify 放在**仓库之外**的独立目录 `C:\Users\<你>\dify`,本仓库不含 Dify 代码。需要已安装并启动 Docker Desktop(Dify 官方要求 Docker 至少分到 4 GB 内存)。

```powershell
cd C:\Users\<你>
git clone --depth 1 --branch <版本号> https://github.com/langgenius/dify.git dify
cd dify\docker
copy .env.example .env
docker compose up -d
```

- 版本:`<版本号>` 换成 Dify 最新的发布标签(`git ls-remote --tags --refs https://github.com/langgenius/dify.git` 可查)。本次实际部署用的版本记录在 `docs/progress.md`。
- 首次会拉取十几个镜像,需要几分钟到十几分钟。
- 实际跑的结果:`docker compose up -d` 退出码 0;`nginx / api / worker / web / plugin_daemon / db_postgres / redis / weaviate / sandbox / ssrf_proxy` 等容器全部 Up;`http://localhost/install` 返回 HTTP 200。
- 默认占用本机 80 / 443 端口;被占用时改 `.env` 里的 `EXPOSE_NGINX_PORT` / `EXPOSE_NGINX_SSL_PORT`。
- 停止:`docker compose down`(数据保存在 `dify\docker\volumes\`);升级或迁移请看 Dify 官方文档。

### A2. 启动本仓库的 MCP 服务器(HTTP)

在仓库根目录、已安装依赖(`pip install -r requirements.txt`)的环境里:

```powershell
$env:DEEPSEEK_API_KEY = "<你的 key>"      # 没有 key 时 list_cases / get_evidence 仍可用,run_adjudication 会报错
python -m mcp_server --transport http --port 8765 --allow-host host.docker.internal:8765
```

- 只监听本机 `127.0.0.1:8765`,地址是 `http://127.0.0.1:8765/mcp`。
- `--allow-host host.docker.internal:8765` 让服务器接受来自 Dify 容器的 `Host` 头(服务器默认会拒绝陌生的 Host,这是防 DNS 重绑定的保护)。
- 没有内置认证,所以**不要**用 `--host 0.0.0.0` 暴露到局域网。
- 密钥只放在这个终端的环境变量里,不要写进 Dify。

**已实测**:在 Dify 的 `api` 容器里向 `http://host.docker.internal:8765/mcp` 发 MCP `initialize` 请求,得到 HTTP 200 和服务器能力(即容器能通过 `host.docker.internal` 访问本机上只监听 127.0.0.1 的服务)。

### A3. 【需要你在网页上操作】创建管理员账号

1. 浏览器打开 `http://localhost/install`。
2. 填邮箱、用户名、密码,点"设置"。**这个账号和密码只保存在你本机的 Dify 里,不要发给任何人,也不要发给我。**
3. 用刚建的账号登录 `http://localhost`。

### A4. 【需要你操作 · 待验证】配置模型

Dify 自己的对话需要一个语言模型(和 MCP 服务器里的 DeepSeek key 是两回事)。

1. 右上角头像 → **设置 → 模型供应商**。
2. 安装 **DeepSeek**(插件市场;需要能访问外网),填入你的 DeepSeek API Key,保存。
3. 系统模型设置里把默认推理模型选为 `deepseek-chat`。

### A5. 【需要你操作 · 待验证】接入 MCP 服务器

1. 顶部 **工具 → MCP → 添加 MCP 服务(HTTP)**。
2. 服务端点填 `http://host.docker.internal:8765/mcp`,名称填"界面裁决器",图标随意。
3. 保存并授权;应能看到三个工具:`list_cases`、`get_evidence`、`run_adjudication`。
4. 若连接失败,先看第 A7 节。

### A6. 【需要你操作 · 待验证】搭问答应用

1. **工作室 → 创建空白应用 → Agent**,名称"蛋白质界面问答"。
2. 提示词:粘贴 [`integrations/dify/system_prompt.md`](../integrations/dify/system_prompt.md) 里“系统提示词”一节的全部内容。
3. 工具:添加刚接入的 MCP 服务里的三个工具。
4. 模型:`deepseek-chat`。
5. 开场白建议:"你好,我可以帮你查 FAT10 和 MAD2 结合界面的证据。可以直接问,比如:证据是否冲突?"
6. 在右侧预览里测试(见下面的三个问题),回答里每条信息应带"实时 / 引用 / 待定"之一,并且不出现工具没给过的数字或文献。

测试问题:

- "FAT10 和 MAD2 是在哪里结合的?MD 结果和文献一致吗?"(应调用 `get_evidence`,如实说 MD 的 C 端区域与文献 / NMR 的 UBL1 6–81 不一致,并且不判断哪一方正确)
- "帮我做一次完整调查。"(会调用 `run_adjudication`,较慢、要花一点 DeepSeek 额度)
- "MDM2 和 p53 呢?"(应调用 `list_cases` / `run_adjudication`,并说明这对蛋白没有分子动力学数据,该项为待定)

### A7. 导出应用配置(DSL)【需要你操作 · 待验证】

应用页面右上角菜单 → **导出 DSL**(**不要**勾选"包含密钥"),把下载的 `.yml` 保存为 `integrations/dify/interface-adjudicator-qa.yml`。提交前检查文件里没有 API Key。

### A8. 常见问题

- **MCP 连接失败**:
  1. 先确认 MCP 服务器在运行(`http://127.0.0.1:8765/mcp` 用浏览器打开会返回 HTTP 400 `Missing session ID` 的 JSON 错误,说明服务在监听;本机实测)。
  2. 启动命令必须带 `--allow-host host.docker.internal:8765`,否则服务器会返回 HTTP 421 `Invalid Host header`(本机用伪造的 Host 头实测过)。
  3. Dify 的 `ssrf_proxy` 容器会拦截对内网地址的请求;如果 Dify 通过它访问 MCP 端点被拒,需要在 `dify\docker\ssrf_proxy\` 的 squid 配置里放行 `host.docker.internal`,然后 `docker compose restart ssrf_proxy`。(这一点尚未在本机遇到或验证,遇到时请把现象记下来。)
- **`run_adjudication` 超时**:这是一次完整的调查,要几十秒;把 Dify 里工具调用的超时时间调大。
- **回答里出现了工具没给过的数字或文献**:提示词没有约束好,重设为 `integrations/dify/system_prompt.md` 的内容,并把它当缺陷记录下来。

---

## B. OpenAPI 自定义工具(方式 B)

目标:让不写代码的同事在 Dify 的聊天界面里问"MAD2 结合 FAT10 的哪里?证据是否冲突?",答案由本仓库的 FastAPI 服务提供。

> 说明:本文按 Dify 的通用界面写成,尚未在某个具体版本上逐步实测;菜单名称可能随版本略有不同。

Dify 只是一个"前台":真实数据、判断逻辑和"真实 / 引用 / 待定"标签都由 API 给出,Dify 里的语言模型只负责把 API 返回的内容转述成人话。

### B1. 先在本机把 API 跑起来

任选一种:

```bash
# A. Docker(推荐)
docker compose up --build            # 读取环境变量 DEEPSEEK_API_KEY(可以为空)

# B. 本地 Python
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

检查:浏览器打开 `http://localhost:8000/health`,应看到 `"status": "ok"`。`llm_configured` 为 `false` 时,`/evidence` 仍可用,`/adjudicate` 和 `/debate` 会拒绝(需要在环境变量里设置 `DEEPSEEK_API_KEY`)。

不想搭 Dify 时,直接用浏览器打开 `http://localhost:8000/` 就是一个可用的网页界面(见 README)。

### B2. 导入 OpenAPI 文件

接口说明文件在 `docs/openapi.json`,由脚本从代码生成(改了接口后重新生成):

```bash
python scripts/export_openapi.py            # 生成 docs/openapi.json
python scripts/export_openapi.py --check    # 检查是否过期
```

在 Dify 中:**工具 → 自定义 → 创建自定义工具 → 选择"导入 OpenAPI"**,粘贴 `docs/openapi.json` 的全部内容(或上传文件)。

**服务器地址要改成 Dify 真正能访问到的地址**(文件里默认写的是 `http://host.docker.internal:8000`):

| Dify 在哪里运行 | 服务器地址填 |
|---|---|
| 同一台电脑的 Docker | `http://host.docker.internal:8000`(Linux 需要在 Dify 的 compose 里给相关服务加 `extra_hosts: ["host.docker.internal:host-gateway"]`) |
| API 与 Dify 在同一个 Docker 网络 | `http://adjudicator:8000`(`docker-compose.yml` 里的服务名) |
| Dify 云端版本 | 云端访问不到你的 localhost,需要按第 B4 节做受保护的公网入口 |

导入后会出现这些工具(名字来自接口的 operationId):

| 工具名 | 作用 | 需要 key | 耗时 |
|---|---|---|---|
| `get_evidence` | 真实 MD 证据 + 文献预期区域 + 冲突标记 | 否 | 快 |
| `health_check` | 服务是否在线、是否配置了 LLM key | 否 | 快 |
| `service_info` | 服务说明和接口列表 | 否 | 快 |
| `list_cases` | 网页用的预设案例列表 | 否 | 快 |
| `run_query` | 网页用的一次完整查询:通俗结论 + 带"实时 / 引用 / 待定"标签的证据 + 本次耗时和费用(参数:`case_id`,或两个 UniProt 号) | 是 | 慢 |
| `run_query_stream` | 与 `run_query` 相同的查询,但用 Server-Sent Events 实时推送每一步(给网页用)。**不要**把它当 Dify 工具用,Dify 的自定义工具读不了事件流,请用 `run_query` 或 MCP | 是 | 慢 |
| `run_adjudication` | 让调查 agent 自己查证并给出结论 | 是 | 慢 |
| `run_debate` | MD 辩方 / NMR 辩方 / 法官辩论 | 是 | 慢 |

在工具页面点"测试",先测 `health_check` 和 `get_evidence`。

### B3. 搭一个最简单的聊天流(Chatflow)

在 Dify 新建 **Chatflow**,节点依次为:

1. **开始**:使用默认的用户输入。
2. **工具节点**:选 `get_evidence`(没有参数)。
3. **LLM 节点**:把工具节点的输出作为上下文,系统提示词填:

   > 你是蛋白质界面证据的解说员。只能使用工具返回的内容回答,不许编造残基、数值、PDB 号或文献。请区分三类信息并明确标注:**真实**(工具在本次运行中测得或取得)、**引用**(已发表文献的结论,不是本系统重新推导的)、**待定**(还没有数据)。如果工具返回了矛盾标记,如实说明"MD 结果与文献预期不一致",不要判定哪一方正确,并建议用户做实验验证。回答用用户的语言。

4. **直接回复**:输出 LLM 节点的回答。

想让用户能"深入调查"时,再加一个**条件分支**:用户消息包含"深入调查"或"完整调查"时,走 `run_adjudication`(把用户的问题填进它的 `goal` 参数);其余情况走上面的 `get_evidence`。注意:

- 这两个慢工具要在 Dify 里**调高工具/HTTP 超时时间**,默认的超时通常比一次完整调查短。
- 它们会消耗 DeepSeek 额度,不要放在会被频繁触发的自动流程里。
- 目前 API 只针对 FAT10-MAD2 这一对蛋白;别的蛋白对不会因为问题里换了名字就切换。

### B4. 安全地暴露本地 API

**这个 API 自己没有任何身份验证。** 谁能访问到它,谁就能调用 `/adjudicate` 和 `/debate`,消耗你的 DeepSeek 额度。因此:

1. **默认只在本机可见。** 用 Docker 时把 `docker-compose.yml` 里的端口写成 `"127.0.0.1:8000:8000"`(现在写的 `"8000:8000"` 会对整个局域网开放);用 uvicorn 时用 `--host 127.0.0.1`。
2. **Dify 和 API 在同一台机器时,不需要公网入口**,用第 B2 节表格里的内部地址即可。
3. **必须让云端 Dify 访问时**,不要直接开放端口。在 API 前面放一层带密钥的反向代理(Caddy / nginx),或用带访问控制的隧道(Cloudflare Tunnel + Access、Tailscale),并且:
   - 要求请求头带密钥(在 Dify 自定义工具的"鉴权方式"里选 API Key,把密钥填在那里),代理校验后才转发;
   - 如果只是想让别人看证据,代理里**只放行 `GET /evidence` 和 `GET /health`**,不要放行 `/adjudicate`、`/debate`;
   - 定期更换密钥,并在代理里做访问日志和限流。
4. **`DEEPSEEK_API_KEY` 只放在运行 API 的机器的环境变量里**,不要写进 Dify 的工作流、提示词、仓库或截图。
5. 不要把 `results/` 里的运行日志发到公开地方,里面有完整的提问内容。

### B5. 常见问题

- **工具调用报连接失败**:服务器地址不对(见第 B2 节表格),或 API 没在运行。先在 Dify 所在环境里访问 `/health`。
- **`run_adjudication` 返回 400**:运行 API 的环境没有设置 `DEEPSEEK_API_KEY`。
- **回答里出现了工具没给过的数字或文献**:LLM 节点的提示词没有约束好,按第 B3 节的系统提示词重设,并把它当作缺陷记录下来。
- **改了接口之后 Dify 里的工具没变**:重新运行 `python scripts/export_openapi.py`,在 Dify 里重新导入。
