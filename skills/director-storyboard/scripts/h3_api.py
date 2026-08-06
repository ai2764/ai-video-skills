"""MiniMax H3 official API adapter.

H3 has no negative conditioning, no per-segment local prompts, no strength and
no retake. Nothing in this module may emit them -- writing an LTX-shaped payload
here does not fail loudly, it just encodes your negative words as picture
content.

Region matters: `api.minimax.io` pairs with a platform.minimax.io key and
`api.minimaxi.com` with a platform.minimaxi.com key. A mismatched pair returns
`Invalid API key`, which reads like a bad secret and is actually a bad host.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from routing import H3_MAX_SECONDS, H3_MIN_SECONDS

DEFAULT_BASE_URL = "https://api.minimax.io"
VALID_RESOLUTIONS = ("768P", "2K")
MODEL_ID = "MiniMax-H3"
MAX_PROMPT_CHARS = 7000
FRAME_ROLES = ("first_frame", "last_frame")


def build_request(
    shot: dict[str, Any],
    resolution: str = "768P",
    ratio: str = "16:9",
) -> dict[str, Any]:
    """A `/v2/video_generation` payload for one shot.

    Only `prompt`, `keyframes` and `duration_s` are read off the shot. Anything
    else it happens to carry -- negative_prompt, strength -- is deliberately
    dropped.
    """
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(
            f"resolution must be one of {VALID_RESOLUTIONS}, got {resolution!r}"
        )

    duration = int(round(float(shot.get("duration_s") or 0)))
    if duration < H3_MIN_SECONDS:
        raise ValueError(f"H3 duration floor is {H3_MIN_SECONDS}s, got {duration}s")
    if duration > H3_MAX_SECONDS:
        raise ValueError(
            f"H3 duration ceiling is {H3_MAX_SECONDS}s, got {duration}s — split the shot"
        )

    keyframes = list(shot.get("keyframes") or [])
    if not keyframes:
        raise ValueError("H3 needs at least a first frame")
    if len(keyframes) > 2:
        raise ValueError(
            "H3 accepts at most a first and a last frame; split the span upstream"
        )

    prompt = str(shot.get("prompt") or "")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt exceeds {MAX_PROMPT_CHARS} characters")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for reference, role in zip(keyframes, FRAME_ROLES):
        content.append({
            "type": "image_url",
            "image_url": {"url": str(reference)},
            "role": role,
        })

    return {
        "model": MODEL_ID,
        "duration": duration,
        "resolution": resolution,
        "ratio": ratio,
        "content": content,
    }


class H3ApiClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError(
                "MINIMAX_API_KEY is not set. Create a key at platform.minimax.io "
                "(or platform.minimaxi.com for mainland China) and export it."
            )
        self.base_url = (
            base_url or os.environ.get("MINIMAX_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")

    def _request(
        self,
        path: str,
        payload: dict | None = None,
        method: str = "GET",
        timeout: float = 120.0,
    ) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw or "{}")
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {error.code} from {path}: {raw[:800]}") from None

        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code"):
            self._raise_for(base_resp)
        return body

    def _raise_for(self, base_resp: dict) -> None:
        message = str(base_resp.get("status_msg") or "")
        if "api key" in message.lower() or base_resp.get("status_code") in {1004, 1008}:
            raise RuntimeError(
                f"{message}. MINIMAX_BASE_URL ({self.base_url}) and MINIMAX_API_KEY "
                "must be from the same region — api.minimax.io pairs with a "
                "platform.minimax.io key, api.minimaxi.com with a "
                "platform.minimaxi.com key."
            )
        raise RuntimeError(f"MiniMax API error {base_resp.get('status_code')}: {message}")

    def create(self, request: dict[str, Any]) -> str:
        body = self._request("/v2/video_generation", request, method="POST")
        task_id = body.get("task_id") or (body.get("task") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"no task_id in response: {json.dumps(body)[:400]}")
        return str(task_id)

    def poll(
        self,
        task_id: str,
        interval: float = 10.0,
        timeout: float = 1800.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout
        while True:
            body = self._request(f"/v2/query/video_generation/{task_id}")
            task = body.get("task") or body
            status = str(task.get("status") or "").lower()
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"H3 task {task_id} ended as {status}")
            url = (task.get("content") or {}).get("url")
            if url:
                return {"task_id": task_id, "url": url, "status": status or "success"}
            if time.time() >= deadline:
                raise TimeoutError(
                    f"H3 task {task_id} still running after {timeout:.0f}s — it is not "
                    f"lost; retrieve it later with "
                    f"GET /v2/query/video_generation/{task_id}"
                )
            time.sleep(interval)

    def download(self, url: str, dest: Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=600.0) as response:
            dest.write_bytes(response.read())
        return dest


def strip_audio(path: Path) -> Path:
    """Drop H3's native audio track.

    H3 encodes a fresh voice per clip, so a character's voice changes between
    shots. Dropping segment audio into an otherwise silent LTX cut produces
    sound that appears and vanishes shot to shot. Lay audio in post instead.
    """
    path = Path(path)
    out = path.with_name(path.stem + "_mute" + path.suffix)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-an", "-c:v", "copy", str(out)],
        check=True,
        capture_output=True,
    )
    return out
