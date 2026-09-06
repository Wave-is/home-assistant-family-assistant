"""Router write scope is separate from credentials and never inferred from a name."""

import hashlib
import json

from ..domain.validation import DomainError
from .inventory import mac


def protected(config):
    values = [mac(config.get("ha_mac")), mac(config.get("management_mac"))]
    if config.get("allow_write") is True and (
        None in values or config.get("management_confirmed") is not True
    ):
        raise DomainError("network_management_required")
    return sorted({value for value in values if value})


def identity(config):
    return hashlib.sha256(
        json.dumps(
            {
                "url": config.get("url", "").rstrip("/"),
                "username": config.get("username"),
                "protected": protected(config),
                "write": config.get("allow_write") is True,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
