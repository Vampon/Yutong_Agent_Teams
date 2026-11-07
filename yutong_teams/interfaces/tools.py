"""One tool contract, shared by MCP and the native CCU/MATLAB bridges."""


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


TEXT = {"type": "string"}
STRINGS = {"type": "array", "items": TEXT}
VERSION = {"type": "integer", "minimum": 1}


def tool(name, op, description, properties=None, required=None, read_only=False):
    return dict(name=name, op=op, description=description, inputSchema=schema(properties, required),
                annotations={"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False})


TOOLS = [
    tool("teams_context_get", "context.get", "Read the team brief, constraints, decisions, handoffs, roster and member focus. Read this before working.", read_only=True),
    tool("teams_context_update", "context.update", "Update shared coordination context using the version just read. Peers may append decisions/handoffs. Only the foreman may change brief/constraints.",
         {"version": VERSION, "brief": TEXT, "constraints": STRINGS, "decision": TEXT, "handoff": TEXT}, ["version"]),
    tool("teams_send", "message.send", "Send to team members or human. send wakes a managed member, request_reply explicitly tracks a response, mail waits in the inbox without interrupting. Use stable client_id for retries.",
         {"targets": STRINGS, "text": TEXT, "mode": {"enum": ["send", "request_reply", "mail"]}, "client_id": TEXT}, ["targets", "text"]),
    tool("teams_reply", "message.reply", "Reply to an existing message by its ID. This creates a real reply receipt; terminal output alone does not. Never impersonate another member.",
         {"reply_to": TEXT, "text": TEXT, "mode": {"enum": ["send", "mail"]}, "client_id": TEXT}, ["reply_to", "text"]),
    tool("teams_history", "message.history", "Read recent shared conversation without acknowledging your inbox. Every member in this collaboration can see this shared history.",
         {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, read_only=True),
    tool("teams_inbox_list", "inbox.list", "List your inbox without marking anything read. Mail is available here even while other work continues.",
         {"limit": {"type": "integer", "minimum": 1, "maximum": 100}, "unread": {"type": "boolean"}}, read_only=True),
    tool("teams_inbox_read", "inbox.read", "Read your inbox and explicitly acknowledge the returned messages. Omit message_ids to read the current unread batch.", {"message_ids": STRINGS}),
    tool("teams_task_list", "task.list", "Read durable tasks, owners, dependencies, results and current versions.", read_only=True),
    tool("teams_task_create", "task.create", "Delegate a concrete deliverable to a team member, or create your own task. Dependencies use existing task IDs. Do not send a duplicate message for the same work.",
         {"title": TEXT, "description": TEXT, "agent_id": TEXT, "depends_on": STRINGS, "client_id": TEXT}, ["title", "agent_id"]),
    tool("teams_task_update", "task.update", "Report progress, a blocker or a real result on your own task. Use the current version. submit requests human review when enabled; agents cannot approve their own deliveries.",
         {"id": TEXT, "version": VERSION, "action": {"enum": ["progress", "block", "submit", "start", "cancel", "assign"]}, "text": TEXT, "agent_id": TEXT}, ["id", "version", "action"]),
    tool("teams_request_human", "human.request", "Ask a human a concrete question or decision. The durable request returns immediately; a later answer is delivered to your inbox. Do not pretend an unanswered request is approved.",
         {"title": TEXT, "detail": TEXT, "options": STRINGS}, ["title"]),
    tool("teams_request_status", "human.status", "Read the result of a human request you created.", {"id": TEXT}, ["id"], read_only=True),
    tool("teams_set_status", "actor.status", "Publish your current focus or blocker to teammates and the human operator.", {"focus": TEXT, "blocked": TEXT}),
]
BY_NAME = {t["name"]: t for t in TOOLS}


def public_tools():
    return [{k: v for k, v in t.items() if k != "op"} for t in TOOLS]


def validate_arguments(definition, arguments):
    """Small strict validator for this deliberately small JSON Schema subset."""
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    spec = definition["inputSchema"]
    if set(arguments) - set(spec["properties"]):
        raise ValueError("Unknown tool argument")
    if any(k not in arguments for k in spec["required"]):
        raise ValueError("Missing required tool argument")
    for name, value in arguments.items():
        rule = spec["properties"][name]
        typ = rule.get("type")
        if typ == "string" and not isinstance(value, str):
            raise ValueError(name + " must be a string")
        if typ == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ValueError(name + " must be an integer")
        if typ == "boolean" and not isinstance(value, bool):
            raise ValueError(name + " must be a boolean")
        if typ == "array" and (not isinstance(value, list) or not all(isinstance(x, str) for x in value)):
            raise ValueError(name + " must be a string array")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError("Invalid " + name)
        if "minimum" in rule and value < rule["minimum"] or "maximum" in rule and value > rule["maximum"]:
            raise ValueError(name + " is outside its supported range")
