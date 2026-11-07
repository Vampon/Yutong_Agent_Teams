"""Bridge model settings between DSH profiles without editing their source files.

The Web UI writes its own profile; the ACP bundle has a separate default route.
Only model-related overrides are copied into an owned, per-session launch patch.
Credentials remain references resolved by Harness from its own home directory.
"""
import copy
import os
from pathlib import Path

import yaml

from ...config import atomic_json


MODEL_ROWS = {"llm-pi-ai", "llm-deepseek", "llm-deepseek-api-key", "llm-deepseek-account", "agent-default-model"}


def _read(path, required=False):
    if not path.is_file():
        if required:
            raise ValueError("找不到 Harness 模型配置文件：" + str(path))
        return []
    if path.stat().st_size > 4_000_000:
        raise ValueError("Harness 模型配置文件超过 4 MB")
    try:
        value = yaml.safe_load(path.read_text("utf-8-sig")) or []
    except (UnicodeError, yaml.YAMLError):
        # Parser exceptions can contain source lines, including inline secrets.
        raise ValueError("Harness 模型配置必须是 UTF-8 YAML：" + str(path)) from None
    if not isinstance(value, list):
        raise ValueError("Harness 配置文件应为 patch 列表：" + str(path))
    return value


def _models(rows):
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("id") not in MODEL_ROWS | {"acp"}:
            continue
        ident = row["id"]
        if row.get("disabled"):
            result.pop(ident, None)
        elif isinstance(row.get("config"), dict):
            # A Cordis config override replaces the entire row config.
            result[ident] = copy.deepcopy(row["config"])
    return result


def resolve(agent):
    """Return model-only launch patches and a non-secret diagnostic summary."""
    root = Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh").expanduser().resolve()
    explicit = str(agent.get("dsh_config_path") or "").strip()
    provider, model = (str(agent.get(key) or "").strip() for key in ("model_provider", "model"))
    if bool(provider) != bool(model):
        raise ValueError("请同时填写模型提供方和模型 ID，或都留空沿用 Harness 设置")
    home = _read(root / "cordis.patch.yml")
    native = _models(_read(root / "profiles" / "acp" / "cordis.patch.yml") + home)
    args = agent.get("args", [])
    custom_launch = any(x in ("--patch", "--profile") or x.startswith(("--patch=", "--profile=")) for x in args)
    # Respect a deliberately configured ACP profile or user launch overlay.
    if explicit:
        source = Path(os.path.expandvars(explicit)).expanduser().resolve()
        chosen = _models(_read(source, required=True) + home)
    elif native or custom_launch:
        source, chosen = None, native
    else:
        source = root / "profiles" / "web" / "cordis.patch.yml"
        chosen = _models(_read(source) + home)
        if not chosen:
            source = None
    selection = chosen.get("acp") or chosen.get("agent-default-model") or {}
    provider = provider or selection.get("provider", "")
    model = model or selection.get("model", "")
    if bool(provider) != bool(model):
        raise ValueError("Harness 默认模型设置不完整，请在原界面选择提供方和模型")
    if source and chosen and not provider:
        raise ValueError("检测到 Harness 模型提供方，但未选择默认模型；请在原聊天界面选择模型，或在成员设置填写提供方和模型 ID")
    patches = [{"id": ident, "config": value} for ident, value in chosen.items() if ident in MODEL_ROWS] if source else []
    if provider and model:
        patches.append({"id": "acp", "config": dict(chosen.get("acp", {}), provider=provider, model=model)})
    return {"patches": patches, "provider": provider, "model": model,
            "source": str(source) if source else "Harness ACP 配置"}


def launch_patch(plan, directory):
    if not plan["patches"]:
        return []
    path = Path(directory) / "harness-models.patch.json"
    # JSON is a YAML subset, so no custom serializer or shell interpolation.
    atomic_json(path, plan["patches"])
    return ["--patch", str(path)]
