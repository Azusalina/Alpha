# Translator 的只读提取评测

这衡量基础规则从文本提取参数证据的行为，不评估人格、临床状态或选择预测。
工具不打开数据库、不提交材料、不拟合模型，也不读取个人词汇／纠正规则。
日常录入仍是自然语言与 `.txt/.md`；下面的 JSON 是另一个带人工标签的实验文件，
不是新增前端录入格式或 JSON API 方法。

从 `back-end-core` 执行：

```bash
python -m translator.evaluation --cases docs/translator-evaluation.example.json
python -m translator.evaluation --cases /absolute/path/private-corpus.json --details
python -m unittest discover -s tests -p 'test_translator_evaluation.py' -v
```

默认输出仅有汇总；`--details` 才增加不含原文的 `case_results`，含不透明案例 ID、
错误种类、参数方向或证据位置，便于在自己保留的语料中定位。
标注文件含原文、证据和人工判断，必须留在本机、不要提交 Git；报告也不是匿名化保证。
工具没有网络调用或报告上传。CLI 错误不回显原文。

## 人工标注约定

顶层只有 `schema_version=1` 和 `cases`。每条案例需要：

- `id`、`group_id`：1–80 字符的不透明 ASCII ID，字符限字母、数字、`_`、`.`、`-`。
  不写人名、事件描述。原文及其改写／片段应使用相同 group_id。
- `split`：`development` 或 `held_out`。规则开发材料放前者；真正独立留出材料放后者。
- `domain`：`daily`、`study`、`interpersonal`、`philosophy`。
- `partition`：`rational`、`emotional`、`crazy`。当前基础提取规则不随分区变化；
  分区只用于分组报告，不表示在拟合或跨分区合并个人状态。
- `kind`：`diary`、`chat`、`philosophy`；chat 再提供 `self_speaker`。
  聊天仍须逐行 `姓名: 内容`／`姓名：内容`。
- `text`：保留待评测原文，包括 emoji／CRLF；不自动规范化其证据位置。
- `label_scope`：人工已经检查的参数列表，或者明确写 `"all"` 表示检查全部 13 个参数。
  **未检查的参数不是负例**，其预测只计入 ignored_predictions。
- `expected`：在 label_scope 内应该出现的贡献，每个参数至多一条，字段与原文纠正
  相同：parameter、sign、evidence、span。这里 sign 只能为 +1 或 -1，且只有 value.*
  允许 -1。scope 内未列入 expected 的参数，表示这份材料**不应有可提取贡献**，
  不是测得用户对该价值中性或不认可材料。

evidence 必须等于 `text[start:end]`；span 按 Unicode 码点，右端不含。
chat 的标注必须在指定发言者的一条消息中，不得借用别人发言。
价值贡献目前按完整子句、情绪贡献通常按情绪词返回；标注哪个证据窗口应事先一致。
若人工与模型采用不同窗口，方向可正确而严格证据匹配失败。

请独立标注，再看模型输出；不要把自动输出复制为 gold，或把整份 T/F 当作每条语义标签。
无法明确判断的参数暂不列入 scope；不是强行标为“没有贡献”。
参数名称使用 [`parameters.md`](parameters.md) 中的当前 13 个实现项。
不采用额外的心理量表或临床风险值。

## 指标及其边界

按 overall、split、领域、分区、split×领域和参数给出计数。
overall 会混合开发／留出材料，不得把它当作留出成绩。

- TP：已检查参数的非零方向相同；FP／FN：多提取／漏提取。
- 方向相反：同时算一个 FP 与 FN，并另计 direction_errors。
- precision = TP/(TP+FP)，recall = TP/(TP+FN)，F1 = 2TP/(2TP+FP+FN)。
  分母为零时返回 null，不伪造 100%。TN 只计人工已检查且双方都没有贡献的参数。
- strict_evidence_*：除方向相同，还需证据文本及 span 完全一致。
  evidence_span_mismatches 单独计数，不把窗口差异混成方向错误。
- case_exact_parameter_match_rate：整条案例**已检查参数**均正确的比例；
  不表示全部潜在语义都已理解。group_macro_* 先在组内平均，再等权平均来源组，
  避免同一原文的多个变体直接当作多个独立来源。
- withheld_fragments 是基础价值规则暂不采纳的片段总数；记录理由每案例最多 64 条。
  recorded_withheld_* 仅反映这部分有限诊断；它们不等于 FP/FN、也不一定落在 label_scope 内。
  by_parameter 不输出无法完整归属的诊断总量。

工具拒绝同一 group_id 跨 split，也拒绝相同 kind／发言者／原文被复制到另一组或 split。
重复检查仅对换行及外层空白做规范化，不改变标注 span；不同分区／领域不让副本变成新材料。
同一 split／组中的变体允许出现，但人工标签一致性仍需人工复核。
它不能发现所有语义改写、既往规则开发或数据库训练暴露；held_out 的来源仍是标注者声明。
分组平均不构成置信区间、样本独立性证明或个人效度证明。

最多 1000 案例，单案例文本上限与录入相同（1,000,000 码点），
总 text 上限 5,000,000 码点，语料文件上限 32,000,000 字节。
文件必须为严格 UTF-8 JSON 的普通文件；拒绝重复键、非有限数字、代理字符和 FIFO／设备。

## 当前合成示例与下一步

[`translator-evaluation.example.json`](translator-evaluation.example.json) 全部是开发用合成材料，
没有 held_out 案例。示例包含“我觉得她把自由看得很重要”：人工期待不提取用户的自由倾向，
assertion-guards-v1 曾产生误提取；v2 的 `other_subject_value` 保护修复了这个已知例子。
示例标签未为迁就规则而修改，现在作为该缺口的开发回归；不是独立验证集或准确率承诺。
更广的主体、间接表达、反讽与真实材料覆盖仍待完善。

`tests/test_translator_evaluation.py` 的 14 项测试检验计数、范围、分组、严格标注、隐私边界和
只读性。测试通过不意味着提取效果已经过真实用户验证。
后续应收集独立标注的真实材料，按来源／时间隔离开发和留出，再依据漏／误提取决定是否
需要局部 NLP、监督学习或本地 LLM。这个工具不自动更新规则、参数或冻结拟合。
它与 [`evaluation.md`](evaluation.md) 的选择排序评测是两件不同的事。
