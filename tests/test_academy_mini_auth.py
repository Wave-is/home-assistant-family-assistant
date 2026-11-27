"""Mini App auth: synthetic Telegram signatures, not live bot credentials."""
import hmac
import json
from urllib.parse import urlencode

import pytest

from custom_components.family_assistant.academy.mini_auth import (
    AcademyError, Sessions, binding, consume, origin, verify_init,
)

NOW = 1800000000
TOKEN = "synthetic-test-token"


def signed(**changes):
    data = {"auth_date":str(NOW),"user":json.dumps({"id":123}),"query_id":"test"} | changes
    check = "\n".join(f"{k}={v}" for k,v in sorted(data.items()))
    key = hmac.digest(b"WebAppData",TOKEN.encode(),"sha256")
    return urlencode(data | {"hash":hmac.digest(key,check.encode(),"sha256").hex()})


def test_signature_age_duplicates_and_chat():
    assert verify_init(signed(),TOKEN,NOW)[0] == 123
    for raw,now in [(signed()+"&auth_date=1",NOW),(signed(),NOW+301),
                    (signed(chat_type="group"),NOW),(signed()+"x",NOW)]:
        with pytest.raises(AcademyError):
            verify_init(raw,TOKEN,now)


def test_origin_and_durable_nonce():
    assert origin("https://academy.example.com") == "https://academy.example.com"
    for bad in ("http://academy.example.com","https://a.example.com/path",
                "https://user@a.example.com","https://a.example.com:123"):
        with pytest.raises(AcademyError):
            origin(bad)
    state = {}
    consume(state,"digest",NOW)
    restored = json.loads(json.dumps(state))
    with pytest.raises(AcademyError):
        consume(restored,"digest",NOW)


def test_session_bound_to_epoch_and_policy():
    state = {"settings":{"modules":["academy"]},"members":{"c":{"id":"c","active":True,
             "role":"child","revision":1,"telegram_id":123}},
             "academy":{"c":{"member_revision":1,"epoch":1,"enabled":True}},
             "academy_mini":{"revision":1,"enabled":True,"origin":"https://academy.example.com"}}
    sessions = Sessions()
    stamp = binding(state,123,99)
    token = sessions.issue("home",stamp,NOW)
    assert sessions.check(token,"home",state,99,NOW) == stamp
    state["academy"]["c"]["epoch"] = 2
    with pytest.raises(AcademyError):
        sessions.check(token,"home",state,99,NOW)
