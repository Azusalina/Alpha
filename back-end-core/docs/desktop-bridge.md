# 本机 Tauri 桥接 v1

宿主已在 `src-tauri/` 实现，React 连接层尚未接线。没有修改 `src/`，
浏览器独立运行时没有这个命令。Python API 现已支持双 T/F、exclamation
自动双 true、再次判定和非训练材料预览；编辑／删除仍未实现。

## 前端调用

唯一应用命令是 `brain_call`，参数名为 `request`，返回 API 响应信封。
可将它接到现有 `src/backend/remote.ts` 的 `Transport`：

```ts
import { invoke } from '@tauri-apps/api/core';
import type { Transport, ResponseEnvelope } from './remote';

export const transport: Transport = {
  request: (request) => invoke<ResponseEnvelope>('brain_call', { request }),
};
```

这个例子不是已修改的前端文件。前端负责安装／使用 Tauri JS API 包、
判断桌面环境、选择连接时机，并调用现有 `backendStore.connectRemote`。
先探测 `health.features.two_judgements=true`，再为 RemoteBrainAdapter 设置
`twoJudgements=true`；旧后端仍保持 false。`proposedMethods=false` 不变，
编辑／删除尚不可用。继续用 `health.methods` 判断方法能力。
`input_list` 现返回摘要，不再需要逐条 input_get。分页另接新增 input_page，
不要把旧 input_list 的数组当分页对象；STALE_CURSOR 时丢弃旧页并重新取第一页。
前端 mock／验证逻辑若拒绝 immediate=false + exclamation=true，须改为
用户新确认的“exclamation 直接设双 true”；不要在前端自动从文字推断。
exclamation 提交返回正式 effects，应在提交时显示，不能再调用 pending preview。

业务与传输故障都尽量返回 schema version 1 信封；传输失败使用已有
`MODEL_UNAVAILABLE`。Tauri ACL 拒绝、桌面不可用等仍可能使 `invoke` reject，
要由 Transport／RemoteBrainAdapter 的异常处理覆盖，不自动重试写请求。

## 宿主配置（只能在启动桌面程序时设置）

- Python：`ALPHA_BRAIN_PYTHON`，默认 `python3`。是可执行文件名或路径，
  不是一串 shell 命令；不能附加参数。建议显式指定合适的本机解释器。
- 后端：`ALPHA_BRAIN_ROOT`，必须是含 `core/api.py` 的绝对目录。
  debug 默认使用当前仓库的 `back-end-core`；release 默认查找资源目录里的
  `back-end-core`。当前没有打包 Python／后端／jieba，发行部署仍待实现。
- 数据库：`ALPHA_BRAIN_DB`，必须是绝对文件路径。默认是 Tauri
  `app_local_data_dir()/brain.sqlite3`，**不是仓库里的开发数据库**。
  不自动迁移／复制已有资料；开发时若要读已有模型，应显式设置这个变量。

宿主按固定参数运行 `python -E -s -u -m core.api --db HOST_DB`，cwd 为后端目录。
Python 至少 3.10，jieba 仍按 model/README.md 的本机依赖布局提供。
IPC 无法更改程序、数据库、cwd 或读取文件路径；`.txt/.md` 仍由前端选取、
严格解码后将文本发给 submit。启动失败不会改成 mock 或另建一个备用模型。

后端懒启动：第一次合法调用时启动，后续复用同一进程。健康查询会让
Python 初始化所选数据库的零基线，但不会认可任何材料或训练模型。

## 生命周期与故障

- 所有请求串行执行，队列最多 32 项；满了立即报“未发送”，不无限等待入队。
- 单次调用总期限 30 秒，包含在队列里的时间。过期／已取消且未执行的
  项目不发送；执行中取消前端等待不会留下错位响应，worker 仍结束该交换。
- UTF-8 请求 JSON 最多 6,004,096 字节（另加换行）；响应最多 16,000,000 字节。
  这比 Python 的字符级上限多了一层字节边界；超大 effects 历史需要后续分页。
  响应过大或耗时过长，也可能发生在某次写入已经提交之后。
- 验证响应 ID、版本、信封形状。EOF、无效响应、写入错误、超时会关闭／回收
  当前进程；失败请求**不重放**，只有下一次显式调用才可启动新进程。
- 失败提示会说明写入结果可能不确定。先 `input_get`／`state`／`effects`
  核对，不把“连接失败”当作“没有训练”。submit 尚无幂等键；若未拿到
  source_id，先查询输入列表，避免盲目再次提交造成重复材料。
- 应用 `RunEvent::Exit` 时通知 worker 退出；空闲进程收到 stdin EOF，
  必要时强制结束并等待回收。新调用被拒绝，排队调用不再发送。
- stderr 按小块持续读取后丢弃，防止填满管道；不复制私人诊断内容到
  webview、磁盘日志或无限内存缓冲。需要诊断依赖时可独立运行 Python CLI。

## 权限与限制

应用命令通过 `AppManifest::commands` 纳入 Tauri ACL，而不是依赖自定义命令
的默认开放行为。`default` capability 仅授权 `main` 本地 webview：
`allow-brain-call` 与原来的 `core:app:allow-tauri-version`；没有 remote URL
授权，也没有 shell、网络或任意文件系统插件权限。

配置依据 [Tauri capabilities](https://v2.tauri.app/security/capabilities/) 和
[Tauri permissions](https://v2.tauri.app/security/permissions/)。宿主会进一步
检查 window label。这个边界**不是**原文口令门、磁盘加密或 XSS 防护：
本地主窗口的受信任代码仍可调用原文 API，CSP／渲染安全和原文访问保护
需要后续审查。没有产生临床风险值。

## 已验证与仍待验证

- Rust 真实 Python 进程：submit → preview → 非法审核拒绝 → review →
  关闭／重启 → 原文和 agreed 状态回读。
- 并行请求串行匹配、取消等待、超时后显式新进程、队列满／过期、stdout
  无效／EOF／超大响应、stderr 大量输出、关闭中断与进程回收。
- Tauri MockRuntime 使用真实命令及生成的权限配置，允许本地主窗口调用，
  拒绝其他窗口、远程来源及 app name 查询；原版本查询仍可用。
- `cargo check`、Rust 测试、debug 二进制构建及 Python 回归。
- **尚未验证**：React Transport 接线后的实际 WebKitGTK 点击流程、原生桌面
  关闭时的验收、release runtime 打包和跨平台安装。MockRuntime 测试不是
  原生 WebKitGTK 或 GPU 性能证明；保持 DESKTOP_CHECK.md 的验收边界。
