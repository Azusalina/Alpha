# 下一个会话的交接 prompt

更新于 2026-09-29（session 7：round 2 完成）。

本文件分两部分：

- **第一部分**：到目前为止做成了什么，给人看。
- **第二部分**：可以直接复制粘贴到新 chat session 的 prompt。

细节以仓库里的文件为准，本文件不重复它们：

- `documentations/log/log-v2.md`：round 2 的完整记录、决定 D1–D31、"Next round"
- `docs/CONTRACTS.md`：接口约定（资产格式、`window.__alpha` 检查器）
- `docs/ACCEPTANCE.md`：验收门槛及其推导
- `docs/HAND_ASSETS.md`：Blender 构建器如何把姿态文件变成网格
- `docs/DESKTOP_CHECK.md`、`outputs/qa/desktop-check.md`：桌面测量流程和第 7 步结果

---

## 第一部分：现有成果说明

### 项目与阶段

Alpha 是一个本地桌面应用（React + TypeScript + Vite + three.js / R3F，Tauri 2 外壳）。启动页是《创造亚当》式的双手构图：左上是雕塑质感的人手（实体加构造线），右下是粒子手（从网格上采样粒子）。视觉唯一基准是 `aes-ref/alpha-white-geom.PNG`（1644 × 957）。

- **Round 1**（`0453b74`）：启动页原型。
- **Round 2**（2026-09-19 → 09-29，已完成）：按外部审查 `alpha-v1-review/review.md` §E 做"静态形体 + 验收"，不做导航。

### Round 2 的成果

| 项 | 结果 |
|---|---|
| 手部资产 | 两只手都是 Blender 无头脚本从姿态文件生成的连续网格（GLB），带轮廓 JSON 和指甲 D 形轮廓 |
| 姿态匹配 | 左 IoU 0.984、轮廓 p95 2.0 px；右 IoU 0.933、p95 7.6 px；食指尖间隙 29.1 px（基准 30.4），全部门槛通过 |
| 网格完整性 | 两只手都是单个封闭壳体、绕向一致（A1） |
| 种子复现 | 同一种子得到逐位相同的粒子云；粒子常量改用整数哈希，跨 GPU 同帧（A2、D29） |
| 粒子保形 | 五个种子中位数，只评手指和手掌：IoU 0.863、轮廓均值 6.15 px、负空间 0.717（D10、D27） |
| 测试 | `tsc` 通过；Playwright 11/11 通过 |
| 桌面 | Tauri dev 在目标机上走硬件 GL（Iris Xe、DMA-BUF），能到达 home；**帧率稳定 31 fps**，记为已知问题（D31） |

### 下一轮待办（log-v2 "Next round"）

1. **D31 桌面帧率**：先分清是 WebKitGTK 按 60 Hz 定时器的节拍出帧导致的，还是 GPU 负载导致的。分别测 KDE 100%（DPR 1）、`?tier=low`、Chromium 跑同一场景、release 构建，再对症修。需要用户在桌面上配合测量。
2. **D28 美术**：雕塑表面的平面折面（mass-1）；粒子尾部过腕之后不散开；粒子云密度约为画稿的 1.7 倍。
3. **D30 小项**：穿过指尖间隙的构造线（pose-gapline）；4.2 px 的轮廓接缝（seams-3）。
4. 第 2 步收尾时收集的构建器请求（log-v2 "Step 2 closed"）。
5. 导航（审查 §C）：两个目的地、粒子脑、技术树、输入框、反向转场。round 2 没有做。

### 踩过的坑（下次避开）

1. **按名字调用 workflow 会拿到缓存的旧版脚本**：一律用 `scriptPath` 调用。
2. **后台会话可能被 worktree 保护拦住**，不能修改根目录文件。被 git 忽略的 `.claude/settings.local.json` 里设置了 `"worktree": {"bgIsolation": "none"}`。
3. **`/tmp` 重启就清空**：草稿放在 `outputs/qa/scratch/`（已写进 `.git/info/exclude`）。
4. **workflow 不能跨会话接管**：`resumeFromRunId` 只在同一个会话里有效。换了会话就重新启动，用 `only` 参数只跑还没完成的部分。
5. **Vite 冷启动后的第一个 Playwright 测试可能超时**：`reachHome` 已经放宽到 60 s。
6. **这个沙箱里 git 没有 GitHub 凭据**：由用户自己执行 `! git push origin main`。

---

## 第二部分：粘贴到新会话的 prompt

```text
开始 Alpha v1 的 round 3。round 2（形体与验收）已完成，不要重做。

【环境】
- 直接在仓库根目录 /home/a/Documents/Alpha 的 main 上工作，不要在 .claude/worktrees/ 里（见根目录 CLAUDE.md）。
- 不要自己跑 npm install，它会卡死；缺依赖时让我跑 npm install --legacy-peer-deps。
  Playwright 用 ALPHA_CHROMIUM=/usr/bin/chromium（沙箱里是 SwiftShader，帧时间不代表硬件）。
  Blender 5.2 可以无头运行；cargo 可用；Python 有 numpy / Pillow / scipy。
- 用中文回复我。commit 可以直接做；push 前先问我（沙箱里没有凭据时让我用 ! git push origin main）。

【开工前先读】
1. documentations/log/NEXT_SESSION_PROMPT.md 第一部分
2. documentations/log/log-v2.md：顶部状态、决定 D1–D31、"Step 7"、"Next round"
3. docs/CONTRACTS.md、docs/ACCEPTANCE.md、docs/HAND_ASSETS.md、docs/DESKTOP_CHECK.md

【这一轮做什么】
先把 log-v2 "Next round" 的各项（D31 帧率、D28 美术、D30 小项、构建器请求、导航）
列出来，问我这一轮的范围和顺序，再开始。

【规则】
- 所有待定项和冲突先列出来问我（新决定从 D32 开始编号），不要自己定，也不要让子 agent 定。
- 工作流用 scriptPath 调用，而且要有人在场。
- 每完成一步：更新日志并 commit。
```
