from fastapi.testclient import TestClient
import json
from pathlib import Path
import pytest
from mock_robot import AccessUnits
from settings import Settings
from web_server import create_app


def test_mock_access_units_split_across_network_reads():
    aud = b"\x00\x00\x00\x01\x09\x10"
    frame1 = aud + b"\x00\x00\x01\x67parameter" + b"\x00\x00\x01\x65frame1"
    frame2 = aud + b"\x00\x00\x01\x41frame2"
    data = frame1 + frame2 + aud
    splitter = AccessUnits()
    result = []
    for i in range(0, len(data), 3):
        result.extend(splitter.feed(data[i:i+3]))
    assert result == [frame1, frame2]


def test_three_byte_aud_is_supported():
    splitter = AccessUnits()
    aud = b"\x00\x00\x01\x09\x10"
    assert splitter.feed(aud + b"abc" + aud) == [aud + b"abc"]


CONFIG = Path(__file__).resolve().parents[1] / "cameras.json"


def test_four_distinct_sources_and_paths():
    mock = Settings().load_cameras(CONFIG)
    hardware = Settings(mode="hardware").load_cameras(CONFIG)
    assert len({c.url for c in mock.cameras}) == 4
    assert len({mock.target_url(c) for c in mock.cameras}) == 4
    assert len({mock.whep_url(c) for c in mock.cameras}) == 4
    assert [c.source for c in hardware.cameras] == ["m20", "m20", "publisher", "publisher"]
    assert [c.url for c in hardware.cameras[:2]] == [
        "ws://192.168.126.176:8765/front", "ws://192.168.126.176:8765/back"]
    assert all(c.source == "simulated" for c in mock.cameras)


def test_local_ports_and_publisher_config():
    s = Settings().load_cameras(CONFIG)
    yaml = s.mediamtx_yaml()
    assert "source: publisher" in yaml and "live/camera_1:" in yaml
    assert "rtspAddress: 127.0.0.1:28554" in yaml
    assert "webrtcLocalUDPAddress: 127.0.0.1:28189" in yaml
    assert yaml.count("source: publisher") == 4


def test_dashboard_config_process_health_and_resources():
    with TestClient(create_app(Settings().load_cameras(CONFIG), lambda: {"bridge_camera_1": {"running": True, "returncode": None}})) as c:
        config = c.get("/api/config").json()
        assert config["mode"] == "simulated"
        assert config["channel_count"] == 4
        assert config["cameras"][3]["whep_url"] == "http://127.0.0.1:28889/live/camera_4/whep"
        assert c.get("/api/health").json()["processes"]["bridge_camera_1"]["running"]
        for url in ("/", "/static/player.js", "/static/style.css"):
            assert c.get(url).status_code == 200


def test_rtsp_disabled_and_credentials_are_not_exposed(tmp_path):
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    data["cameras"][2].update(source="rtsp", url='rtsp://admin:secret@10.0.0.5:554/color?token=private')
    data["cameras"][3]["source"] = "disabled"
    file = tmp_path / "sources.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    settings = Settings(mode="hardware").load_cameras(file)
    generated = settings.mediamtx_yaml()
    assert 'source: "rtsp://admin:secret@10.0.0.5:554/color?token=private"' in generated
    assert "rtspTransport: tcp" in generated
    assert "live/camera_4:" not in generated
    with TestClient(create_app(settings)) as c:
        body = c.get("/api/config").text
        assert "secret" not in body and "private" not in body and "10.0.0.5" not in body
        assert not c.get("/api/config").json()["cameras"][3]["enabled"]


@pytest.mark.parametrize("change", ["duplicate", "missing", "bad_source", "bad_url", "bad_fps"])
def test_bad_camera_config_rejected(tmp_path, change):
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if change == "duplicate":
        data["cameras"][1]["id"] = "camera_1"
    elif change == "missing":
        data["cameras"].pop()
    elif change == "bad_source":
        data["cameras"][2]["source"] = "unknown"
    elif change == "bad_url":
        data["cameras"][2].update(source="rtsp", url="http://wrong/path")
    else:
        data["cameras"][0]["fps"] = 0
    file = tmp_path / "invalid.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        Settings(mode="hardware").load_cameras(file)


def test_all_disabled_yields_explicit_empty_paths(tmp_path):
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    for row in data["cameras"]:
        row["source"] = "disabled"
    file = tmp_path / "disabled.json"
    file.write_text(json.dumps(data), encoding="utf-8")
    settings = Settings(mode="hardware").load_cameras(file)
    assert settings.mediamtx_yaml().endswith("paths: {}\n")
    assert all(not c["enabled"] for c in settings.public_cameras())
