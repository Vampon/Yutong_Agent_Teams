"""The public vocabulary shared by desktop, MCP, SDK and runtime adapters."""
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    code = "conflict"


class Forbidden(ValueError):
    code = "forbidden"


@dataclass(frozen=True)
class Principal:
    actor_id: str = "human"
    group_id: str = ""
    admin: bool = False


HUMAN = Principal(admin=True)
MESSAGE_MODES = {"send", "request_reply", "mail"}
RUN_TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
TASK_TERMINAL = {"done", "cancelled"}


def require_text(value, name, maximum=32000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("%s 应为 1～%s 个字符" % (name, maximum))
    return value.strip()
