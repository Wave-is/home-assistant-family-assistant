"""Owner-defined score thresholds are explanatory reports, never device effects."""

from .validation import DomainError, enum, fields, text


def validate(ctx, values):
    """Validate and copy explicit rules without household-specific defaults."""
    if not isinstance(values, list) or len(values) > 20:
        raise DomainError("invalid_field", "thresholds")
    result, seen = [], set()
    for value in values:
        if not isinstance(value, dict):
            raise DomainError("invalid_field", "thresholds")
        fields(
            value,
            {"id", "label", "direction", "points", "members"},
            {"id", "label", "direction", "points", "members"},
        )
        identifier = text(value["id"], "id", 80)
        if identifier in seen:
            raise DomainError("invalid_field", "id")
        seen.add(identifier)
        points = value["points"]
        if type(points) is not int or not -10000 <= points <= 10000:
            raise DomainError("invalid_field", "points")
        members = value["members"]
        if not isinstance(members, list) or len(members) > 50:
            raise DomainError("invalid_field", "members")
        selected = []
        for identifier_member in members:
            member = ctx.member(identifier_member)
            if member["role"] == "guest" or member["id"] in selected:
                raise DomainError("invalid_field", "members")
            selected.append(member["id"])
        result.append(
            {
                "id": identifier,
                "label": text(value["label"], "label", 240),
                "direction": enum(value["direction"], {"at_most", "at_least"}, "direction"),
                "points": points,
                "members": selected,
            }
        )
    return result


def project(rules, rows):
    """Derive threshold status only for the authorized rows passed by the caller."""
    result = []
    for row in rows:
        for rule in rules:
            if rule["members"] and row["member"] not in rule["members"]:
                continue
            balance, points = row["total"], rule["points"]
            remaining = max(
                0, balance - points if rule["direction"] == "at_most" else points - balance
            )
            result.append(
                {
                    "rule_id": rule["id"],
                    "label": rule["label"],
                    "member": row["member"],
                    "direction": rule["direction"],
                    "points": points,
                    "balance": balance,
                    "reached": remaining == 0,
                    "remaining": remaining,
                }
            )
    return result
