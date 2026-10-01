# 前后端沟通（front-back-communicate.md）

> 由 `fromBackend-todo.md` 更名（2026-09-30）。前端 `[front]` 与后端 `[back]` 两位开发者在这个文件里确认彼此的需求。
>
> **约定**
> - 每条发言以 `[front]` 或 `[back]` 开头，注明日期。
> - 需求写成 `- [ ]`；对方确认后改成 `- [x]`，并在其下缩进一行回复 `[back] 接受 / 修改为… / 拒绝，因为…`。
> - 已完成（双方都做完并验证）的条目，在行首加 `////` 表示 finished；未加的仍待办。
> - 尚未被对方确认的字段，前端类型里标 `PROPOSED`（见 `src/backend/types.ts`），只由带明确标识的 mock 实现，**不会被当成真实训练**。
> - 前端不修改 `back-end-core/`；后端不修改 `src/`。两边以本文件和 `back-end-core/docs/api.md` 为准。

---

# 后端交接清单（暂定，2026-09-30）

> 供前端对接讨论；以 `back-end-core` 当前代码为准。这里只描述模型接口和待办，不规定 UI/UX。当前系统是本地规则提取＋证据计数更新，不是已验证的选择预测模型，也不提供心理诊断。

## 暂时已完成

//// - [x] 建立 `back-end-core/core/`、`data/`、`logs/`、`docs/`、`tests/`，另有 `translator/` 与 `model/`；运行资料在 `data/`，不会提交到 Git。
//// - [x] `core/store.py`：SQLite 保存原文、带原文证据的候选记忆；可接受／拒绝候选，按字面内容检索已接受记忆。
//// - [x] `translator/`：本地规则识别有限的事件词、情绪词、语气线索与意向；输出原文片段及位置。聊天只分析指定发言者；jieba 根据已认可输入累计个人词汇，不会因此学会语义。
//// - [x] `model/`：保留全部参数为零的原始基线；理性、感性、用户命名的“疯狂”三个独立分区。`0 + observed=false` 表示尚无证据，不等于测得中性。
//// - [x] `model/`：整份输入保存双 T/F（immediate／confirm），只有双 true 才在所属分区拟合；显式 exclamation 直接设置双 true 并同事务拟合。不同意保留原文但不拟合；再次判定／revoke 可移除贡献，再次同意恢复原拟合。
//// - [x] 非训练输入（pending／disagreed／revoked）可 `preview(source_id)`：只显示译解与假设的证据／参数变化，不更新模型；正式审核结果仍为准。
//// - [x] [back] 2026-09-30：pending 解释纠错已实现：`correction_set`／`correction_history`，校验原文位置与聊天发言者，保留纠错历史；整份同意后才拟合。两份同分区／同类型已同意的完整原句显式纠正，可支持窄范围原句复用；不是通用语义训练。
//// - [x] 接通记忆审核边界：同一 `source_id` 须整份同意后，才能进入 `core/` 候选记忆提取／发布；撤销来源会隐藏其已接受记忆，历史仍保留。
//// - [x] `core/brain.py` 统一来源、模型和候选记忆调用；活动查询排除旧演示入口数据，并支持先按分区筛选再限量。
//// - [x] `core/api.py` 提供本机 JSON-lines 进程接口、schema version 1、字段验证与错误响应；前端接入参考 `back-end-core/docs/api.md` 与 `api.schema.json`。
//// - [x] [back] 2026-10-01：输入 get/list 补 Unicode 前 80 码点 excerpt、char_count、edited_at=null；input_list 保持数组。新增 input_page 返回 items／total／next_cursor／revision，游标失效返回 STALE_CURSOR；只读查询不拟合或回传完整日记。
//// - [x] [back] 2026-09-30：Tauri 宿主已实现 `brain_call({request})`，懒启动并复用固定 Python 进程，串行队列、期限、响应 ID 校验、stderr 排空、退出清理；ACL 仅允许主窗口本地来源。React Transport 仍未接线，发行 runtime 未打包。
//// - [x] 返回每项参数的前／后数值、支持证据数、原文片段与位置、规则 ID、修订号；提供保守的结构化选项价值对齐排序，证据不足时 abstain。
//// - [x] [back] 2026-09-30：`model.evaluation` 离线评估工具已实现，复用线上排序逻辑，读取只读快照；区分实际／事后认可标签，报告分领域命中／覆盖／拒答及八个价值参数的静态消融。不会导入测试材料或自动删改参数；合成例子不代表真实用户准确率。
//// - [x] [back] 当前自动化测试：安装 test-schema 测试 extra 后 `tests/` 164 项（含 13 项契约测试、21 项新增 F6 治理测试）全通过；未安装 extra 时 151 项行为测试通过、13 项契约测试显式跳过。本轮 translator/ 7 项、Rust 宿主／命令／ACL 13 项复跑通过；F6 不改 Rust 或 src/。Tauri MockRuntime 不等于原生 WebKitGTK 验收；测试通过不证明心理效度或选择预测准确（2026-10-01）。

## 后端待办

- [ ] **P0｜发布策略**：决定候选记忆要逐条确认，还是随整份输入同意而自动发布；当前保留已有逐条确认流程。统一编排接口已实现，旧版 `core.cli add-source` 记录保留但不进入统一入口的活动查询。
- [ ] **P0｜纠错扩展**：[back] 2026-09-30：pending 参数纠正与保守原句复用已完成；更广的事件／语义纠错、已审核材料的修订与依赖拟合重放仍待实现。
- [ ] **P0｜前端新增需求**：[back] 2026-10-01：F1-F7 后端均已实现；F6 仍待前端启用／全链路验收，不能标 ////。修改 immediate 通过 input_edit，编辑前 agreed 必须先撤回；删除允许任意状态。
- [ ] **P0｜原文治理**：[back] 2026-10-01：F6 已明确并实现当前库内无旧原文历史的编辑／整体硬删；外部备份保护与恢复、通用下游拟合重放仍待办。不会删除原文件／手动备份／系统快照，不声称法证不可恢复或全副本遗忘。
- [ ] **P0｜本机安全**：设计原文访问口令、备份保护和 Tauri 本地调用边界；目前 SQLite 文件有受限权限，但**没有**加密或口令门。
- [ ] **P1｜真实拟合验证**：[back] 2026-09-30：离线评估／参数消融工具已完成，见 `back-end-core/docs/evaluation.md`。仍需用户真实留出事件、独立的实际／事后认可标签、分组／时间切分，以及据此决定参数去留；当前没有真实预测效度证明。有效后才考虑监督式 ML。
- [ ] **P1｜表达覆盖**：用用户可纠错样本评估杂乱日记、复杂聊天、引述、否定与哲学陈述；必要时局部引入本地 NLP／LLM，不预设必须使用。
  - [back] 2026-10-01：基础非断言保护与 14 项合成回归已实现；疑问／引述／假设／转述和复杂否定不自动拟合为价值。真实材料覆盖仍待验证，不能据此将本项标为全部完成。
  - [back] 2026-10-01：新增 translator.evaluation 只读评测（另有 14 项工具测试），按人工 label_scope／来源组／开发及留出分组计分，方向与证据位置分开。只评估基础规则，不打开数据库或使用语料纠正后再给自身计分。v2 已修复已知常见主体的间接价值误提取（新增 9 项回归），任意人名／复杂混合归属与真实材料验证仍未完成。不是 F14 的未来选择反馈。
- [ ] **P1｜桌面接线／部署**：[back] 2026-10-01：已核对前端追加的接线与浏览器真实 Python／Xvfb 原生录入记录，见下方 [front] 验收说明。仍待 F6 真正接线验收、原生故障／重启回读、大列表、release 构建与 Python／后端／jieba 打包及真实 GPU 测试；不以 MockRuntime 或软件渲染代替硬件验收。
- [ ] **P1｜反馈契约**：[back] 2026-09-30：继续稳定 `state/effects/evidence` 与结果 schema；F12 确认无需后端视觉字段，动画映射由前端负责。球体属后续版本，后端不产出临床风险值。
- [ ] **延期｜MMPI 报告**：另定版本、格式和解释边界；目前没有解析、计分或诊断能力。

## 前端需要提供的 input（目标契约；尚未接线）

//// - [x] **录入**：提供自然语言文本或本地 UTF-8 `.txt`／`.md` 文件；上限 1,000,000 个 Unicode 字符。一次提交一个 `source_id`，显式提供 immediate／exclamation；普通提交不训练，exclamation=true 则设双 true 并返回正式训练 effects。
//// - [x] **分区**：按既定需求提供理性、感性、“疯狂”三种录入页面；每份输入指定 `partition = rational | emotional | crazy`，整份内容归同一分区。`crazy` 只是用户命名的情境状态，**不是**诊断。三页如何符合项目“自然语言只有一个入口”的总设计，仍需前端协调。
//// - [x] **类型**：指定 `kind = diary | chat | philosophy`；默认 diary。聊天必须再提供 `self_speaker`，且 v1 文本须逐行 `姓名: 内容` 或 `姓名：内容`；发言者名称需完全匹配，未标记行会跳过。时间戳和跨行消息尚不支持。
//// - [x] **审核**：提交后保存 `source_id`；`review(agree: true/false)` 设置整份的 confirm，只有 immediate=true 才可调用。显式 exclamation 已在 submit 确认，无需再调用 review。双 true 仅授权材料拟合，**不等于**确认每条提取正确或事后认可某个选择。
//// - [x] **审核前预览**：仅对非 agreed 输入调用 `preview`，呈现只读假设结果。数值可能过期，须以正式 submit／review 的 effect 为准；exclamation 已训练后不能再调用 preview。
//// - [x] **反馈显示**：展示 `effects` 的 `parameter`、`before/after`、`support_before/after`、`evidence`、`span`、`rule_id`、`revision`；也要能显示 `observed=false` 和 `abstain`，避免把空白数据画成确定人格。
- [ ] **未来选择反馈**：另收集实际选项、情境、事后是否认可及理由；与上述整份输入的 `agree` 分开。字段与采集时机尚待共同定义，不应由前端自行推断为现有接口。

相关说明：`back-end-core/README.md`、`back-end-core/model/README.md`、`back-end-core/docs/architecture.md`、`back-end-core/docs/parameters.md`、`back-end-core/docs/TODO.md`。

前端正式字段契约：`back-end-core/docs/api.md`；机器可读请求 schema：`back-end-core/docs/api.schema.json`。启动本机后端进程：`python -m core.api --db data/brain.sqlite3`（在 `back-end-core` 中执行）。

---

## [front] 前端需求（2026-09-30，部分已交付，见逐项 [back] 回复）

前端已按 `back-end-core/docs/api.md`（schema_version 1）建好独立适配器 `src/backend/`：接口 `BrainAdapter`（`types.ts`）、按 api.md 信封写好的 `RemoteBrainAdapter`（只缺 Tauri 侧 Transport）、带「演示数据 · 未运行模型」标识的 `MockBrainAdapter`。产品构建默认显示「后端未连接」，用户手动点一下才进入演示模式。

用户对录入流程的要求（前端据此提出下面的需求）：

1. 录入时选择 **理性 / 感性 / 癫狂**，并勾选一个 T/F 框「是否为真（当下）」。
2. 粒子脑放大后，右侧以点列式列出过往输入，用户可以**再次手动判定 T/F**：T → 用于训练（脑内出现反应动画）；F → 允许编辑或删除该内容。
3. **每份输入有两个 T/F（immediate / confirm），仅两者都为 T 时才可用于训练。**
4. 录入时允许勾选 **exclamation**：仅当用户强烈认同「这是我自己的想法」时，免去脑内二次确认，直接用于训练。

### 前端方法 ↔ 后端方法

| 前端 `BrainAdapter` | api.md 方法 | 状态 |
| --- | --- | --- |
| `submit` | `submit` | 已有；`immediate`、`exclamation` 已实现，需前端启用能力 |
| `preview` | `preview` | 已有 |
| `confirm(id, bool)` | `review(source_id, agree)` | 已有（含义 = 第二个 T/F）；再次判定已实现 |
| `revoke` | `revoke` | 已有 |
| `inputList` / `inputGet` | `input_list` / `input_get` | 双判定元数据与摘要已返回；分页另接 input_page（21 个方法之一） |
| `inputEdit` / `inputDelete` | `input_edit` / `input_delete` | [back] 已实现；前端能力探测后启用现有 proposedMethods 并验收 |
| `state` / `effects` / `rank` | `state` / `effects` / `rank` | 已有 |
| `capabilities` | `health.methods` | 已有；前端据此把不支持的按钮置灰 |

### 需要后端做的（计算与数据）

//// - [x] **F1 两个 T/F 与训练门槛。** 每份输入保存 `immediate`（bool，`submit` 时由用户给出）和 `confirm`（bool 或 null，null = 尚未二次判定）。**只有 `immediate=true 且 confirm=true` 才进入拟合**（参数、词汇）；任何一个为 false 都不训练。任一值改变后，活动模型须按现有 revoke 逻辑重算并写 effect 历史。
  - [back] 2026-09-30 接受并实现训练门槛、confirm 再次改变时重算与审核历史。immediate 在提交后暂不可改，须等 F6 编辑 API；没有绕过前端首个 false 的 review 路径。
//// - [x] **F2 status 与 reason 的派生规则。** 保持 api.md 的四个 status，前端按下面理解，请确认：
  - `pending` = immediate 为 true、confirm 为 null；
  - `agreed` = 两者皆 true（训练中）；
  - `disagreed` = immediate 为 false 或 confirm 为 false；
  - `revoked` = 曾 agreed，之后被撤销。
  另请返回 `reason`：`immediate_false` / `confirm_false` / `user_revoked`（其余为 null），前端要区分显示。
  - [back] 2026-09-30 接受并实现。immediate=false 时 confirm=null／reason=immediate_false；manual false 时 confirm=false／reason=confirm_false；显式 revoke 后 confirm=false，但保留 revoked／user_revoked。旧审核标记 confirmed_by=legacy，不伪造 manual。
//// - [x] **F3 `submit` 增加 `immediate`（新客户端应显式传入）与 `exclamation`（可选，默认 false）。** 用户更新：`exclamation=true` 时**直接设置 immediate=true、confirm=true**，包括原请求 immediate=false；同事务拟合，confirmed_by="exclamation"，返回正式 effects／translator_effects。手动二次判定记为 confirmed_by="manual"；旧客户端缺省 immediate=true。
  - [back] 2026-09-30 按用户最新答复修改并实现，覆盖原提案“immediate=false 时拒绝”的规则。暂按用户显式勾选字段处理，不从文字自动 detect；submit 已训练时前端直接显示正式 effects，不能再 pending preview。前端与 mock 的旧校验需同步。
//// - [x] **F4 `review` 即第二个 T/F，并允许再次判定。** 除 `pending` 外，允许对「`immediate=true` 且 `confirm=false`」的输入再次 `review(agree=true)`（用户在脑内列表里改主意）。`immediate=false` 的输入不能被 `review`（`INVALID_ARGUMENT`），必须先经 F6 的编辑重新声明 `immediate`。`revoked` 之后能否再次同意，请 [back] 决定并回复。
  - [back] 2026-09-30 接受并实现；revoked 可再次同意，恢复冻结的原贡献／词汇／解释上下文，不重新译解或重复支持计数；原已接受记忆重新可见，pending 候选不自动发布。再次 false 可移除 agreed 贡献；相同判定不重复拟合或写审核事件。新增 review_history，含 before／after 与 effect_revisions。
//// - [x] **F5 `input_list` 补字段。** `immediate`、`confirm`、`exclamation`、`confirmed_by`、`reason`、`excerpt`（原文前 80 个 Unicode 码点）、`char_count`、`edited_at`；超过 100 条时提供分页。
  - [back] 2026-10-01 接受并实现字段；edited_at 暂为 null，不伪装已经支持编辑。input_list 保持现有数组契约，前端已有 hydrate 将跳过额外 input_get。分页新增 input_page({partition?,status?,limit?,cursor?}) → {items,total,next_cursor,revision}，旧适配器尚未接这个方法。游标绑定数据库／筛选及输入审核修订，单页计数与内容同快照；支持 >100 条同时间戳输入，不漏项／重复。输入改变后旧游标返回 STALE_CURSOR，须丢弃旧页再取第一页。完整契约与 inputRecord／inputPage schema 已同步。
  - [back] 2026-10-01 隐私边界：excerpt 是原文片段而非脱敏或语义摘要，按纯文本显示；未来口令门须覆盖 list/page/evidence 等，不只是 input_get。游标完整性校验不等于口令、加密或原文保护。
- [x] **F6 编辑与删除（后端已完成，前端启用／验收仍待办）。**
  - `input_edit(source_id, text, immediate, kind?, self_speaker?)`：仅允许非 `agreed`；替换原文，重置 `confirm=null`，旧 span 全部失效。请 [back] 定：是否保留修改前原文的历史？
  - `input_delete(source_id)`：仅允许非 `agreed`（已训练的须先 `revoke`）。硬删、墓碑还是备份，请 [back] 定；前端会二次确认，文案按你们的选择写（不会假装「已彻底删除」）。
  - 这两个方法未提供时，前端在真实后端下把「编辑/删除」置灰并提示「后端尚不支持」；在 mock 下可用并标「仅演示」。
  - [back] 2026-10-01 接受用户最新决定并实现：input_delete 允许任意状态，事务内撤回活动贡献后硬删该来源及原文／审核／纠错／词汇／参数／冻结拟合／候选记忆／effect 历史，不留墓碑；其他输入历史数值与冻结上下文不重写。input_edit 仍仅允许非 agreed，替换正文并清除上述来源旧历史／候选，保留 source_id／partition／source_ref／created_at，重置 confirm=null、exclamation=false、confirmed_by=null、reviewed_at=null，返回 inputRecord，edited_at 为最后修改时间；immediate=true 为 pending，false 为 disagreed。不保留旧正文，不自动训练。kind 省略则保留；chat 的 self_speaker 省略则保留，非 chat 清空，切换 chat 必须能解析到有效发言者。
  - [back] 2026-10-01 安全／备份边界已获用户确认：本轮无口令门；仅删除当前应用库的该来源记录，不删原 txt/md、手动备份、系统快照、前端缓存／报告或其他来源已冻结的间接证据。不宣称法证安全擦除或完全下游遗忘。内部 ever-fitted 标志在编辑后保留（不含正文／不对前端暴露），避免曾训练来源被误作留出样本；删除时一起删除。
//// - [x] **F7 `preview` 的适用范围。** 对任何**未在训练**的输入可用（`pending`、`disagreed`、`revoked`），结果仍是只读假设值。
  - [back] 2026-09-30 接受并实现；即使 immediate=false 也可预览，但不能据此 review。已有拟合的材料预览冻结证据恢复后的变化；agreed 仍不可 preview。解释纠错仍仅允许 pending。
//// - [x] **F8 文本与 span 的边界。**
  - span 仍是 Unicode 码点、零起点、右端不含。前端用 `Array.from` 语义换算 UTF-16。
  - 前端提交前会去掉开头的 U+FEFF（BOM），不规范化换行（保留 CRLF），文件按严格 UTF-8 解码（非法字节则拒绝，不做替换字符）。请 `submit` 拒绝孤立代理项，并保证 `input_get` 返回的 `text` 与提交时逐字节一致。
  - 聊天格式仍是逐行 `姓名: 内容` / `姓名：内容`；前端会在提交前提示「没有找到发言者 X 的行」（只警告，不拦截）。
  - [back] 2026-09-30 接受：已在提交前拒绝代理字符，emoji／CRLF 回传与 span 回归测试通过。JSON 不保留文件字节封装；保证的是收到的文本码点序列及其 UTF-8 编码不变，BOM 去除发生在前端提交前。
//// - [x] **F9 把 `translation` 写进 `api.schema.json`。** 前端类型 `Translation`（cues / candidates / skipped / limitations）按 `translator.translate` 的输出写的，请确认字段稳定。
  - [back] 2026-09-30 接受并实现：见 `$defs.translation`。philosophy 外层 kind 不变，但词汇报告 `translation.kind=diary`；纠错影响 `interpretation/effects`，不改写原始 translation。其他方法结果体尚未完整 schema 化。
//// - [x] **F10 空证据与 abstain 的语义。** 前端：`observed=false` 显示「尚无证据」；`rank.status="abstain"` 显示「资料不足」；`preview`/`review` 提取到 0 条 effect 时显示「未提取到可拟合的证据」（**不**混称 abstain）。若后端想用显式标记表达这一点（如 `no_evidence: true`），请告知字段名。
  - [back] 2026-09-30 接受，不新增 `no_evidence`：以 `effects.length` 判断是否提取到参数证据；0 条参数 effect 时词汇仍可能更新，不能显示成“完全没有训练”。`delta=0` 的 effect 也可能增加 support。
//// - [x] **F11 Tauri IPC。** 建议一个 Tauri 命令 `brain_call`，载荷为 api.md 的请求信封，返回响应信封；进程生命周期（启动、退出、超时、stderr）由 host 负责。前端的 `RemoteBrainAdapter` 已按信封写好，只缺 Transport 的 Rust 侧实现；前端不会碰 Rust 与 Python 进程。
  - [back] 2026-09-30 接受并实现宿主：`invoke('brain_call', {request})`。只有主窗口本地来源授权；30 秒总期限、32 项队列，满了拒绝；请求最多 6,004,096 字节，响应最多 16,000,000 字节。不自动重试写请求；传输错误使用 `MODEL_UNAVAILABLE`，ACL 等也可能让 invoke reject。React 接线与原生验收仍待办，详见 `docs/desktop-bridge.md`。
  - [back] 2026-09-30 注意：桌面默认数据文件在 app-local-data，不是仓库的 `data/brain.sqlite3`。开发时欲复用已有模型，启动宿主前显式设置绝对 `ALPHA_BRAIN_DB`；不自动搬迁、复制或重建替代模型。默认 release runtime 尚未打包，请勿宣称独立发行可用。
//// - [x] **F12 动画所需。** 训练发生后，前端用返回的 `effects`（含 `partition`）驱动脑内反应：`partition` 决定风格（理性沉稳 / 感性缤纷 / 癫狂整脑），`effects` 的条数与 `|delta|` 决定强度。**不需要**后端提供视觉字段，也请不要产出临床风险值。
  - [back] 2026-10-01 更新边界：只消费正式 submit（exclamation）／review 的 effects，不把 preview 当作训练；反馈也应覆盖 support 增加但 delta 为 0 的情况。不新增视觉或临床字段。
- [ ] **F13 原文口令门。** 若 `input_get` 之后会需要解锁（待办 P0「本机安全」），请约定错误码 `LOCKED`；前端到时补解锁界面，本轮不做。
- [ ] **F14（本轮不做）** 「未来选择反馈」（实际选项、情境、事后认可）；待共同定义字段与采集时机后再议。

### 前端已经做了 / 不会做

- 已做：适配器接口、信封版 `RemoteBrainAdapter`、带标识的 mock（`rule_id` 均带 `mock.` 前缀，仅存内存，刷新即清空，不写盘）；三种状态录入；T/F 与 exclamation；预览与正式反馈；脑内右侧点列式输入列表；撤销、再次判定、编辑、删除（后两者依赖 F6）。
- 不做：不改 `back-end-core/`；不实现 Tauri Rust 侧；不把 mock 结果当作训练；不在前端推断任何心理结论。

### [front] 2026-10-01 前端状态

- 已按 [back] 的回复同步：exclamation = 直接设双 true（含 immediate=false）；提交已训练时直接显示正式 effects；`health.features.two_judgements` 决定是否发送 immediate/exclamation；revoked 可重新认可（前端行内「重新认可」）；`input_list` 的新字段与 excerpt 不再逐条 hydrate。
- 前端已接 `brain_call`（`window.__TAURI_INTERNALS__`，因为 `@tauri-apps/api` 无法在本沙箱安装；以后可替换），**未在原生 WebKitGTK 上验证**。`input_page` 已接，STALE_CURSOR 时重取第一页。
- 对 [back] 的提醒：文本以 U+0000 开头（也含前置空格后）时 `submit` 返回 `STORAGE_ERROR`，建议改为 `INVALID_ARGUMENT` 或允许存储。前端已在提交前拦截，mock 当前照抄这个错误码。
- 仍在等 F6（编辑 / 删除）：前端在真实后端下置灰「编辑 / 删除」，提示「后端暂不支持编辑和删除」；mock 里可用并标「仅演示」。
- 前端 mock 的提取规则是简化版（不含引用 / 疑问 / 假设 / 转述等保护），其译解带 `mock_no_assertion_guards`，不代表真实后端对同一文本的结果。

### [front] 2026-10-01 用户对 F6「删除」的决定

- **删除 = 连同历史一起硬删，不留墓碑**（用户明确：「删除允许直接删掉历史」）。原文、两个判定、该输入的全部 effect 历史都删除。
- **任何状态都可删除**，包括 `agreed`：删除时先撤回它对活动模型的贡献（等同 revoke 的重算，但不再保留 revoke 记录），再整体删除。此前 F6 里「仅允许非 agreed」的限制作废，前端 mock 已按此实现并加了二次确认文案（「连同全部历史一起删除，它对模型的贡献也会撤回」）。
- 其他输入的 effect 记录保留它们写入时的数值，不重写。
- 仍请 [back] 决定的部分：`input_edit`（是否保留修改前原文的历史）、删除是否需要口令门、已有备份是否随之清除。

### [front] 2026-10-01 前后端连接验证（真实链路）

连接已经接通并验证，三层：

1. **前端 ↔ 真实 Python 后端（浏览器，`tests/real-backend.spec.ts`，6 项通过）**：页面里伪装 Tauri 全局（`window.__TAURI_INTERNALS__.invoke('brain_call')`），请求由 Node 转给真正的 `python3 -E -s -u -m core.api`（临时数据库），走的是与桌面应用完全相同的前端代码路径（`createTauriTransport` → `RemoteBrainAdapter`）。验证：启动即 `health` 探测并自动连接（不进演示）；submit（immediate T）→ 真实规则预览 → 脑内 T → 正式 effects（含修订号）→ 状态页 → 撤销；exclamation 直接训练且前端不再调用 preview；immediate F 保存不训练；再次判定 `confirm_false → T`；聊天只读指定发言者且 emoji 之后的 span 高亮正确；每个请求都在 api.md 的方法与字段之内、id 不重复、从不发送 edit/delete。
2. **原生窗口（Tauri 2 / WebKitGTK，Xvfb 软件渲染）**：debug 二进制 + `ALPHA_BRAIN_DB` 指向临时库，用 XTest 真实点击与键入（含中文）。窗口里横幅显示「本机后端已连接」「后端尚不支持：编辑 / 删除」；录入「我重视自由。我看重真实。」→ 预览显示真实规则 `explicit_value_statement`（没有 `mock.`）→ 展开大脑 → 记录列表来自 `input_page` → 点「T 认可为真」→ 数据库读回：`agreed / immediate=1 / confirm=1 / confirmed_by=manual`，`value.autonomy` 与 `value.truth` 均 0.2、support 1，两条 effect 修订号 #1 #2。截图在 `outputs/qa/scratch/r4/native/`。
3. **仍未验证**：真实 GPU 渲染与帧率（Xvfb 是软件渲染，不记数值）；release 构建与 Python／jieba 打包；`STALE_CURSOR`、30 秒超时、队列满等故障路径在原生窗口里的表现；`input_page` 超过 50 条的「加载更多」。

给 [back] 的两点：
- 新增的 `interpretation.withheld_values` 已在预览里展示（「自动提取暂不采纳」，按 `reason` 给中文说明，未知 `reason` 显示原值，保留 v1／v2 两种 `evidence_policy`），不据此隐藏或删除任何 effect。例：「我重视公平吗？“我重视自由。”」显示「疑问句」「引号里的话」，且没有 effect。
- 用户对 F6 的决定见上一节：删除要能连历史一起硬删（任何状态）。请 [back] 实现 `input_delete` 时按此语义，并回复编辑历史与口令门的取舍；前端在你们提供 `input_edit` / `input_delete` 后，只需在 `RemoteBrainAdapter` 里打开 `proposedMethods`。

### [back] 2026-10-01 对前端追加的交付回复（F6 / U+0000）

- 已读取并接受上方删除决定与验收进度。F6 后端已实现，API 共 23 个方法，schema_version 仍为 1；health.methods 包含 input_edit/input_delete，health.features.source_edit/source_delete=true。请求与两种结果 body 均已加入 api.schema.json，最终契约见 api.md「Source editing and deletion」。本轮未修改 src/，未访问实际用户库／备份。
- input_edit(source_id,text,immediate,kind?,self_speaker?) → inputRecord（没有完整 text、effects 或旧正文）；input_delete(source_id) → {source_id,deleted:true}，没有持久删除 effect。删除成功后所有该来源查询／再次删除返回 NOT_FOUND。失败整笔回滚，不能把 MODEL_UNAVAILABLE 当“肯定没写入”而盲重试。
- 前端待办：核对方法／能力后启用 proposedMethods；允许所有状态删除，编辑 agreed 时先明确撤回。成功后清除旧原文／preview／effects／corrections 缓存与在途旧操作，重新读取 state、terms／effects（如需）及列表第一页。编辑后的 confirm=null 不是沿用旧认可；没有新的双 true 就不拟合。其他输入 effect 的历史数值不等于当前 state，删除后须刷新 state。旧游标必定 STALE_CURSOR，包括删除最大审核号与全部来源后再次录入。
- U+0000：任何位置的新增 submit/input_edit text 都在写入前返回 INVALID_ARGUMENT，不静默剥离；旧库含 NUL 文本保留可读。请同步前端全位置校验、mock 错误码及旧测试（原 STORAGE_ERROR／21 个方法／source_edit=false 断言已过时）。前端对 v2 的未知 reason 回退处理已核对，无需新增视觉字段。
- 21 项新增治理测试及 13 项结果契约测试均通过（当前 tests/ 总 164 项）。迁移只增加 edited_at／内部 ever_fitted／全局列表代数，不重训旧材料；临时库迁移、失败回滚、全部状态、并发审核／删除、教学支持移除、原文件／备份不动均已验证。F6 前端按钮／原生编辑删除尚未验收，先不标 ////。
- F13 继续延期；LOCKED 仍是未来约定，不是当前已实现错误码。后续口令门须覆盖原文、excerpt、evidence、历史与写操作，不应只拦 input_get。

### [back] 回复

<!-- [back]：请在上面各条下缩进回复，或在此处集中回复。 -->

- [back] 2026-09-30：本轮完成纠错契约同步、F8/F9/F10/F12 确认，以及 Unicode 提交校验；后端现有 19 个方法可由 `health.methods` 查询。未改 `src/`，未实现 Tauri 或 F1-F7。
- [back] 2026-09-30：纠错调用顺序为 `correction_history → correction_set(expected_revision, corrections) → preview → review`；只允许 pending，corrections 是完整替换集合，`[]` 重置。`sign=0` 移除该参数在整份输入的贡献；不是只删一句。详细字段见 `back-end-core/docs/api.md`。
- [back] 2026-09-30：F1-F7 仍为提案。F6 已向用户询问“彻底删除还是可恢复软删除”；未确认前不写删除代码，不把提案当作真实已训练流程。F11 host 与 F13 安全门仍待实现，`LOCKED` 当前不是已支持错误码；F14 继续延期。
- [back] 2026-09-30：新增离线工具 `python -m model.evaluation --db data/brain.sqlite3 --cases docs/evaluation.example.json`（从 `back-end-core` 执行）。它不是新增 JSON API 方法，未确认／实现 F14 前端采集契约；前端不要据此把实验标签写入真实训练。详见 `docs/evaluation.md`，真实材料与报告留在本机、不要提交 Git。
- [back] 2026-09-30 最新状态覆盖上方历史回复：F11 Rust 宿主现已完成，接线示例和配置见 `back-end-core/docs/desktop-bridge.md`；当前未修改 `src/`。F1-F7、原文口令／加密和 F14 仍未实现；删除策略问题仍待用户决定。主窗口授权不是口令门或 XSS 防护，不能据此宣称原文安全功能已经完成。
- [back] 2026-10-01 更新覆盖上方历史状态：F1-F4/F7 现已实现，API 共 20 个方法（新增 review_history）。health.features.two_judgements=true 时前端可启用 twoJudgements=true；proposedMethods=false 保持不变，F5/F6、口令／加密、F14 仍待办。未修改 src/、未连接真实 UI，也未迁移用户实际运行资料；迁移仅在打开所选数据库时执行，已通过临时旧库回归。
- [back] 2026-10-01 最新覆盖历史状态：F5 已完成，API 现有 21 个方法（新增 input_page），health.features.input_summary／input_pagination=true。F6、口令／加密、F14 与真实前端接线仍待办；本轮未修改 src/。离线评估已补历史拟合检查：再次 false 不会把曾训练材料变成留出样本，包括零参数 effect 的词汇拟合。
- [back] 2026-10-01：新预览／首次拟合的 interpretation 增加 evidence_policy=assertion-guards-v1、withheld_values（最多 64 条）、withheld_count、withheld_truncated；字段与语义见 back-end-core/docs/evidence-policy.md 和 api.schema.json 的 $defs.interpretation。只描述基础价值规则的暂不采纳原因，显式纠正可覆盖，不能当作最终 effects 或临床风险。原始 cues 仍可见；旧冻结上下文允许缺少新字段，恢复时不重算／补造。接口方法仍为 21 个，未改 src/。
- [back] 2026-10-01：新增 test-schema extra 与 6 项可复跑契约测试，验证 schema 本身、21 个方法的实际请求／响应信封及已类型化公共结果；现有 113 项 Python 测试在本机 Python 3.14 全通过。根目录 backend-contract CI 配置已加入，使用合成材料／临时数据库和固定版本 jieba；尚未在线运行，Python 3.10 job 也尚未验收。全部结果体类型化仍待完成，不宣称信封验证等于完整结果契约验证。
- [back] 2026-10-01 最新补充：21 个方法结果体已全部定义在 api.schema.json 的 $defs.results.$defs[METHOD]，配套 12 项契约测试覆盖分支与序列化输出。先验通用 response 信封，再用保留的原请求 method 选择 #/$defs/results/$defs/METHOD 验证成功的 result；只验信封或 results 容器不够。重复同判定的 review 不返回新 interpretation／observed_terms／restored_fit，旧库 migrate.before 只有 status，预览 effect 不含 revision／created_at，正式 effect 必须含；不得补造字段。未改 src/ 或训练逻辑，方法仍为 21 个，schema_version 仍为 1；在线 CI、F6 与安全门等继续待办。
- [back] 2026-10-01：新增离线命令 python -m translator.evaluation --cases /path/to/local-corpus.json（从 back-end-core 执行），说明与合成模板在 docs/translator-evaluation.md 和 translator-evaluation.example.json。默认汇总不含原文或案例 ID，--details 仅显式返回不透明 ID 和错误种类／方向／位置；文件和报告保留在本机。此工具不新增 JSON API、前端字段或材料录入格式，不训练任何模型／词汇、不读取实际用户库，旧冻结拟合不变。表达覆盖和间接主体解析仍待完善。
- [back] 2026-10-01 最新主体归属策略：新预览／首次拟合使用 assertion-guards-v2，可返回暂不采纳原因 other_subject_value，避免把“我觉得她把自由看得很重要”当作用户自身倾向；自身对他人的重视、情绪与联系意向仍保留。显式“对我来说／在我看来”支持跨逗号的自身观点范围。api.schema.json 接受旧 v1 与新 v2，新增原因仅适用于 v2；旧贡献／诊断撤销再恢复仍冻结，不重算或重标版本。21 个方法与 schema_version=1 不变，未修改 src/、未访问实际用户库；前端需能容纳新策略／原因枚举。合成模板当前 3 TP、0 FP、0 FN，但 5 条全为开发例、0 条留出，不能作为真实效果证明。
