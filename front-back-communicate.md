# 前后端沟通：未完成事项

- 本清单更新于 2026-10-06（Asia/Taipei）；已完成索引、历史决策及全部原始发言见 [frontback-log.md](frontback-log.md)。历史快照中的 pending／PROPOSED／延期文字仅表示当时状态。
- 契约与分工以 [API](back-end-core/docs/api.md)、[schema](back-end-core/docs/api.schema.json)、[backend TODO](back-end-core/docs/TODO.md) 和 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md) 为准；后端不修改前端，前端不修改后端。
- 技术栈与两条通道见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md#技术栈与两条通道)：React／TypeScript／Vite → Tauri 2 → Python／SQLite；来源双 true → translator／13-rule model／memories，与显式 labels／impacts／consent／reviewed groups → 八参数偏好临时拟合分开。F13／F14 已纳入范围。
- 验收边界：main 已限定接受 schema_version=1／contract_revision=5／34 methods 的后端合成契约：576 tests／59.590s／OK／0 skips，三份最终 reviews 无 blockers。三个 rev5 完成项已移至 [Oct 6 日志](frontback-log.md#oct-6-final-rev5-backend-synthetic-contract)；当前接口及精确证明见 [API](back-end-core/docs/api.md#oct-6-final-rev5-backend-synthetic-contract)。旧 rev4 证明保留历史范围；整体目标 active，前端及真实效度仍待验收，不能仅凭 health 声明启用 UI。
- 完成迁移流程：未来经验证完成的事项从本清单移至 [日志](frontback-log.md)，以日期、实际结果／证据和限定范围记录为 `//// - [x]`；批准或源码存在不等于完成。部分完成须拆出已完成子项归档，剩余任务保持 `[ ]`。

- [ ] **P0｜一般语义纠错**：完成广义事件／语义标签修订及重新双确认的实现与验收；已交付的版本绑定有限 typed retain/suppress 不关闭此任务。见 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **P0｜一般因果／下游重放**：定义并验证一般依赖图与通用下游拟合重放；已交付 selected replay 不代表一般因果重放完成，保留历史 effects／冻结拟合／Reset 排除边界。见 [API](back-end-core/docs/api.md)。
- [ ] **Typed correction 性能**：验证 typed correction 逐项重译的资源预算、性能与结果一致性。见 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md) 和 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **F13 前端解锁／私有缓存**：完成并验收 unlock、LOCKED、malformed unlock／lock／reconnect 后私有原文、excerpt、evidence、history、feedback／rank／search 缓存及在途操作失效。已验收的 backend gate／encrypted backup 不替代 UI／native 验收。见 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md)。
- [ ] **前端版本／consent guards 与 F6 后续边界**：完成 source_version／GLOBAL revision／CURRENT epoch 的 guarded UI；F6 重置 source_version=0 时丢弃排队旧操作，完成未来 content-revision guard 的设计与验证；冲突或不确定写结果不得自动写重试。见 [API](back-end-core/docs/api.md) 和 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md)。
- [ ] **F14 前端／event groups 接线**：完成 actual／endorsed、显式审核 impacts、独立 training_consent、event-group ID／review／draft 与编辑既有反馈协议；分别展示 informative training_sources／training_groups、input 规则 activity／feedback 偏好资格，核对 group means 与至少三组门。Backend reviewed groups 已完成；前端 adapters／能力协商／错误与拒答显示须独立验收，无自动写重试。见 [API](back-end-core/docs/api.md)、[schema](back-end-core/docs/api.schema.json) 和 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md)。
- [ ] **前端／native 最新完整验收**：验证 administrative model-only Reset 后重连、epoch／state／列表刷新与旧缓存／effects 失效，以及最新并行前端的完整接线和 F13／F14 native 行为；不得自动重新纳入旧材料或补确认。既有浏览器与五个 Xvfb 软件渲染 native scenarios 保留历史范围。见 [frontend handoff](back-end-core/docs/frontend-contract-handoff.md) 和 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **真实语义／表达覆盖**：用独立代表性留出材料评估杂乱日记、复杂聊天、引述、否定、任意人名／混合归属、反讽及哲学陈述；验证新 encoder 的实际语义质量与覆盖，必要时再决定本地 NLP／LLM。现有规则／mock 合成证明不代替真实覆盖。见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md)。
- [ ] **真实选择效度／参数选择**：完成独立 actual／endorsed labels、provenance、训练暴露及分组／时间留出，评估 coverage／拒答／预测、baselines、八参数 ablations、calibration、same-span utility validity 与参数去留。已交付的有限 offline evaluator 和 numeric canonicalization 不证明真实效度；reviewed group ID 不证明真实独立性。见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md) 和 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **Broad P2／P3**：完成剩余整体设计与验收；已归档 backend groups、偏好数值修复和合成 evaluator 子任务不能关闭整个阶段。见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md)。
- [ ] **Exact-text duplicate hint**：实现并验证原文完全重复提示；不推断不同文本属于同事件，不自动授予 group review、来源认可或 consent。见 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **实体输入／GPU 与跨平台验收**：验证真实输入、GPU 渲染／帧率及 macOS／Windows 行为与发行；Linux portable release 和 Xvfb 软件渲染记录不覆盖这些范围。见 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **新 encoder 离线发行／资源性能**：定稿本地 weights／依赖的 model hash、license／manifest、打包及离线安全验证，测量 CPU／RAM／延迟／UI 响应。既有 Python／jieba Linux runtime 交付不证明新 encoder 已打包或实际 weights 有效。见 [hybrid plan](back-end-core/docs/hybrid-learning-plan.md)。
- [ ] **在线 CI／Python 3.10**：取得实际在线 CI 和最低支持 Python 3.10 的验收结果；本机 Python 合成证明不替代。见 [backend TODO](back-end-core/docs/TODO.md)。
- [ ] **可选整库加密决策**：后续明确是否将 SQLite 整库加密纳入范围及其实现／验收；当前库仍为明文，访问门与 encrypted backup 不表示整库加密完成。见 [backend TODO](back-end-core/docs/TODO.md)。
