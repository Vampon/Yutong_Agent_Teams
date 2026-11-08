# 验证记录

日期：2026-11-06。以下区分真实运行器、协议/模型夹具和界面样本。测试使用项目 `.test-data/` 下独立用户目录，未把样本数据写入日常用户目录。

## 0.4.0：重复派发、结案唤醒与统一验收（2026-11-08）

- 对照本地 CCCC 0.4.48 的 tracked-send、任务版本与 Mail 语义实现。最终交付 work 状态机是本项目新增的简化业务层，架构对应与边界见 `ARCHITECTURE.md`。
- 84 项单元、适配器及接口测试通过（`evidence/v040-unit.txt`）。最终补充根请求的真实交付回复关联后，22 项相关回归再次通过（`evidence/v040-workflow-unit.txt`）：过期分配不得回退 review/done/cancelled；任务开始前再检查；外部领取一次；当前运行接管排队任务；内部提交释放依赖；重复结果仅唤醒一次；最终提交幂等；审批权限；修订轮次隔离；旧数据升级。
- 两个**真实 Claude Code 原生会话**完成协作（`evidence/v040-live-claude.json`）：队长分配、评审成员执行、队长汇总，共 3 次执行；内部任务 1 项；最终验收请求 1 项。测试在隔离数据中模拟人类确认，之后观察 20 秒没有新增执行，无遗留审批。不是用模型夹具代替真实协作证据。
- Claude + DeepSeek 真实联调中，DeepSeek 模型调用返回 `Internal error: turn failed: Request timed out.`（`evidence/v040-live-deepseek.json`）。本次未证明该网络环境下 DeepSeek 能完成模型响应；没有更改用户 VPN、提供方、凭据或原 Harness 设置。协议与协调层回归通过不能替代该模型可用性验证。
- 用 SQLite 只读连接备份用户最近的真实协作库，在独立副本运行升级（`evidence/v040-real-data-upgrade.json`）：两项历史批准任务保持完成，任务链按已有批准事实关闭，待审项为 0，没有新增运行，源库事件版本不变。新程序首次启动才会迁移用户的实际历史。
- UI：原有 11 项 smoke 与 4 项最终交付流程检查通过，无页面 JS 错误（`evidence/v040-ui-smoke.json`、`evidence/v040-ui-workflow.json`）。验证内部评审无审批卡、一次确认关闭、刷新状态保留、显式重新打开只产生一条修订消息，以及 1024px 布局。截图均来自明确的界面夹具。
- 最终单文件 EXE 的 10 项检查通过（`evidence/v040-packaged.json`）：资源自检、真实 WebView2 窗口、成员 HTTP、分身恢复、windowed MCP stdio/工具、外部命令、最终提交幂等、验收仍由人类处理，以及关闭链不被外部领取。测试清除了 Python/Node 的 PATH；外部命令运行器仍使用测试指定的现有 Python 安装。

发布文件：`dist/0.4.0/Yutong Agent Teams.exe`，17,706,417 字节，Windows 文件版本 `0.4.0.0`，SHA256 `f6397672270e7ecdfbd160cb75fc0bde29b89ea95131205d450c07257e2641f7`。原版本保留。工具权限与业务提问仍按原策略处理；统一最终验收只替换内部子任务的逐项人工审核。已进入模型的当前轮次可正常结束，旧任务链不能再派发新的轮次。

## 0.3.2 Harness 模型配置与 ACP 恢复（2026-11-07）

- 只读核对本机 Harness `0.2.0-rc.2`：`profiles/web/cordis.patch.yml` 配置了 `huoshan`，默认模型是 `deepseek-v4-1-flash-260910`，凭据通过 `HUOSHAN_API_KEY` 引用；`profiles/acp/cordis.patch.yml` 没有模型覆盖。ACP 官方 bundle 默认 `deepseek-official / deepseek-v4-flash`，这才是原先“缺少 DEEPSEEK_API_KEY”的直接原因。不是把截图中的已保存火山凭据判定为无效。
- 修复后真实 Harness 启动选中 `huoshan / deepseek-v4-1-flash-260910`，不再报官方密钥缺失；初次实际模型请求返回 `Request timed out`。该次失败保存在 `evidence/v032-deepseek-vpn-timeout.json`。用户随后确认开着 VPN，关闭后原 Harness Web 可正常回复。
- 同一隔离测试会话关闭进程后，真实 `session/resume` 成功，session ID、模型提供方和模型均保留（`evidence/v032-deepseek-resume.json`）。此项没有发起模型请求，不能替代真实端到端调用。
- 独立 Node `fetch` 对同一火山地址两次返回 `UND_ERR_CONNECT_TIMEOUT`（约 10.6 秒），说明连接问题并非仅发生在协作流程里。本机该域名解析到 `198.18.0.37`；没有修改用户 DNS、代理或网络策略。
- 用户反馈关闭 VPN 后 Web 可用，随后独立 Node 无凭据请求已收到 HTTP 401（预期的鉴权响应，证明能连到服务）。重新进行真实协作探针仍在模型请求阶段超时，没有输出或工具执行；最新记录 `evidence/v032-deepseek-live.json` 为 `ok: false`。不能把原 Web 可用或协议恢复成功描述为工作台真实协作已通过。
- 火山 [官方 Harness 接入文档](https://docs.volcengine.com/docs/ark/coding-plan-personal-ai-deepseek-harness?lang=zh) 的示例模型名与用户配置不同；用户已确认现有模型能正常回复，因此保留原模型 ID、地址和协议，没有仅凭文档名称差异修改用户配置。

自动测试证据 `evidence/v032-unit.txt` 覆盖模型条目筛选、原文件/凭据仓库不变、显式 ACP/启动补丁优先、缺省模型与错误配置、旧会话模型保留、首轮失败后的模型切换及回执验证、新版 resume 与旧版 load，以及只含工具调用 ID 的权限请求。模型选择信息可在成员的“会话详情”查看。

61 项单元/接口检查通过；清理新会话旧模型元数据后，相关 9 项会话测试再次通过。界面原 11 项检查与模型设置保存/重载、检查结果显示实际路由的专项检查通过（`evidence/v032-ui-smoke.json`、`evidence/v032-ui-models.json`）。打包后 7 项检查通过，包含 YAML 解析器和 WebView2 窗口（`evidence/v032-packaged.json`）。

发布文件为 `dist/0.3.2/Yutong Agent Teams.exe`，17,695,756 字节，Windows 版本 `0.3.2.0`，SHA256 `cb50abf82a513eb119de881167fc5f1e3e47a6623396af13061636fa6688c27d`。原 Harness 配置和工作台日常协作库未修改；失败的旧运行需由用户选择允许继续或重发，不自动重放业务动作。

## 0.3.1 消息顺序、执行过程与输入框

- 顺序排查：用户截图对应的只读记录显示，任务委派发生在 14:54:33.849640 UTC，关联回复在 14:54:34.822511 UTC，原界面都显示为 22:54。因此保留真实的先委派、后回复；新增秒级时间、独立委派样式和稳定的入库顺序，避免同秒/墙钟回拨或过程更新影响位置。没有修改日常历史记录。
- 单元/接口回归 53 项通过（`evidence/v031-unit.txt`），新增覆盖同时间/时钟回拨、更新不改变顺序、实时输出在完成前可读、工具 ID 关联及失败、截断/脱敏、MATLAB 公共输出映射、远端授权不冒充工具结果，以及 ACP 历史回放不计入当前轮。
- 补充修复“等待中切换权限策略”后的过程状态更新，相关 10 项再次通过（`evidence/v031-permissions-unit.txt`）。MATLAB `checkcode` 完成，仅报告已有 `previous` 赋值的 NASGU 提示，无语法错误（`evidence/v031-matlab-checkcode.txt`）；这不是模型或工具端到端验收。
- **真实 Claude Code**：`evidence/v031-claude-progress.json`。独立目录中实际运行 Claude 原生会话，仅调用团队上下文、收件箱和回复工具。在执行尚未结束时，探针观察到了公开文字、工具输入和关联结果；执行正常完成。没有将界面样本当作真实模型证据。
- 界面：`evidence/v031-ui-progress.json` 覆盖双成员同时输出、工具输入/结果、等待确认、详情实时刷新、结束后收起、秒级时间和委派样式。刷新后保留同一输入框 DOM、草稿、光标、工具展开状态和历史阅读位置；自动增高、无蓝色描边/拖拽角、1024 宽度无横向溢出。原有 11 项 smoke 检查也通过（`evidence/v031-ui-smoke.json`）。无 JS 页面错误。
- 截图 `screenshots/v031-live-output.png`、`v031-process-detail.png`、`v031-composer-1024.png` 均来自明确标记的本地双成员夹具。实时界面以 500 ms 拉取更新，工具自身多久返回仍取决于运行器。
- 本次没有重跑 DeepSeek / CCU / MATLAB / ADP 的真实模型端到端调用；新增协议处理用自动测试验证。MATLAB 远端工具若只回传授权，界面保留“已调用/等待结果”，不会伪造输出。旧执行只能回看当时留存的数据。

过程验证可运行 `python scripts/progress_live_probe.py`；界面先运行 `python scripts/progress_ui_fixture.py`，再运行 `node tests/ui_progress.cjs`。所有脚本使用独立测试目录。

实际 EXE 的 7 项检查通过（`evidence/v031-packaged.json`）：资源自检、真实 WebView2 窗口、成员 HTTP、同源分身恢复、windowed MCP stdio/工具及外部命令。版本 `0.3.1.0`，17,516,616 字节，SHA256 `7365ac1c568aa35972c90ba712a91762250b4c788a61e266feec03248b355ca9`，发布记录为 `evidence/v031-release.json`。原 EXE 正在运行且被 Windows 锁定，因此新版输出为 `dist/0.3.1/Yutong Agent Teams.exe`；未强行关闭用户程序或替换正在使用的文件。退出旧版后再启动新版，配置仍使用同一用户目录。

## 0.3.0 工具权限与成员分身

- 单元/接口回归 46 项通过（`evidence/v030-unit.txt`）；最后补充策略决定的持久事件后，相关 10 项再次通过（`evidence/v030-profiles-unit.txt`）。覆盖共享接入/凭据不复制、分身来源验证、权限继承及原子校验、等待中的请求实时处理、来源被活动分身使用时禁止修改、原生会话/成员凭据隔离、业务提问和交付审核不被工具策略处理。
- **真实双 Claude Code**：`evidence/v030-claude-profiles.json`。在同一协作创建需求评审与代码开发两个分身，各执行三轮。两个原生 session ID 不同；第二轮分别从各自原生记忆返回不同随机口令及职责代号；随后评审分身实际调用团队工具发消息，开发分身以关联回复返回结果。6 次执行全部完成，不读写工程文件或执行终端命令。
- 界面：原有 11 项 smoke 检查通过（`evidence/v030-ui-smoke.json`）；新建双分身、预设、保存/重载工作说明、全局/来源/成员权限继承、同组加入双分身、交付默认值、1024/1440 紧凑布局通过（`evidence/v030-ui-profiles.json`），无 JS 错误及远程资源请求。权限列表头像经实际渲染确认均为 32 px，无拉伸和横向溢出。
- ADP：`tests/test_profiles.py` 检查实际 HTTP 客户端发送的 `SystemRole` 和按成员/代数区分的 `ConversationId`；默认关闭及显式开启的界面流程见 `evidence/v030-adp-ui.json`。这是协议与界面夹具，**没有公司 ADP 凭据，未调用真实应用**。DeepSeek/CCU 的真实模型连接限制维持原记录；本次没有重跑多 MATLAB 实例。
- 实际 EXE：`evidence/v030-packaged.json`，7 项通过。移除 Python/Node PATH 后，资源自检、实际 WebView2 窗口、成员 HTTP、打包环境恢复同源分身、windowed MCP stdio/工具以及调用外部程序均通过。Windows 文件版本为 `0.3.0.0`。

当时 EXE：17,508,789 字节；SHA256 `e8f3cb59dca83b41d92450589f948f617b4f9d5d27fb45ff294c1c04f8f91df7`。发布记录 `evidence/v030-release.json`；界面样本为 `screenshots/v030-create-persona.png`、`screenshots/v030-permissions.png`、`screenshots/v030-personas-1440.png`。

真实分身测试可运行 `python scripts/profile_live_probe.py`；测试脚本创建独立用户目录，工具策略设为拒绝原生额外确认请求，仅使用成员自身有权调用的团队协作工具。日常用户权限不会因此改变。

## 0.2.1 启动、布局与图标修复

用户提供的内网异常堆栈定位到 `HTTPServer.server_bind → socket.getfqdn`。这次修复只替换 HTTP 服务的绑定元数据初始化：直接记录绑定地址和端口，避免启动时反向解析 Windows/内网主机名，不修改全局 socket 行为，也不忽略编码异常。

- 自动测试：36 项通过，日志 `evidence/v021-unit.txt`。新增测试令 `socket.getfqdn` 抛出同样的 `UnicodeDecodeError('utf-8', b'\xbb', 0, 1, 'invalid start byte')`；桌面监听和 Agent 网关仍能绑定并响应请求。这里是故障模拟，不代表已经远程运行过用户的内网电脑。
- 界面：原有 11 项 smoke 检查通过；`evidence/fixes-ui.json` 另验证 4 个本地品牌图标、未知/失败图标回退、成员选择框在 1440/1024 宽度下没有越界，并实际创建两个成员的协作；无外部资源请求或 JS 错误。
- 紧凑卡片：`evidence/fixes-card-density.json`，常规卡片约 173 px 高；1024/1440/1920 宽度分别为 2/3/4 列，没有页面水平溢出。去掉名称相同的重复类型标题。
- 透明图标：用户明确选择程序裁切；最终图与原图 RGB 逐像素一致，只修改 alpha。9 种 ICO 尺寸的四角透明、内部不透明，见 `evidence/fixes-icon-alpha.json`；深浅背景预览见 `screenshots/fixes-icon-backgrounds.png`。
- 实际 EXE：`evidence/v021-packaged.json`，6 项通过；实际 WebView2 窗口加载应用图标和 4 个 Agent 图标。Windows 从 EXE 提取的 32 px 原生图标四角透明，9 种嵌入图标逐帧哈希匹配；文件版本 `0.2.1.0`。

当时 EXE：17,500,452 字节；SHA256 `ff06ad1ed1f3c6de814887bfd497560e1975a27d294c63a80f78d2cf6740f36d`。发布记录为 `evidence/v021-release.json`。成员选择和紧凑列表预览为 `screenshots/fixes-member-picker.png`、`screenshots/fixes-agent-icons.png`，均为独立样本数据。

## 配色与协作图标更新

2026-11-06 更新了中性灰配色、侧栏品牌、浏览器图标和 EXE 图标。生成原图与最终提示词见 `assets/brand/prompt.md`，界面截图见 `screenshots/v2-neutral-*.png`。图标包含宇通三重拱形与三个互联 Agent 节点。

- 接口回归：`python -m unittest tests.test_interfaces -v`，7 项通过，包括 PNG 二进制响应、路径边界，以及原有身份和 MCP/SDK 流程。
- 界面回归：`tests/ui_smoke.cjs`，原有 10 项交互检查及图标加载通过，无 JS 页面错误；测试数据为独立夹具。
- 实际配色：`evidence/neutral-palette.json`，侧栏 `#f5f5f5`、选中项 `#e8e8e8`、内容 `#ffffff`、正文 `#252525`。
- EXE 图标：`evidence/neutral-icon.json`，9 种尺寸（16–256 px）均已嵌入，逐帧哈希与源 ICO 一致。
- 新包回归：`evidence/neutral-packaged.json`，6 项通过，包括实际 WebView2 窗口加载新图标、资源自检、身份 HTTP、MCP stdio/工具和外部命令调用。本次未重新调用真实供应商模型；此前真实协作证据仍列在下方。

该次视觉更新的 EXE：17,490,731 字节；SHA256 `db2b449929497bf91a3e73f427a01570be74cc3343e29f7a6abaab0ff6f09b61`。下方 `v2-packaged.json` 对应这次视觉更新之前的包。

## 已完成验证

| 范围 | 证据 | 结果 |
|---|---|---|
| 核心与接口自动测试 | `python -m unittest discover -s tests -p 'test_*.py' -v` | 34 项通过：独立回执、身份隔离、CAS、幂等、事务回滚、不可变事件、任务依赖/审核、租约不确定状态、旧库迁移、持续会话、实时同伴调用、循环预算、HTTP/MCP、ACP 权限和输出上限 |
| Claude 原生会话 | `evidence/v2-claude-memory.json` | 真实 CLI + MCP，两轮同进程/同 session ID；第二轮记住随机单词；两轮均实际调用已读和回复工具 |
| 真实异构协作 | `evidence/v2-live-team.json` | Claude 原生工具委派任务给 MATLAB → 实际 MATLAB 计算 `disp(2+2)` → 提交交付 → 审核通过 → Claude 继续汇报 |
| MATLAB 持续会话 | `evidence/v2-matlab-memory.json` | 两轮同进程/同会话，第二轮记住随机单词，协作已读与回复均真实产生 |
| CCU 原内核桥接 | `evidence/v2-ccu-fixture.json` | 真实 `build_runtime/Agent` + 本地确定性模型夹具；团队工具确实暴露并被执行，两轮原生历史与进程保持 |
| 当前模型可用性 | `evidence/v2-availability.json` | CCU 当前模型 `Connection error.`；DeepSeek 缺 `DEEPSEEK_API_KEY`；没有把这两项报告为真实模型成功 |
| 腾讯 ADP | `tests/test_adapters.py` | 官方 v2 数据结构的本地 SSE 夹具，成功/替换/中断判断通过；无公司凭据，未连真实应用 |
| 外部 Agent | `tests/test_interfaces.py` | SDK 连接、领取、送达、已读、回复；MCP 工具；拒绝身份注入/非法 Origin；重启端口刷新；网关不开放管理 API |
| 界面 | `tests/ui_smoke.cjs`, `screenshots/v2-*.png` | 群聊、任务创建、上下文编辑、收件回执、人类答复、动态适配器表单、外部连接、转义和 1024 宽度操作通过，无 JS 页面错误 |
| 单文件 EXE | `evidence/v2-packaged.json` | PATH 移除 Python/Node 后，资源自检、WebView2 窗口、身份 HTTP、windowed EXE 的 MCP stdio、协作工具、外部 Python 命令，以及实际 Claude 两轮 MCP/记忆验证通过 |

MCP / ACP 测试只覆盖本实现所声明的功能，不等于通过完整协议一致性认证。窗口测试覆盖本机环境，不等于已在所有公司终端镜像验收。

真实 MATLAB 工具测试中，第一次 MCP evaluate 调用出现连接超时，随后 Agent 使用原项目的 `execute_matlab` 工具获得实际输出 4。报告保留这个过程，不把首次超时省略为全链路无故障。

真实协作验收脚本自动代行了一次**范围限定的测试人工操作**：只允许参数包含 `disp(2+2)` 且不含文件写入等动作的工具请求；任务结果含实际计算值后通过审核。正式软件仍等待界面中的人类确认，不自动采用测试脚本的规则。

## 重现

```powershell
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/v2_claude_probe.py
python scripts/v2_claude_probe.py matlab
python scripts/v2_live_team_probe.py
python scripts/v2_ccu_probe.py
python scripts/v2_availability_probe.py
```

真实探针使用已有模型配置，可能产生原供应商的模型调用费用。`v2_ccu_probe.py` 明确使用本地模型夹具，不读取或替换真实 CCU 模型配置。

界面测试先运行 `python scripts/v2_ui_fixture.py`，再运行 `node tests/ui_smoke.cjs`。测试脚本使用本机 CCU browser-runtime 已安装的 Playwright/Edge；其他开发机应按其 Playwright 安装位置调整 require。界面截图是样本数据，不是模型运行证据。

```powershell
.\scripts\build.ps1 -Python python
python scripts/packaged_check.py --live
```

构建环境：Windows x64，Python 3.8.20，PyInstaller 6.21.0，pywebview 5.4，httpx 0.28.1，Edge WebView2。EXE 哈希由构建脚本写入 `dist/Yutong Agent Teams.exe.sha256`，包测试记录同时保存所测 EXE 的 SHA256。

## 部署前仍需完成

- 核对 DeepSeek 所使用的实际提供方、对应模型目录与网络连通性；当前火山调用超时。修复 CCU 模型连接后，再运行真实业务验收。
- 使用公司 ADP 的已发布应用凭据验证实际权限、会话和内网可达性。普通 SSE 对话接口不能自动提供中途的团队工具调用。
- 用实际两台电脑测试公司防火墙/代理/证书及共享文件路径。本版已验证同机网关的协议与权限边界，未声称完成公司网络的跨机器验收。
- MATLAB 本机启动日志为 Sponsored License；商业部署需使用适用许可。EXE 没有捆绑 MATLAB 或相关商业运行器。

所有 0.1 版证据与源码已归档在 `archives/v0.1-source.zip`。当前 0.2 结论以本文件列出的 v2 证据为准。
