# 前后端完成日志与历史记录

整理日期：2026-10-05；最新限定验收追加于 2026-10-06（Asia/Taipei）。活动未完成清单见 [front-back-communicate.md](front-back-communicate.md)。

> **当前最新状态｜2026-10-06（Asia/Taipei）**：main session90162 exit0，620／100.682s／OK／0 skips＋Aquinas／Tesla／Franklin 三份终态 fresh reviews 无 blockers，仅接受 rev6 exact-text duplicate hint 后端；见 [最新完成记录／精确证明](#oct-6-rev6-exact-text-duplicate-hint)。当前 schema_version=1／contract_revision=6／35 methods；旧 [main601／84.585s](#oct-6-offline-comparisons-and-typed-validation-performance) 与 [rev5 main576／59.590s](#oct-6-final-rev5-backend-synthetic-contract) 保留历史范围。下方八项既有索引、原始快照及 dated proof 保留原文。整体目标 ACTIVE／NOT ACHIEVED，root 仍有 13 项 pending，frontend adapter／UI／cache／native 继续待验收。

本日志汇集已有完成记录；以下结果来自原沟通记录，本次文档整理未重新执行代码或测试。后续已验证事项按日期、实际结果／证据、限定范围追加 `//// - [x]`；批准、方案和源码存在不单独构成完成，部分完成只归档已完成子项。

## 已完成索引（限定范围）

//// - [x] **2026-10-05｜文档迁移**：仅将根沟通整理为未完成要点，并把完成索引与逐字原始 464 行快照归档到本日志；重复／部分任务已拆分。此完成项仅表示两份文档整理，不是新增代码、测试执行、rev5 或整体阶段验收。
//// - [x] **2026-09-30 至 2026-10-02｜基础后端与 F1–F12**：本地 SQLite 证据记忆、translator／词汇、13-rule 分区模型、来源双 true／exclamation、审核／撤销／冻结恢复、preview、effects、Unicode／NUL 校验、摘要／分页、F6 库内编辑与任意状态硬删、JSON-lines／brain_call、结果 schema 及正式反馈边界已交付。Oct 2 main backend283／0 skips、translator7、Rust16、release tests3 和 typecheck／fmt 等记录见下方原始快照；原文保留每次接口演进与前端回复。一般语义纠错、一般因果重放和最新前端整体仍未完成。
//// - [x] **2026-10-02｜候选发布／有限版本纠错／selected replay／Reset**：fresh 当前来源／版本双 true 自动发布 authored candidates；legacy pending/rejected 不自动发布。guarded correction_reopen／review_version／replay_preview／replay_reopen、exact typed retain/suppress 与 model-only Reset 已验收，保留历史 effects／冻结拟合和 translator 学习。来源 t/t → translator／13-rule model／memories 不要求 choice-group；administrative Reset 后 native 重连另待验收。见 [API](back-end-core/docs/api.md)。
//// - [x] **2026-10-02，后续兼容证明范围见快照｜F13 后端访问门与加密备份**：AccessSession／LOCKED、Argon2id、私有读写及 CLI／eval access 复查、XChaCha20 encrypted backup／明确 fresh-target restore 已交付；hybrid feedback table 严格 schema 兼容及独立 backup12／11.220s／0 skips 的后续证明保留。Frontend unlock／private-cache／native 和可选整库加密未完成；SQLite 明文／same-OS-user 文件读取边界不变。见 [API](back-end-core/docs/api.md)。
//// - [x] **2026-10-01 至 2026-10-02｜浏览器／Linux runtime／软件渲染 native 范围**：真实 Python 浏览器链路、F6／NUL／model_epoch／model_active 接线已有验收；前端各 dated comments 与 D62 crazy 动画交付记录原样保存在快照。Linux x86_64 portable release/runtime、relocation／security／artifact hashes 已验证（glibc >=2.34、nonstatic GTK dependencies）；Xvfb native real／persistence／fault-eof／fault-invalid／fault-timeout 五 scenarios passed，明确 reconnect、恰好一次 submit／no_write_autoretry=true。精确命令及报告路径见快照；不覆盖实体输入／GPU、macOS／Windows、administrative Reset 重连、新 encoder 打包或最新前端完整验收。
//// - [x] **2026-10-02 至 2026-10-05｜合成／本地评测工具与偏好有限修复**：readiness／collection／旧 evaluation／translator evaluation 工具已交付；digest-only 筛选缓存、收敛 Newton／near-tie 拒答及巨大整数 weight 受控错误依据 main411／170.066s／OK／0 skips、fresh92／85.576s 与 scoped reviews 限定验收。numeric-copy canonicalization 的 omitted zero／等值 int/float／signed-zero 子修复有 Pauli68、Lorentz51／4.258s 与八项 repro 证明。资源观测为合成 Python tracemalloc／CPU，非 native RSS 或正常延迟保证；不关闭 broad P2／P3 或真实效度。
//// - [x] **2026-10-05｜合成离线 P3 evaluator 限定交付**：冻结 manifest／development groups、production pure fit、先完成 predictions 后 scoring、actual／endorsed 与 axes 分离、coverage／abstain／group metrics 和 authoritative fit['training_groups'] report 已交付；owner51／4.695s、main settled51／4.139s／0 skips，canonical／sources-groups 回归及独立 reviews 见快照。后续 rev5 变更需新证明；真实 holdout／baselines／ablations／calibration／参数选择未完成。
//// - [x] **2026-10-05｜rev4 reviewed-groups 后端合成契约**：schema_version=1／contract_revision=4／34 methods，optional group_id／group_reviewed、normalized returns、legacy exact payload 不 backfill、reviewed eligibility、training_sources／training_groups 独立计数与 min3 gate 已限定验收；event loss=1/(G*n_g)，group total=1/G。main session28196 exit0：483 tests／121.151s／OK／0 skips；Lagrange／Meitner／Kant 三份 fresh reviews no blockers，重叠 counts 不相加。见 [API final rev4 proof](back-end-core/docs/api.md#oct-5-final-rev4-backend-synthetic-contract)。此证明只覆盖 rev4，当前 rev5 contrast 实现、病态 span／列序问题与新的 final suite／reviews 均未接受；不接受 frontend 或真实预测效度。

## 完整原始沟通快照（464 行，逐字保留）

**以下全部内容是迁移前的历史快照，不是最新 API 契约或活动状态声明。** 原始 464 行的顺序、日期、决策、前端评论、完成标记及混合待办完整保留；旧 pending／PROPOSED／do-not-send／F13 或 F14 延期／运行中结果只反映各自日期，不重新开启已完成任务或已移出范围的议题。当前活动任务以根 [未完成清单](front-back-communicate.md) 为准，接口须核对 [API](back-end-core/docs/api.md)／[schema](back-end-core/docs/api.schema.json)。本次不更改 broader goal 状态。

快照原始 UTF-8 字节数：93135；SHA-256：`1d8ebad1de498f9ff526128916751d4f5d3030225e2f663b6636e26e0eae0cf2`。下方 BEGIN／END 标记属于归档元数据，不属于原始文本。

<!-- BEGIN ORIGINAL COMMUNICATION SNAPSHOT -->
# 前后端沟通（front-back-communicate.md）

> 由 `fromBackend-todo.md` 更名（2026-09-30）；同名的后端交接索引已于 2026-10-02 并入本文件（见下方「后端交接索引」）。前端 `[front]` 与后端 `[back]` 两位开发者在这个文件里确认彼此的需求。
>
> **约定**
> - 每条发言以 `[front]` 或 `[back]` 开头，注明日期。
> - 需求写成 `- [ ]`；对方确认后改成 `- [x]`，并在其下缩进一行回复 `[back] 接受 / 修改为… / 拒绝，因为…`。
> - 已完成（双方都做完并验证）的条目，在行首加 `////` 表示 finished；未加的仍待办。
> - 尚未被对方确认的字段，前端类型里标 `PROPOSED`（见 `src/backend/types.ts`），只由带明确标识的 mock 实现，**不会被当成真实训练**。
> - 前端不修改 `back-end-core/`；后端不修改 `src/`。两边以本文件和 `back-end-core/docs/api.md` 为准。

> [back] **2026-10-04 当前状态**：用户已恢复开发；主线程目标为 active。Oct 2 的 rev2／30 methods 是已验收历史基线；当前源码声明 rev3／34 methods，hybrid 新能力仍待 main 最终独立验证，不能仅据 health 能力启用。Oct 3 暂停及旧 F14 延期均为历史记录；本轮 F14 已获授权。下方旧文本／日期保留，按逐项 Oct 4 注释及末尾恢复记录解读。

> [back] **2026-10-05 最新限定交付**：当前 schema_version=1／contract_revision=4／34 methods；main483 tests／121.151s／OK／0 skips＋全部三份 fresh reviews 接受 reviewed-event-groups 后端合成契约，合成 P3 工具限定交付已通过。旧 rev3 458／411 证明保留范围；旧 dated pending／PROPOSED／do-not-send 叙述已 superseded，以当前 [API](back-end-core/docs/api.md) 与末尾 final milestone 为准。Oct 4 [front] 留言原样保留；P2/P3 整体、contrast span、前端／真实效度仍 pending。

---

# 后端交接索引（Backend handoff index — 2026-10-02）

> 原为独立文件 `fromBackend-todo.md`，2026-10-02 并入本文件，正文未改。

## Contract references

- Canonical queue: [backend TODO](back-end-core/docs/TODO.md).
- Frontend instructions: [revision 2 handoff](back-end-core/docs/frontend-contract-handoff.md).
- API: schema_version=1, contract_revision=2, 30 methods.

## Delivered

- Fresh double-approval authored candidate publication; legacy pending/rejected untouched.
- Guarded correction_reopen/review_version/replay_preview/replay_reopen.
- Exact typed event/intent/tone/candidate retain/suppress; selected replay is not a
  general causal graph or semantic relabelling ML.
- F13 private API/CLI/evaluation access gate and encrypted fresh-target backup/restore.
- Local readiness/evaluation templates/tools.
- Model-only reset retains translator learning.

## Frontend inputs

- Implement unlock/private-cache invalidation and guarded version-consent UI using the handoff.
- F6 resets source_version=0: discard queued source operations; future content-revision
  guards remain TODO.
- Latest concurrent frontend changes are preserved and have not all been verified.

## Pending and scope

- Online CI/Python 3.10.
- Frontend unlock/version UI.
- Native administrative model-reset/reconnect acceptance.
- Physical input/GPU acceptance.
- Real independent held-out coverage/prediction.
- Typed per-item retranslation performance.
- F14 deferred; MMPI has no active or deferred queue.

## Verification evidence

- Linux x86_64 portable production release/runtime passed, glibc >= 2.34 with
  nonstatic GTK dependencies.
- Relocated runtime/security acceptance and artifact hashes independently verified by main.
- Xvfb DOM functional F6/paging and second-process persistence passed;
  no physical/GPU/macOS/Windows acceptance claim.
- Main verified: backend 283 (no skips), translator 7, Rust 16, release-script 3;
  typecheck, Rust formatting and diff whitespace checks passed.
- Main verified native DOM fault-eof/fault-invalid/fault-timeout: exit 0,
  summary and all three reports passed in `/tmp/alpha-native-faults-20261002`.
  Each covers startup failure with explicit reconnect and ambiguous submit with
  explicit read recovering exactly one source; exactly one submit, no_write_autoretry=true.
- Five native DOM scenarios passed overall: real, persistence and the three faults.
  This does not establish physical input/GPU or F13 UI acceptance.
- Historical EOF failure before submit was a harness failure (no state selected),
  not a product failure; the final main-verified run supersedes that acceptance status.

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

//// - [x] **P0｜发布策略实现**：[back] 2026-10-01：用户已确认当前来源／版本双 true 后自动发布提取的候选记忆；实现与验证仍待办，最近已验收基线为逐条审核，并行变更待证据确认，不通过迁移静默发布旧 pending／rejected 候选。统一编排接口已实现，旧版 `core.cli add-source` 记录保留但不进入统一入口的活动查询。
  - [back] 2026-10-04：完成状态依据 Oct 2 最终文档对齐：fresh 当前来源／版本双 true 在同事务发布 authored candidates；migration/startup/frozen reapproval 不发布 legacy pending/rejected。见 core/brain.py、model/engine.py、tests/test_revisions.py 与 api.md「Access and publication」。上行 Oct 1「实现仍待办」仅为历史。
- [ ] **P0｜纠错扩展**：[back] 2026-10-01：pending 参数纠正与保守原句复用已完成；用户确认已审核材料的语义修订先撤回当前贡献，再对修订解释重新取得双 true 才拟合。版本绑定修订、广义事件／语义标签和显式依赖重放仍待实现／验证，历史 effect 数值与 Reset 排除不改写；不是 F6 文本替换。
  - [back] 2026-10-04：原始广义纠错任务保持 [ ]；有限 typed retain/suppress、版本双同意与 selected replay 子任务另列，不以缩小广义语义修订／标签范围勾整个类别。一般语义重标／一般因果图／通用下游重放未完成。
  //// - [x] **已完成子任务｜版本绑定有限纠错与 selected replay**：Oct 2 main 已验收 correction_reopen/review_version/replay_preview/replay_reopen、exact typed event/intent/tone/candidate retain/suppress；保留历史 effects／冻结拟合／Reset 排除。见 tests/test_revisions.py、api.md「Revision tokens and source lifecycle」与 Oct 2 主验收记录。
- [ ] **P0｜前端新增需求验收**：[back] 2026-10-01：F1-F7 后端均已实现；最新 [front]／[back] 记录确认 F6 能力探测启用、浏览器真实 Python 与模型活动／轮次接线已验收。原生 F6／Reset 重连与故障恢复仍待办，不能标 ////。修改 immediate 通过 input_edit，编辑前 agreed 必须先撤回；删除允许任意状态。
  - [back] 2026-10-04：部分完成，保留 [ ]：Oct 2 native DOM 已验证 F6/paging137、第二进程持久性及三种故障重连／恰好一次 submit；行政 model-only Reset 后重连、guarded version-consent UI 和最新并行前端完整验收仍待办。见末尾 Oct 2 native fault 记录、docs/TODO.md。
- [ ] **P0｜原文治理**：[back] 2026-10-01：F6 已明确并实现当前库内无旧原文历史的编辑／整体硬删；外部备份保护与恢复、通用下游拟合重放仍待办。不会删除原文件／手动备份／系统快照，不声称法证不可恢复或全副本遗忘。
  - [back] 2026-10-04：部分完成，保留 [ ]：F6 与 encrypted backup/fresh-target restore、显式选定 replay 已于 Oct 2 交付；通用下游因果重放／全副本遗忘没有完成，也不作此承诺。新增反馈表与 access/backup/restore 兼容修复正在另一 worker 范围内，最终主验收待提供。
- [ ] **P0｜本机安全 / F13**：[back] 2026-10-01：访问口令门与加密备份／恢复已获用户确认纳入本轮，不再延期；实现、API 集成、前端解锁接线与验证仍待办。门须覆盖原文、excerpt、evidence、历史与写入；恢复验证到明确的新目标，不静默覆盖运行库。当前 SQLite 仍为明文，整库加密在本轮之外；应用门不防同 OS 用户直接读文件。
  - [back] 2026-10-04：部分完成，保留 [ ]：Oct 2 backend AccessSession／LOCKED、CLI/eval 复查、Argon2id 与 XChaCha20 backup/fresh-target restore 有主验收记录；frontend unlock/private-cache UI 未验收。Oct 4 新反馈表曾实际触发 unsupported Alpha database schema；修复草稿存在，独立最终 access/backup/restore 回归未提供，历史完成不代表当前 hybrid 安全兼容已通过。
- [ ] **P1｜真实拟合验证**：[back] 2026-10-01：离线评估／参数消融工具已完成，见 `back-end-core/docs/evaluation.md`。用户确认本轮没有真实私有留出材料，只交付本地收集模板／就绪检查工具，交付仍待 worker 验证。独立实际／事后认可标签、分组／时间切分、真实覆盖／预测效度与参数去留仍是后续验收前提；合成样例不能代替。有效后才考虑监督式 ML。
  - [back] 2026-10-04：部分完成，保留 [ ]：Oct 2 collection/readiness/evaluation 模板与工具已交付验收；真实独立标签、分组／时间留出、覆盖／预测效度及参数去留未验证。没有本轮私人留出材料，工具／合成结果不能代替真实验证。
- [ ] **P1｜表达覆盖**：用用户可纠错样本评估杂乱日记、复杂聊天、引述、否定与哲学陈述；必要时局部引入本地 NLP／LLM，不预设必须使用。
  - [back] 2026-10-04：保留 [ ]：基础规则／v2 主体保护及只读评测工具已有合成证据；真实代表性材料、任意人名／复杂归属／反讽与新 encoder 的真实语义覆盖仍未验证。
  - [back] 2026-10-01：基础非断言保护与 14 项合成回归已实现；疑问／引述／假设／转述和复杂否定不自动拟合为价值。真实材料覆盖仍待验证，不能据此将本项标为全部完成。
  - [back] 2026-10-01：新增 translator.evaluation 只读评测（另有 14 项工具测试），按人工 label_scope／来源组／开发及留出分组计分，方向与证据位置分开。只评估基础规则，不打开数据库或使用语料纠正后再给自身计分。v2 已修复已知常见主体的间接价值误提取（新增 9 项回归），任意人名／复杂混合归属与真实材料验证仍未完成。不是 F14 的未来选择反馈。
- [ ] **P1｜桌面接线／部署**：[back] 2026-10-01：已核对最新浏览器真实 Python F6／模型活动元数据接线与较早 Xvfb 原生基本录入记录。仍待原生 F6、故障／重连／重启回读、大列表、release 构建与 Python／后端／jieba 打包及真实 GPU 测试；不以 MockRuntime 或软件渲染代替硬件验收。
  - [back] 2026-10-04：部分完成，保留 [ ]：Oct 2 Linux portable release/runtime／relocation/security/artifact hashes 和五个 Xvfb DOM scenarios 有主验收记录；行政 Reset 重连、F13/F14 前端 native、实体输入／GPU、跨平台及新 encoder 离线发行未验收。
- [ ] **P1｜反馈契约**：[back] 2026-09-30：继续稳定 `state/effects/evidence` 与结果 schema；F12 确认无需后端视觉字段，动画映射由前端负责。球体属后续版本，后端不产出临床风险值。
  - [back] 2026-10-04：持续稳定契约为原始任务，整体 [ ]；rev3／34 methods、F14 与后续交接仍待最终主验收，不因旧 rev2 子任务通过而关闭类别。
  //// - [x] **已完成子任务｜Oct 2 rev2 结果体与 F12 边界**：30 methods typed results、state/effects/evidence 与不新增后端视觉／临床字段已验收；见 tests/test_schema_contract.py、Oct 2 主验收记录、frontend-contract-handoff.md。

## 前端需要提供的 input（基础录入已接线；未来选择反馈待定义）

//// - [x] **录入**：提供自然语言文本或本地 UTF-8 `.txt`／`.md` 文件；上限 1,000,000 个 Unicode 字符。一次提交一个 `source_id`，显式提供 immediate／exclamation；普通提交不训练，exclamation=true 则设双 true 并返回正式训练 effects。
//// - [x] **分区**：按既定需求提供理性、感性、“疯狂”三种录入页面；每份输入指定 `partition = rational | emotional | crazy`，整份内容归同一分区。`crazy` 只是用户命名的情境状态，**不是**诊断。三页如何符合项目“自然语言只有一个入口”的总设计，仍需前端协调。
//// - [x] **类型**：指定 `kind = diary | chat | philosophy`；默认 diary。聊天必须再提供 `self_speaker`，且 v1 文本须逐行 `姓名: 内容` 或 `姓名：内容`；发言者名称需完全匹配，未标记行会跳过。时间戳和跨行消息尚不支持。
//// - [x] **审核**：提交后保存 `source_id`；`review(agree: true/false)` 设置整份的 confirm，只有 immediate=true 才可调用。显式 exclamation 已在 submit 确认，无需再调用 review。双 true 仅授权材料拟合，**不等于**确认每条提取正确或事后认可某个选择。
//// - [x] **审核前预览**：仅对非 agreed 输入调用 `preview`，呈现只读假设结果。数值可能过期，须以正式 submit／review 的 effect 为准；exclamation 已训练后不能再调用 preview。
//// - [x] **反馈显示**：展示 `effects` 的 `parameter`、`before/after`、`support_before/after`、`evidence`、`span`、`rule_id`、`revision`；也要能显示 `observed=false` 和 `abstain`，避免把空白数据画成确定人格。
- [ ] **未来选择反馈**：另收集实际选项、情境、事后是否认可及理由；与上述整份输入的 `agree` 分开。字段与采集时机尚待共同定义，不应由前端自行推断为现有接口。
  - [back] 2026-10-04：F14 自 Oct 3 已解除延期；当前有未验收 choice_feedback_set/get/preference_rank 草稿。actual_choice_id／endorsed_choice_id 分开，独立 training_consent、前端提供且用户审核 impacts；与材料双 true 分开。契约和 UI 最终验收未完成，保留 [ ]。

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
//// - [x] **F6 编辑与删除（后端已完成，前端浏览器启用／验收已完成，原生验收仍待办）。**
  - [back] 2026-10-04：Oct 2 main 已验证 native DOM F6/paging 与持久性，故将此既有已确认任务补齐 //// 前缀；原行「原生验收仍待办」是 Oct 1 的历史状态。删除任意状态，agreed 编辑先 revoke；行政 Reset/reconnect 与 physical 验收另列未完成，不包含在 F6 完成标记中。
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
  - [back] 2026-10-04：部分完成，保留 [ ]：Oct 2 LOCKED/backend gate 与 encrypted backup/restore 已交付，旧「本轮不做／LOCKED 未实现」为历史；frontend unlock/cache/native 未验收，且新反馈表的安全兼容最终验证待 main。
  - [back] 2026-10-01 最新用户决定覆盖上方历史提案的“本轮不做”：F13 访问门与加密备份纳入本轮，整库加密除外；实现／接口集成／解锁 UI／验收仍待办，`LOCKED` 不据此成为已实现错误码。门的覆盖范围须包括原文、excerpt、evidence、历史及写操作。
- [ ] **F14（本轮不做）** 「未来选择反馈」（实际选项、情境、事后认可）；待共同定义字段与采集时机后再议。
  - [back] 2026-10-04：此行标题保留历史；当前 F14 已解除延期，实际／认可标签、独立 consent、审核 impacts 与反馈专用 activity 按 hybrid-learning-plan.md 和 api.md 草稿交接。功能／前端验收未完成，保留 [ ]。

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

- [back] 2026-10-01 本机试用评估与 model-only Reset：基础录入／预览／双确认／effect／撤销链路可开始小规模本机试用，不等于真实自我拟合／选择预测已验证。F6 后端已完成，但当前 RemoteBrainAdapter.proposedMethods 仍默认 false，前端须启用并补验收；本轮不修改 src/。缺少口令／加密／保护备份，不建议先导入最敏感材料；原生故障、release Python/jieba 打包、在线 CI 与真实留出验证仍待办。
- [back] 2026-10-01 用户确认 Reset 只清零 personalized model、保留 translator 的理解学习。已提供本机管理命令（不是隐藏 API，也不是前端按钮），具体操作见 back-end-core/docs/model-reset.md：先停止使用该库的 app/backend，指定已有绝对 DB 路径，reset-info 取轮次／修订，再 reset --confirm RESET_MODEL --expected-epoch N --expected-revision R。三个分区回到 0/support=0/observed=false；原文、词汇、显式纠错支持、认可、候选记忆及历史保留。旧贡献通过模型轮次隔离，新输入／重启不自动恢复，只有用户明确 review(...,agree=true) 才重新纳入选中的旧来源；保留 translator 不等于整个系统出厂重置。确认短语不是身份认证，口令门继续延期。
- [back] 2026-10-01 前端新增接线待办：health.model_epoch；input_get/list/page/edit 的 model_active/model_epoch；正式 effects 的 model_epoch（历史值不改写）。status=agreed 现在可为 model_active=false，代表“仍认可但不属于当前模型”，不要标成当前已训练。已认可但旧轮次的材料仍不能 preview，重新纳入要用户主动 review，不能连接时自动补确认。Reset 后重连刷新 health/state/列表第一页、清除缓存和旧在途操作，不能播放旧轮次 effects；旧游标必定 STALE_CURSOR。schema_version=1、23 个 JSON API 方法不变，新增元数据允许旧 v1 结果缺省。Reset UI／live reset endpoint 留待前后端另行定义验收。
- [back] 2026-10-01 本轮验收：177 项后端测试（含 14 项 schema 校验）、7 项 translator 测试、13 项 Rust 宿主测试通过；使用系统 Chromium 的 6 项真实 Python 前端链路测试在 Reset 改动后再次全通过，npm run build／typecheck 与 git diff --check 通过。Playwright 初次缺少下载版 Chromium，已用 ALPHA_CHROMIUM=/usr/bin/chromium 复跑。Vite 仍有 >500 kB chunk 警告，未修改前端分包；这些结果不等于原生 GPU／release runtime／真实材料效度验收。本轮 Reset 只在合成材料与临时库上执行，未重置／访问用户实际运行数据库。

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

### [front] 2026-10-01 对 [back] 最新回复的前端接线

- F6：`probe` 在 `health.methods` 含 input_edit/input_delete 且 `features.source_edit/source_delete` 都为 true 时自动启用；编辑只对非 agreed 开放（agreed 须先撤销）；任意状态可删除（二次确认，文案不宣称彻底擦除）；编辑／删除成功后重载第一页（旧游标必定 STALE_CURSOR）并重读模型状态。已用真实 Python 验收（浏览器链路 `tests/real-backend.spec.ts`、适配器 `tests/backend.spec.ts`）；原生窗口里的编辑／删除尚未验收，先不标 ////。
- U+0000：前端任意位置拦截；mock 与后端一致返回 INVALID_ARGUMENT；旧的 STORAGE_ERROR／21 个方法／source_edit=false 断言已更新为 23 个方法。
- 模型重置：读取 `health.model_epoch`、行上的 `model_active`/`model_epoch`、effect 的 `model_epoch`；`agreed` + `model_active=false` 显示为“仍认可但不属于当前模型”，并提供「纳入当前模型」（即 `review(agree=true)`），不自动补确认；旧轮次 effect 标「旧模型轮次」。重置后需重连（新 generation 会清掉缓存和在途操作）；没有 reset 按钮／接口，留待另行定义。
- evidence_policy v2 的 `other_subject_value` 前端已有中文标签，未知 reason 仍显示原值。
- 仍未做：F13 口令门、F14 选择反馈、原生窗口 F6 验收、release 构建与 Python/jieba 打包、真实 GPU 验收。

### [back] 2026-10-01 终端追踪与前端接线确认

- 已读取并核对最新 F6/NUL/model_active/model_epoch 接线：probe 按真实能力启用编辑／删除，旧轮次已认可材料的「纳入当前模型」是主动 review，不自动补确认。浏览器验收与原生验收分开记录；原生 F6／故障重连仍待办，不标 ////。D62 动画为前端交付，本轮不修改／重验动画，也不修改 src/ 或已有前端暂存变更。
- 用户要求的 terminal 实时状态已实现：CLI/API 默认通过 stderr 即时打印 [alpha.model] JSON，含接收、保存到数据库地址、双确认、正式拟合／恢复、参数 before/after/delta/support/revision/epoch、撤销／删除与 Reset 状态。成功与参数日志只在事务 commit 后输出；回滚不输出虚假的已训练／参数更新。preview 不打印实际训练，零参数 effect 拟合与重复认可也明确区分。
- Rust 宿主原先丢弃全部 stderr，现只转发经字段／值白名单校验的状态日志至启动终端；普通 stderr、异常堆栈与任意原文仍丢弃，单行最多 4096 字节，不写自动磁盘日志。stdout 信封、23 个方法及 schema_version=1 不变，不需前端新增调用或修改协议。用终端重新启动 npm run tauri -- dev 即可跟踪实际桌面请求；ALPHA_BRAIN_TRACE=0 关闭。详见 back-end-core/docs/terminal-tracing.md。
- 本轮验收：186 项后端测试（含 schema 全量校验）、7 项 translator、14 项 Rust 测试通过；6 项真实 Python 前端链路测试与 4 项适配器/F6/NUL/Reset 元数据检查通过。日志失败／事务回滚／重复认可／零参数 effect／原文不泄漏／stdout 不污染，以及宿主长行与分块过滤均已覆盖；原生窗口新日志展示／F6／GPU 验收仍不据此标完成。测试仅用合成材料、临时数据库，未访问实际用户数据。

### [back] 2026-10-01 18:16 +08:00 Phase 1 范围／决策对齐

- 用户决定已记录，尚非实现交付：当前来源／版本双 true 自动发布候选；已审核语义修订撤回当前贡献后重新取得双确认；F13 访问门与加密备份恢复纳入本轮，当前 SQLite 明文／整库加密在范围外。保留旧候选审核状态、冻结历史 effect 与 model-only Reset 排除；实现、集成和独立验证仍待并行 worker 回报。
- 报告分析需求从当前及延期队列移出，唯一当前范围说明见 `back-end-core/docs/TODO.md`；保留历史对话，不把旧讨论重新当作实现要求。用户没有真实私有留出材料，本轮只交付收集模板／工具；真实覆盖／预测效度未验收，F14 仍延期。
- 最新前端 F6 能力启用与 model_active/model_epoch 浏览器验收已完成；原生 F6／Reset／故障重连、大列表、release runtime、真实 GPU 与在线 CI 继续待办。上方历史“mock-only／待启用／F13 延期”按此及最新接线记录解读；不新增 API 或宣布 worker 功能完成。
- 后续文档交接：各 worker 提供修改路径、实际接口／版本、命令与结果、合成／临时库范围及未验收项；API／schema 由后续集成负责人同步，评估、安全／恢复、桌面发行说明由各负责人同步。协调者审核证据后再更新本 TODO／账本，浏览器、原生、软件渲染和真实材料验收分别记录，不暂存／提交／推送。

### [back] 2026-10-02 最终文档对齐

- schema_version=1、contract_revision=2、30 methods。fresh 双 true 自动发布 authored candidates，legacy pending/rejected 不变。guarded typed correction/version review/selected replay 已交付，非一般语义重标 ML 或 causal graph，其他冻结拟合不重算。
- F13 LOCKED 覆盖私有读写，malformed unlock 清授权/cache，CLI/eval 复查 session。Argon2id gate、XChaCha20 encrypted backup/fresh target restore、readiness/eval 模板工具已交付；SQLite 明文及 same-OS-user 限制保留，无真实效度证明；reset 保留 translator。MMPI 无 active/deferred queue，F14 延期。
- preview.translation 反映 active corrections，保留原材料/evidence spans，非 raw translator output。frontend unlock/cache/version UI、F6 version=0 queued review/future content-revision guard、typed retranslation performance 仍待办；见 frontend-contract-handoff.md。
- main 验证 backend283/no skips、translator7、Rust16、release tests3、typecheck、fmt/whitespace、独立 runtime/security/artifact hashes passed。Linux x86_64 glibc>=2.34、nonstatic GTK dependencies；Xvfb DOM F6/paging137/persistence passed。faults pending，当前 EOF harness 未选状态在 submit 前失败，不记 fault pass。admin reset/reconnect、physical input/GPU、online CI/Python3.10、真实 hold-out coverage/prediction 仍 pending，无 macOS/Windows claim。
- 保留 user/concurrent frontend 修改，不宣称最新前端全部验证；仅文档，无代码/前端/Git/live DB 修改。剩余 native 结果由 main 记录。

### [back] 2026-10-02 最终 native DOM fault 验证

- main 执行 `python3 scripts/native/run.py --resources /tmp/alpha-runtime-20261002 --output /tmp/alpha-native-faults-20261002 --cases fault-eof fault-invalid fault-timeout`，exit 0；summary passed=true，三个 report 均 passed=true。
- 报告：`/tmp/alpha-native-faults-20261002/fault-eof.json`、`/tmp/alpha-native-faults-20261002/fault-invalid.json`、`/tmp/alpha-native-faults-20261002/fault-timeout.json`。每项覆盖 actual native DOM startup failure + explicit reconnect、ambiguous submit + explicit read 恢复恰好一条；fixture method logs 恰好一次 submit，no_write_autoretry=true。
- real/persistence + 三个 fault，共五个 native DOM scenarios passed。此前 process inspection / 未选 partition 的初始失败属于 harness failure，非 product failure；保留历史，由最终 main 验证覆盖其待验状态。
- administrative model-reset/reconnect、physical input/GPU、F13 unlock/cache UI 仍 pending；不宣称最新 frontend 全部验证或真实数据效度。仅最小文档状态同步，无代码修改或重复测试。

### [back] 2026-10-03 Hybrid 项目授权与文档阶段（main-authored synthesis）

- 用户现已授权 hybrid 项目开发，**F14 不再延期**。本追加记录覆盖上方历史「F14 deferred／本轮不做／仍延期」的范围状态；历史正文保留。当前执行仅为文档编写，新增能力尚未实现。详细主线、阶段、签名草案、复制位置和验收边界见 [hybrid-learning-plan.md](back-end-core/docs/hybrid-learning-plan.md)。其余未编辑文档中的 F14 延期文字是旧状态，不代表本次拒绝授权。
- 新项目工作目标：本机 hybrid 理解＋带可编辑证据的记忆＋显式选择偏好 ML。材料 `immediate/confirm` 双 T/F、`actual_choice` 实际选择、`endorsed_choice` 理性事后认可分别记录；双 true 不产生选择标签或 F14 训练同意。目标不是 digital-self、心理诊断或 MMPI；检索相似度不是事实真值，排序／softmax 分数不是已校准的真实选择概率。
- 已静态核对当前栈：React 19／TypeScript／Vite 7，**Tauri 2**（package.json CLI ^2.12.0；Cargo.toml tauri/tauri-build major 2；锁文件 tauri 2.11.5、tauri-build 2.6.3、CLI 2.12.0），不是猜测的 Tauri 3。后端 Python >=3.10、SQLite、现有 jieba 词汇／分词；`core.api`、api.md、api.schema.json 和 revision 2 handoff 当前仍为 schema_version=1、contract_revision=2、30 methods。
- 技术主线：可选 SentenceTransformers／PyTorch CPU 冻结预训练 encoder（无需 LLM）；BGE-M3 仅候选，未在本阶段安装／验证。先写离线接口与合成替身，不下载模型权重。首个选择 ML 基线为纯 Python 正则化 multinomial logistic，使用当前八个 `value.*` 的显式、有限 [-1,1] 选项 impacts；按 target／partition／domain 隔离，ML 权重按显式请求从合资格反馈派生，证据记忆仍在 SQLite，不写入模型权重。小 MLP／LoRA 只有独立留出增益支持后才考虑。
- 目标设置工具状态记录：用户提供的既有记录为 **BLOCKED：unfinished prior goal，usageLimited**；保留该阻碍，不覆盖／完成旧目标。本阶段只在项目文档记录新 working goal，没有创建工具目标，也没有创建产品 active goal。本次只读 `get_goal` 返回 goal=null，未复现历史拒绝；不把用户提供的历史状态伪装成本次失败或当前已创建目标。

- [ ] **P0｜契约／访问发现与主验收基线**：从当前 30 methods rev2 与 AccessSession 出发，核对 public/private gate、授权／全局 revision／source_version／epoch 和旧 F6 排队操作边界。静态发现已记录，阶段实施与 main 验收未完成。
- [ ] **P1｜可选本机语义编码与检索**：计划 evidence-gated `memory_search_semantic`，仅 accepted＋agreed＋当前 source_version 的记忆参与，分区先筛选；禁用／缺失 encoder 时 lexical fallback disabled，不静默改用字面检索。既有 `memory_search` 保持单独的显式字面方法；不持久化 embedding cache，不训练 encoder，不因检索发布候选。
- [ ] **P2｜F14 显式反馈与选择偏好基线**：计划 guarded `choice_feedback_set/get`、只读 `preference_rank`。approved source＋current source version＋current epoch＋独立明确 training consent 才能拟合；actual／endorsed 分开，跨 target／partition／domain 不混训。删除／编辑 purge 反馈与派生贡献；reopen／revoke 使旧贡献失效；Reset 排除至明确重新纳入，不自动恢复。读取／推断不训练；拟合触发、未定结果字段和不足样本阈值留给实现契约，不由文档自选行为。
- [ ] **P3｜分组／时间留出评估**：沿用 readiness／evaluation 模板和授权只读 snapshot，再补 hybrid 多 target／partition／domain 评估及泄漏保护；保留训练暴露、复制／改写分组、冻结时间和独立盲标。现有工具不等于新 ML evaluator 已实现；合成验证不声称真实预测效度。
- [ ] **P4｜前端／native／离线模型发行交接**：前端 owner 负责 unlock/cache、F14 标签及 consent、能力探测／版本、只读与训练显示；host/release owner 负责 native、离线模型 manifest／打包与硬件性能。后端不写 `src/`。现有 release/native 基线不等于新模型、F14 或 physical GPU 已验收。

- 新方法仅 **PROPOSED / planned, not implemented**，不属于当前 30-method schema；未来实现须由各 owner 同步 api.md、api.schema.json、handoff、host 和前端能力探测，并经 main 证据验证后才勾选。此处没有把授权写成实现，也不重新声明旧测试已在本轮复跑。
- 本轮只追加本文件并新建计划文档，使用 apply_patch；未编辑 `src/`、用户现有 `translator/discourse.py` 变更或其他文件，未读取／导入／训练真实私人数据，未访问实际用户数据库，未下载模型权重，未 commit/push。**No real data used.**
- 官方依据：[SentenceTransformer API](https://sbert.net/docs/package_reference/sentence_transformer/model.html) 支持本地路径、CPU、local_files_only 与 encode；[BAAI BGE-M3 model card](https://huggingface.co/BAAI/bge-m3) 描述候选 encoder。它们支持接口研究，不证明 Alpha 已装好模型、中文语义正确或 CPU 性能合格。

### [back] 2026-10-03 暂停检查点（覆盖上方本轮草稿的冲突描述）

- 用户要求 **pause for today, save progress**；开发代理已停止，既有工具目标返回 `status=paused`。主代理此前 create_goal 因本线程已有未完成目标而被拒绝；新 hybrid 项目目标记录在文档，未创建新的工具目标、未标成完成。上方“用户提供 BLOCKED／本次 get_goal=null”是文档代理线程的误记，不是主线程工具事实。
- 接续入口：[hybrid-learning-checkpoint-2026-10-03.md](back-end-core/docs/hybrid-learning-checkpoint-2026-10-03.md)。实现草稿和未验收测试保留在工作树，无 commit/push；保留并行前端与用户已有修改，不访问真实材料/数据库、不下载模型权重。
- 已确认：F14 解除延期，实际/事后认可选择独立，来源双 true 不代替选择标签或 training_consent；首版由前端显式提供 impacts 并由用户审核。
- 技术栈：Tauri 2（已有宿主）＋Python >=3.10/SQLite/jieba；可选 SentenceTransformers 6.1.0/PyTorch CPU 冻结 encoder；纯 Python L2 multinomial logistic 的 8 个偏好特征，与现有 13 个规则参数独立。参考代码已克隆至 ext-refs/sentence-transformers，无权重和真实模型验收。
- 当前目标流程：`文本 → AccessSession → 规则/纠错 → 来源双确认 → 证据记忆 → 可选本机向量检索`；另一条为 `显式选项/审核 impacts + actual/endorsed + training_consent → 当前来源/版本/epoch 筛选 → 临时偏好拟合/排序 → 解释或拒答 → 后续留出验证`。
- 更正草稿：未配置 encoder 时，新检索接口明确返回 `lexical_fallback`，配置后失败则报错；偏好 domain 为 daily/study/relationships。当前 preference_rank 草稿会按请求从合资格快照临时拟合，不写 DB、不训练 encoder，**不是“从不调用 fit”**。新接口参数为闭合的显式字段，不是任意 feedback 字典。
- 已保存 semantic/preferences 模块与测试、API/来源清理/schema 草稿及计划。代码尝试声明 revision 3 / 34 methods，但契约、文档、安全兼容和全量回归尚未完成，前端 **不要据此启用新能力**。
- 最后已观察证据：semantic 25 项合成测试通过（早于最后修改）；集成中间态 27 项有 7 failures/6 errors，后续草稿未复跑。首要实际问题是新反馈表尚未进入 backup.validate_database 的严格参考 schema，导致 setup_access 失败；下次先补旧/新库与备份/恢复兼容，再统一反馈字段/schema/tests/docs。离线预检、最终回归、新偏好留出工具、前端/native/模型硬件验收均未完成。
- **暂停状态：未交付 hybrid 新能力、没有真实效度证明；暂不要在真实运行库启用/迁移本轮草稿。** 保存进度后不继续开发，等待用户明确恢复。

### [back] 2026-10-04 恢复与文档审计（新 hybrid 未验收）

- 用户已明确恢复开发。主线程 `01a0ece3-759d-7ec0-bccc-4157827f3358` 在本轮开始实际 `get_goal` 返回 `status=active`、objective=`continue build back-end`、tokensUsed=1773028；这是主线程提供的目标证据，不是文档 worker 的 goal=null。Oct 3 pause/create_goal 拒绝只保留为历史，不描述当前状态。项目范围继续为本机个人 hybrid 理解／证据记忆／显式选择偏好，不宣称 digital-self 或真实效度。
- 当前静态事实：`core/api.py` 声明 schema_version=1、contract_revision=3、34 methods。Oct 2 rev2／30 methods 主验收是历史基线；新表曾破坏 protected setup/access/backup 严格校验，backup owner 已实际复现该 gate error。当前兼容修复草稿正在核对，不把源码存在或中间结果写成最终通过。
- 更正 Oct 3 初稿：未配置 encoder 返回明确 `mode=lexical_fallback`（score=null），配置后的 provider/path/load/encode 失败返回错误（MODEL_UNAVAILABLE），不自动回退；domain 为 daily/study/relationships。反馈为闭合的平铺字段，非 `feedback: dict`，实际签名／结果见 api.md。F14 独立 actual/endorsed、training_consent、前端显式 impacts 与用户审核缺一不可。
- `preference_rank` 按请求在通过来源双确认、版本／内容摘要、反馈 epoch 和独立 consent 筛选的快照上临时 CPU 拟合再排序；返回快照 input_revision/model_epoch，不写 DB、不保存权重、不训练 encoder。`choice_feedback_set/get` 不拟合。反馈记录 `model_active` 表示偏好反馈资格，**不同于 inputRecord 的规则模型 model_active**；Reset 后须明确 guarded save 重新纳入反馈，不因规则 re-review 自动恢复。
- 技术栈及两通道完整流程见 [hybrid-learning-plan.md](back-end-core/docs/hybrid-learning-plan.md)：React/TypeScript/Vite → Tauri 2 brain_call → Python AccessSession；规则/证据记忆/可选冻结 SentenceTransformers＋PyTorch CPU 检索，与 flat F14 labels/consent/impacts → 独立纯 Python L2 logistic 临时拟合/排序分开。真实 encoder 权重、资源性能、语义质量与选择效度均未验证。
- 中间证据（主线程转交，非最终）：`/tmp/alpha-verify-20261004.tPaapz/bin/python -m unittest tests.test_semantic_encoder tests.test_preferences -q`，semantic 35＋preferences 28 项通过，0 skips，无 heavy dependencies；**早于当前 offline protection 更新**。不据此勾选新 hybrid，也不替代 access/backup/schema/full-suite 的最终验证。Oct 3 的 25 pass 与 27 项 7 failures/6 errors 是更早历史快照。
- Oct 2 native 报告路径／命令保留在上节；此文档 worker 本轮未找到对应 /tmp 报告，因此使用既有 main 验收记录，未声称重新执行或当前 artifact 仍存在。

- [ ] **Hybrid 契约／安全兼容主验收**：main 提供最终版本、34 方法 request/result schema 一致性、旧／新库及严格异常 DDL、protected setup/access/backup/restore 的独立命令／结果／报告后再更新。
- [ ] **Hybrid semantic／preferences／lifecycle 主验收**：最后 offline protection 修改后的模块与全量回归，授权／快照竞态、F6 purge、reopen/revoke、Reset 明确反馈再纳入及 no-write/no-encoder-training 证据待 main；中间 35＋28 pass 不足以勾选。
- [ ] **Hybrid 分组／时间留出工具与真实效度**：新偏好评测交付及最终主验收待确认；真实独立语义覆盖／actual 和 endorsed 预测效度仍未验证。
- [ ] **Frontend／native／发行与物理验收**：unlock/cache、guarded version UI、F14 标签/consent/审核 impacts、行政 Reset 重连、新 encoder 离线发行/资源测量与实体输入/GPU 待各 owner 验收；在线 CI/Python 3.10 仍待办。

- 文档审计部分仅修改指定文档；既有 [front] 发言、历史日期／结果及已勾项上下文保留。完成任务统一 `//// - [x]`，部分完成类别维持 `[ ]` 并逐项注明；文档 worker 未改源码／前端／Rust／schema，未访问 live DB、私人 corpus、weights、网络或 Git。已向 main 请求最终独立验收证据；未收到前不勾整体 hybrid 阶段；已测试安全子任务不代表整体完成。

### [front] 2026-10-04 前端状态核对（对照上方全部条目）

- 前端负责且已完成：F1–F5/F7–F12 接线；F6 能力探测启用（浏览器真实 Python 验收）；U+0000 全位置拦截；model_epoch／model_active 显示与「纳入当前模型」；evidence_policy v2 标签；`input_page`＋STALE_CURSOR；`brain_call` Transport；D62 crazy 坍缩动画。均已有测试，见 2026-10-01 各节。
- 前端仍待办（`src/` 中尚无任何实现，grep 无 `LOCKED`／unlock／choice_feedback／preference_rank／source_version）：
  - [ ] F13 解锁界面＋私有缓存失效（`LOCKED` 处理、malformed unlock 清缓存）。
  - [ ] 版本同意 UI／`source_version`、F6 version=0 排队操作丢弃（见 frontend-contract-handoff.md）。
  - [ ] F14 选择反馈（actual／endorsed／training_consent／显式 impacts）与能力探测；**后端 revision 3／34 methods 仍是暂停草稿，前端不据此启用。**
  - [ ] 原生窗口 F6／model-reset／重连验收（目前只有后端 main 的 Xvfb DOM 记录和前端浏览器记录）；真实 GPU／帧率验收。
- 无需前端动作：Reset 无按钮／接口，留待另行定义；其余 [back] 待办（CI、评估、打包）属后端。
- 提醒 [back]：`test-ref-data/mental.txt`（含私人日记）已在提交 b2ba2a4 进入 Git 并已在 origin/main，与 material-import-static-review.md 的「保持本地、不入 Git」冲突，待用户决定处理方式。

### [back] 2026-10-04 中间验证追加（保留上方 [front] 原文）

- main 独立执行 `TMPDIR=/tmp/alpha-verify-20261004.tPaapz /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest tests.test_hybrid_api tests.test_schema_contract tests.test_access_api -q`：39 pass／0 skips，27.496s；worker 仍在增加检查，不是最终全量验收。
//// - [x] **Hybrid 安全兼容已测试子任务**：backup owner 完成 brain_choice_feedback 可选表／索引的精确参考 schema 支持，保留 unknown/tampered DDL 拒绝；tests.test_hybrid_backup 12 pass／0 skips，security/access/evalaccess 54 pass／0 skips，main 已看过 6 行实现补丁。此勾选只表示 owner 测试＋main 代码审核的子任务证据，不表示完整 hybrid 主验收。
  - [back] 2026-10-04：具体严格 schema 路径为 core/backup.py validate_database；测试路径 back-end-core/tests/test_hybrid_backup.py、test_security.py、test_access_api.py、test_evaluation_access.py。精确 owner 命令／最终全套结果仍由 main 提供，此处不杜撰或称已独立重跑。
- [ ] **Hybrid 最终全量主验收**：最终 offline protection、semantic/preferences/evaluator/schema/access/backup/lifecycle 所有变更后的独立 full-suite 命令／结果待 main。上面的新安全子任务和 35＋28／39 项中间通过不改变整体 [ ]。
- [back] 2026-10-04：上方 [front] 的全部 Oct 4 文字／复选框原样保留。其「暂停草稿」措辞为当时状态；用户现已恢复，但 backend 最终 34-method 证据尚未提供。main 完成后再明确通知 frontend：后端契约通过，不等于前端 34-method 接线／unlock/version/F14/native 已验收。
- [back] 2026-10-04：用户已对上方历史隐私提醒答「不管」，记录 no action；保留 [front] 原文。文档审计未访问 Git／远端或移除文件／修改历史，不再追加相关警告。

### [back] 2026-10-04 偏好验收阻碍与审计收尾

- API owner 最新 targeted 151 项 distinct tests pass；main 已完成下方独立回归。新 hybrid 未最终验收，以下偏好阻碍即使测试通过也须单独解决／验证。此审计不实施修复或新增 P3 实现。
- 以下为 Mencius review 转交的具体阻碍，非文档 worker 独立复现实验：
- [ ] **偏好内存预算**：最多 1000 来源的整份 body 缓存，40×1,000,000 ASCII 合成约 40MB、潜在约 1GB；改为有明确预算的 provenance/digest 筛选，避免全部原文同时驻留；验证来源数／文本上限的峰值内存与输出一致性。
- [ ] **收敛与 near-tie 拒答**：固定 400 iterations 与 4000/Newton 对照出现 winner reversal；定义可测收敛／误差界和不稳定 tie 的 abstain，验证 loss/gradient／排序及排列稳定性。
- [ ] **巨大整数权重边界**：huge integer weight 的 float 转换可 OverflowError；校验数值／类型与安全错误响应，补边界回归，拒绝泄漏或进程崩溃。
- [ ] **反馈 provenance／复制 group 独立性**：3 个不同 source_id 只是数量门，不证明独立样本；明确复制／改写／同事件 group、暴露／标签 provenance 的资格和评估隔离，验证复制不虚增支持。
- [ ] **contrast span／外推限制**：used_features 单特征覆盖不足以证明新 option contrasts 位于训练可识别方向；定义 contrast 子空间／不可识别组合的拒答，验证共线与新方向外推。
- [back] 2026-10-04：用户 `test-ref-data/split/` 及其他并行修改保留、未检查。文档审计只操作指定五份文档，保留历史与前端新发言；偏好阶段保持未接受，真实语义／weights／选择效度未验证。
- [back] 2026-10-04 最新主线程证据：此前所有「full discover 仍运行／结果待 main」均为中间状态，以下实测记录覆盖它们。访问／备份兼容子任务不再仅据 worker 报告；main 独立 `tests.test_hybrid_backup` 12 pass／0 skips，11.220s。
//// - [x] **已完成子任务｜本轮合成回归与最终 semantic 复跑**：在 `back-end-core/` 执行 `TMPDIR=/tmp/alpha-verify-20261004.tPaapz HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest discover -s tests -q`：396 tests、134.672s、OK、0 skips。随后同一环境执行 `-m unittest tests.test_semantic_encoder -q`：51 tests、1.142s、OK、0 skips。最新 discovery 有 398 项，新增的两项 semantic 测试已由后一次复跑覆盖；不声称一次执行过完整 398 项，不相加为互不重复测试数。semantic 使用合成 export／mock，不是实际预训练模型验收。
  - [back] 2026-10-04：独立复核完成标记格式，全部任务 `[x]` 都带 `////`；`git diff HEAD --check -- front-back-communicate.md back-end-core` 通过。保留并行暂存区和私人材料，不 commit/push。此完成标记只覆盖测试执行与文档审计；上述偏好缺陷、P3、新前端／native／权重及真实效度任务继续 `[ ]`，整体目标未完成。

### [back] 2026-10-04 当前实现续接与文档整合（待最终证据）

- [back] 历史分工／waiting narrative 已由 Oct 5 最终限定证明 supersede；以下精确已完成子任务更新复选框，broad tasks 继续待办。

- [back] 上节 396 full／134.672s、之后 semantic 51／1.142s（discovery 398 的最后两项另行覆盖）及独立 backup 12／11.220s，均为已提供的历史合成证明、0 skips；不覆盖本次后续修改，不宣称新 full 结果。主目标 active、整体未完成；前端／历史／暂存及并行修改保留。
//// - [x] **偏好修复自动化子任务**：Goodall digest-only 筛选缓存、收敛纯 Python solver＋near-tie 拒答、巨大整数 weight 受控 ValueError 已依据下方历史411／fresh proof 限定验收，不完成整个 P2。
//// - [x] **新偏好 evaluator 自动化子任务｜合成工具限定交付**：model/preference_evaluation.py、tests 与 docs/preference-evaluation.md/example.json 四个 owner 文件已交付／核对；冻结 manifest／development groups／production pure fit／先预测后计分／独立 actual/endorsed／coverage/abstain/group metrics，canonical 与 report 接线 final51＋main483 proof 见末尾。不完成 broad P3／baselines／ablation／真实效度。
- [ ] **线上来源组与 contrast span 验收（部分完成）**：线上 reviewed groups 后端子任务已完成（下方 IMPLEMENTATION 勾项／末尾 final proof）；contrast span／不可识别新方向拒答继续待办，used_features 不证明可辨识方向，reviewed ID 也不证明真实独立性。
- [ ] **后续最终验证与 fresh-agent review**：仅 main 已验证自动化子任务可标 `//// - [x]`；P2/P3 整体及真实效度不因测试通过而完成。不接 live DB／导入私人实际数据／encoder weights；文档 owner 只修改指定六份 Markdown。

### [back] 2026-10-05 用户确认决策：审核后的事件组 ID

- [back] 历史 proposal 已 superseded：当前 rev4 字段／review gate／legacy exclusion 已后端限定验收；下方保留原决定措辞及日期，不能据旧 PROPOSED／未来实现文案推断当前不可发送字段。exact-text duplicate hint 尚未实现，仍 TODO。

- [back] **DECISION（已确认，不代表实现完成）**：采用前端显式提供、用户审核后的事件组 ID，草稿字段 `group_id` 为 **PROPOSED**。同一组所有材料的训练 loss 总权重合计一份，不能因多个 source_id、复制／改写／摘录而重复加权；actual/endorsed、partition/domain 仍按原有轴隔离。后端仅提供原文完全重复提示，不推断不同文本属于同一事件，不自动分组或替用户审核。
//// - [x] **IMPLEMENTATION｜后端组字段／审核 gate／group means／legacy exclusion**：Descartes 已完成，main483＋Lagrange／Meitner／Kant 全部验证限定验收；来源组作用于反馈 event，legacy／未知 group 反馈在明确 guarded user-reviewed save 前排除偏好训练，无 backfill／自动认可。归一化每 event1/(G*n_g)、group1/G；最终证明见 [API final proof](back-end-core/docs/api.md#oct-5-final-rev4-backend-synthetic-contract) 及末尾 milestone。前端任务不在此勾项范围。
- [ ] **前端契约／接线验收**：组输入／审核状态／编辑及既有反馈更新协议须 main 和 frontend owner 定稿；`group_id` 及所有未定新字段保持 PROPOSED，当前 API/schema 未据此扩展。离线 evaluator 的 manifest group 隔离不代表此线上 gate 已实现；contrast span 验收仍待办。

### [back] 2026-10-05 偏好修复中间证据（不勾完成）

- [back] main 提供 preferences 36 pass、22.441s、0 skips，早于最终新增 tests；不是最终 worker／full-suite 结果，精确命令待提供。
- [back] main 独立 seed804：修复后 winner=b，margin=`1.0117349352838784e-05`，assert pass；旧 400-step winner=a。此为受控合成反例对照，不是实际选择预测效度，也不覆盖其他收敛／规模边界。
- [ ] **最终验收门**：最终 worker 证据＋fresh reviews＋最终 full-suite 齐备并由 main 确认前，本次偏好／evaluator 新子任务均不标 `//// - [x]`。既有 Oct 4 已验证子项只保留其历史范围。

### [back] 2026-10-05 Goodall 最终交付与主验证中（不勾完成）

- [back] main 转交 FINAL worker：preferences 41＋hybrid 21＋schema 18＝80 tests，128.728s，0 skips。当前 solver 为纯 Python damped Newton／Cholesky，64 steps、32 backtracks、gradient infinity norm <=1e-11、L2=0.1、tie gap tolerance=1e-8；有限数值及 roundoff slack 的 residual 降低 guard。schema 仅新增 fit_not_converged reason enum，未接入线上 group 字段。缓存只留 metadata／digest、逐个 body 分块 hash；rank_from_fit 的巨大整数 weight 在 float 前抛 ValueError。源码参数及资源明细见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md#oct-5-final-worker-proof--mainfresh-acceptance-pending)。
- [back] worker dense 1000-event／8-option fit：2.144934741 CPU seconds、final grad=2.609e-17。40 distinct sources×1m code points／1000 events 的 Python tracemalloc peak：ASCII consent false/true 为 55,959／2,531,834 bytes，Unicode false/true 为 54,423／5,924,752 bytes。这些不含 native RSS；instrumented test 65.940s（含 tracing，CPU 18.66s）不是正常请求延迟。
- [ ] **main scoped base full proof／fresh reviews**：含 backup 的独立验证、基础后端 full discovery 和 fresh preference reviews 正在运行；精确 commands/counts/timing 待 main，不据预期 discovery 数量填结果。P3 tests/docs/example 尚未 ready，当前 base full 不能称最终新工具或 whole hybrid 证明。

- [back] Oct 5 main 转交 fresh antipattern review：no findings，17 pure tests／parity pass；该隔离环境没有 jsonschema，schema 验证由另一个装有 validator 的 full 环境承担。fresh quality review：no blockers，41 preferences pass；uneven mass 7/1/1 的 reference difference=1.18e-12，seed804 gradient=3.26e-15、max weight difference=1.89e-12，Cholesky residual=1.39e-17；另一次 1000-event／8-option 观测为 1.48 CPU seconds，仍非请求延迟保证。
- [ ] main 92 项验证与 scoped base full 411 项仍运行，结果未到；两者通过后仅勾 **digest 缓存／收敛 near-tie／巨大整数边界** 三个有限修复子任务，不勾线上 source groups、contrast span、整个 P2 或 P3。

- [back] Oct 5 evaluator 路径核对：Zeno 报 47 tool tests，但三个新 tests/docs/example 文件误建于根目录；main 已要求该 owner 用 apply_patch 修正为 back-end-core/tests/test_preference_evaluation.py、back-end-core/docs/preference-evaluation.md、back-end-core/docs/preference-evaluation.example.json。文档整合不移动／修改这些 owner 文件、不链接根目录错误产物。修正后在 back-end-core 执行 tests.test_preference_evaluation 的精确命令／结果及 fresh tool reviews 待 main；411 base full 不包含这 47 项。

### [back] 2026-10-05 基础修复有限验收（不含 P3）

- [back] main 在 back-end-core 独立执行 `TMPDIR=/tmp/alpha-verify-20261004.tPaapz HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261004.tPaapz/bin/python -B -m unittest discover -s tests -q`：411 tests、170.066s、OK、0 skips；执行早于 P3 测试迁移，明确不含新 evaluator。此证明更新上节「411 仍运行」，不是 whole hybrid／P3 final proof。
- [back] FreshVerifier 92 tests（41 preferences＋21 hybrid＋18 schema＋12 backup），85.576s、无 failures／skips；fresh antipattern 17 pure 与 quality 41 均 no findings／blockers。main supplemental live API（合成临时测试调用，不是用户 live DB）验证 fit_not_converged 的完整 schema、0 SQL writes、0 encoder calls，source hashes unchanged；精确补充命令未提供，不杜撰。
//// - [x] **已完成有限修复｜digest-only 筛选缓存**：逐个 source body 分块摘要、缓存 metadata／digest，流式 feedback 和仅训练字段；40 distinct 1m-code-point sources／1000 events 合成内存证据通过。只验收此次修复与 Python tracemalloc 范围，不声称 native RSS／正常延迟／线上 group 独立性。
//// - [x] **已完成有限修复｜收敛与 near-tie 拒答**：64-step／32-backtrack 纯 Python Newton、gradient infinity norm <=1e-11、L2=0.1、tie gap <=1e-8、residual-guarded slack，fit_not_converged reason 与 fail-closed/no-write 合成证据通过；seed804 对照及独立 reference／Cholesky residual 由 main／fresh reviews 确认。
//// - [x] **已完成有限修复｜巨大整数 weight 受控错误**：rank_from_fit 在 float 前验证 bounded finite weights，巨大整数抛 ValueError；对应 preference/hybrid/schema 边界回归通过，不新增外部 fitted-weight JSON endpoint。
- [ ] **后续范围**：source-group field/review gate/legacy exclusion、contrast span、整个 P2、P3 工具最终证据／fresh reviews、真实效度、frontend/native 均未完成。正确路径已出现的 [evaluator 说明](back-end-core/docs/preference-evaluation.md) 与 [合成 manifest](back-end-core/docs/preference-evaluation.example.json) 可供核对，交付验收仍待 main；未链接根目录错误产物。

### [back] 2026-10-05 quota 恢复续接：新基线证明与未验收改动

- [back] 历史 recovery sequence：以下 intermediate pending 叙述由末尾最终接受记录 supersede，早期测试数保留原有 scope，不再代表当前 waiting。

//// - [x] **限定已完成子任务｜fresh rev3 baseline 全量回归**：main 转交终态，在 `back-end-core` 执行 `TMPDIR=/tmp/alpha-verify-20261005.SHU7GE HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 /tmp/alpha-verify-20261005.SHU7GE/bin/python -B -m unittest discover -s tests -q`：458 tests、181.564s、OK、0 skips。发生于零 impact canonicalization 修复及 rev4 group 改动之前；只验收该基线回归，不接受随后变更、P3 工具或整个 hybrid。原 411／170.066s 历史证明及三个有限修复勾项保留。

- [back] 旧 main job 97510 的终态缺失、旧临时环境已消失；UnknownProcess 不作为 pass 证据。fresh job 9839 提供上述终态。新临时环境 Python 3.14.7／jsonschema 4.26.0，PyNaCl 为继承依赖，不是永久 runtime／发行环境证明。agents 已可用，历史 quota 记录不是当前阻碍；main broad goal 仍 active。
- [ ] **P3 工具修复与 fresh verification**：Lorentz recovery 47 tests 发现 omitted zero／等值 numeric impacts 可绕过复制 identity，造成指标虚增。Pauli 最终 targeted proof 为 68 pass＝51 evaluator（47 old＋4 new）＋17 pure，使用 Oct 5 临时环境、早于 concurrent groups partial edits。独立 Lorentz re-review＋fresh anti/code-quality 尚进行中；main overlapping evaluator51 遇 WIP MIN_SOURCES NameError，不作为验收。待 settled-code 新证明，不勾最终 P3，不替 evaluator owner 改文件。
- [ ] **rev4 分组实现／契约验收**：Descartes 已于 fresh baseline 终态后开始写入，拟维持 34 methods。`group_id:string|null` 可选、`group_reviewed:bool=false` 仍 PROPOSED handoff，允许草稿保存；legacy 原存储 payload 精确保留，读时 normalize 为 unknown/unreviewed，在明确 guarded user-reviewed save 前排除 online eligibility。须同时满足 training_consent、来源双 true、version/body_digest/epoch 与组审核。
- [ ] **组计数／事件范围**：每 reviewed group 总 loss mass=1，至少 3 个 informative training_groups；training_sources 独立计 actual source IDs。pure-fit legacy caller 自行筛 provenance，可 source-ID fallback 供离线使用，不赋予 online／UI 训练资格。反馈 group 是 EVENT，不是整份 txt。自动 exact-text duplicate hint 仍 TODO；后端不推断不同文本属于同事件、不自动审核。
- [ ] **下一安全动作**：最终 owner source／signatures／reason statuses 和新 main/fresh proof 到齐后，核对真实接口与当前技术流程再同步六份文档；仅已验证子任务标 `//// - [x]`。contrast span、P2/P3 整体、真实 held-out／calibration／weights／GPU、frontend/native 保持 pending。
- [back] 常规 portable CLI 从 `back-end-core` 执行 `python -m model.preference_evaluation --manifest docs/preference-evaluation.example.json`；可加 `--validate-only`。合成示例／完整说明见 [README](back-end-core/README.md#oct-5-verification-recovery-and-next-integration)，不要求永久保留临时测试环境。此文档整合只改授权六份 Markdown；Oct 4 [front] 留言及其他 owner 编辑保留，未改代码／测试／schema／evaluator docs，未 stage/commit/push，未接 real corpus／DB／weights。

//// - [x] **有限验收｜numeric-copy canonicalization 子修复**：Pauli 68 targeted pass（51 evaluator＝47 old＋4 new，17 pure；早于 group WIP）；Lorentz 独立 51 evaluator／4.258s／0 skips，module hashes unchanged。八项 actual/endorsed intfloat／0／0.0／-0.0 反例复核，heldout 与 macro=0.5、devrecords=4 稳定，fit／predictions identical。Mill fresh static quality 与 James fresh static anti 均 no blocker；James AST 2 parse／51 testdefs inspected，不计 runtime。只勾该子修复，不勾 whole P3。
- [ ] **后续 report／group final**：Pauli 小型 report 集成接 `fit['training_groups']`，须 settled-code 最终复跑；main evaluator51 session37713 已启动，未提供结果。group owner checkpoint 92 existing／91.197s／0 skips，另 18 new／7.916s／0 skips，非最终 full；final schema／backup additions 与 fresh verification／quality／anti 进行中。groups 仍 PROPOSED／未接受，待 exact final code/tests。P3 baselines／ablation／真实效度及前端任务继续待办。

//// - [x] **有限交付｜合成离线 P3 tool provision**：Pauli 最终接 authoritative fit['training_groups']、回归 sources/groups 区别，51 evaluator／4.695s／0 skips；main settled-code evaluator51／4.139s／0 skips（session37713）。canonical 不变，独立 Lorentz51／4.258s＋八项 repro及 Mill／James no-blocker reviews 保留原有证据范围。只勾合成工具交付，whole P3／baselines／ablation／真实效度继续待办。
- [ ] **rev4 已实现待主验收**：owner 八路径完成，实际 choice_feedback_set 可选 group_id:str|null=None／group_reviewed:bool=False；全部返回 feedback 含 normalized 两字段。health rev4／34／reviewed_event_groups=true；training_sources 实际 informative IDs，training_groups 另计且 min3，reason=insufficient_training_groups。新 20 group＋19 schema＝39 tests／34.034s／0 skips；旧 92／91.197s 分开保留。新 group test 覆盖 encrypted reviewed＋exact legacy payload backup／DDL／no-backfill，原 backup 文件未改。main full 与 fresh3 reviews 已启动，字段从 PROPOSED code 更新为 implemented-awaiting-acceptance；最终勾选及当前契约 header／health table 切换待 main＋reviews，不推断 frontend 完成。exactduplicatehint 仍 TODO。
- [back] **当前数学定义**：本 target/partition/domain 有 G 个 informative groups，组 g 有 n_g 个 informative events；event loss weight=1/(G*n_g)，group 总贡献=1/G。objective 为 group means 的均值＋L2/2||w||²。「一组一个权重单位」是组间平均前的单位，不是归一化后 mass=1；早期带日期提案保留为历史。计数门不证明真实独立性。

### [back] 2026-10-05 FINAL：rev4 后端合成契约限定交付

//// - [x] **Reviewed-groups 后端契约交付**：rev4／34 methods，health.features.reviewed_event_groups=true；choice_feedback_set 可选 group_id:str|null=None、group_reviewed:bool=False（true 要求非空白1–128码点 ID，无 NUL/surrogates），draft 可保存；所有返回 feedback 均含 normalized 两字段。legacy exact stored payload 不 backfill，null/false 未审核反馈排除至 guarded user-reviewed save。rank.training_sources 计实际 informative IDs，training_groups 独立计且 min3，reason=insufficient_training_groups。
//// - [x] **最终合成验证执行**：main session28196 exit0，483 tests／121.151s／OK／0 skips，覆盖 final numeric canonical＋group20＋schema19＋evaluator51 report integration。Lagrange focused51（20groups／19schema／12backup）19.543s／0 skips，另 independent3／7.380s／0 skips；62 tracked hashes stable，legacy DB bytes 两次重启不变、onlineaxes isolated、unequalgroups 符合独立 scalar equal-mass reference、network0／DB 全部 temp。Meitner8 targeted／7.990s／0 skips＋all34 parity／12axes；Kant9 pure＋8guards，三份 reviews 均 no blockers。精确 main／focused 命令见 [API final proof](back-end-core/docs/api.md#oct-5-final-rev4-backend-synthetic-contract)，不将重叠 tests 相加。
//// - [x] **合成离线 evaluator 限定交付**：owner final51／4.695s＋main settled51／4.139s／0 skips，report 读取 authoritative fit['training_groups']，sources/groups 回归和 canonical 不变；早期独立 Lorentz51／八项 numeric repro及 anti/quality 保留范围，不完成整个 P3。

- [back] 当前 flow 分两支：whole-source t/t → 原有 translator＋13-rule model＋memories，**不要求 choicegroup**。8-weight supervised PREFERENCE 才要求來源双 true＋独立 actual/endorsed labels＋consent＋groupreview＋current version/digest/epoch → 合资格 snapshot → preference_rank 临时 CPU group-mean L2 fit → explain/rank/abstain。feedback_set/get 不 fit、不保存训练 weights、不训练 encoder；input.model_active 是规则活动，feedback.model_active 是偏好资格。每 event1/(G*n_g)，group1/G，objective=global mean of group means＋L2/2||w||²。
- [ ] 前端下一步：显式 event-group review／labels／impacts／consent／guards UI＋adapters，分别展示 group/source counts 与 input/feedback activity；unlock/version/F14/native 独立验收，无自动写重试。
- [ ] 模型下一步：contrast-span／不可识别新方向拒答；exactduplicatehint、P2/P3 整体、baselines／ablations／calibration／real held-out validity／实际 weights／native/GPU／CI 仍 pending。
- [back] 六份自有 Markdown 形成稳定 final milestone，停止编辑供 main review diff。保留日期与 Oct4 [front] comments／其他 owner changes；此 worker 未改代码／schema／tests／frontend／evaluator docs、未 stage/commit/push、未接 real corpus／DB／weights。
<!-- END ORIGINAL COMMUNICATION SNAPSHOT -->

## Oct 6 final rev5 backend synthetic contract

以下三项于 **2026-10-06（Asia/Taipei）** 经 main 限定接受后从根活动清单迁入；原始 464 行快照、八项既有完成索引及 dated history 不变。根清单由 18 项减至 15 项；整体目标 active，未完成。

//// - [x] **2026-10-06｜rev5 contrast 数值修复**：病态 dyadic plane 的 false-outside 修复采用隔离的 80-digit Decimal，rank／membership／orthogonality tolerances 保持 1e-10／1e-12／1e-12。原反例约 8.13e-8 的残差降至约 <1e-15，不承诺不同归一化探针的完全相同数值。Archimedes 独立 216 Fraction cases（2160 inside／756 outside／2772 normal checks，最大 residual 6.939e-17，0.613s）及 main576 支持此次有限工程修复；不证明统计置信度、参数幅度、convex hull、calibration 或 same-span utility validity。资源及 owner55 证明见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md#oct-6-rev5-numeric-proof-and-remaining-scope)。
//// - [x] **2026-10-06｜rev5 列序契约／review 对齐**：八列固定为 value.autonomy、value.fairness、value.care、value.truth、value.security、value.growth、value.achievement、value.connection；不依赖 baseline JSON／13-rule catalog 的迭代顺序。Public preference_rank 返回 closed contrast_rank／contrast_basis，行数等于 rank、每行八个有限 [-1,1] 坐标；every query pair 检查 span，feature-support 检查优先，未覆盖方向返回 unidentified_option_contrasts。P3 evaluator report 仅输出 scalar contrast_rank，不输出 raw basis／weights／私有内部变量；API preference_rank 仍返回 contrast_basis／weights，legacy `rank` 的 value-alignment 返回形状不变。固定列序回归及三份最终 reviews 无 blockers；见 [当前 API](back-end-core/docs/api.md#rev5-contrast-contract)。
//// - [x] **2026-10-06｜rev5 最终限定验收**：main session80693 exit0，576 tests／59.590s／OK／0 skips。包含 phase 内巨大整数输入 bounds 修复：先检查类型／[-1,1] bounds，再 math.isfinite／float，受控 ValueError／API INVALID_ARGUMENT，存储及进程保持；新增两项 regressions，owner8＋69 pass。Archimedes161 distinct（initial／corrected temporary-URI guard runs），post-bounds8／1.113s／0 skips；Chandrasekhar post8／1.144s／0 skips；Kant13 pure／0.057s／0 skips，post pure1／0.003s／0 skips、DB/network denied。三份最终 reviews 均无 blockers，重叠 counts 不相加。Quality exploratory3684 checks exit1：九项错误 rank-threshold expectations 已独立解释为 expected rank6／residual 6.93855e-11，完整 harness 未重跑全绿，不列为通过。旧 main574／61.668s 为 prerepair history；quality 重复574／61.968s 不算 main。最终 hashes 见 [API proof](back-end-core/docs/api.md#oct-6-final-rev5-backend-synthetic-contract)。

main 在 `back-end-core` 执行的精确最终命令（本次文档整合未重跑测试）：

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/tmp/alpha-verify-20261005-night.khVPhV /tmp/alpha-verify-20261005-night.khVPhV/bin/python -B -m unittest discover -s tests -q
```

本次只接受 rev5 backend synthetic contract。来源 t/t → translator／13-rule model／memories 保持原有语义，reviewed groups 只约束八参数 preference；rank 临时 read-time fit，不写 DB／持久 weights，不训练 encoder。Frontend、一般语义纠错／一般因果重放、P2/P3 整体、真实效度、actual weights／GPU／CI 仍 pending；不重新纳入历史排除议题。

## Oct 6 offline comparisons and typed validation performance

2026-10-06（Asia/Taipei）：main 独立检查冻结源码／hashes、完整证明和三份已完成 fresh reviews 后，仅接受本节三个限定子项。根清单的 typed 性能项迁入，baselines／ablations 从 broad 真实效度任务拆出工具交付部分；根未完成数由 15 减至 14。整体目标 **active，未 achieved**。上方八项旧索引、原始 464 行快照及 rev5 main576／59.590s 的 dated proof 均逐字保留，不以新计数改写旧证明。

//// - [x] **2026-10-06｜离线 baseline 比较工具**：显式 opt-in `--comparisons` 提供 full、nonpersonal equal_weight sum heuristic 与 analytic uniform chance；chance 是期望值而非随机抽样或实际个人准确率。沿用原始 target eligibility／consent／contamination／axis 边界，所有 predictions／distributions 在 scoring labels 读取前完成；无自动选择、promotion 或真实效度声明。owner69／3.415s、main601／84.585s、main synthetic CLI 和三份 fresh reviews 支持本次工具交付；参见 [evaluator 协议](back-end-core/docs/preference-evaluation.md#opt-in-offline-comparisons)。
//// - [x] **2026-10-06｜八参数 matched-ablation 比较工具**：full＋两种 baselines＋固定八个 leave-one-feature-out ablations 共 11 variants／10 full-vs-variant pairs；原始 cohort 只 admission／numeric dedup 一次，projection 后不再次去重，保留原始 event multiplicity／group ownership／target masking，无跨轴 pooling。生产 support／span／tie／convergence guards 保持；BOTH_PREDICTED 交集与原始 cohort／equal-group denominators 同时披露 support loss，18 default／162 comparison fits，既有 1000-case 上限不变。只交付比较工具，不完成参数选择、calibration、独立真实 holdout 或整个 P3。
//// - [x] **2026-10-06｜Typed validation 性能预算及一致性证明**：`validate_corrections` 每次函数调用惰性完整重译至多一次，empty／parameter-only／pretranslation failure 为零；batch 上限仍 64，无跨调用／全局缓存。`correction_reopen` 仍有事务前后两次 validation，observations 另有翻译，不能写成每个 API request 仅一次。main40／9.939s 与 full601、fresh resources12 支持一致性／调用预算限定验收。历史 98,752-char／64 distinct-tone-target benchmark 的 median2.857913091s→0.057367233s、64→1 calls、Python peak542,710→429,267B 保留原始测量；本轮文档整合未重跑 benchmark。不是 API latency／native RSS／前端响应保证。Typed annotations 仍不产生 13 参数贡献，一般语义纠错／generic replay 和未来统一消费问题仍待用户决定；见 [原始性能证明](back-end-core/docs/correction-performance.md)。

Main 独立完整执行：session65720 exit0，**601 tests／84.585s／OK／0 skips**；另独立 discovery 得 601 unique IDs／0 loader errors。这是实际完整 suite，不由旧576＋新增 counts 算出，也未为取回终态重新启动。Main focused session67821 exit0：**40 tests／9.939s／OK／0 skips**，与 full 重叠，不相加。Owner evaluator69／3.415s，DB／network denied，及其 synthetic comparisons／validate-only exit0 保留 owner 原证明范围。

Main full 的精确命令（工作目录 `back-end-core`；文档 owner 未重跑）：

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/tmp/alpha-verify-20261006.ltAAKM /tmp/alpha-verify-20261006.ltAAKM/bin/python -B -m unittest discover -s tests -q
```

`/tmp/alpha-verify-20261006.ltAAKM` 为该日期的临时验证环境：CPython3.14.7／jsonschema4.26.0，不是永久 runtime，不能保证以后仍存在。通用项目 Python 命令见 [README](back-end-core/README.md#oct-6-offline-tools-and-typed-validation-performance)。Main synthetic `--comparisons` CLI exit0／stderrEmpty：11 variants、10 pairs，full actual／endorsed 各 correct=1，chance expected=0.5，automatic_selection=False／validity_claim=False／database_opened=False；只证明 synthetic wiring。

三份 fresh reviews 均 completed，无 demonstrated blockers；重叠测试、assertions 和 probes 不合算成独立 suite 数：

- **Lovelace verification**：81 focused／5.403s／0 skips；21,313 independent Fraction assertions／1.147228s，pre-import DB／network denials 下 0 attempts。核对 matched original cohort，chance expected63/40、21/80、63/320；held-out flips 及全部162 queries 先于72 scoring label reads；六个 axis scenarios、support loss3→2、无 automatic selection。Reviewer harness 的 SSL import order 与 substring privacy assertion 两项错误在成功 probe 前已修正，非 production defects，失败 runs 不列 passed。
- **Linnaeus antipattern**：12 resources／5.590s＋18 pure preferences／0.722s，两轮 guarded no file writes／DB／network0 attempts；四个 positive CLI 和五个 failure CLI（exit2／generic error），20/20 source hashes stable。CLI stdout 大小只是该合成 fixture 的观测，不是资源硬上限或 API latency。
- **Ramanujan quality**：24 focused／0 skips；1000 randomized Fraction paired-summary probes／60,000 field assertions，original projection group mass matched；1000 cases 的18／162 fit bounds 与1001 rejection 正确。未编辑源码／未运行 full。非阻碍建议：`_ratio` numerator annotation 应允许 float；`_informative_events` 镜像 production admission，未来 fitter 更改时须维护 parity。当前 runtime 正确，本轮不改源码，也不新增强制 root tasks。

Main 接受的冻结 SHA-256（文档整合前核对一致）：

| File（相对 back-end-core） | SHA-256 |
| --- | --- |
| model/preference_evaluation.py | `58ad89efc4b9921e6d8ed952da0c259ca4d341a266c6f0becb224c31a0f5a5c8` |
| model/corrections.py | `cddf331fc10baf7041946c35d6b2ef74b2c61d1cee4a0deb7ced2728a4d95f96` |
| tests/test_preference_evaluation.py | `44036f7a05d3c4a9e1668b7879df31a92b7e3e09bc913525084773ed26676050` |
| tests/test_correction_resources.py | `271c1f822a94638ebdf45d6306aa588cc4b3b1b7c7489648c665591a6a097a58` |

API／schema／preferences／contrast／baseline 未因本阶段更改，schema_version=1／contract_revision=5／34 methods 不变。来源 t/t → translator／13-rule model／memories 与显式 labels／consent／reviewed groups → 八参数临时 preference fit 保持分开；不写 DB／持久 weights、不训练 encoder。独立真实 labels／holdout／calibration／参数选择、整体 P0／P2／P3、一般纠错／generic replay、frontend/native、encoder weights／资源发行／GPU／CI 及整库加密决策仍待办。使用 holdout 比较结果选参会使其成为 development data，最终效度需要新的独立 holdout。此记录是已验证阶段的文档整合，不完成整体目标。

## Oct 6 rev6 exact-text duplicate hint

2026-10-06（Asia/Taipei）：main 核对冻结源码与三份终态 fresh reviews 后，仅接受 exact-text duplicate hint 后端。根独立 hint task 从14项迁出，剩13项；frontend duplicate adapter／UI／cache／native acceptance 合入既有 F14／guards／native bullets，继续 pending。八项旧索引、原始464行快照和全部 dated history／recovery amendments 保留；整体目标 **ACTIVE／NOT ACHIEVED**。

//// - [x] **2026-10-06｜Exact-text duplicate hint 后端限定交付**：authenticated read-only `input_duplicates(source_id: str, *, limit: int = 20)`、health.features.exact_text_duplicate_hint=true；schema_version=1／contract_revision=6／35 methods。仅对当前 stored raw text 做 SQLite BINARY equality，单 BEGIN read snapshot 返回 bounded metadata／total／target version／GLOBAL revision／CURRENT epoch；不返回原文／引用／证据／hash／labels／weights，不写 DB、不 refit。后端不在 submit/edit/review 等操作内自动调用；前端可在保存／编辑后显式请求读取，trigger 由 owner 接线验收。不同文本不推断同事件；不自动分组／审核／认可／consent／合并／去重／阻挡提交。用户审核 event groups 仍需要，前端能力／guards／缓存要求见 [API](back-end-core/docs/api.md#oct-6-rev6-exact-text-duplicate-hint) 与 [handoff](back-end-core/docs/frontend-contract-handoff.md#oct-6-rev6-exact-text-duplicate-hint)。

Main full session90162 exit0，**620 tests／100.682s／OK／0 skips**；独立 discovery620 unique IDs／0 loader errors。工作目录 `back-end-core`，精确命令（本次文档整合未重跑）：

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TMPDIR=/tmp/alpha-duplicate-20261006.gbby9M /tmp/alpha-duplicate-20261006.gbby9M/bin/python -B -m unittest discover -s tests -q
```

Main translator7／0.002s／0 skips；临时 CPython3.14.7／jsonschema4.26.0／PyNaCl1.6.2 仅属本轮验证环境，不是永久 how-to 路径或 Python3.10／发行验收。Owner Carson focused187／23.090s／0 skips；此前81 tests 四项 fixture failures、84 tests 一项 fixture failure均为修正 lifecycle assumptions 前的失败 runs，不列 passed 或 production bugs。三份 fresh reviews 均终态无 blockers，重叠 counts 不相加：

- **Aquinas verification**：109／36.019s；独立 seeded20261006 oracle 用360 application／36 legacy／25 body variants，1800 matching queries＋4 missing/legacy＋26 invalid probes／8.689s；另8 snapshot/access probes／1.334s。初始 oracle trigger fixture failed 后修正，不是 production bug，不记为成功 run。
- **Tesla antipattern**：18／2.946s＋selected7／2.470s＋6 new adversarial／1.259s；核对 read-only SQL、无 raw-text locals、WAL delete/Reset 与 lock/config rotation。
- **Franklin quality**：26／11.850s＋3／0.264s＋1／0.189s＋7 independent／0.271s。非阻碍建议为 duplicated-validation coordination 与既有 JSON Schema integer 接受1.0、runtime exact-int 拒绝的限制；validator 不构成 semantic proof。

Main 另核对 Unicode／closed shape／DB dump stable；readonly URI authorizer0 write attempts，910000 chars 的一次观测为402B wire／0.02693s／cold Python peak1508952B，不是全库 scan latency／RSS 保证。Access gate 在操作前后复查，lock/config rotation 抑制 metadata；locked missing DB 不创建库，SQLite 明文边界不变。

Main 接受的六个 SHA-256（相对 `back-end-core`；文档整合时只读核对）：

| File | SHA-256 |
| --- | --- |
| core/brain.py | `c34824ab3eeda19a1cd1c8b8b9fcdbfd33497766f4809206187479673c618081` |
| core/api.py | `787d2c43d1dfbf00d2d2dcc0aebeb9aa318ee75ceaaccb04f710b3eace9567d8` |
| docs/api.schema.json | `0c2d75893f2172a8613f546c35a6bf143975507d288c18f0eeef86f78be02989` |
| tests/test_input_duplicates.py | `d1ed6b8ffadf812ef792758f4671278659ab08b0c768246456912f54ac8807ae` |
| tests/test_schema_contract.py | `4c00234c3e00a4355469d60e61705e9e95f6422e230f2250acd4213f91f874a9` |
| tests/test_hybrid_api.py | `f8de6354f4cd0b95b91ddde6099cd5c2060845d0be0d7e339b2083931ab84110` |

Main verified preferences／corrections／evaluator／contrast／baseline unchanged. 旧 main601／84.585s、rev5 main576／59.590s 保留各自历史范围。Typed annotations 的未来统一消费用户决定仍未回答，当前 split／13-rule params 不自动覆盖。一般语义纠错／依赖重放、真实 holdout／encoder weights／资源／CI／Python3.10／native／frontend 与 broad P0/P2/P3 仍 pending；duplicate hint 不关闭这些任务。

## Oct 6 general downstream replay scope decision

- **2026-10-06（Asia/Taipei）｜用户确认**：一般因果／下游重放范围为「计算依赖＋人工审核的语义／因果依赖（推荐）」。这是范围授权，非实现或验收；用户审核的语义／因果边仍待实现，根 P0 保持未完成，根清单仍为 13 项 pending／0 项 completed。
- **阶段与边界**：main 指定当前阶段为 computational input provenance／read-only transitive planner，尚未验收；下一阶段为人工关系工作流。不自动推断心理／事件因果，不自动审核／认可／consent／拟合，不强制改写既有 effects；重放仍须显式请求并对修订解释重新取得双确认，保留历史 effects／冻结拟合／Reset 排除边界。
- **保留未决事项**：typed annotations 未来统一消费仍待用户决定，当前 split／13-rule params 不自动覆盖。本记录不更改 rev6／620 证明、日志头部验收状态或整体 ACTIVE／NOT ACHIEVED 状态。

## Oct 6 semantic label revision (rev7 backend, pending acceptance)

- **2026-10-06（Asia/Taipei）｜用户确认范围**：一般语义纠错取「版本绑定的事件／语义标签修订＋修订后强制重新双确认，不自动推断」。
- **已实现（待 main 验收，非完成）**：typed correction 增加可选 `revised_value`（1–64 字符、已 trim、无控制字符／代理项、≠原 value，仅 sign=1）；仅改写精确命中的 translator 输出在 interpretation.translation 与 deterministic memory claim 中的值，原文、13 规则 effects、raw translation 报告不变。`health.features.semantic_label_revision=true`；前端须同时检查此特性位才可发送 `revised_value`。沿用既有 `correction_reopen`／`replay_reopen` 的 source_version／revision／epoch guards：已 fitted 来源修订后回到 pending／disagreed，必须重新双确认。修订不自动审核、不扩散到其他来源、不教授新规则（学习规则仍只读 parameter 类纠错）。
- **证据**：本机 `python -B -m unittest discover -s tests -q` 在临时 venv（含 jsonschema4.26.0）657 tests／OK／0 skips；新增 tests/test_label_revision.py 5 项与 schema 契约 1 项＋health 特性位变异。未经独立 reviews；无真实数据。同时修复上一阶段遗留的 test_expression_coverage 断言（preview 的 dependency_provenance.fit_id 为 null、review 后为实 ID，属设计行为）。
- **未做**：任意新增（translator 未识别的）标签、前端 UI／adapter、对 13 规则参数的覆盖（仍待用户统一消费决定）。

## Oct 6 manual relations (rev7 backend, pending acceptance)

- **用户确认设计（2026-10-06）**：人工审核依赖边采用新表＋`relation_set`／`relation_list` 两个方法。
- **已实现（待 main 验收，非完成）**：`brain_relations`（semantic／causal、有向、绑定两端 source_version 与 model_epoch、note≤1024、每来源≤64 边）；`relation_set` 带 guards，`reviewed=true` 保存／替换、`false` 撤回；`relation_list` 标 stale；F6 编辑／删除清除边，reopen／Reset 使边 stale 并被 planner 忽略。`dependency_plan` 合并新鲜人工边（via_kinds 增 `manual_semantic`／`manual_causal`，maxItems4）；health 增 `manual_relations`，methods 38；backup validate 识别可选表。不自动推断、审核、consent、拟合、重放或改写 effects。
- **证据**：临时 venv（jsonschema4.26.0）`python -B -m unittest discover -s tests -q`：664 tests／OK／0 skips；新增 tests/test_relations.py 7 项及 schema 契约 live 示例／signature／health 变异。无独立 reviews；无真实数据。
- **未做**：前端人工关系 UI／adapter；是否让 replay_preview 默认包含人工边；本改动未更新 rev7 验收文本。
