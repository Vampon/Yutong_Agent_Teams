"""Adapter registration plus declarative UI fields and capability disclosure."""
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AdapterSpec:
    kind: str
    title: str
    factory: object
    capabilities: dict
    fields: list
    description: str


def field(key, label, required=False, hint="", type="text"):
    return dict(key=key, label=label, required=required, hint=hint, type=type)


class AdapterRegistry:
    def __init__(self):
        self.specs = {}

    def register(self, spec):
        if spec.kind in self.specs:
            raise ValueError("Duplicate adapter: " + spec.kind)
        self.specs[spec.kind] = spec

    def get(self, kind):
        if kind not in self.specs:
            raise ValueError("未注册的接入方式：" + kind)
        return self.specs[kind]

    def catalog(self):
        return [dict(kind=s.kind, title=s.title, capabilities=s.capabilities, fields=s.fields, description=s.description)
                for s in self.specs.values()]

    def check(self, agent, config):
        from .processes import executable
        spec = self.get(agent["kind"])
        for f in spec.fields:
            if f["required"] and not agent.get(f["key"]):
                raise ValueError("请填写" + f["label"])
        if spec.capabilities.get("local"):
            executable(agent.get("command"), agent["kind"])
        marker = {"ccu": "ccu_agent/core/runtime.py", "matlab": "+autoagent/Runner.m"}.get(agent["kind"])
        if marker and not (Path(agent.get("project", "")) / marker).is_file():
            raise ValueError("项目目录缺少 " + marker)
        if agent["kind"] in ("adp", "http"):
            if not agent.get("url", "").startswith(("https://", "http://")):
                raise ValueError("接口地址应使用 HTTP(S)")
        if agent["kind"] == "adp" and not config.secret(agent):
            raise ValueError("请填写 ADP AppKey 或配置凭据环境变量")
        if agent["kind"] == "deepseek":
            from .providers.deepseek_config import resolve
            plan = resolve(agent)
            model = "%s / %s" % (plan["provider"], plan["model"]) if plan["provider"] else "Harness ACP 默认模型"
            return {"message": "模型：%s；配置检查通过，尚未验证连接" % model, "capabilities": spec.capabilities,
                    "model": {k: plan[k] for k in ("provider", "model", "source")}}
        return {"message": "配置检查通过，尚未验证模型连接", "capabilities": spec.capabilities}


def default_registry():
    from .providers.claude import ClaudeAdapter
    from .providers.acp import ACPAdapter
    from .providers.ccu import CCUAdapter
    from .providers.matlab import MatlabAdapter
    from .providers.http import HttpAdapter
    from .providers.command import CommandAdapter
    registry = AdapterRegistry()
    program = [field("command", "可执行程序", True), field("args", "附加参数", hint="JSON 字符串数组", type="json")]
    project = [field("project", "项目目录", True)]
    credentials = [field("secret", "凭据", type="password", hint="留空保留现有凭据"), field("secret_env", "凭据环境变量")]
    network = [field("url", "接口地址", True), field("ca_bundle", "私有 CA 证书路径")]
    native = dict(local=True, tools=True, session="native", approvals=True, streaming=True, auto_reply=False, profiles=True)
    registry.register(AdapterSpec("claude", "Claude Code", ClaudeAdapter, native, program,
        "持续会话与原生 MCP 协作工具；工具执行遵循原生权限与工作台确认策略。"))
    registry.register(AdapterSpec("deepseek", "DeepSeek Harness", ACPAdapter, dict(native, session="acp"), program + [
        field("dsh_config_path", "模型配置文件（可选）", hint="留空优先使用已有 ACP 配置，否则读取 Harness Web 设置；也可指定 cordis.patch.yml。"),
        field("model_provider", "模型提供方（可选）", hint="与模型 ID 成对填写，例如 huoshan；留空使用原默认选择。"),
        field("model", "模型 ID（可选）", hint="使用 Harness 模型目录中已配置的模型 ID。"),
        field("secret", "DeepSeek 官方 API Key（可选）", type="password", hint="自定义提供方沿用 Harness 中已保存的凭据，无需重复填写。"),
        field("secret_env", "DeepSeek 官方凭据环境变量（可选）")],
        "通过 ACP 协作；自动衔接已有模型设置，凭据仍由 Harness 管理。"))
    registry.register(AdapterSpec("acp", "ACP 智能体", ACPAdapter, dict(native, session="acp"), program,
        "接入支持 Agent Client Protocol 的运行器；会话恢复取决于服务端能力。"))
    registry.register(AdapterSpec("ccu", "CCU Agent", CCUAdapter, native, program + project + [field("config_path", "配置文件")],
        "保留 CCU 的原生会话、工具与技能，注册统一协作工具。"))
    registry.register(AdapterSpec("matlab", "MATLAB Agent", MatlabAdapter, dict(native, session="bridged"), program + project,
        "驻留 MATLAB 运行器与持久消息历史，使用原有汽车电子 Agent。"))
    registry.register(AdapterSpec("external", "外部智能体 · MCP / SDK", None,
        dict(local=False, tools=True, session="external", approvals=False, streaming=False, auto_reply=False), [],
        "模型、会话和工具由原系统管理。通过 MCP 或 HTTP/SDK 加入协作。"))
    registry.register(AdapterSpec("adp", "腾讯 ADP", HttpAdapter,
        dict(local=False, tools=False, session="provider", approvals=False, streaming=True, auto_reply=True, profiles="opt_in"),
        network + credentials + [field("user_id", "ADP 用户标识", True)],
        "文本接口接入；ADP 会话由平台管理。原生协作工具需在 ADP 应用中另行配置 HTTP 调用。"))
    registry.register(AdapterSpec("http", "HTTP 智能体", HttpAdapter,
        dict(local=False, tools=False, session="provider_declared", approvals=False, streaming=False, auto_reply=True),
        network + credentials + [field("response_path", "结果字段路径", hint="默认 result；例如 data.answer")],
        "向现有接口投递任务并接收回复；会话保持依赖该接口实现。"))
    registry.register(AdapterSpec("command", "命令行程序", CommandAdapter,
        dict(local=True, tools=False, session="none", approvals=False, streaming=False, auto_reply=True), program,
        "stdin 输入任务、stdout 返回文本。一次性程序不具备原生持续会话。"))
    return registry
