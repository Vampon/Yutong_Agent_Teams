# 接入现有 Agent

目标是统一协作接口，不替换各系统的模型、工具或会话。根据原系统暴露的能力选择接入方式。

| 原系统能力 | 选择 | 工作台提供的能力 |
|---|---|---|
| 支持 MCP 工具 | 外部成员 + MCP | 群消息、收件箱、任务、上下文和人类提问工具 |
| 能调用 HTTP / 能改自研代码 | 外部成员 + HTTP/Python SDK | 同样的领域操作，外加领取、确认、心跳与会话声明 |
| 支持 ACP v1 stdio | ACP 智能体 | 工作台管理持续会话、传入 MCP 配置并转交权限请求 |
| 只有请求/响应 API | HTTP 或腾讯 ADP | 转交任务与结果；原系统若要主动协作，需另行调用成员 API |
| 只有 stdin/stdout 命令 | 命令行程序 | 每次独立执行，stdin 输入、stdout 文本结果 |
| 没有可调用接口的封闭 GUI | 当前不直接支持 | 需为原系统补接口或桥接；不能承诺零改造接入 |

## 外部成员接入步骤

1. “智能体”→“接入智能体”→“外部智能体 · MCP / SDK”，设置唯一 ID、名称和职责。
2. 在协作的“成员”设置中加入它。
3. 右侧“连接外部成员”或成员详情“获取接入配置”。每份配置只绑定这个协作中的这个成员。
4. MCP 系统复制本机 MCP 配置；自研 Python 使用“导出 SDK”得到 `teams_client.py`，放入原工程；其他语言调用 HTTP。
5. 让原系统读取上下文和收件箱，处理实际任务，再显式回复/提交交付。工作台不会自动启动外部系统或替它建立轮询循环。

本机 MCP 配置使用独立 stdio 桥接进程，启动命令为本 EXE 的 `--mcp --connection <文件>`。即使使用无控制台单文件 EXE，也支持继承的 stdin/stdout 管道。桥接每次调用读取连接文件，因此工作台重启换端口后无需重新复制本机配置。

外部 MCP 通道只提供工具，没有主动向任意模型会话推送输入的通用机制。原运行器需要在用户请求或自身调度中读取收件箱；需要自动领取新工作时，使用下面的 SDK 轮询循环，或选择受管理的 ACP 适配器。

## Python SDK

导出的 SDK 仅使用标准库。直接连接 HTTP 不依赖桌面包；本机 Windows DPAPI 配置也能由此单文件读取。

```python
from teams_client import AgentClient

# 在原 Agent 所在的 Python 环境中运行；本机配置只能由同一 Windows 用户解密。
client = AgentClient.from_connection(r"C:\Users\你的用户名\.yutong-agent-teams\connections\生成的文件.json")

# 跨电脑时改用连接面板里的地址和成员凭据：
# client = AgentClient(endpoint="http://协作电脑:43821/agent/v1", token="成员凭据")

client.connect(client="My existing agent", session_id="原系统自己的会话ID")
context = client.call("context.get")
```

把领取动作接入原系统的调度。示例中的 `existing_agent.run` 是你自己系统的真实入口，须由集成方提供：

```python
import threading
import time

shutdown = threading.Event()

def keep_alive():
    while not shutdown.wait(20):
        try:
            client.heartbeat()
        except Exception:
            # 连接恢复后继续心跳；不自动重放业务执行。
            pass

threading.Thread(target=keep_alive, daemon=True).start()
try:
    while not shutdown.is_set():
        batch = client.claim(limit=1)
        if not batch:
            time.sleep(1)
            continue
        message = batch[0]["message"]
        mid = message["id"]
        client.delivered(mid)  # 已由本系统接收
        client.read(mid)       # 实际开始处理前确认已读
        result = existing_agent.run(message["text"])
        client.reply(mid, result, client_id="reply-" + mid)
        if message.get("task_id"):
            task = next(t for t in client.call("task.list") if t["id"] == message["task_id"])
            client.call("task.update", id=task["id"], version=task["version"],
                        action="submit", text=result)
finally:
    shutdown.set()
```

业务异常不要假装成功；可通过 `actor.status` 报告 `blocked`，或给原消息发送真实失败原因。外部 Agent 应在自己的系统持久记录已执行的消息 ID/结果，恢复时先核对；本 SDK 不会自动重试可能已成功的 POST。`claim` 的 60 秒窗口用于**确认接收**，无需在 60 秒内完成长任务；接收后先 `delivered`，再执行。

同一成员身份只能代表同一个执行主体。如果多台机器希望同时参与，为每个执行主体建立独立成员。会话 ID 由外部系统持有，工作台不伪造其会话恢复能力。

## MCP 工具 / HTTP 操作

HTTP：`POST /agent/v1`，请求头 `Authorization: Bearer <成员凭据>`，JSON 内容：

```json
{"op":"message.send","data":{"targets":["matlab"],"mode":"request_reply","text":"请核对这个工况","client_id":"stable-request-id"}}
```

返回成功 `{ "ok": true, "data": ... }`；参数错误 400、身份权限错误 403、版本/幂等冲突 409。调用参数中的 `actor_id` 不能改变作者身份；凭据绑定的协作决定操作范围。

| MCP 工具 | HTTP op | 用途 |
|---|---|---|
| `teams_context_get` | `context.get` | 目标、约束、决定、交接、成员职责与工作状态 |
| `teams_context_update` | `context.update` | 携带 version；同伴追加决定/交接，队长可改目标/约束 |
| `teams_send` / `teams_reply` | `message.send` / `message.reply` | 发送消息或以 reply_to 关联回复 |
| `teams_history` | `message.history` | 最近共享群历史，不产生已读确认 |
| `teams_inbox_list` / `teams_inbox_read` | `inbox.list` / `inbox.read` | 查看收件箱 / 显式读取 |
| `teams_task_list/create/update` | `task.list/create/update` | 分配任务、查看依赖、提交结果 |
| `teams_request_human/status` | `human.request/status` | 异步请求人类决策与查询答复 |
| `teams_set_status` | `actor.status` | 更新 focus / blocked |
| SDK 专用 | `session.connect/heartbeat`, `inbox.claim`, `delivery.ack` | 外部运行器接入、心跳、领取和传输确认 |
| HTTP 专用 | `events.list` | 以 after 游标查看协作事件 |

`targets` 支持成员 ID、`@all`、`@peers`、`@foreman`、`human`。群历史是当前协作成员共享的，定向投递不会自动变成成员间保密的私聊。`request_reply` 是跟踪语义，不会阻塞 API 等待模型回复。

MCP HTTP 为 `/mcp`，采用支持 JSON 响应的无状态 Streamable HTTP。支持 initialize、ping、tools/list、tools/call；通知返回 202；不提供服务器发起 SSE 通道，GET 返回 405。此核心实现不包含 MCP OAuth、资源/提示词服务或完整 MCP 全功能。协议参考：[MCP transport specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)。

## 跨电脑

在“设置”启用 Agent 接入服务，默认监听 `0.0.0.0:43821`，填写其他电脑实际可访问的根地址。连接面板随后提供远端 MCP 配置及 HTTP 地址/凭据。公司防火墙需要允许选定的监听端口；跨不可信网络使用 HTTPS 反向代理。

本机 UI 管理端始终只接受 loopback 和桌面访问令牌。Agent 网关不开放 `/api`，成员凭据也不能充当管理员令牌。停止工作台会停止这个接入服务；独立服务模式可以用 `--worker --host 0.0.0.0 --port 43821`，但同一用户数据目录不能同时运行两份控制服务。应先在桌面配置好成员和连接。

工作目录是本机路径。跨电脑运行时，原系统需使用自己的路径映射或共同共享盘；本版不做工程目录上传、复制或同步。

## 各运行器

**Claude Code**：启动原 CLI 的双向 stream-json 模式，传入工作台 MCP 配置；每个成员保留进程和 session ID，重启后使用原生 resume。协作工具在自身权限范围内可直接调用，其他被原 CLI 送来确认的工具按工作台的成员/全局策略处理，手动模式进入“待我处理”。已安装的 CLI 登录、项目规则和工具权限仍生效。

**DeepSeek Harness**：使用 `dsh --profile acp`。Web 页面把提供方和模型选择写入 `$DSH_HOME/profiles/web/cordis.patch.yml`，ACP 默认有独立的 `deepseek-official` 路由；在 Web 配好自定义提供方不等于 ACP 已选择它。0.3.2 自动检测：已有 ACP 模型覆盖或显式 `--patch/--profile` 参数时保留它们，否则从 Web 配置只提取模型相关条目，通过当前成员会话目录中的独立 `--patch` 注入，不启动 Web 插件、不修改原 Harness 配置，也不读取凭据文件。凭据引用仍由 Harness 在同一 `DSH_HOME` 解析。可在成员设置指定其他模型配置文件，以及成对填写提供方/模型 ID；“检查配置”会报告选中的路由，尚不代表网络连通。

新建会话使用所选路由；第一次执行即失败、没有完成轮次的历史会话，在恢复后可通过 ACP 提供的模型选项纠正路由。已有成功轮次的会话保留原模型，要换模型请明确新建会话。显式更改成员模型设置仍遵循原有运行环境指纹检查。模型配置修改在下次启动该运行器时生效。

本机 Harness `0.2.0-rc.2` 提供 `sessionCapabilities.resume`，恢复调用 `session/resume`；其他 ACP 实现声明 `loadSession` 时继续兼容 `session/load`。不宣称提供客户端文件系统/终端能力。参考 [Harness ACP 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)、[模型配置与 Profile 路径](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)。

**CCU**：指向 `D:\Project\CCU Agent` 和能运行其依赖的 Python；可选配置文件。通过原 `build_runtime/new_agent` 创建驻留成员，在保留领域工具路由的同时注册团队工具，不修改原项目。当前真实模型连接错误需要在 CCU 原环境排查，桥接本身的持续会话/工具测试使用本地模型夹具。

**MATLAB**：指向原 automotive-agent 与 MATLAB 程序。桥接沿用原 Runner、模型配置、工具和 SDK，保存原生消息历史。实际计算工具和协作工具走不同通道：业务工具按原权限分类提交工作台确认策略，团队工具受成员身份范围约束。当前本机许可属于 Sponsored License，不能据此判断已满足公司商业使用条件。

**腾讯 ADP**：使用已发布应用的 AppKey 和 UserId，`POST https://wss.lke.cloud.tencent.com/adp/v2/chat`。实现独立 ConversationId、唯一 RequestId、reply 文本过滤、text.delta/text.replace、成功完成事件校验；流提前断开按失败处理。官方说明此 HTTP SSE 对话接口是单向流，不支持请求中双向交互。因此普通 ADP 接入能接任务、回结果，不能凭这个接口自动成为会调用 Teams 工具的原生成员。需要在 ADP 应用的工具/工作流中另行调用成员 HTTP API，并解决公司 ADP 到内网的网络可达性。尚未获得公司应用凭据，未做真实调用。[腾讯官方对话端文档](https://cloud.tencent.com/document/product/1759/129202)。

**通用 HTTP**：请求体 `{message, session_id, request_id}`；默认从 JSON 的 `result` 字段读取结果，支持自定义字段路径如 `data.answer`。稳定 session_id 只是接口参数，是否保存上下文由原系统决定。

**单次命令**：程序路径与 JSON 参数数组，不执行 shell 包装字符串。stdin 接收 UTF-8 任务，stdout 作为结果。超时/取消终止自己拥有的进程树，输出超过 1 MB 明确失败；没有跨次原生会话。任意 CLI 若支持 ACP，优先使用 ACP 入口获得原生会话与工具协作。


## 分身与确认策略

原生运行器可以从同一个接入创建多个独立成员，复用接入配置但隔离会话和成员身份；详见 [PROFILES.md](PROFILES.md)。ADP 仅在接入设置显式开启 `allow_personas` 后允许分身，角色设定传为 `SystemRole`，`ConversationId` 包含协作、成员和会话代数。未声明 `profiles` 能力的适配器不会默认开放分身。
