"""Narrow Telegram Mini App authorization, independent of HA and transport."""
import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import parse_qsl, urlsplit

from .household import AcademyError, learner_stamp

MAX_AGE = 300
TTL = 3600
PATH = "/api/family_assistant/academy/mini"


def origin(value):
    if type(value) is not str or len(value) > 253:
        raise AcademyError("invalid_field")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.path or parsed.query or parsed.fragment
            or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,63}", parsed.hostname)
            or value != "https://" + parsed.hostname):
        raise AcademyError("invalid_field")
    return value


def configure(state, actor, payload):
    member = state["members"].get(actor, {})
    if member.get("active") is not True or member.get("role") != "owner":
        raise AcademyError("forbidden")
    if "academy" not in state["settings"]["modules"]:
        raise AcademyError("module_disabled")
    old = state.get("academy_mini", {})
    if (set(payload) != {"revision","enabled","origin"} or type(payload["revision"]) is not int
            or payload["revision"] != old.get("revision",0) or type(payload["enabled"]) is not bool):
        raise AcademyError("conflict")
    config = {"revision":payload["revision"]+1,"enabled":payload["enabled"],
              "origin":origin(payload["origin"]) if payload["enabled"] else ""}
    state["academy_mini"] = config
    return config


def policy(state):
    config = state.get("academy_mini",{})
    if "academy" not in state["settings"]["modules"] or config.get("enabled") is not True:
        raise AcademyError("forbidden")
    origin(config["origin"])
    return config


def launch_url(state, household):
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",household):
            return None
        return policy(state)["origin"] + PATH + "/" + household + "/index"
    except (AcademyError, KeyError, ValueError):
        return None


def verify_init(raw, token, now):
    """Telegram WebAppData HMAC, strict duplicate/age/identity checks."""
    if type(raw) is not str or not 1 <= len(raw) <= 8192 or type(token) is not str:
        raise AcademyError("forbidden")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          max_num_fields=16, encoding="utf-8", errors="strict")
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError
        received = fields.pop("hash")
        if not re.fullmatch(r"[a-f0-9]{64}",received):
            raise ValueError
        check = "\n".join(f"{key}={value}" for key,value in sorted(fields.items()))
        secret = hmac.digest(b"WebAppData",token.encode(),"sha256")
        expected = hmac.digest(secret,check.encode(),"sha256").hex()
        if not hmac.compare_digest(received,expected):
            raise ValueError
        if not fields["auth_date"].isdigit() or not 0 <= now-int(fields["auth_date"]) <= MAX_AGE:
            raise ValueError
        user = json.loads(fields["user"])
        if (type(user["id"]) is not int or user["id"] <= 0 or user.get("is_bot")
                or fields.get("chat_type") not in (None,"private","sender")):
            raise ValueError
        return user["id"], received
    except (ValueError,TypeError,KeyError,UnicodeError,AttributeError):
        raise AcademyError("forbidden") from None


def member_for(state,user_id):
    candidates = [m for m in state["members"].values() if m.get("active") is True
                  and type(m.get("telegram_id")) is int and m["telegram_id"] == user_id]
    if len(candidates) != 1 or candidates[0].get("role") != "child":
        raise AcademyError("forbidden")
    member = candidates[0]
    if user_id == state.get("telegram",{}).get("group_id"):
        raise AcademyError("forbidden")
    record = state.get("academy",{}).get(member["id"],{})
    learner_stamp(state,member["id"],record.get("epoch"))
    return member,record


def binding(state,user_id,bot_id):
    member,record = member_for(state,user_id)
    return {"actor":member["id"],"user":user_id,"bot":bot_id,"member_revision":member["revision"],
            "epoch":record["epoch"],"generation":state.get("academy_generation",0),
            "policy_revision":policy(state)["revision"]}


def consume(state, digest, now):
    """One-use signed launch, durable across HA restart; never store raw initData."""
    used = state.setdefault("academy_mini_replays",{})
    for key,expiry in list(used.items()):
        if expiry < now:
            del used[key]
    if digest in used or len(used) >= 1024:
        raise AcademyError("conflict")
    used[digest] = now + MAX_AGE


class Sessions:
    """Opaque process-local session tokens. Restart revokes tokens, not course state."""
    def __init__(self):
        self.records = {}

    def issue(self, household, stamp, now):
        self.records = {k:v for k,v in self.records.items() if v[2] > now}
        if len(self.records) >= 256:
            raise AcademyError("conflict")
        token = secrets.token_urlsafe(32)
        self.records[hashlib.sha256(token.encode()).hexdigest()] = (household,stamp,now+TTL)
        return token

    def check(self, token, household, state, bot_id, now):
        if type(token) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{43}",token):
            raise AcademyError("forbidden")
        row = self.records.get(hashlib.sha256(token.encode()).hexdigest())
        if not row or row[0] != household or row[2] <= now:
            raise AcademyError("forbidden")
        if row[1] != binding(state,row[1]["user"],bot_id):
            raise AcademyError("forbidden")
        return row[1]
