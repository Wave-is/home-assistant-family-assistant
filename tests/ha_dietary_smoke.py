"""Dietary notes stay private through actual HA identities, tools and reload."""

from copy import deepcopy

from homeassistant.core import Context
from homeassistant.helpers import llm


async def verify_dietary_controls(hass, entry, owner, child, child_id, request):
    from custom_components.family_assistant.llm_api import FamilyAPI
    from custom_components.family_assistant.runtime import safe_diagnostics

    engine = entry.runtime_data.engine
    adult_user = await hass.auth.async_create_user("Synthetic dietary adult")
    adult = await request(
        owner,
        "members.save",
        {"name": "Synthetic dietary adult", "role": "adult", "ha_user_id": adult_user.id},
    )
    member_id = adult["id"]
    canary = "SYNTHETIC_DIETARY_PRIVATE_NOTE"
    payload = {
        "member_id": member_id,
        "likes": ["Synthetic apples"],
        "dislikes": [],
        "avoid": ["Synthetic nuts"],
        "allergy_note": canary,
    }
    untouched = {
        key: deepcopy(engine.snapshot()[key]) for key in ("shopping", "pantry", "outbox", "court")
    }
    await request(owner, "pantry.dietary_save", payload, error="forbidden")
    first = await request(adult_user, "pantry.dietary_save", payload, "ha-dietary-create")
    assert set(first) == {"member_id", "revision", "status"}
    assert await request(adult_user, "pantry.dietary_save", payload, "ha-dietary-create") == first
    for user in (owner, child):
        assert canary not in str(await request(user, "view", {}))
    assert canary in str((await request(adult_user, "view", {}))["pantry"]["dietary_profiles"])

    shared = await request(
        adult_user,
        "pantry.dietary_access_set",
        {
            **{k: first[k] for k in ("member_id", "revision")},
            "member_revision": adult["revision"],
            "share_with_parents": True,
        },
    )
    assert canary in str((await request(owner, "view", {}))["pantry"]["dietary_profiles"])
    assert canary not in str(await request(child, "view", {}))
    await request(
        owner, "pantry.dietary_save", {**payload, "revision": shared["revision"]}, error="forbidden"
    )

    # Actual LLM tool, entity states and diagnostics never inherit the profile,
    # including while the caller is an authorized consenting-parent viewer.
    context = llm.LLMContext(
        platform="conversation",
        context=Context(user_id=owner.id),
        language="en",
        assistant="conversation",
        device_id=None,
    )
    api = await FamilyAPI(hass, entry).async_get_api_instance(context)
    records = await api.async_call_tool(llm.ToolInput(tool_name="ReadFamily", tool_args={}))
    assert canary not in str(records)
    assert canary not in str(safe_diagnostics(entry.runtime_data))
    assert canary not in str([state.as_dict() for state in hass.states.async_all()])

    for role in ("child", "adult"):
        current_member = engine.snapshot()["members"][member_id]
        await request(
            owner,
            "members.save",
            {
                "id": member_id,
                "revision": current_member["revision"],
                "name": current_member["name"],
                "role": role,
            },
        )
        assert canary not in str(await request(owner, "view", {}))
    assert not (await request(adult_user, "view", {}))["pantry"]["dietary_profiles"]["self"][
        "share_with_parents"
    ]
    await request(
        adult_user,
        "pantry.dietary_access_set",
        {
            "member_id": member_id,
            "revision": shared["revision"],
            "member_revision": adult["revision"],
            "share_with_parents": True,
        },
        error="conflict",
    )
    member_revision = engine.snapshot()["members"][member_id]["revision"]

    revoked = await request(
        adult_user,
        "pantry.dietary_access_set",
        {
            "member_id": member_id,
            "revision": shared["revision"],
            "member_revision": member_revision,
            "share_with_parents": False,
        },
    )
    assert canary not in str(await request(owner, "view", {}))
    await request(
        adult_user,
        "pantry.dietary_access_set",
        {
            "member_id": member_id,
            "revision": shared["revision"],
            "member_revision": member_revision,
            "share_with_parents": True,
        },
        error="conflict",
    )
    child_payload = {**payload, "member_id": child_id, "allergy_note": "SYNTHETIC_CHILD_NOTE"}
    child_profile = await request(owner, "pantry.dietary_save", child_payload, "ha-dietary-child")
    assert child_profile["status"] == "active"
    assert "SYNTHETIC_CHILD_NOTE" in str(await request(child, "view", {}))
    assert "SYNTHETIC_CHILD_NOTE" not in str(await request(adult_user, "view", {}))
    await request(
        child,
        "pantry.dietary_save",
        {**child_payload, "revision": child_profile["revision"]},
        error="forbidden",
    )
    saved = engine.snapshot()
    assert all(saved[key] == value for key, value in untouched.items())
    for key in ("audit", "processed", "outbox"):
        assert canary not in str(saved[key]) and "SYNTHETIC_CHILD_NOTE" not in str(saved[key])
    assert revoked["revision"] > shared["revision"]


def verify_dietary_reload(entry, expected):
    engine = entry.runtime_data.engine
    assert engine.snapshot()["dietary_profiles"] == expected
    record = next(p for p in expected.values() if p["management"] == "self")
    own = engine.view(record["member_id"])["pantry"]["dietary_profiles"]["self"]
    assert own["revision"] == record["revision"]
    assert own["allergy_note"] == record["allergy_note"] and own["share_with_parents"] is False
    assert record["allergy_note"] not in str(engine.view("owner"))
    print("PASS: actual HA dietary identity/consent/privacy, bounded LLM tools and private reload")
