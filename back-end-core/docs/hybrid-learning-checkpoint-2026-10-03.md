# Hybrid learning checkpoint — PAUSED (2026-10-03)

用户要求今天暂停并保存进度。开发代理已停止；既有工具目标已返回 `status=paused`。新 hybrid 目标此前未能通过 create_goal 创建（本线程已有未完成的旧目标）；这里只保留项目工作目标，**不宣称目标完成**。本文件是本轮接续入口；计划文档及沟通文件较早的草稿有漂移，以本检查点和沟通文件最后的暂停记录为准。

## 已确认的目标与决定

- 本机混合后端：冻结预训练文本编码器辅助语义检索，SQLite 保存可追溯证据，独立的监督式偏好基线学习用户明确标注的选择。不是完整数字自我、心理诊断或保证收益最大化。
- F14 已解除延期：实际选择 `actual_choice_id` 与事后认可 `endorsed_choice_id` 独立保存；来源 immediate/confirm 双 true 不充当选择标签或独立训练授权。
- 首版由前端显式提供选项 `impacts`，用户审核；不自动从日记推定选项利弊或正确答案。
- 本轮不下载权重、不导入真实材料、不访问或训练实际用户数据库。MMPI 不在当前范围。
- 原有双确认、来源版本、访问控制和模型轮次边界必须保留；Reset 保留 translator/记忆，排除旧个人模型材料，重新纳入须明确操作。

## 技术栈与目标流程

- 桌面已有 Tauri 2；React/TypeScript/Vite 的前端由其 owner 负责，本轮未改前端。
- 后端 Python >=3.10、SQLite、既有 jieba；可选 `sentence-transformers==6.1.0` / PyTorch CPU，尚未安装和真实加载验收。
- 偏好分支：纯 Python、L2 正则化的 multinomial logistic/softmax，共 8 个 `value.*` 特征，独立于现有 13 个规则参数；按 actual/endorsed、状态分区及 daily/study/relationships 隔离。
- 开源参考克隆在 `ext-refs/sentence-transformers`，commit `4a3b5cd6ec718e421f57e824a41ed3fd99595df6`（6.2.0.dev0 参考源码，**不是**已安装运行版本），Apache-2.0。

```text
txt/md/输入 -> AccessSession -> 规则/jieba/显式纠错 -> 来源双确认
                                                  -> SQLite 证据记忆
检索 query + 活动记忆 -> 可选冻结本机 encoder -> 相似证据（不是事实真值）
                         未配置时明确 lexical_fallback；配置后失败则报错

显式选项/审核 impacts + actual/endorsed 标签 + 独立 training_consent
    -> 来源双确认 + 当前版本/内容 + 当前 model_epoch 筛选
    -> preference_rank 对合资格快照临时拟合偏好基线并排序
    -> 权重/逐特征贡献/未校准 softmax 输出，或 abstain
    -> 后续分组/时间留出评估 -> 有独立增益后才考虑 MLP/LoRA
```

目前草稿 `preference_rank` 会进行 CPU 临时拟合，**不是此前持久训练模型的纯前向推断**；不写数据库或训练 encoder。set/get 不进行拟合。读取请求不会补造训练同意。临时权重不替代原文记忆，重启后仍从合资格反馈重算。

## 已保存的实现草稿（未交付）

- `translator/semantic.py`、`tests/test_semantic_encoder.py`：本机路径、懒加载、向量校验、批次和文本限制、余弦检索；离线/模块安全预检正在收紧，尚未最终验收。
- `model/preferences.py`、`tests/test_preferences.py`：选择反馈表、版本/全局 revision/epoch guards、标签/授权、监督式偏好拟合和逐特征解释；测试草稿已保存，最终套件未验收。
- `core/brain.py`、`core/api.py`、`model/sources.py`：新增接入点、来源编辑/删除清理草稿、长推断后的授权复查。
- `docs/api.schema.json`、`tests/test_schema_contract.py`、`tests/test_hybrid_api.py`、`pyproject.toml`：尝试扩展为 schema_version=1 / contract_revision=3 / 34 methods（新增 memory_search_semantic、choice_feedback_set、choice_feedback_get、preference_rank）。运行方法、全部结果 schema、文档及测试尚须最终一致性核对，**不能作为已稳定的前端契约**。
- `front-back-communicate.md` 和 `docs/hybrid-learning-plan.md` 已有追加/草稿。暂停时还存在过时或相互冲突的描述，需要下次统一，不应照旧草稿开启功能。
- 用户原有 `translator/discourse.py`、私有材料整理及并行 `src/` 变更保留，不属于本轮完成/验收。

## 验证证据与已知阻碍

- 主代理曾运行 `python -m unittest tests.test_semantic_encoder -q`：25 项合成测试通过；此结果早于最后的离线保护修改，不代表暂停时最终代码全通过，更不代表真实语义能力。
- 集成草稿阶段运行 `tests.test_hybrid_api tests.test_schema_contract`：27 项，7 failures / 6 errors。部分来自尚未完成的 fixture/字段/schema 同步；之后又有草稿修改，未重跑，因此这里保存的是最后看到的失败证据，不是对当前全部代码的最终判定。
- **首要实际兼容性缺陷**：BrainCore 新增 `brain_choice_feedback` 后，`core.backup.validate_database` 的严格 schema 参考仍只初始化旧 BrainModel，导致新临时库 `setup_access` 报 `unsupported Alpha database schema`。必须支持经严格核对的新可选表，同时保留旧库和异常 DDL 拒绝；不要简单放宽任意表的白名单。
- 反馈公开字段曾在 `learning_eligible` 与反馈专用 `model_active` 间变动；恢复时以最终源码统一 schema/tests/docs，并明确区别于 input 的规则模型 activity。
- API 全方法覆盖、候选记忆 fixture、配置后 provider 失败分支、推断期间 revoke/edit/delete/reopen/lock 和 Reset 再纳入验收未完成。
- 离线 encoder 必须拒绝不完整本机布局、远程引用、自定义模块及不安全权重，不能仅靠顶层 local_files_only 宣称完全离线；尚无实际模型加载/零网络/CPU 性能证明。
- 临时测试环境：`/tmp/alpha-phase0-runtime.V1tVlSHj/bin/python`，Python 3.14.7，jsonschema 4.26.0 及依赖已可导入，继承系统 PyNaCl 1.6.2。该目录不保证重启后存在；未安装新的 Torch/Transformers 或模型权重。

## 下次接续顺序

1. 先检查工作区和本检查点，不覆盖并行前端/用户修改；暂停代码为未验收草稿，**先不要用真实库启用新能力或迁移**。
2. 修复新表与 access/backup/restore 严格 schema 兼容，验证旧/新临时库、篡改 schema、来源编辑/删除与模型 Reset。
3. 统一 F14 公开结果字段及 34 方法的运行 allowlist、完整请求/结果 schema、api.md、handoff 和能力声明。
4. 完成离线预检与无输出泄漏、无自动下载、配置后失败不 fallback 的合成测试。
5. 重跑 semantic/preferences/hybrid/schema/access/security 及后端全套，所有仅合成/临时库；保存最终证据，再更新完成勾选。
6. 后续交付新的偏好分组/时间留出评估模板与工具；真实留出验证、前端解锁/F14/cache/native、模型离线发行及硬件验收仍待办。

无 commit/push；更改保存在工作树。这里只保存暂停进度，没有继续修复、训练或实施新功能。
