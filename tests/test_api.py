"""The `tdjson_ext` contract, pinned to the C++ tdjson semantics.

The reference behaviors are the tdjson-crate tests in td-rs
(`crates/tdjson/src/lib.rs`), which are C++-byte-pinned; here they run
through the Python surface. The process-wide manager is shared by every
client in this process, so manager-API tests attribute events through
`@client_id`.
"""

import json

import pytest

import tdjson

API_VERSION = "1.8.67"


def encode(request):
    return json.dumps(request).encode("utf-8")


def receive_event(want, timeout=0.5, limit=20):
    """The next event satisfying `want(json_object)` (the C++ receive loop).

    `None` between events is normal manager-API behavior: around a client's
    close, the consumed `authorizationStateClosed` update is replaced by one
    null response (the C++ wake-up tick) before the synthesized closed update
    arrives, so the loop must tolerate `None` like every shipped example.
    """
    for _ in range(limit):
        event = tdjson.td_receive(timeout)
        if event is None:
            continue
        event = json.loads(event)
        if want(event):
            return event
    raise AssertionError("the wanted event never arrived")


def client_event(client_id, want, **kwargs):
    """Like `receive_event`, but only events of the given client."""
    return receive_event(
        lambda event: event.get("@client_id") == client_id and want(event), **kwargs
    )


# ---------- td_execute ----------


def test_execute_get_option_version():
    response = tdjson.td_execute(encode({"@type": "getOption", "name": "version"}))
    assert isinstance(response, bytes)
    assert json.loads(response) == {"@type": "optionValueString", "value": API_VERSION}


def test_execute_rejects_non_synchronous_methods():
    response = tdjson.td_execute(encode({"@type": "getMe"}))
    assert json.loads(response) == {
        "@type": "error",
        "code": 400,
        "message": "The method can't be executed synchronously",
    }


def test_execute_get_text_entities():
    # The README example: a heterogeneous `@extra` survives the round trip.
    response = tdjson.td_execute(
        encode(
            {
                "@type": "getTextEntities",
                "text": "@telegram /test_command https://telegram.org telegram.me",
                "@extra": ["5", 7.0, "a"],
            }
        )
    )
    entities = json.loads(response)
    assert entities["@type"] == "textEntities"
    assert entities["@extra"] == ["5", 7.0, "a"]
    assert {entity["type"]["@type"] for entity in entities["entities"]} == {
        "textEntityTypeMention",
        "textEntityTypeBotCommand",
        "textEntityTypeUrl",
    }


def test_execute_invalid_json_is_an_error_object():
    response = tdjson.td_execute(b"not json")
    error = json.loads(response)
    assert error["@type"] == "error"
    assert error["code"] == 400
    assert error["message"].startswith("Failed to parse request as JSON object")


def test_execute_rejects_non_utf8():
    with pytest.raises(UnicodeDecodeError):
        tdjson.td_execute(b"\xff\xfe")


# ---------- td_create_client_id / td_send / td_receive ----------


def test_create_client_id_send_receive_round_trip():
    client_id = tdjson.td_create_client_id()
    assert isinstance(client_id, int)
    tdjson.td_send(client_id, encode({"@type": "getOption", "name": "version"}))
    event = client_event(client_id, lambda event: event["@type"] == "optionValueString")
    assert event["value"] == API_VERSION
    assert event["@client_id"] == client_id


def test_fresh_client_emits_startup_authorization_state():
    # A bare receive with no send yields the startup state — the contract the
    # shipped binding examples rely on.
    client_id = tdjson.td_create_client_id()
    event = client_event(client_id, lambda event: event["@type"] == "updateAuthorizationState")
    assert event["authorization_state"]["@type"] == "authorizationStateWaitTdlibParameters"


def test_close_reaches_authorization_state_closed():
    client_id = tdjson.td_create_client_id()
    client_event(client_id, lambda event: event["@type"] == "updateAuthorizationState")
    tdjson.td_send(client_id, encode({"@type": "close"}))
    event = client_event(
        client_id,
        lambda event: event["@type"] == "updateAuthorizationState"
        and event["authorization_state"]["@type"] == "authorizationStateClosed",
    )
    assert event["authorization_state"]["@type"] == "authorizationStateClosed"


def test_send_invalid_json_delivers_an_error_object():
    client_id = tdjson.td_create_client_id()
    tdjson.td_send(client_id, b"not json")
    event = client_event(client_id, lambda event: event["@type"] == "error")
    assert event["code"] == 400
    assert event["message"].startswith("Failed to parse request as JSON object")


def test_send_non_object_json_is_an_error():
    client_id = tdjson.td_create_client_id()
    tdjson.td_send(client_id, b"123")
    event = client_event(client_id, lambda event: event["@type"] == "error")
    assert event["message"] == "Expected a JSON object"


def test_send_requires_bytes_and_int():
    # Rejected during argument conversion, before any TDLib interaction.
    with pytest.raises(TypeError):
        tdjson.td_send("0", b"{}")
    with pytest.raises(TypeError):
        tdjson.td_send(0, '{"@type": "close"}')


def test_send_rejects_non_utf8():
    with pytest.raises(UnicodeDecodeError):
        tdjson.td_send(0, b"\xff\xfe")


def test_receive_timeout_returns_none():
    # Drain whatever is pending, then an idle receive times out to None
    # (the C++ null pointer).
    for _ in range(100):
        if tdjson.td_receive(0.1) is None:
            break
    assert tdjson.td_receive(0.1) is None


# ---------- package metadata ----------


def test_package_metadata():
    assert tdjson.__version__ == API_VERSION
    assert tdjson.__copyright__.startswith("Copyright (c)")
    assert tdjson.__license__ == "MIT License"
    assert set(tdjson.__all__) == {
        "td_create_client_id",
        "td_send",
        "td_receive",
        "td_execute",
        "__version__",
        "__copyright__",
        "__license__",
    }


def test_version_pins_are_consistent():
    """Cargo.toml, pyproject.toml and _version.py must pin the same version."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    cargo_version = re.search(
        r'^version = "([^"]+)"', (root / "Cargo.toml").read_text(encoding="utf-8"), re.M
    ).group(1)
    pyproject_version = re.search(
        r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M
    ).group(1)
    assert cargo_version == pyproject_version == tdjson.__version__
