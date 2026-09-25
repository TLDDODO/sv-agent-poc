# 现状盘点(v1,S1)

> 只读盘点,未改任何代码。盘点基于 commit `4069eaa`。

## 1. 用途

一个 LLM agent(DeepSeek,ReAct 循环):用真实证据(PDBe 结构、UniProt 序列、100 ns MD
接触占有率、PubMed)判定 FAT10–MAD2 的蛋白界面;证据与文献冲突时召开三方辩论
(MD 辩方 / NMR 辩方 / 法官),报告矛盾但不宣判谁对。

## 2. 文件 / 模块清单

**agent/**
- `agent/__init__.py` — 包说明(agent 由 LLM 决定调用哪些工具)。
- `agent/llm_client.py` — `make_client()`:指向 DeepSeek 的 OpenAI 兼容客户端;`MODEL` 取自环境变量。
- `agent/run_agent.py` — ReAct 主循环 `run()`;`render()` 生成 markdown 报告;CLI 写 `outputs/`。
- `agent/tools.py` — 全部工具实现 + `DISPATCH` 映射 + `TOOLS`(function-calling schema)。
- `agent/structures.py` — PDBe:已核实快照 `offline_structures()`、live MCP 客户端 `mcp_structures()`、`canonical_map()`。
- `agent/literature.py` — PubMed E-utilities 检索;`retrieve_binding_region()` 用 LLM 从摘要抽取结合区。
- `agent/debate.py` — 三方辩论:`evidence_bundle()` 组装真实事实,两位辩方 + 法官,写 `outputs/`。
- `agent/compare.py` — 弱/强模型对比:同一份证据交给两个模型裁决,比较分歧。
- `agent/skills.py` — 从 `skills/` 加载角色提示词(`===PROMPT===` 之后的文本)。

**skills/**(运行时加载的角色提示词)
- `skills/README.md` — skills 目录说明。
- `skills/investigator.md` — 主 agent 提示词。
- `skills/md_advocate.md` — MD 辩方提示词。
- `skills/nmr_advocate.md` — NMR/文献辩方提示词。
- `skills/judge.md` — 法官提示词(强制 JSON、区分"是否矛盾"与"谁对")。

**analysis/**
- `analysis/md_to_scores.py` — 在 HPC 上把 Amber prmtop + cpptraj nativecontacts 输出转成逐残基占有率 JSON。
- `analysis/md_interface_scores.json` — 上一步的产物:FAT10 各残基与 MAD2 的接触占有率(100 ns)。
- `analysis/adjudicate_md.py` — 确定性冲突检查(无 LLM、无网络):MD 核心界面是否落在 UBL1 6–81。
- `analysis/build_report.py` — 纯 Python 生成 HTML 报告(有 key 时含文献与辩论)。
- `analysis/render_structure.py` — PyMOL + Pillow 渲染带标注的结构图。

**api/**
- `api/__init__.py` — 包说明。
- `api/main.py` — FastAPI:`/`、`/health`、`/evidence`(无需 key)、`/adjudicate`、`/debate`(需 key)。

**数据 / 图 / 其他**
- `complex_protein.pdb` — MD 轨迹第 1 帧(去水去离子)。
- `interface.png`、`interface_labeled.png` — 渲染的结构图(后者带标注)。
- `outputs/md_vs_nmr_adjudication.md` — `analysis/adjudicate_md.py` 的样例输出(唯一提交的运行产物)。
- `outputs/.gitkeep` — 保留运行时输出目录。
- `notebooks/fat10_mad2_pipeline.ipynb` — 五阶段流程的可执行演示。
- `FLOW.md` — 架构流程图(mermaid)。
- `README.md` — 项目说明 + 诚实状态表。
- `CLAUDE.md` — 本次 Agent 2.0 自动运行规则。
- `.claude/agents/reviewer.md` — 独立审查子 agent。
- `Dockerfile`、`docker-compose.yml`、`.dockerignore` — 容器化。
- `requirements.txt` — 运行依赖。
- `.gitignore` — 忽略规则。

## 3. 完整运行时的典型工具调用顺序

仓库里**没有提交过任何一次完整运行的轨迹**,所以下面不是实测顺序,而是
`skills/investigator.md` 提示词建议的顺序(实际顺序由 LLM 每次自行决定):

1. `search_literature` — 查 PubMed,读摘要,了解 MAD2 预期结合 FAT10 哪个区域
2. `get_expected_interface_region` — 取文献/NMR 预期区域(UBL1 6–81)
3. `fetch_structures` — 确认体系(PDBe 结构)
4. `validate_residues` — 用真实 UniProt 序列核对残基标签
5. `map_residues` — 映射到 UniProt 编号并判断是否在结构域内
6. `get_md_interface_scores` — 取真实 MD 接触占有率
7. `convene_debate` — 若 MD 界面落在预期区域之外(冲突),召开辩论(内部 3 次 LLM 调用)
8. `submit_adjudication` — 提交最终裁决,结束循环

另有 `list_interface_tools` / `get_tool_prediction` 在 schema 中可用,但提示词未提及;它们对
AFM/HADDOCK/PISA 返回 `pending`。

## 4. 数据来源分类

**Live(每次运行实时联网)**
- `search_literature` → NCBI E-utilities(esearch + efetch);失败时返回引用的回退结论并标 `retrieved_live: False`。
- `validate_residues` → `rest.uniprot.org` 的 FASTA。
- 所有 LLM 调用 → DeepSeek API(`run_agent`、`debate`、`compare`、`literature.retrieve_binding_region`)。
- `mcp_structures()` → PDBe MCP 服务器(经 `uvx`)——代码存在,但当前**没有任何入口调用它**。

**Snapshot(提交在代码里的已核实快照)**
- `fetch_structures` → `offline_structures()`:6GF1、6GF2、2MBE、7PYV(均为 FAT10 结构,无 FAT10:MAD2 复合物)。该函数**忽略传入的 `uniprot` 参数**,总是返回这 4 条。

**本地文件**
- `analysis/md_interface_scores.json` — 真实 MD 占有率(原始 prmtop / 轨迹不在仓库中)。
- `complex_protein.pdb`、`interface.png`、`interface_labeled.png` — MD 结构与渲染图。
- `skills/` 下的提示词文件。

**硬编码的引用事实(cited,非本系统推导)**
- `get_expected_interface_region`:UBL1 6–81,来源 Theng et al. 2014 PNAS + NMR 2MBE + UniProt 结构域表。
- `agent/literature.py` 中的 `FALLBACK` 结论。
- FAT10 结构域表 `DOMAINS` 在 `analysis/adjudicate_md.py`、`agent/debate.py`、`analysis/build_report.py`、`notebooks/fat10_mad2_pipeline.ipynb` 四处各写了一份。

**Pending(无数据,绝不编造)**
- AlphaFold-Multimer、HADDOCK、PISA 的逐残基评分(`get_tool_prediction` 返回 `status: pending`)。

**与 README 状态表的对照 — 不一致之处**
1. README 写 PDBe 检索是 "live MCP client or verified snapshot";实际 agent、API、CLI **只走快照**,`mcp_structures()` 没有调用入口(原来的 `--source mcp` 入口随旧模块在 `7c3627b` 中删除)。
2. README 写 FAT10 结构域边界 "UBL1 6–81 ✅ verified";但 `map_residues` 默认 `domain_hi=80`、`agent/structures.py` 的 `NTERM_UBL_RANGE = (1, 80)`、`agent/compare.py` 的 `gather_evidence(domain=(1, 80))` 仍在用旧的、未经核实的 1–80。
3. pending 工具名不一致:`agent/tools.py` 用 `PISA`,`agent/compare.py` 的 `_CAVEATS` 用 `PISA-contacts`(对 pending 状态无实际影响)。

其余条目(ReAct 循环、MD 数据、`validate_residues`、引用的预期区域、辩论、弱强对比、pending 三件套)与 README 一致。

## 5. 本地运行

必须在**仓库根目录**运行(数据路径都是相对路径)。

```bash
pip install -r requirements.txt            # 本云端镜像需加 --ignore-installed
export DEEPSEEK_API_KEY=...                # 必需(LLM 部分)
export DEEPSEEK_BASE_URL=https://api.deepseek.com   # 可选,默认值
export DEEPSEEK_MODEL=deepseek-chat        # 可选,默认值
export INTERFACE_SCORES=analysis/md_interface_scores.json   # 可选,默认值

python -m agent.run_agent                  # 自主 agent → outputs/
python -m agent.debate                     # 三方辩论 → outputs/
python -m agent.compare                    # 弱/强模型对比 → outputs/
python analysis/adjudicate_md.py           # 确定性冲突检查(无需 key / 网络)
python -m analysis.build_report            # HTML 报告
uvicorn api.main:app --reload              # API,文档在 /docs
docker compose up --build                  # 容器方式运行 API
```

图重绘另需 `pymol-open-source` + `pillow`(`analysis/render_structure.py`);`analysis/md_to_scores.py`
需在有 MD 文件的 HPC 节点上运行。

## 6. 没有测试覆盖的部分

仓库目前**没有任何测试**(没有 tests 目录,也没有 CI)。以下全部未覆盖:
- `agent/run_agent.py` 的循环(工具分发、`submit_adjudication` 终止、达到 `max_steps` 的情形)
- `agent/tools.py` 全部工具(含网络失败时的回退分支)
- `agent/structures.py` 的快照、MCP 解析 `_parse()`、`canonical_map()`
- `agent/literature.py`、`agent/debate.py`、`agent/compare.py`(含 JSON 解析)
- `agent/skills.py` 的加载与回退
- `api/main.py` 全部端点
- `analysis/` 下全部脚本、`notebooks/fat10_mad2_pipeline.ipynb`

## 7. 最脆弱的 3 个点

1. **`fetch_structures` 写死 FAT10**:忽略 `uniprot` 参数,永远返回 FAT10 快照,live MCP 未接入。换任何其他蛋白对都会给出错误结构;而且快照里的 7PYV 是 FAT10–UBA6 实验复合物——若 benchmark 选这一对,它就是现成的答案泄漏源。
2. **FAT10 常量与相对路径散落各处**:结构域表复制了四份,域范围 1–80 与 6–81 并存,MD 路径和 `outputs/` 都是相对路径。不在仓库根目录运行就找不到数据;将来改一处容易漏改另外三处。
3. **LLM 输出解析脆弱且静默**:`debate`、`compare`、`literature` 用贪婪正则 `\{.*\}` 抽 JSON,失败时返回 `{"error": ...}` 而不报错;`search_literature` 任何异常都静默回退到引用结论;辩论嵌套在 agent 循环里,3 次 LLM 调用没有超时/重试控制。
