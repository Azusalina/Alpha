# Alpha v1 审查与下一阶段实现建议

审查日期：2026-09-19  
仓库：Azusalina/Alpha  
审查基线：main @ `0453b74092a1688ed31d6b1a81a4ff42ef6eaad4`

## 结论

当前成果适合作为启动交互原型，已有可保留的技术骨架：React / TypeScript / R3F、单一进度值、GPU 粒子动画、集中配置、启动阶段隔离和基本回归测试。

最需要投入的是双手的形体与参考图匹配。人手仍有明显的管状拼接感、接缝和尖爪状指尖；粒子手的弯曲手指朝向与参考不同。建议下一轮优先修正网格和验收工具，再完成静态构图，不要同时扩展脑、树和复杂特效。

README 已明确本次只实现启动页。因此目的地和往返缺失属于尚未完成的功能范围；下面的随机采样、网格朝向和图像对比问题则属于当前实现中的缺陷。

## 本次实际验证

- `npm run build` 成功，包含 TypeScript 检查；Vite 给出单个 JS chunk 超过 500 kB 的提示，这不是当前美学问题的首要原因。
- 现有 Playwright 测试 7/7 通过；它们覆盖的是启动阶段，不足以证明视觉质量、目的地导航或可逆变形达标。
- 在独立端口 5175 运行审查版本，以 1644 × 957、DPR 1 重新截图。
- 鼠标停留左上角 1 秒后：角标已点亮，状态仍为 `home`，符合当前尚未接入导航的代码。
- 粒子鼠标影响强度在移入后约为 0.975，移出后降至约 0.00364；本次运行未捕获 console error 或 pageerror。
- 渲染器为 ANGLE / SwiftShader。没有完成真实 Intel Xe GPU 或 Tauri / WebKitGTK 的性能验收。
- 安装依赖时 `npm ci` 长时间无输出，已终止；本次复用本机现有项目依赖的副本，两个项目的 package-lock.json SHA-256 完全相同。此次不声称验证了从空缓存安装。
- 未修改仓库源文件，也未提交或推送本次审查。

证据文件：

- [独立运行首页截图](home-independent.png)
- [鼠标移入截图](pointer-independent.png)
- [运行记录](runtime-independent.json)
- [几何与随机采样诊断](geometry-independent.json)

## A. 应先修正的具体问题

### A1. 网格三角形朝向与法线不一致，且各部位没有连成连续表面

**优先级：高。**

[mesh.ts:105](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/src/hand/mesh.ts#L105) 中的 `out.indices.push(a, c, b, b, c, d)` 与环绕顶点的排列方向相反。对当前左手全部 5640 个三角形计算几何面法线与所存顶点法线之和的点积：5495 个为负，145 个为正。

这说明绝大多数三角形的正面方向与提供的法线相反。`DoubleSide` 能让反面显示出来，却不能代替正确的网格朝向；它还会影响着色时的法线方向。

另外，[buildHandSurface](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/src/hand/mesh.ts#L267) 只是把前臂、手掌和各指的顶点放入同一几何体，没有使连接处共享连续表面。截图能直接看到腕部和掌指连接处的白色三角缺口。修正三角形朝向不能单独消除这些接缝。

**实现方法：**

1. 先修正管壁三角形顺序，例如 `(a,b,c)`、`(b,d,c)`；封口单独验证方向，不要整张网格盲目翻转。
2. 椭圆截面及变化半径的管面应使用正确表面导数计算法线，或在正确连接后的网格上重算法线。
3. 采用连续手掌拓扑，连接腕部与指根；仅调用 `mergeVertices` 无法焊接本来就位置不同的截面。
4. 以关闭构造线、使用单色材质的视图验收：先看轮廓、接缝、受光是否连续。

### A2. 同一 seed 不能重建同一粒子分布

**优先级：高，修复成本低。**

[sampling.ts:71](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/src/hand/sampling.ts#L71) 创建了有种子的 `rng`，但没有把它传给 `MeshSurfaceSampler`。后者的表面采样仍默认使用 `Math.random`。

独立验证：用同一 rig、同一 seed 和 10000 个粒子连续生成两次，30000 个 `home` 坐标分量全部不相等。因此重载截图不能严格重现，也不满足“从 seed 重建”的约定。当前同一会话保留已有数组的做法仍可保留，不能由此推断尚未实现的返回动画必然失败。

**修正：**

```ts
const sampler = new MeshSurfaceSampler(mesh)
  .setRandomGenerator(rng)
  .setWeightAttribute('aWeight')
  .build();
```

验收：同 seed 的 home / size / id 数组相同，不同 seed 的 home 数组不同。未来反向动画必须复用原先的粒子 ID 与 home 数据。

依据：[Three.js MeshSurfaceSampler 官方文档](https://threejs.org/docs/pages/MeshSurfaceSampler.html)。

### A3. 显现 shader 使用未定义的 smoothstep 边界顺序

**优先级：中，建议一起修复。**

[HumanHand.tsx:75](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/src/scene/HumanHand.tsx#L75)：

```glsl
smoothstep(uReveal, uReveal - 0.16, vReveal)
```

其第一个边界恒大于第二个边界。GLSL 对这种情况不保证结果。当前 Chromium 看起来可用，不足以保证目标 WebKitGTK / GPU 驱动表现一致。

改成：

```glsl
float edge = 1.0 - smoothstep(uReveal - 0.16, uReveal, vReveal);
```

确认 progress=0、0.5、1 时的边界和最终完整显现。依据：[Khronos GLSL 规范](https://registry.khronos.org/OpenGL/specs/gl/GLSLangSpec.1.20.pdf)。

### A4. 当前“红蓝叠图”无法区分参考和结果

**优先级：高，避免后续验收失真。**

[overlay_check.py:35](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/scripts/overlay_check.py#L35) 对红、蓝通道都使用了 `lighter(image, 全白图)`，结果恒为 255。实际检查已提交的 overlay：R、B 通道范围均为 `(255,255)`，只剩绿色通道在变化。因此图例声称的“参考红色、结果蓝色”并没有成立。

**实现方法：**

- 把两张图先归一化成白背景黑墨迹，再用 `(renderGray, min(refGray,renderGray), refGray)` 组合，实现参考红、结果蓝、重叠黑。
- 要求输入截图分辨率匹配；不要把任意宽高比截图直接拉伸到参考尺寸。
- 左右手分别输出 ID / silhouette mask，构造线、粒子尾巴与手形轮廓分开评估，避免线条被识别成指尖。
- 当前只寻找 4 个局部极值；“平均误差 14.3px”不能表示整体手形准确。增加指关节、腕角、轮廓采样点、指间负空间以及两指间隙的测量。

### A5. Playwright 的项目配置覆盖了参考视口

[playwright.config.ts:30](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/playwright.config.ts#L30) 展开 `devices['Desktop Chrome']`，该预设包含 1280 × 720，会覆盖顶层的 1644 × 957。

**修正：**在该展开之后再次显式设置 `viewport: { width: 1644, height: 957 }`。这针对测试配置；本次独立截图已明确使用 1644 × 957，原项目单独的截图脚本也有自己的尺寸设置。

现有“短暂 hover 不跳转”测试即使完全没有导航也能通过。以后要补充持续 hover 能进入目标、反方向能返回、动画期间重复输入不会产生第二个 timeline 的正向验证。

## B. 美学路线：保留框架，重新建立手的可信形体

### B1. 先完成双手静态形体

**推荐工作流：可编辑的手模型 → 分别摆出两只手的姿态 → 固定主相机校准 → GLB → R3F 显示 / 表面采样。**

“几何版本”描述的是美术语言，不要求整只手必须通过 TypeScript 管道生成。建议用有合适授权的基础手网格，或自行制作的连续手网格，在 Blender 中调整并保留可编辑源文件。运行时使用真正的模型，便于摄像机移动、遮挡、显现以及粒子采样。Three.js 可通过 [GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html) 加载 glTF / GLB。

当前程序化骨架仍可作为定位辅助和构造线的数据源。若继续程序化建模，需要明确增加手掌体块、指根连接、指腹、指节转折与合理指尖，这会是专门的建模工作。

具体顺序：

1. 锁定主相机与参考画幅，建立双手独立的骨骼姿态。
2. 先用纯色 silhouette 比对手腕方向、掌宽、每根手指及指间负空间。
3. 再调整指节和掌面体块，最后添加材质与线条。
4. 使用实际相机的投影 / 反投影校准；当前 imageToWorld 的线性 XY 换算只在 z=0 平面精确，添加深度后需考虑透视投影。
5. 微幅检查侧面，确保主视角校准没有把手压成无法承受镜头移动的纸片。

右手必须独立摆姿态。[当前 buildRightHandRig](https://github.com/Azusalina/Alpha/blob/0453b74092a1688ed31d6b1a81a4ff42ef6eaad4/src/hand/skeleton.ts#L177) 仅根据腕部和食指尖，把左手整体旋转、缩放、平移。这能约束两个点，不能匹配另一只手的所有关节；实拍截图中其余手指向上伸展，与参考图明显不同。

可逆粒子映射只要求每个粒子的起点、终点和 ID 稳定，不要求两只手共用同一个姿态。

### B2. 左手：柔和实体和有理由存在的几何线

- 材质从浅色石膏 / 象牙灰开始，保持较高粗糙度、非金属；先纠正法线，再调整灯光。
- 灯光以柔和主光和较弱补光展现指节与掌骨；控制背景与亮部的差异，避免整只手成为同一块灰色。
- 构造线分成主轮廓、关节轴与比例圆、少量延长辅助线；它们应围绕骨点及比例关系生成。
- 使用长度属性控制绘制顺序：腕部结构 → 掌骨 → 指节 → 外轮廓 → 实体显现。各层留有少量重叠，避免机械的串行切换。
- 线条细节验收放在实体轮廓之后，避免线条掩盖建模问题。

### B3. 右手：先读成手，再读成流动粒子

当前粒子偏密、黑色团块明显。建议先修正右手姿态，再改变分布与动画。

- 指尖、指节和主轮廓保持足够采样密度；掌面使用疏密变化，腕后逐渐散开。
- 采用分层的粒径与透明度，减少多个大黑点重叠成斑块；稀疏连线可以作为后续可选项。
- 周期运动围绕固定 home 坐标计算，让每个粒子有固定相位。限制轮廓附近的位移，保留形状可读性。
- hover 使用平滑的局部衰减场，移出后扰动项趋近零，回到原 home 分布；不需要为此引入完整物理模拟。
- 继续使用现有 GPU uniform 驱动方案，避免每帧在 React 中更新数千个位置。

## C. 下一条完整交互：main → human → main

静态双手达到视觉要求后，先完成一个方向的完整往返，再拓展右侧。推荐沿用一个持久 Canvas 和一个相机写入入口。

### 状态与交互

`home → toHuman → human → fromHuman → home`

- home 的左上热区持续 hover 达到阈值后触发；短暂经过取消。
- toHuman / fromHuman 期间锁定重复触发，只允许一个过渡驱动器。
- human 状态在右下启用返回热区；返回完成后重新启用主画面热区。
- 让摄像机、材质显隐、粒子迁移、目的地 DOM 都读取同一个 `p`。CameraRig 当前逐帧固定 home 相机，需改为按状态和 p 计算相机位置、朝向。
- 输入框直到目标区域稳定时才挂载或解除 inert；启动时完全不存在可聚焦的目标内容。
- 键盘以明确的 Enter / Space 激活方式触发导航，避免仅获得焦点便自动离开当前区域。

### 双手如何参与形成新区域

1. 为左手表面预采样固定粒子集合，保存 `id / handPosition / brainPosition / phase`。
2. 几何线先延展，实体通过空间遮罩解体；同一位置的粒子同时显现，避免突然切换成另一团点。
3. 粒子沿确定路径迁移到 brainPosition。中途扰动乘以端点为零的 envelope，例如 `sin(PI*p)`，保证端点准确。
4. 右手作为辅助形体逐渐解体、淡出；`ambientBorderParticles` 继续默认 false。以后打开时，把粒子终点切换为边框分布即可。
5. 返回采用同一组起终点、同一路径，让 p 从 1 回到 0；不要重放 startup，也不要重新随机采样。
6. 起步可按空间分区 / 排序建立稳定匹配，减少粒子横穿形成的混乱；更复杂的最优运输留到确实需要时。

之后复用这套机制实现 `home → system → home`，技术树先使用固定占位数据；脑与树的语义关联随后接入。

## D. 桌面验证时机

保留当前 Web 技术栈来实现和调试视觉，同时尽早做最小 Tauri 外壳验证，不要等全部特效完工。

Tauri 在 Linux 使用 WebKitGTK，与本次 Chromium 验证不同。[Tauri 官方说明](https://v2.tauri.app/reference/webview-versions/)

在目标 Arch / KDE Wayland / Intel Xe 上记录实际渲染器、分辨率、DPR、帧时间 p50 / p95、首次 shader 编译、窗口缩放以及最小化恢复。优先使用当前 6000 / 12000 粒子档位比较；必要时调整 DPR 和粒子预算。软件光栅结果不能用来认定 Intel Xe 不够用。

只有出现已复现且难以解决的目标 WebView 问题，才评估 Electron；目前没有证据需要换引擎或使用游戏开发框架。

## E. 给 Claude 的下一轮任务边界

建议下一轮只交付“静态形体与验收修正”，按下列顺序执行：

1. 修复 seed、smoothstep、网格朝向、overlay 和测试 viewport。
2. 建立双手独立姿态；决定连续网格 / GLB 的资产实现方案，并保留可编辑来源。
3. 在真实参考视口输出 silhouette、无构造线实体、完整材质三组截图。
4. 完成参考图叠加、关键点与指间负空间检查；记录仍存在的偏差，不把少数骨点误差当作整只手达标。
5. 调整构造线和粒子明暗层次，再复查启动显现与 hover 恢复。
6. 在目标桌面环境进行最小运行验证。

该轮验收应能明确回答：两只手的姿势是否匹配、是否还有可见接缝、实体是否有古典雕塑体块、粒子是否保持手形、相同 seed 是否可复现。之后再开展左侧目的地往返。
