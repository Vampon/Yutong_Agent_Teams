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
    tool("teams_send", "message.send", "Peer messages default to quiet mail. Use request_reply for a concrete new question, send for necessary immediate work. For delegation use teams_task_create once, without a second message. Use stable client_id for retries and work_id from context for external clients.",
         {"targets": STRINGS, "text": TEXT, "mode": {"enum": ["send", "request_reply", "mail"]}, "client_id": TEXT, "work_id": TEXT}, ["targets", "text"]),
    tool("teams_reply", "message.reply", "Reply once to an existing message. The first answer to request_reply wakes the requester; receipts, replies to replies and later answers are quiet mail. New work requires a new explicit request. Terminal output is not a group reply.",
         {"reply_to": TEXT, "text": TEXT, "mode": {"enum": ["send", "mail"]}, "client_id": TEXT}, ["reply_to", "text"]),
    tool("teams_history", "message.history", "Read recent shared conversation without acknowledging your inbox. Every member in this collaboration can see this shared history.",
         {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, read_only=True),
    tool("teams_inbox_list", "inbox.list", "List your inbox without marking anything read. Mail is available here even while other work continues.",
         {"limit": {"type": "integer", "minimum": 1, "maximum": 100}, "unread": {"type": "boolean"}}, read_only=True),
    tool("teams_inbox_read", "inbox.read", "Read your inbox and explicitly acknowledge the returned messages. Omit message_ids to read the current unread batch.", {"message_ids": STRINGS}),
    tool("teams_task_list", "task.list", "Read durable tasks, owners, dependencies, results and current versions.", read_only=True),
    tool("teams_task_create", "task.create", "Create and automatically dispatch one internal task, including peer review. Use stable client_id on retries. Do not ALSO send a message requesting the same work. Internal completion never requests human acceptance. External clients specify work_id from context.",
         {"title": TEXT, "description": TEXT, "agent_id": TEXT, "depends_on": STRINGS, "client_id": TEXT, "work_id": TEXT}, ["title", "agent_id"]),
    tool("teams_task_update", "task.update", "Report progress/block/submit on your task using the current version. submit completes INTERNAL work and notifies the requester once; no duplicate result message is needed. The owner or leader may retry within an active chain. Only teams_submit_final requests final human acceptance.",
         {"id": TEXT, "version": VERSION, "action": {"enum": ["progress", "block", "submit", "start", "cancel", "assign", "retry"]}, "text": TEXT, "agent_id": TEXT}, ["id", "version", "action"]),
    tool("teams_submit_final", "work.submit", "Leader only: after completing internal work and peer review, submit the final deliverable and evidence once. Read work_id/version from context. Creates the single final acceptance request, quiets the chain, and needs no extra message asking for confirmation. Identical retry returns the existing submission. Only a human can accept or reopen it.",
         {"work_id": TEXT, "version": VERSION, "title": TEXT, "text": TEXT}, ["work_id", "version", "title", "text"]),
    tool("teams_request_human", "human.request", "Ask a human a concrete question or decision. The durable request returns immediately; a later answer is delivered to your inbox. Do not pretend an unanswered request is approved.",
         {"title": TEXT, "detail": TEXT, "options": STRINGS, "work_id": TEXT}, ["title"]),
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
