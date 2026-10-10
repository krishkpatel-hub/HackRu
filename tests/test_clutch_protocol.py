"""Synthetic wire observations and deterministic command grammar, not live proof."""

from copy import deepcopy
import math
from uuid import uuid4

import pytest

from companion.voice.parser import parse_command
from shared.protocol import ProtocolError, Session, decode, encode, validate_event


def observation(**changes):
    result = dict(valid=True, confidence=.99, u=.4, v=.6, palm_u=.45, palm_v=.65,
                  pinching=False, open=True, gesture_id=None, event="NONE",
                  shape_valid=True, shape_error=None, angle=0., openness=1., open_palm=True, extrude_pose=True, pinch_pending=False)
    result.update(changes)
    result['orientation']=changes.get('orientation',[1.,0.,0.,0.] if result['shape_valid'] else None)
    result['fingers']=changes.get('fingers',[result['openness']]*4 if result['shape_valid'] else None)
    return result


def missing(**changes):
    return observation(valid=False, confidence=0, u=None, v=None, palm_u=None,
                       palm_v=None, open=False, shape_valid=False, shape_error='Missing hand', angle=None, openness=None, open_palm=False, extrude_pose=False, **changes)


def frame(left=None, right=None, **changes):
    payload = dict(profile='left_clutch_v3', aspect=4/3, frame_id=1, t=0., hands=dict(Left=left or observation(), Right=right or missing()))
    payload.update(changes)
    return dict(type="hands_frame", payload=payload)


def paired():
    client, server = Session("client"), Session("server")
    _, response = server.accept(client.wrap(dict(type="hello", payload={})))
    client.accept(response)
    return client, server


def test_atomic_capture_survives_wire_roundtrip_with_two_independent_ids():
    left_id, right_id = str(uuid4()), str(uuid4())
    event = frame(observation(event="START", gesture_id=left_id, pinching=True, open=False),
                  observation(event="START", gesture_id=right_id, pinching=True, open=False))
    original = deepcopy(event)
    client, server = paired()
    encoded = encode(server.wrap(event))
    assert len(encoded) < 8192
    received, response = client.accept(decode(encoded))
    assert received == original and event == original and response is None
    # Independent pinch UUIDs carry Left selection and Right extrusion boundaries.
    assert received["payload"]["hands"]["Left"]["gesture_id"] != right_id


def test_observed_release_and_loss_cancel_are_distinct():
    identifier = str(uuid4())
    for hand in (observation(pinching=True, open=False, gesture_id=identifier),
                 observation(event="END", gesture_id=identifier),
                 missing(event="CANCEL", gesture_id=identifier), missing()):
        validate_event(frame(hand))
    with pytest.raises(ProtocolError, match="observed release"):
        validate_event(frame(missing(event="END", gesture_id=identifier)))


def test_whole_fist_openness_is_valid_without_extrusion_pose():
    left = observation(pinching=True, open=False, gesture_id=str(uuid4()))
    for openness in (0., .01, .2, .5, 1.):
        validate_event(frame(left, observation(openness=openness, open_palm=False, extrude_pose=False)))


@pytest.mark.parametrize("change", [
    dict(valid=1), dict(pinching=1), dict(open=None), dict(confidence=True),
    dict(confidence=-.1), dict(confidence=1.1), dict(u=None), dict(palm_v=1.1),
    dict(u=float("nan")), dict(v=float("inf")), dict(palm_u=10**1000),
    dict(gesture_id=str(uuid4())), dict(event="START"),
    dict(event="END"), dict(event="RELEASE"),
    dict(pinching=True, open=True, gesture_id=str(uuid4())),
    dict(pinching=True, open=False), dict(angle=None), dict(openness=None),
    dict(angle=math.pi+.001), dict(angle=float('nan')), dict(angle=True),
    dict(openness=-.01), dict(openness=1.01), dict(openness=True),
    dict(openness=float('nan')), dict(shape_valid=False), dict(shape_error='bad'),
    dict(pinch_pending=True, extrude_pose=False), dict(grip=True), dict(aperture=1),
    dict(event="CANCEL", pinching=True, open=False, gesture_id=str(uuid4())),
    dict(orientation=[0,0,0,0]), dict(orientation=[True,0,0,0]), dict(fingers=[1,1,1,.5]), dict(extra="unrecognized"),
])
def test_rejects_malformed_observations(change):
    with pytest.raises(ProtocolError):
        validate_event(frame(observation(**change)))


@pytest.mark.parametrize("field,value", [
    ("confidence", .8), ("u", .4), ("open", True), ("pinching", True),
    ("shape_valid", True), ("open_palm", True), ("angle", 0), ("openness", 1),
    ("extrude_pose", True), ("pinch_pending", True),
])
def test_invalid_observation_cannot_imply_presence_or_release(field, value):
    hand = missing()
    hand[field] = value
    with pytest.raises(ProtocolError):
        validate_event(frame(hand))


@pytest.mark.parametrize("change", [
    dict(aspect=0), dict(aspect=True), dict(profile='left_clutch_v2'), dict(profile='either_hand_v1'), dict(profile=None), dict(frame_id=0), dict(frame_id=True), dict(frame_id=1.2), dict(frame_id=2**53),
    dict(t=True), dict(t=-.001), dict(t=float("nan")), dict(t=float("inf")),
    dict(t=10**1000), dict(hands={"Left": observation()}),
    dict(hands={"Left": observation(), "Right": missing(), "Unknown": missing()}),
    dict(extra=1),
])
def test_rejects_malformed_capture(change):
    with pytest.raises(ProtocolError):
        validate_event(frame(**change))


def test_selected_ready_status_and_legacy_compatibility():
    validate_event(dict(type="status", payload=dict(mode="MOVE", phase="SELECTED_READY",
                   selected_object="Cube", hovered_object=None, tracking=True, last_error=None)))
    validate_event(dict(type="hand_frame", payload=dict(u=None, v=None, present=False, pinching=True)))
    validate_event(dict(type="selector_frame", payload=dict(pose="THREE", manipulator="Right", selector="Left")))
    for event in ("gesture_start", "gesture_end"):
        validate_event(dict(type=event, payload=dict(gesture_id=str(uuid4()), u=.5, v=.5)))


@pytest.mark.parametrize("phrase,plane,axis", [
    ("Extrude plane XY.", "XY", "NONE"),
    ("extend plane xz axis z", "XZ", "Z"),
    ("extrude plane yz axis y", "YZ", "Y"),
    ("extrude plane auto", "AUTO", "NONE"),
    ("extrude plane auto axis x", "AUTO", "X"),
    ("extend plane xy axis none", "XY", "NONE"),
    ("extrude axis z", "AUTO", "Z"),
    ("extend axis none", "AUTO", "NONE"),
])
def test_plane_axis_phrases_use_same_strict_wire_validator(phrase, plane, axis):
    payload = parse_command(phrase)
    assert payload == dict(action="set_mode", mode="EXTRUDE", plane=plane, axis=axis)
    validate_event(dict(type="command", payload=dict(payload, id=str(uuid4()))))


@pytest.mark.parametrize("phrase", [
    "extrude plane xy axis z", "extrude plane xz axis y", "extend plane yz axis x",
    "extrude plane x", "extrude plane xyz", "extrude axis q", "extrude plane auto axis auto",
    "please extrude plane xy", "extrude plane xy and undo", "set extrusion plane xy",
    "extrude plane xy 1 unit", "extrude 0.5 units plane xy", "rotate plane xy",
])
def test_rejects_unsupported_plane_phrases(phrase):
    assert parse_command(phrase) is None


@pytest.mark.parametrize("mode,fields", [
    ("MOVE", dict(axis="X")), ("ROTATE", dict(plane="XY")),
    ("ROTATE", dict(axis="NONE")), ("SCALE", dict(plane="AUTO")),
    ("EXTRUDE", dict(plane="XY", axis="Z")),
    ("EXTRUDE", dict(plane="XYZ")), ("EXTRUDE", dict(axis="Q")),
])
def test_rejects_conflicting_or_invalid_mode_controls(mode, fields):
    with pytest.raises(ProtocolError):
        validate_event(dict(type="command", payload=dict(id=str(uuid4()), action="set_mode", mode=mode, **fields)))


def test_plane_command_dedup_and_fresh_session_do_not_change():
    event = dict(type="command", payload=dict(parse_command("extend plane yz axis z"), id=str(uuid4())))
    client, server = paired()
    assert client.accept(server.wrap(event))[0] == event
    assert client.accept(server.wrap(event))[0] is None
    assert client.duplicates == 1
    fresh_client, fresh_server = paired()
    assert fresh_client.accept(fresh_server.wrap(event))[0] == event


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), 10**1000])
def test_precision_nonfinite_and_overflow_values_fail_closed(value):
    with pytest.raises(ProtocolError, match="finite"):
        validate_event(dict(type="command", payload=dict(id=str(uuid4()), action="precision",
                       mode="MOVE", axis="X", value=value)))
