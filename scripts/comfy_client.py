"""Minimal ComfyUI HTTP client. Standard library only."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8188"
# Filenames arrive under different output keys depending on the save node.
_OUTPUT_KEYS = ("gifs", "videos", "images", "audio")


class ComfyClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def _get(self, path: str, timeout: float = 30.0) -> Any:
        with urllib.request.urlopen(self.base_url + path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def _post(self, path: str, payload: dict, timeout: float = 60.0) -> Any:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            # ComfyUI rejects a bad graph with 400 and puts the whole diagnosis
            # -- node_errors, per-input messages -- in the *body*. Letting the
            # HTTPError propagate throws away the only useful part.
            body = error.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body or "{}")
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {error.code} from {path}: {body[:800]}") from None

    def alive(self) -> bool:
        try:
            self._get("/system_stats", timeout=8.0)
            return True
        except Exception:
            return False

    def object_info(self) -> dict:
        return self._get("/object_info", timeout=60.0)

    def upload_image(self, path: Path, subfolder: str = "") -> str:
        """Stage an image into ComfyUI's input dir; returns the name to
        reference it by."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"image does not exist: {path}")
        boundary = f"----ai-video-skills-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts: list[bytes] = [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            path.read_bytes(),
            b"\r\n",
        ]
        if subfolder:
            parts += [
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="subfolder"\r\n\r\n',
                subfolder.encode(),
                b"\r\n",
            ]
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="overwrite"\r\n\r\n',
            b"true\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        request = urllib.request.Request(
            self.base_url + "/upload/image",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=120.0) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
        name = result.get("name") or path.name
        stored_subfolder = result.get("subfolder") or ""
        return f"{stored_subfolder}/{name}" if stored_subfolder else name

    def submit(self, graph: dict) -> str:
        result = self._post("/prompt", {"prompt": graph, "client_id": self.client_id})
        node_errors = result.get("node_errors") or {}
        if node_errors:
            details: list[str] = []
            for node_id in sorted(node_errors):
                entry = node_errors[node_id] or {}
                node_type = (graph.get(node_id) or {}).get("class_type", "?")
                for item in entry.get("errors") or [{}]:
                    details.append(
                        f"node {node_id} ({node_type}): "
                        f"{item.get('type', '?')} — {item.get('message', '')} "
                        f"{item.get('details', '')}".strip()
                    )
            raise RuntimeError(
                "ComfyUI rejected the graph:\n  " + "\n  ".join(details)
            )
        error = result.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            details = error.get("details", "") if isinstance(error, dict) else ""
            raise RuntimeError(f"ComfyUI rejected the graph: {message} {details}".strip())
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI returned no prompt_id: {result}")
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict:
        return self._get(f"/history/{prompt_id}", timeout=30.0)

    def outputs(self, prompt_id: str) -> list[str]:
        """Output filenames, empty while the job is still running."""
        entry = (self.history(prompt_id) or {}).get(prompt_id) or {}
        names: list[str] = []
        for node_output in (entry.get("outputs") or {}).values():
            for key in _OUTPUT_KEYS:
                for item in node_output.get(key) or []:
                    name = item.get("filename")
                    if name:
                        names.append(name)
        return names
