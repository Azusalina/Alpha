# 下一个会话的交接 prompt

更新于 2026-09-22 13:40（session 5 应用户要求暂停）。

本文件分两部分：

- **第一部分**：到目前为止做成了什么，给人看。
- **第二部分**：可以直接复制粘贴到新 chat session 的 prompt。

细节以仓库里的文件为准，本文件不重复它们：

- `documentations/log/log-v2.md`：状态、决定 D1–D19、"Step 2 — calibration runs"、"Resume here"
- `docs/CONTRACTS.md`：接口约定
- `docs/ACCEPTANCE.md`：验收阈值及其推导
- `docs/HAND_ASSETS.md`：构建器怎样把姿态变成网格
- `outputs/qa/calib/reports/`：上一轮各 agent 的完整报告（构建器请求、残差、验证意见）

---

## 第一部分：现有成果说明

### 项目与阶段

Alpha 是一个本地桌面应用（React + TypeScript + Vite + three.js / R3F，Tauri 2 外壳）。启动页是《创造亚当》式的双手构图：左上是雕塑质感的人手（实体），右下是粒子手（从网格上采样粒子）。视觉唯一基准是 `aes-ref/alpha-white-geom.PNG`（1644 × 957）。

- **Round 1**（已合并，`0453b74`）：启动页原型。
- **Round 2**（进行中，在仓库根目录的 `main` 上直接工作）：按外部审查 `alpha-v1-review/review.md` 的 §E 执行，范围是"静态形体 + 验收工具"，不做导航。

### Round 2 各步状态

| 步骤 | 状态 |
|---|---|
| 0 环境 | ✅ 仓库根目录、`main` |
| 1 三项基础：参考遮罩与测量工具、Blender 连续网格、Tauri 外壳 | ✅ 三项都通过了独立验证 |
| 2 逐手标定姿态 | ⏸ 等第 3 步。左手只差轮廓 p95；右手门槛全过，但有一个 major 要修（见下） |
| 3 扩展构建器（D17、D19） | ⏸ 在第一段 "arm" 中途暂停；构建器草稿已保存 |
| 4 应用接入 Blender GLB | ✅ |
| 5 测试和三组截图、6 对抗式复核、7 真机桌面运行（用户）、8 文档与提交 | 未开始 |

### 当前数字（已提交的姿态和构建器）

| 手 | IoU | 轮廓 mean / p95 | 负空间 IoU | 结果 |
|---|---|---|---|---|
| 左 | 0.963（门槛 ≥ 0.960） | 1.69 / 4.12 px（门槛 ≤ 2.0 / 2.0） | 0.915（门槛 ≥ 0.865） | 只有 p95 没过；指尖、16 个关节、网格指标（A1）、轮廓覆盖（D9）都过 |
| 右 | 0.931（门槛 ≥ 0.918） | 3.34 / 7.62 px（门槛 ≤ 3.7 / 8.9） | 0.879（门槛 ≥ 0.825） | 全部门槛通过；验证者报一个 major：中指和小指的指间关节在 3D 里向侧面弯折（指间关节只能单向屈伸） |

### 为什么现在做第 3 步

- 左手标定了 21 次后停在 p95 = 4.12 px。剩下的误差主要是旧构建器做不出的形状：食指指节的鼓包和台阶、腕背凹口、腕横纹和掌根、前臂背线下垂。你选了 **D17 (a)**：先扩展构建器，再按原门槛重新标定左手。
- **D18 (b)**：重新标定时，左手蜷曲的中指和无名指向掌侧屈，使近节约为中节的 1.4–1.6 倍。
- **D19**（你交给我决定）：第 3 步做全部已收集的构建器请求，分两段。
  - **arm 段**：两只手的手掌结构、腕背过渡、腕横纹和掌根、前臂下垂和腕突、腕部凸环、袖口。
  - **digits 段**：指节突出、指间关节凸起按手分开、拇指朝向按手分开、指甲浮雕、拇指根缝、网格报告的指尖检测 bug。
- 右手的侧弯关节不单独修，放进第 3 步之后的重新标定里一起修。第 3 步改的是两只手共用的构建器，右手之后本来就要再标定一次。

### arm 段草稿（暂停时的状态）

- 仓库文件没有改动。草稿在 `outputs/qa/scratch/build-arm/`，本地保存、被 git 忽略：
  - `dev/build_hands.py`：新的手掌结构，比仓库版本多 485 行、删 34 行；
  - `runs/r01–r05`：5 次实验构建；
  - `progress.md`：各轮得分。
- 同一份草稿也以补丁形式存进了 git：`outputs/qa/calib/reports/step3-arm-wip.patch`，可以直接应用到已提交的 `build_hands.py`。
- 5 次实验都保住了 A1（每只手 1 个壳体、0 非流形边、0 边界边、28 854 个三角形）。套在旧姿态上时 IoU 下降（左 0.963 → 0.943，右 0.931 → 0.915），这在预料之中：姿态是按旧构建器标定的，第 3 步完成后会重新标定。

### 这一轮踩过的坑（下次避开）

1. **按名字调用 workflow 会拿到缓存的旧版脚本**：一律用 `scriptPath` 调用。
2. **后台会话默认会被 worktree 保护拦住**，不能修改根目录文件。本机已在被 git 忽略的 `.claude/settings.local.json` 里设置了 `"worktree": {"bgIsolation": "none"}`。
3. **`/tmp` 是 tmpfs，一重启就清空**。三次运行的草稿因此丢失。现在的工作流把草稿放在 `outputs/qa/scratch/`，该目录已写进 `.git/info/exclude`。
4. **账户额度、服务器过载（529）和关机都会中断 agent**。进度保存在磁盘上，续跑时带 `args: { resume: true }`。`resumeFromRunId` 只在同一个会话里有效。
5. **每次续跑都要重新读文档**，一个 agent 大约要消耗 30 万 token 以上。尽量让一个工作流一次跑完，中途不要关机。

---

## 第二部分：粘贴到新会话的 prompt

```text
继续 Alpha v1 的 round 2（形体与验收）。这是续做，不要从头开始。

【环境】
- 直接在仓库根目录 /home/a/Documents/Alpha 的 main 上工作，不要在 .claude/worktrees/ 里（见根目录 CLAUDE.md）。
  后台会话如果被 worktree 保护拦住编辑，检查 .claude/settings.local.json 里是否有 "worktree": {"bgIsolation": "none"}。
- 不要自己跑 npm install，它会卡死；缺依赖时让我跑 npm install --legacy-peer-deps。
  Playwright 用 ALPHA_CHROMIUM=/usr/bin/chromium。Blender 5.2.2 可以无头运行；Python 只有 numpy / Pillow / scipy。
- 用中文回复我。commit 可以直接做。push：按 D8，本轮每完成一步可以直接 push，其他情况先问我。

【开工前先读】
1. documentations/log/log-v2.md：顶部状态、决定 D1–D19、"Step 2 — calibration runs"、"Resume here"
2. docs/CONTRACTS.md、docs/ACCEPTANCE.md、docs/HAND_ASSETS.md
3. outputs/qa/calib/reports/：上一轮 agent 的完整报告

【从哪里接着做】
第 3 步（扩展构建器，D17 / D19）暂停在第一段 "arm"。续跑：
  Workflow({ scriptPath: ".claude/workflows/alpha-v1-builder-step3.js", args: { resume: true } })
arm 段草稿在 outputs/qa/scratch/build-arm/（本地）。如果这个目录不在了，
outputs/qa/calib/reports/step3-arm-wip.patch 可以直接应用到 build_hands.py 的副本上。
第 3 步两段都通过验证后，在新构建器上重新标定两只手：左手按 D17 / D18，右手修掉侧弯的指间关节。
  Workflow({ scriptPath: ".claude/workflows/alpha-v1-calibrate-poses.js", args: { resume: true } })
然后是第 5–8 步，见 log 的 "Resume here"。

【规则】
- 工作流用 scriptPath 调用；跑的时候要有人在场，或者开着 auto mode。
- 出现新的待定项（从 D20 开始编号）先问我，不要自己定，也不要让子 agent 定。
  工作流里的 agent 遇到这类问题，会通过 decisionsForUser 让那一手或那一段暂停。
- 关机会中断正在运行的工作流；续跑时带 resume: true。
- 每完成一步：更新 log-v2.md 并 commit。
```
