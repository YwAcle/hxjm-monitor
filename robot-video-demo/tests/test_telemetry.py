import asyncio
import json

from fastapi.testclient import TestClient

from settings import Settings
from telemetry import SIMULATION, TelemetryStore, simulate_step
from web_server import create_app, telemetry_events


def test_no_hardware_observation_is_never_defaulted_to_safe_state():
    with TestClient(create_app(Settings(mode="hardware"))) as client:
        payload = client.get("/api/telemetry").json()
        assert payload["mode"] == "hardware"
        for device in payload["devices"]:
            assert device["connection"] == "waiting"
            assert device["current_state"] is None
            assert device["received_at"] is None


def test_devices_are_independent_and_heartbeats_expire_without_new_reports():
    tick = [100.0]
    store = TelemetryStore("hardware", clock=lambda: tick[0])
    with TestClient(create_app(Settings(mode="hardware"), telemetry_store=store)) as client:
        assert client.post("/api/devices/dog/state", json={"state": "adjusting"}).status_code == 200
        tick[0] += 4
        client.post("/api/devices/arm/state", json={"state": "holding_return"})
        tick[0] += 1
        dog, arm = client.get("/api/telemetry").json()["devices"]
        assert dog["connection"] == "stale" and dog["current_state"] is None
        assert dog["reported_state"] == "adjusting"
        assert arm["current_state"] == "holding_return"
        client.post("/api/devices/dog/state", json={"state": "adjusting"})
        dog = client.get("/api/telemetry").json()["devices"][0]
        assert dog["connection"] == "online" and len(dog["history"]) == 1


def test_rejects_invalid_device_state_and_extra_fields_without_changing_state():
    with TestClient(create_app(Settings(mode="hardware"))) as client:
        client.post("/api/devices/dog/state", json={"state": "standing"})
        for device, body, status in [
            ("dog", {"state": "grasping"}, 422),
            ("arm", {"state": "navigating"}, 422),
            ("dog", {"state": 1}, 422),
            ("dog", {"state": "lying", "move": True}, 422),
            ("camera_1", {"state": "lying"}, 404),
        ]:
            assert client.post(f"/api/devices/{device}/state", json=body).status_code == status
        assert client.get("/api/telemetry").json()["devices"][0]["current_state"] == "standing"
        client.post("/api/devices/dog/state", json={"state": "unknown"})
        assert client.get("/api/telemetry").json()["devices"][0]["current_state"] == "unknown"


def test_simulation_is_labeled_and_cannot_be_mixed_with_hardware_reports():
    with TestClient(create_app(Settings())) as client:
        data = client.get("/api/telemetry").json()
        assert data["mode"] == "simulated"
        assert [d["connection"] for d in data["devices"]] == ["online", "online"]
        assert client.post("/api/devices/dog/state", json={"state": "adjusting"}).status_code == 409
    store = TelemetryStore("simulated")
    observed_dog, observed_arm = set(), set()
    for step in range(len(SIMULATION) * 3):
        simulate_step(store, step)
        dog, arm = store.snapshot()["devices"]
        observed_dog.add(dog["current_state"])
        observed_arm.add(arm["current_state"])
        assert len(dog["history"]) <= 6 and len(arm["history"]) <= 6
    assert observed_dog == {"lying", "standing", "navigating", "adjusting"}
    assert len(observed_arm) == 6


def test_sse_delivers_snapshot_and_updated_state_then_cancels_cleanly():
    class Request:
        async def is_disconnected(self):
            return False

    async def exercise():
        store = TelemetryStore("hardware")
        generator = telemetry_events(Request(), store)
        first = await anext(generator)
        assert first.startswith("event: telemetry\ndata: ")
        assert json.loads(first.split("data: ")[1])["devices"][0]["current_state"] is None
        store.update("dog", "navigating")
        second = await anext(generator)
        assert json.loads(second.split("data: ")[1])["devices"][0]["current_state"] == "navigating"
        await generator.aclose()

    asyncio.run(exercise())
