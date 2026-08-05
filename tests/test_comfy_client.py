import json
from unittest.mock import patch

import pytest

from comfy_client import ComfyClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_alive_true_when_system_stats_answers():
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({})):
        assert client.alive() is True


def test_alive_false_when_connection_refused():
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", side_effect=OSError("refused")):
        assert client.alive() is False


def test_base_url_trailing_slash_is_stripped():
    assert ComfyClient("http://127.0.0.1:8188/").base_url == "http://127.0.0.1:8188"


def test_submit_returns_prompt_id():
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({"prompt_id": "abc123"})):
        assert client.submit({"1": {"class_type": "X", "inputs": {}}}) == "abc123"


def test_submit_raises_on_node_errors():
    client = ComfyClient()
    payload = {"error": "invalid prompt", "node_errors": {"7": {"errors": []}}}
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse(payload)):
        with pytest.raises(RuntimeError, match="node 7"):
            client.submit({"7": {"class_type": "X", "inputs": {}}})


def test_submit_raises_when_no_prompt_id():
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({})):
        with pytest.raises(RuntimeError, match="no prompt_id"):
            client.submit({"1": {"class_type": "X", "inputs": {}}})


def test_outputs_empty_while_running():
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({})):
        assert client.outputs("abc123") == []


def test_outputs_lists_filenames():
    history = {
        "abc123": {
            "outputs": {
                "9": {"gifs": [{"filename": "clip_00001.mp4", "subfolder": "", "type": "output"}]}
            }
        }
    }
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse(history)):
        assert client.outputs("abc123") == ["clip_00001.mp4"]


def test_outputs_covers_every_media_key():
    history = {
        "j": {
            "outputs": {
                "1": {"images": [{"filename": "a.png"}]},
                "2": {"videos": [{"filename": "b.mp4"}]},
                "3": {"audio": [{"filename": "c.wav"}]},
            }
        }
    }
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse(history)):
        assert sorted(client.outputs("j")) == ["a.png", "b.mp4", "c.wav"]


def test_upload_image_returns_stored_name(tmp_path):
    source = tmp_path / "frame.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({"name": "frame.png", "subfolder": ""})):
        assert client.upload_image(source) == "frame.png"


def test_upload_image_joins_subfolder(tmp_path):
    source = tmp_path / "frame.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")
    client = ComfyClient()
    with patch("comfy_client.urllib.request.urlopen", return_value=FakeResponse({"name": "frame.png", "subfolder": "sb"})):
        assert client.upload_image(source, subfolder="sb") == "sb/frame.png"


def test_upload_image_missing_file_raises(tmp_path):
    client = ComfyClient()
    with pytest.raises(FileNotFoundError):
        client.upload_image(tmp_path / "nope.png")
