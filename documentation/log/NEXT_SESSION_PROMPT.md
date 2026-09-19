# 下一个会话的交接 prompt

本文件分两部分：

- **第一部分**：说明到目前为止做成了什么，给人看。
- **第二部分**：可以直接复制粘贴到新 chat session 的 prompt。

细节以仓库里的文件为准，本文件不重复它们：

- `documentation/log/log-v2.md`：状态、D1–D4 决定、"Resume here" 步骤
- `docs/CONTRACTS.md`：接口约定
- `docs/ACCEPTANCE.md`：验收阈值

---

## 第一部分：现有成果说明

### 项目与阶段

Alpha 是一个本地桌面应用（React + TypeScript + Vite + three.js / R3F，Tauri 2 外壳）。启动页是《创造亚当》式的双手构图：左上是雕塑质感的人手，带几何构造线；右下是粒子手，向右下消散。视觉唯一基准是 `aes-ref/alpha-white-geom.PNG`（1644 × 957）。

- **Round 1**（已合并到 main，`0453b74`）：启动页原型。包括单一进度值的状态机、GPU 粒子、启动隔离、7 个 Playwright 回归测试。
- **Round 2**（进行中，分支 `claude/v1-form-acceptance`，未 push）：按独立审查 `/home/a/Documents/Alpha/alpha-v1-review/review.md` 的 §E 执行，范围是"静态形体 + 验收工具"，不做导航。

### Round 2 已完成的成果

| 成果 | 状态 |
|---|---|
| A2 同 seed 不可复现 | ✅ 已修复并验证：0 / 30,000 不一致（原为 30,000 / 30,000） |
| A3 smoothstep 边界顺序 | ✅ 已修复 |
| A5 Playwright 视口被 1280×720 覆盖 | ✅ 已修复，7/7 测试在 1644×957 下通过 |
| **A1 连续网格** | ✅ 由 Blender 无头脚本生成：`assets-source/hands/build_hands.py`，SDF 融合。两只手都是 1 个壳体、0 非流形边、0 边界边、绕序一致 100%、28,854 三角形。⚠️ 独立验证未通过，见下 |
| A4 测量工具 | ✅ `compare_silhouette.py`（红/蓝/黑叠图、IoU、轮廓距离、负空间、指尖、pass/fail、自检）；✅ `overlay_check.py` 已重写，旧 bug 已确认并修掉。⚠️ **从未经过独立验证** |
| 参考数据 | ✅ 两只手的遮罩、指间负空间、关键点（按 D1/D2 命名）、`thresholds.json` 和 `ACCEPTANCE.md`（按 D4 由遮罩自身噪声推导阈值） |
| Tauri 2 外壳 + 诊断 | ✅ **独立验证通过**。`src-tauri/`，`Ctrl+Shift+D` 隐藏面板，`window.__alpha.measureFrames()`，生产包里不含诊断代码。`docs/DESKTOP_CHECK.md` 已写好 |
| 接口文档 | ✅ `docs/CONTRACTS.md`：相机、投影/反投影、Blender↔应用坐标、pose 格式、资产格式、silhouette 渲染约定、CLI、阈值表 |

### 当前数字（校准前基线）

| 手 | IoU | 轮廓 mean / p95 | 负空间 IoU | 验收门槛（ACCEPTANCE） |
|---|---|---|---|---|
| 左 | 0.901 | 6.8 / 13 px | 0.815 | IoU ≥ 0.963，p95 ≤ 2 px，负空间 ≥ 0.872 |
| 右 | 0.803 | 10.2 / 29 px | 0.704 | IoU ≥ 0.901，p95 ≤ 10.2 px，负空间 ≥ 0.825 |

### 用户已确认的决定（log-v2.md D1–D4）

- **D1 右手**：向左伸出的长指 = 中指；指甲朝向观者的短指 = 拇指；向下弯的两根分别是无名指和小指。
- **D2 左手**：带大指甲、指甲朝外的那根 = 拇指；最左边蜷在掌下、指回手腕的那根 = 小指。两只手统一按"指甲朝向观者的那根是拇指"。
- **D3**：严格按 log 的第 0–8 步顺序执行；第 1 步三路全部通过后才能开始第 2 步校准。第 4 步可以与第 2 步并行。
- **D4**：验收阈值以 ACCEPTANCE.md 由遮罩噪声推导的结果为准。凡是比 log 原提议宽松的，必须写明理由。

### 还没做完的

- **第 1 步剩余**：Blender 那一路有验证者提出、但尚未修复的问题：
  - major：轮廓 `outer` 折线只覆盖了约 94% 的边界
  - 手背上一处减面褶皱
  - 指甲边缘的若干凹陷
- **第 1 步剩余**：参考遮罩那一路还没有经过任何一次独立验证。
- **第 2–8 步**：
  - 2：逐手校准
  - 3：修掉前臂"袖口"
  - 4：把 GLB 接入应用（应用目前仍然渲染 round 1 的管状网格）
  - 5：测试和三组截图
  - 6：对抗式复核
  - 7：用户在真机上跑桌面版
  - 8：更新文档并提交

### 上一轮运行出的两个问题（下次必须避开）

1. **按名字调用 workflow，拿到的是缓存的旧版脚本**，里面没有 D1–D4。所以要用 `scriptPath` 调用。
2. **会话无人值守时，权限系统拦下了所有修复 agent**，它们连第一次读文件都没通过，什么也没改。所以跑 workflow 时必须有人在场，或者事先授予权限。

---

## 第二部分：粘贴到新会话的 prompt

```text
继续 Alpha v1 的 round 2（形体与验收）。这是续做，不要从头开始。

【环境】
- 仓库 worktree：/home/a/Documents/Alpha/.claude/worktrees/relaxed-sammet-bbc152（若已被回收，
  就在新 worktree 里 checkout 分支 claude/v1-form-acceptance）。分支保持不 push，
  commit 可以做，push 前必须问我。分支不跟踪 origin/main，这是有意的。
- node_modules：新 worktree 里没有。lockfile 未变，可以复制
  /home/a/Documents/Alpha/v1/node_modules，或者由我来跑 npm install --legacy-peer-deps。
  不要自己跑 npm install，它在沙箱里会卡死。
- Playwright 用系统 Chromium：ALPHA_CHROMIUM=/usr/bin/chromium。
  Blender 5.2.2 可以无头运行；cargo 能访问 crates.io。Python 只有 numpy / Pillow / scipy。
- 用中文回复我。

【开工前先读，按这个顺序】
1. documentation/log/NEXT_SESSION_PROMPT.md 第一部分（成果说明）
2. documentation/log/log-v2.md：先读 "Resume session — decisions confirmed by the user"（D1–D4）、
   "Status after the step-1 run"，再读 "Resume here"
3. docs/CONTRACTS.md（接口约定，改动前先改这里）
4. docs/ACCEPTANCE.md（验收阈值及其推导）
5. /home/a/Documents/Alpha/alpha-v1-review/review.md（外部审查，本轮范围是 §E）

【已确认的决定，不要重新讨论】D1–D4 见 log-v2.md。两只手统一按"指甲朝向观者的那根是拇指"。
严格按 log 的第 0–8 步顺序执行；第 1 步全部通过后才能开始第 2 步（第 4 步可以与第 2 步并行）；
阈值以 ACCEPTANCE.md 为准。

【从哪里接着做】第 1 步还剩两路：
- blender：修复验证者提出的问题（轮廓 outer 覆盖约 94% 是 major、左手背减面褶皱、指甲边缘缺陷、
  HAND_ASSETS.md 的错误说法），然后通过独立验证。不要改姿态和半径，那是第 2 步的事。
- reference：从未经过独立验证，需要跑一轮验证。
Tauri 那一路已经通过验证。

调用 workflow 时用 scriptPath，不要用 name（name 上次解析到了缓存的旧版脚本）：
  Workflow({ scriptPath: ".claude/workflows/alpha-v1-form-foundations.js",
             args: { resume: true, only: ["blender", "reference"] } })
跑 workflow 期间我会在场处理权限提示。上一轮因为无人值守，所有修复 agent 都被权限系统拦下了。

【开工前把这些待定项一起问我，别自己决定】
1. 左手拇指和无名指之间有一条亮缝（x 537–560，y 360–420，约 500 px），参考遮罩目前把它算作手。
   它到底是透过手看到的纸面，还是高光？
2. 左手门槛很严（轮廓 p95 ≤ 2 px，当前是 13 px）。ACCEPTANCE.md 规定：校准停滞时报告差距、
   交给我决定，而不是放宽门槛。确认按这条规则走？
3. Tauri 的权限目前是 core:default，比实际用到的一个权限（core:app:allow-tauri-version）宽。
   要不要收窄？
另外，如果你读完文档发现了新的冲突或含糊之处，也一并列出来问我。

【完成标准】review §E 的五个问题都要能用证据回答：
姿势是否匹配、是否有可见接缝、实体是否有古典雕塑的体块感、粒子是否保持手形、同一 seed 能否复现。
每完成一步，就更新 log-v2.md 并 commit（不 push）。
```
