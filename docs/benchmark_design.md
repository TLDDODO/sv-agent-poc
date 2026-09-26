# 基准设计(S4,仅设计文档)

> 状态:**等待人工审批(GATE)**。本文件只是设计,未改任何代码。
> 文中每个 UniProt / PDB / PMID、界面残基与计数,都来自 2026-09-26 由人工本地电脑(Windows)上运行的真实 API 调用。
> 调用由已提交的脚本 `docs/benchmark_evidence/build_evidence.py` 执行,原始派生结果已提交为 `docs/benchmark_evidence/evidence.json`(含残基名核对、被丢弃残基、共复合物条目与 PMID、文献检索);本文的数字均抄自该文件,可重跑核对。调用清单见附录 A。

## 1. 目的

v1 只在一个案例上评估(n=1)。v2 要在 5 个"实验上已解出复合物"的蛋白对上报告准确率:
agent 只看到**不含答案**的证据,预测界面在哪个区域,再与 PDBe 报告的该复合物界面比对。

## 2. 五个蛋白对

界面 = PDBe 托管的 PISA 服务(附录 A-3)对该条目报告的**面积最大的、连接这两条链的界面**中,
埋藏表面积(bsa)> 0 的残基。残基编号已用 PDBe SIFTS 映射(附录 A-2)换算成 **UniProt 编号**,
并逐残基核对了三字母残基名与 UniProt 序列(附录 A-4)。

| # | 蛋白 A | 蛋白 B | 真值 PDB | 方法 / 分辨率 | PISA 界面(id / 面积 Å²) | 链 A / 链 B |
|---|---|---|---|---|---|---|
| 1 | CDK2 `P24941` | Cyclin-A2 `P20248` | `1FIN` | X 射线 / 2.3 Å | 1 / 1697.5 | A / B |
| 2 | HRas `P01112` | RAF1 `P04049` | `4G0N` | X 射线 / 2.45 Å | 2 / 614.0 | A / B |
| 3 | MDM2 `Q00987` | p53 `P04637` | `1YCR` | X 射线 / 2.6 Å | 1 / 722.4 | A / B |
| 4 | Bcl-xL (BCL2L1) `Q07817` | BAK `Q16611` | `1BXL` | 溶液 NMR | 1 / 865.7 | A / B |
| 5 | PCNA `P12004` | p21 (CDKN1A) `P38936` | `1AXC` | X 射线 / 2.6 Å | 1 / 1087.5 | C / D |

### 真值界面(UniProt 编号)

**1. CDK2–Cyclin A2(1FIN)**
- CDK2(52 个残基,范围 37–279):37–46, 49, 50, 52–54, 56, 57, 69, 71–73, 76, 116, 119–122, 124, 126, 150–159, 162, 179–183, 271, 272, 274, 276–279
- Cyclin-A2(42 个残基,范围 173–317):173–178, 181, 182, 185, 186, 189, 228, 230, 263, 266–272, 274, 275, 288, 289, 292, 293, 295, 296, 299, 300, 303–309, 312, 313, 316, 317
- UniProt 注释:CDK2 `Protein kinase` 4–286(覆盖 52/52);没有任何 UniProt Domain/Region/Motif 特征与 Cyclin-A2 的界面残基重叠(`evidence.json` 中该蛋白 `features` 为空;它的非 Disordered 特征列表 `all_features_non_disordered` 也为空,另有 2 个 Disordered 特征)。

**2. HRas–RAF1(4G0N)**
- HRas(16 个,范围 21–56):21, 24, 25, 27, 29, 31, 33, 34, 36–41, 54, 56
- RAF1(17 个,范围 57–90):57, 59, 64–71, 73, 84, 85, 87–90
- UniProt 注释:RAF1 `RBD` 56–131(覆盖 17/17);HRas `Effector region` 32–40(覆盖 7/16)。

**3. MDM2–p53(1YCR)**
- MDM2(26 个,范围 25–104):25, 26, 49–51, 54, 55, 57, 58, 61, 62, 67, 70–73, 75, 86, 91, 93, 94, 96, 99, 100, 103, 104
- p53(12 个,范围 17–29):17–20, 22–29
- UniProt 注释:MDM2 `SWIB/MDM2` 26–109(覆盖 25/26);p53 `TADI` 17–25(覆盖 8/12)、`Transcription activation (acidic)` 1–44(覆盖 12/12)。

**4. Bcl-xL–BAK(1BXL)**
- Bcl-xL(29 个,范围 93–204):93, 96, 97, 100, 101, 104, 105, 107, 108, 111, 112, 125, 126, 129, 130, 132, 136–139, 141, 142, 146, 194, 195, 199, 200, 203, 204
- BAK(15 个,范围 72–87):72–82, 84–87
- UniProt 注释:BAK `BH3` 74–88(覆盖 13/15);Bcl-xL 无单一主导结构域(BH3 4、BH1 10、BH2 2,合计不到全部 29 个)。
- 1 个残基被丢弃:链 A 210 位 PDB 残基名 LEU,而 UniProt 该位是 F(名字对不上,不能当真值)。

**5. PCNA–p21(1AXC)**
- PCNA(38 个,范围 27–255):27, 29, 40, 43–47, 67–69, 96, 97, 118–129, 131, 133, 208, 211, 232–234, 250–255
- p21(17 个,范围 143–160):143–148, 150–160
- UniProt 注释:p21 `PIP-box K+4 motif` 140–164(覆盖 17/17);PCNA 无 Domain 注释(只有 Region `Interaction with NUDT15` 7–100,覆盖 13/38)。

### 选择这五对的理由(如实说明)

- 每对都有真实的实验复合物,且 UniProt 特征表或文献给 agent 留有可用线索。
- 难度有梯度:#2、#3、#5 的一侧有直接的 UniProt 结构域/基序注释(较容易);#1 的 Cyclin-A2 一侧**没有**结构域注释,必须靠文献/结构推断(较难)。
- 类型不同:结构域–结构域(#1)、结构域–结构域(#2)、结构域–短肽(#3、#4、#5)。
- **注意**:n=5,单案例即占 20%,准确率的置信区间会很宽;结果只能当趋势看,不能宣称统计显著。
- 用 UniProt 特征表会让部分案例偏容易,这是刻意的("agent 可用的结构域注释"),但报告里要如实说明。

## 3. agent 会看到什么(并标注来源类型)

| 证据 | 基准案例中的行为 |
|---|---|
| UniProt 序列 + 特征表(Domain/Region/Motif) | live。**不**提供 UniProt 的 Subunit 等注释文本和交叉引用(可能直接点出复合物)。已核对(`evidence.json` 各蛋白的 `ground_truth_pdb_id_in_uniprot`):特征表和注释(comments)中都没有出现真值 PDB ID;但**交叉引用(uniProtKBCrossReferences)里有**,因此必须不给 agent 看交叉引用(附录 A-5)。 |
| PDBe 结构列表(`fetch_structures`) | live,但**过滤掉所有同时含这两个蛋白的条目**(见 §5),只剩单个蛋白或与其他伙伴的结构。 |
| PubMed 文献(`search_literature`) | live,但**过滤掉所有含这两个蛋白的 PDB 条目的发表文献**(见 §5)。 |
| MD 接触占有率 | `pending`(这些对没有跑 MD)。 |
| AlphaFold-Multimer / HADDOCK / PISA 预测 | `pending`。其中 **PISA 必须保持 pending**:PISA 正是真值来源,一旦开放就等于泄露答案。 |
| 辩论(MD 辩方 vs NMR 辩方) | 无 MD 证据、无 NMR 冲突可辩;基准里不召开辩论,只评估 agent 的界面判断。 |

与 FAT10–MAD2 相比 agent 缺少:MD 轨迹证据、本地评分文件、手工核实的 NMR/文献结论(FAT10 的 UBL1 6–81 是人工核实的先验)。因此基准考察的是"仅凭序列注释 + 结构 + 文献能否定位界面",**不是**矛盾检测能力。FAT10–MAD2 案例仍单独保留,其"MD 界面在 C 端 vs 文献/NMR UBL1 6–81"的矛盾结论及措辞不变。

## 4. 评分规则

对每个蛋白对的每一侧(蛋白 A、蛋白 B),agent 提交预测界面区域 R(残基区间或残基集合,UniProt 编号)。T 为该侧真值界面残基集合(§2)。

1. **区域命中(主指标,0/1)**:同时满足
   - 召回 ≥ 50%:`|R ∩ T| / |T| ≥ 0.5`;
   - 不靠"整条链"取巧:R 覆盖的长度 ≤ 2 × T 的跨度(T 的最大值 − 最小值 + 1)。
2. **残基重叠(辅助指标)**:R 与 T 的 F1 与 Jaccard(仅当 agent 给出残基集合时计算)。
3. **案例得分** = 两侧区域命中的平均值(0、0.5 或 1)。
4. **总体准确率** = 所有案例、所有运行的案例得分平均。
5. **稳定性**:同一案例多次运行,区域命中结果一致的比例(供 S6 报告)。

阈值(50%、2 倍跨度)是设计选择,不是从数据里拟合的,请审批时确认或修改。评分代码在 S6 实现,报告里的数字只从 `results/benchmark.json` 复制。

## 5. 防答案泄露

1. **结构过滤(按"含两个蛋白"整体过滤,不是只挡真值 ID)**:对每个基准对,过滤掉 PDBe 中所有同时映射到这两个 UniProt 的条目。这一点是必要的:见下表,同一对蛋白往往有多个复合物条目,只挡真值 ID 会从其他条目泄露。

   | 对 | 同时含两个蛋白的 PDBe 条目数 |
   |---|---|
   | CDK2–Cyclin A2 | 111 |
   | HRas–RAF1 | 6(`3KUD` `4G0N` `4G3X` `6NTC` `6NTD` `7JHP`) |
   | MDM2–p53 | 2(`1YCR` `4HFZ`) |
   | Bcl-xL–BAK | 3(`1BXL` `2LP8` `5FMK`) |
   | PCNA–p21 | 6(`1AXC` `4RJF` `5E0U` `6CBI` `7KQ0` `7KQ1`) |

   过滤集合在**运行时**从 PDBe 实时构建(每个蛋白各查一次,取交集),不写死在代码里,以免遗漏。
2. **文献过滤**:取这些条目在 PDBe 登记的发表文献 PMID(共 57 / 4 / 2 / 3 / 5 个,顺序同上表),从 `search_literature` 结果中剔除。**已用真实检索证明必要**:对 HRas–RAF1 查询 "HRAS RAF1 interaction binding domain",前 5 条中就有 PMID `34356620`(一篇 Ras–Raf 界面晶体结构论文,是 `7JHP` 的发表文献,不是 `4G0N` 的),不过滤会泄露(附录 A-6)。
3. **PISA 保持 pending**(见 §3)。
4. **UniProt 视图受限**:只给序列和特征表(§3);不给注释文本和交叉引用(交叉引用含真值 PDB ID,见 A-5)。
5. **测试**(S5 实现):断言基准对的真值 PDB ID 及所有同类条目 ID 不出现在任何工具输出中。
6. **残余风险(如实说明)**:
   - 摘要里可能仍以文字描述结合区域。文献过滤只能挡住"复合物结构论文",挡不住综述等其他文献。这本来就是 agent 可以合法使用的证据类型,但会让部分案例偏容易。
   - 单个蛋白的其他结构里若含模拟对方的多肽,无法自动识别。
   - UniProt 特征表本身来自历史文献,可能间接反映该界面。

## 6. 与现有工具的衔接(供 S5 参考,本步不改代码)

- `get_md_interface_scores` / `get_tool_prediction` 对基准对返回 `pending`,不返回占位数字。
- `get_expected_interface_region` 现在写死 FAT10;基准案例需改成从 UniProt 特征表读取(S5)。
- `map_residues` / `validate_residues` 已接受任意 UniProt,可复用。

## 附录 A:本设计用到的真实 API 调用(2026-09-26,本机)

A-1 至 A-6 的调用均成功返回(HTTP 200);A-7 是探测失败的端点。所有值均由这些调用得到,无凭记忆填写的 ID。

- **A-1 UniProt 特征表与序列**:对 `P24941 P20248 P01112 P04049 Q00987 P04637 Q07817 Q16611 P12004 P38936` 各调用
  `https://rest.uniprot.org/uniprotkb/<ACC>.json`(蛋白名、长度、Domain/Region/Motif 特征)与
  `https://rest.uniprot.org/uniprotkb/<ACC>.fasta`(残基名核对)。
- **A-2 SIFTS 映射**:`https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/<pdb>`,`<pdb>` = `1fin 4g0n 1ycr 1bxl 1axc`。
  1YCR 的 MDM2 链 A 在 SIFTS 里作者编号为空,因此假定作者编号 = UniProt 编号,并用 A-4 的残基名核对验证(26/26 一致)。
- **A-3 PISA 界面**:`https://www.ebi.ac.uk/pdbe/pisa/cgi-bin/interfaces.pisa?<pdb>`,同上 5 个条目。取连接两条映射链的面积最大的界面;界面残基 = bsa > 0。
- **A-4 残基名核对**(逐残基结果与被丢弃残基见 `evidence.json` 的 `bsa_residues_checked`、`dropped_name_mismatch`、`sifts_author_numbers_missing_assumed_equal_unp`):把 A-3 的三字母残基名与 A-1 的 UniProt 序列逐位比对。各案例界面残基总数与不一致数:
  1FIN 52+42 全部一致;4G0N 16+17 全部一致;1YCR 26+12 全部一致;1BXL 30+15 中 1 个不一致(链 A 210 位,已丢弃);1AXC 38+17 全部一致。
- **A-5 UniProt 泄露核对**:对 A-1 中 10 个蛋白的 JSON,分别检查 features、comments、uniProtKBCrossReferences 是否含对应真值 PDB ID。结果在 `evidence.json`:10 个蛋白的 features 与 comments 均不含;10 个蛋白的交叉引用均含(所以交叉引用不能给 agent)。
- **A-6 共复合物条目与文献**:
  - `https://www.ebi.ac.uk/pdbe/search/pdb/select?q=uniprot_accession:<ACC>&fl=pdb_id&rows=20000&wt=json`,对 10 个 UniProt 各一次,按蛋白对取交集得到 §5 的条目数与 ID。
  - `https://www.ebi.ac.uk/pdbe/api/pdb/entry/summary/<pdb>`、`.../publications/<pdb>`、`.../experiment/<pdb>`(标题、方法、分辨率、发表 PMID),真值 5 个条目;`publications/<pdb>` 另对所有共复合物条目调用,得到 §5 的 PMID 数。
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=5&term=<query>`,5 条查询("CDK2 cyclin A binding interface"、"HRAS RAF1 interaction binding domain"、"MDM2 p53 interaction binding domain"、"BCL2L1 BAK1 interaction binding region"、"PCNA CDKN1A p21 interaction binding region"),与共复合物发表 PMID 求交:仅 HRAS–RAF1 命中 `34356620`。
  - `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=34356620`(标题、期刊、年份记录在 `evidence.json` 的 `leaked_pmid_summaries`:Crystal Structure Reveals the Full Ras-Raf Interface and Advances Mechanistic Understanding of Raf Activation,Biomolecules,2021)。
- **A-7 探测失败的端点**:`evidence.json` 的 `endpoint_probes` 记录了三个探测的 URL 及其 404 结果(`/pdbe/api/pisa/interfaces/1fin`、`/pdbe/api/pdb/entry/interfaces/1fin`、`data.rcsb.org/rest/v1/core/interface/1FIN/1`),均未使用。
