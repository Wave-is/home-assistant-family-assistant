"""Public defaults; no household-specific values."""

DOMAIN = "family_assistant"
SCHEMA_VERSION = 1
LANGUAGES = ("en", "ru", "uk")
MODULES = (
    "shopping",
    "tasks",
    "alarms",
    "court",
    "routines",
    "calendar",
    "conversation",
    "pantry",
    "school",
    "maintenance",
    "polls",
    "presence",
    "digests",
    "mikrotik",
    "price_watch",
)
DEFAULT_MODULES = ("shopping", "tasks", "alarms", "court", "price_watch")
ROLES = ("owner", "parent", "adult", "child", "guest")
PRIVILEGED = frozenset({"owner", "parent"})
