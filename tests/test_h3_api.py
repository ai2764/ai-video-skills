import json
from unittest.mock import patch

import pytest

from h3_api import DEFAULT_BASE_URL, H3ApiClient, build_request


def shot(n_keys=2, duration=8.0, prompt="she turns and runs"):
    return {
        "keyframes": [f"https://example.test/k{i}.png" for i in range(n_keys)],
        "duration_s": duration,
        "prompt": prompt,
    }


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# --- request shape ------------------------------------------------------


def test_request_has_required_top_level_fields():
    req = build_request(shot())
    assert req["model"] == "MiniMax-H3"
    assert req["duration"] == 8
    assert req["resolution"] == "768P"
    assert req["ratio"] == "16:9"


def test_duration_rounds_to_int():
    assert build_request(shot(duration=8.4))["duration"] == 8
    assert build_request(shot(duration=8.6))["duration"] == 9


def test_duration_below_floor_rejected():
    with pytest.raises(ValueError, match="4"):
        build_request(shot(duration=3.0))


def test_duration_above_ceiling_rejected():
    with pytest.raises(ValueError, match="15"):
        build_request(shot(duration=16.0))


def test_two_keyframes_become_first_and_last_roles():
    content = build_request(shot(2))["content"]
    roles = [item.get("role") for item in content if item["type"] == "image_url"]
    assert roles == ["first_frame", "last_frame"]


def test_one_keyframe_is_first_frame_only():
    content = build_request(shot(1))["content"]
    roles = [item.get("role") for item in content if item["type"] == "image_url"]
    assert roles == ["first_frame"]


def test_three_keyframes_rejected():
    with pytest.raises(ValueError, match="first and a last"):
        build_request(shot(3))


def test_no_keyframes_rejected():
    with pytest.raises(ValueError, match="first frame"):
        build_request({"keyframes": [], "duration_s": 8, "prompt": "x"})


def test_prompt_is_a_text_item():
    content = build_request(shot())["content"]
    assert [i["text"] for i in content if i["type"] == "text"] == ["she turns and runs"]


def test_prompt_over_7000_chars_rejected():
    with pytest.raises(ValueError, match="7000"):
        build_request(shot(prompt="x" * 7001))


def test_no_negative_prompt_ever_emitted():
    """H3 has no negative conditioning; the field must not leak through."""
    req = build_request({**shot(), "negative_prompt": "blurry, deformed"})
    assert "negative_prompt" not in json.dumps(req)
    assert "blurry" not in json.dumps(req)


def test_no_strength_ever_emitted():
    req = build_request({**shot(), "strength": 0.8})
    assert "strength" not in json.dumps(req)


def test_resolution_must_be_known():
    with pytest.raises(ValueError, match="resolution"):
        build_request(shot(), resolution="1080p")


def test_2k_resolution_accepted():
    assert build_request(shot(), resolution="2K")["resolution"] == "2K"


# --- client -------------------------------------------------------------


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        H3ApiClient()


def test_client_defaults_to_international_base_url(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    assert H3ApiClient().base_url == DEFAULT_BASE_URL


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/")
    assert H3ApiClient().base_url == "https://api.minimaxi.com"


def test_invalid_api_key_error_mentions_region(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    payload = {"base_resp": {"status_code": 1004, "status_msg": "Invalid API key"}}
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="same region"):
            client.create(build_request(shot()))


def test_create_returns_task_id(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse({"task_id": "t-1"})):
        assert client.create(build_request(shot())) == "t-1"


def test_poll_raises_on_failed_status(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse({"task": {"status": "failed"}})):
        with pytest.raises(RuntimeError, match="failed"):
            client.poll("t-1", interval=0, timeout=5)


def test_poll_returns_url_on_success(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    payload = {"task": {"status": "success", "content": {"url": "https://cdn.test/v.mp4"}}}
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        assert client.poll("t-1", interval=0)["url"] == "https://cdn.test/v.mp4"


def test_poll_timeout_keeps_the_task_id(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse({"task": {"status": "processing"}})):
        with pytest.raises(TimeoutError, match="t-1"):
            client.poll("t-1", interval=0, timeout=0.01)


# --- real error shapes seen from the live API ---------------------------


def _err(kind, message, monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()
    payload = {"type": "error", "error": {"type": kind, "message": message}}
    return client, payload


def test_insufficient_balance_is_not_reported_as_a_key_problem(monkeypatch):
    client, payload = _err("insufficient_balance_error", "insufficient balance (1008)", monkeypatch)
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="no credit") as excinfo:
            client.create(build_request(shot()))
    assert "same region" not in str(excinfo.value)


def test_balance_error_says_nothing_was_charged(monkeypatch):
    client, payload = _err("insufficient_balance_error", "insufficient balance (1008)", monkeypatch)
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="nothing was charged"):
            client.create(build_request(shot()))


def test_top_level_authorized_error_mentions_region(monkeypatch):
    client, payload = _err("authorized_error", "invalid api key (2049)", monkeypatch)
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="same region"):
            client.create(build_request(shot()))


def test_unclassified_error_still_surfaces_the_message(monkeypatch):
    client, payload = _err("server_error", "record not found (1000)", monkeypatch)
    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="record not found"):
            client.create(build_request(shot()))


# --- local files become data URIs ---------------------------------------


def test_http_url_passes_through():
    from h3_api import image_reference

    assert image_reference("https://x.test/a.png") == "https://x.test/a.png"


def test_existing_data_uri_passes_through():
    from h3_api import image_reference

    assert image_reference("data:image/png;base64,AAAA") == "data:image/png;base64,AAAA"


def test_local_png_becomes_a_data_uri(tmp_path):
    from h3_api import image_reference

    path = tmp_path / "k.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert image_reference(path).startswith("data:image/png;base64,")


def test_local_jpg_maps_to_jpeg_mime(tmp_path):
    from h3_api import image_reference

    path = tmp_path / "k.jpg"
    path.write_bytes(b"\xff\xd8\xff")
    assert image_reference(path).startswith("data:image/jpeg;base64,")


def test_missing_local_file_raises(tmp_path):
    from h3_api import image_reference

    with pytest.raises(FileNotFoundError):
        image_reference(tmp_path / "gone.png")


def test_build_request_inlines_a_local_keyframe(tmp_path):
    path = tmp_path / "k.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    req = build_request({"keyframes": [str(path)], "duration_s": 4, "prompt": "p"})
    url = req["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
