# Round 2: H3 backends + routing layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** Round 1 (`2026-08-04-round1-migrate-and-comfyui-adapter.md`) is complete and its tests pass.

**Goal:** Add MiniMax-H3 as a second model behind the same skill — both locally through ComfyUI and through the official API — and put a routing layer in front that decides per segment which cell of the mode × backend table to use, with fast camera movement as the H3 trigger.

**Architecture:** Routing is a pure function over segment metadata plus a `fast_camera` flag that the *agent* sets by reading keyframes; the scripts never do image analysis. Two new adapters implement the Round 1 backend contract. Cost is computed and shown before anything is submitted.

**Tech Stack:** Python 3 stdlib only, pytest 9.x, `ffmpeg` for stripping audio.

## Global Constraints

- Standard library only at runtime. No `requests`.
- `MINIMAX_BASE_URL` defaults to `https://api.minimax.io`; `MINIMAX_API_KEY` has no default. **Base URL and key must be from the same region** — international (`api.minimax.io` + platform.minimax.io key) or mainland China (`api.minimaxi.com` + platform.minimaxi.com key). Mismatched pairs return `Invalid API key`.
- H3 API: `duration` is an **integer 4–15 seconds**; `resolution` is exactly `"768P"` or `"2K"`; nothing else is accepted.
- H3 has **no negative conditioning, no per-segment local prompts, no `strength`, no retake**. Never emit any of those toward an H3 backend.
- H3 output audio is **stripped by default**. Keeping it requires an explicit flag.
- Default H3 output is `resolution: "768P"`, `ratio: "16:9"`.
- Pricing for estimates: 768P `$0.08`/s, 2K `$0.13`/s, input images free for the first 5 then `$0.04` each.
- Never submit an H3 API job without printing the cost estimate first and getting confirmation.
- Keep `skills/` and `codex/` variants in step.

---

## File Structure

```
skills/director-storyboard/
  references/
    backend-h3-local.md          H3 through ComfyUI
    backend-minimax-api.md       H3 through the official API
    prompting-h3.md              H3 prompt contract (NOT the LTX one)
    routing.md                   the table and the four rules
  workflows/
    ltx23_i2v.api.json           exported this round
    ltx23_flf.api.json           exported this round
    h3_i2v.api.json              from camera-lab/tasks/storyboards/h3/
    h3_flf.api.json
  scripts/
    routing.py                   pure routing + cost, no I/O
    h3_api.py                    MiniMax API adapter
    h3_local.py                  H3-through-ComfyUI adapter
    run_storyboard.py            unified CLI over all backends
tests/
  test_routing.py
  test_h3_api.py
  test_h3_local.py
```

`routing.py` stays free of I/O on purpose — the four rules are the part most likely to be wrong, and pure functions make them cheap to pin down.

---

### Task 1: Export the four remaining workflow graphs

**Files:**
- Create: `skills/director-storyboard/workflows/ltx23_i2v.api.json`
- Create: `skills/director-storyboard/workflows/ltx23_flf.api.json`
- Create: `skills/director-storyboard/workflows/h3_i2v.api.json`
- Create: `skills/director-storyboard/workflows/h3_flf.api.json`

**Interfaces:**
- Consumes: nothing.
- Produces: four API-format graphs. `h3_flf.api.json` contains `MiniMaxH3ImageToVideo` with both a first and a last frame `LoadImage`; `h3_i2v.api.json` is the same graph with the last-frame node removed.

- [ ] **Step 1: Export the two LTX graphs the same way Round 1 exported the Director graph**

```bash
py -3 -c "import sys, json; sys.path.insert(0,'C:/Users/AIBOX/dev/camera-lab'); sys.path.insert(0,'C:/Users/AIBOX/dev/camera-lab/server'); from workflow_graph import workflow_to_api; import pathlib; src=pathlib.Path('C:/Users/AIBOX/dev/camera-lab/workflows/app'); dst=pathlib.Path('C:/Users/AIBOX/dev/ai-video-skills/skills/director-storyboard/workflows'); pairs=[('ltx23_i2v_subtitle_cleaner_nag_extend.json','ltx23_i2v.api.json'),('ltx23_flf_subtitle_cleaner_nag_extend.json','ltx23_flf.api.json')]; [json.dump(workflow_to_api(json.load(open(src/a,encoding='utf-8'))), open(dst/b,'w',encoding='utf-8'), ensure_ascii=False, indent=2) for a,b in pairs]; print('exported')"
```

Expected: `exported`

- [ ] **Step 2: Copy the H3 flf graph, which is already in API format**

```bash
cp C:/Users/AIBOX/dev/camera-lab/tasks/storyboards/h3/h3_fl2va.api.json skills/director-storyboard/workflows/h3_flf.api.json
```

- [ ] **Step 3: Derive the i2v variant by dropping the last-frame node**

`run_h3_plan.py` in camera-lab already does this ("i2v shots drop the last_frame node entirely"). Read how it identifies that node:

```bash
grep -n "last_frame\|last\b" C:/Users/AIBOX/dev/camera-lab/tasks/storyboards/h3/run_h3_plan.py | head -20
```

Apply the same removal once and save the result as `h3_i2v.api.json`. Verify the result still validates:

```bash
py -3 -c "import json; g=json.load(open('skills/director-storyboard/workflows/h3_i2v.api.json')); refs=[i for n in g.values() for i in (n.get('inputs') or {}).values() if isinstance(i,list) and len(i)==2 and str(i[0]) not in g]; print('dangling refs:', refs)"
```

Expected: `dangling refs: []`

- [ ] **Step 4: Commit**

```bash
git add skills/director-storyboard/workflows/
git commit -m "chore: export i2v, flf and H3 workflow graphs"
```

---

### Task 2: `routing.py` — the four rules and the cost estimate

**Files:**
- Create: `skills/director-storyboard/scripts/routing.py`
- Test: `tests/test_routing.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Cell = tuple[str, str]` — `(mode, backend)`, mode in `{"i2v","flf","timeline"}`, backend in `{"ltx","h3_local","h3_api"}`
  - `route_segment(segment: dict, available: dict[str, bool]) -> Cell`
  - `route_storyboard(run: dict, available: dict[str, bool]) -> list[dict]` — one entry per segment: `{"index": int, "cell": Cell, "reason": str, "duration_s": int}`
  - `split_for_h3(run: dict, indices: list[int]) -> list[dict]` — turns ≥3-keyframe spans into adjacent first/last pairs
  - `estimate_cost(plan: list[dict], resolution: str = "768P", image_count: int = 0) -> dict` — `{"seconds": int, "video_usd": float, "image_usd": float, "total_usd": float}`

Segment input keys used: `keyframes` (list of paths), `duration_s` (float), `fast_camera` (bool, set by the agent from reading the images).

- [ ] **Step 1: Write the failing test**

Create `tests/test_routing.py`:

```python
import pytest

from routing import estimate_cost, route_segment, route_storyboard, split_for_h3

ALL = {"ltx": True, "h3_local": True, "h3_api": True}
NO_LOCAL = {"ltx": True, "h3_local": False, "h3_api": True}


def seg(n_keys, duration, fast):
    return {"keyframes": [f"k{i}.png" for i in range(n_keys)], "duration_s": duration, "fast_camera": fast}


# Rule 1: keyframe count picks the row
def test_one_keyframe_is_i2v():
    assert route_segment(seg(1, 8, False), ALL)[0] == "i2v"


def test_two_keyframes_is_flf():
    assert route_segment(seg(2, 8, False), ALL)[0] == "flf"


def test_three_keyframes_is_timeline():
    assert route_segment(seg(3, 8, False), ALL)[0] == "timeline"


# Rule 2: fast camera movement picks the column
def test_slow_segment_stays_on_ltx():
    assert route_segment(seg(2, 8, False), ALL)[1] == "ltx"


def test_fast_segment_goes_to_h3():
    assert route_segment(seg(2, 8, True), ALL)[1] in {"h3_local", "h3_api"}


def test_h3_api_used_when_local_unavailable():
    assert route_segment(seg(2, 8, True), NO_LOCAL)[1] == "h3_api"


# Rule 3: sub-4s vetoes H3 regardless of camera movement
def test_short_fast_segment_forced_back_to_ltx():
    assert route_segment(seg(2, 3.0, True), ALL) == ("flf", "ltx")


def test_exactly_four_seconds_is_allowed_on_h3():
    assert route_segment(seg(2, 4.0, True), ALL)[1] != "ltx"


# Rule 4: >=3 keyframes + fast camera splits into adjacent pairs
def test_timeline_with_fast_camera_splits_into_pairs():
    run = {"segments": [seg(4, 12, True)]}
    pairs = split_for_h3(run, [0])
    assert len(pairs) == 3
    assert all(len(p["keyframes"]) == 2 for p in pairs)


def test_split_preserves_total_duration():
    run = {"segments": [seg(4, 12, True)]}
    pairs = split_for_h3(run, [0])
    assert sum(p["duration_s"] for p in pairs) == pytest.approx(12)


# H3 never routes to timeline
def test_h3_is_never_paired_with_timeline():
    for duration in (5, 10, 15):
        mode, backend = route_segment(seg(5, duration, True), ALL)
        if backend != "ltx":
            assert mode != "timeline"


def test_no_backend_available_raises():
    with pytest.raises(ValueError, match="no backend"):
        route_segment(seg(2, 8, True), {"ltx": False, "h3_local": False, "h3_api": False})


# Cost
def test_cost_768p():
    plan = [{"duration_s": 8, "cell": ("flf", "h3_api")}, {"duration_s": 10, "cell": ("flf", "h3_api")}]
    cost = estimate_cost(plan, "768P", image_count=2)
    assert cost["seconds"] == 18
    assert cost["video_usd"] == pytest.approx(1.44)
    assert cost["image_usd"] == 0.0
    assert cost["total_usd"] == pytest.approx(1.44)


def test_cost_2k_and_extra_images():
    plan = [{"duration_s": 10, "cell": ("flf", "h3_api")}]
    cost = estimate_cost(plan, "2K", image_count=7)
    assert cost["video_usd"] == pytest.approx(1.30)
    assert cost["image_usd"] == pytest.approx(0.08)


def test_cost_ignores_ltx_segments():
    plan = [{"duration_s": 100, "cell": ("timeline", "ltx")}]
    assert estimate_cost(plan)["total_usd"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_routing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'routing'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/routing.py`:

```python
"""Which cell of the mode x backend table each segment goes to.

Pure functions, no I/O and no image analysis. `fast_camera` is set upstream by
the agent after reading the keyframes; this module only consumes the verdict.
"""

from __future__ import annotations

from typing import Any

Cell = tuple[str, str]

H3_MIN_SECONDS = 4
H3_MAX_SECONDS = 15

PRICE_PER_SECOND = {"768P": 0.08, "2K": 0.13}
FREE_IMAGES = 5
PRICE_PER_EXTRA_IMAGE = 0.04


def _mode_for(keyframe_count: int) -> str:
    if keyframe_count <= 1:
        return "i2v"
    if keyframe_count == 2:
        return "flf"
    return "timeline"


def route_segment(segment: dict[str, Any], available: dict[str, bool]) -> Cell:
    if not any(available.values()):
        raise ValueError("no backend is available")

    keyframes = segment.get("keyframes") or []
    duration = float(segment.get("duration_s") or 0)
    fast = bool(segment.get("fast_camera"))
    mode = _mode_for(len(keyframes))

    # Rule 2 + 3: fast camera wants H3, but H3 cannot do under 4 seconds.
    wants_h3 = fast and duration >= H3_MIN_SECONDS
    if wants_h3:
        # Rule 4: H3 has no timeline mode; a split must have happened upstream.
        # Route the pair-level mode instead of the timeline one.
        h3_mode = "flf" if len(keyframes) >= 2 else "i2v"
        if available.get("h3_local"):
            return (h3_mode, "h3_local")
        if available.get("h3_api"):
            return (h3_mode, "h3_api")

    if available.get("ltx"):
        return (mode, "ltx")
    raise ValueError("no backend is available for this segment")


def route_storyboard(run: dict[str, Any], available: dict[str, bool]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for index, segment in enumerate(run.get("segments") or []):
        cell = route_segment(segment, available)
        duration = float(segment.get("duration_s") or 0)
        if cell[1] == "ltx" and segment.get("fast_camera") and duration < H3_MIN_SECONDS:
            reason = f"fast camera but only {duration:g}s — under H3's {H3_MIN_SECONDS}s floor"
        elif cell[1] == "ltx":
            reason = "no fast camera movement"
        else:
            reason = "fast camera movement"
        plan.append({"index": index, "cell": cell, "reason": reason, "duration_s": duration})
    return plan


def split_for_h3(run: dict[str, Any], indices: list[int]) -> list[dict[str, Any]]:
    """Turn a >=3-keyframe segment into adjacent first/last pairs of equal share."""
    pairs: list[dict[str, Any]] = []
    segments = run.get("segments") or []
    for index in indices:
        segment = segments[index]
        keyframes = list(segment.get("keyframes") or [])
        if len(keyframes) < 3:
            pairs.append(dict(segment))
            continue
        span = len(keyframes) - 1
        total = float(segment.get("duration_s") or 0)
        for position in range(span):
            pairs.append({
                "keyframes": keyframes[position:position + 2],
                "duration_s": total / span,
                "fast_camera": bool(segment.get("fast_camera")),
                "prompt": segment.get("prompt") or "",
                "source_index": index,
            })
    return pairs


def estimate_cost(
    plan: list[dict[str, Any]],
    resolution: str = "768P",
    image_count: int = 0,
) -> dict[str, Any]:
    if resolution not in PRICE_PER_SECOND:
        raise ValueError(f"unknown resolution: {resolution}")
    billable = [item for item in plan if item.get("cell", (None, None))[1] == "h3_api"]
    seconds = sum(int(round(float(item.get("duration_s") or 0))) for item in billable)
    video_usd = round(seconds * PRICE_PER_SECOND[resolution], 4)
    extra_images = max(0, image_count - FREE_IMAGES)
    image_usd = round(extra_images * PRICE_PER_EXTRA_IMAGE, 4)
    return {
        "seconds": seconds,
        "video_usd": video_usd,
        "image_usd": image_usd,
        "total_usd": round(video_usd + image_usd, 4),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_routing.py -v`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```bash
git add skills/director-storyboard/scripts/routing.py tests/test_routing.py
git commit -m "feat: route segments across mode x backend and estimate H3 cost"
```

---

### Task 3: `h3_api.py` — MiniMax H3 API adapter

**Files:**
- Create: `skills/director-storyboard/scripts/h3_api.py`
- Test: `tests/test_h3_api.py`

**Interfaces:**
- Consumes: `routing.H3_MIN_SECONDS`, `routing.H3_MAX_SECONDS`.
- Produces:
  - `build_request(shot: dict, resolution: str = "768P", ratio: str = "16:9") -> dict`
  - `class H3ApiClient(base_url: str | None = None, api_key: str | None = None)`
  - `.create(request: dict) -> str` — returns `task_id`
  - `.poll(task_id: str, interval: float = 10.0, timeout: float = 1800.0) -> dict`
  - `.download(url: str, dest: pathlib.Path) -> pathlib.Path`
  - `strip_audio(path: pathlib.Path) -> pathlib.Path`

Shot input keys: `keyframes` (1 or 2 paths or URLs), `duration_s`, `prompt`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_h3_api.py`:

```python
import json
from unittest.mock import patch

import pytest

from h3_api import H3ApiClient, build_request


def shot(n_keys=2, duration=8.0, prompt="she turns and runs"):
    return {
        "keyframes": [f"https://example.test/k{i}.png" for i in range(n_keys)],
        "duration_s": duration,
        "prompt": prompt,
    }


def test_request_has_required_top_level_fields():
    req = build_request(shot())
    assert req["model"] == "MiniMax-H3"
    assert req["duration"] == 8
    assert req["resolution"] == "768P"
    assert req["ratio"] == "16:9"


def test_duration_rounds_to_int():
    assert build_request(shot(duration=8.4))["duration"] == 8


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


def test_prompt_is_a_text_item():
    content = build_request(shot())["content"]
    texts = [item["text"] for item in content if item["type"] == "text"]
    assert texts == ["she turns and runs"]


def test_no_negative_prompt_ever_emitted():
    req = build_request({**shot(), "negative_prompt": "blurry"})
    assert "negative_prompt" not in json.dumps(req)


def test_resolution_must_be_known():
    with pytest.raises(ValueError, match="resolution"):
        build_request(shot(), resolution="1080p")


def test_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MINIMAX_API_KEY"):
        H3ApiClient()


def test_client_defaults_to_international_base_url(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    assert H3ApiClient().base_url == "https://api.minimax.io"


def test_invalid_api_key_error_mentions_region(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    client = H3ApiClient()

    class FakeResponse:
        def read(self):
            return json.dumps({"base_resp": {"status_code": 1004, "status_msg": "Invalid API key"}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with patch("h3_api.urllib.request.urlopen", return_value=FakeResponse()):
        with pytest.raises(RuntimeError, match="same region"):
            client.create(build_request(shot()))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_h3_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'h3_api'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/h3_api.py`:

```python
"""MiniMax H3 official API adapter.

H3 has no negative conditioning, no per-segment local prompts, no strength and
no retake. Nothing in this module may emit them.
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


def _image_item(reference: str, role: str) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": reference}, "role": role}


def build_request(
    shot: dict[str, Any],
    resolution: str = "768P",
    ratio: str = "16:9",
) -> dict[str, Any]:
    if resolution not in VALID_RESOLUTIONS:
        raise ValueError(f"resolution must be one of {VALID_RESOLUTIONS}, got {resolution!r}")

    duration = int(round(float(shot.get("duration_s") or 0)))
    if duration < H3_MIN_SECONDS:
        raise ValueError(f"H3 duration floor is {H3_MIN_SECONDS}s, got {duration}s")
    if duration > H3_MAX_SECONDS:
        raise ValueError(f"H3 duration ceiling is {H3_MAX_SECONDS}s, got {duration}s")

    keyframes = list(shot.get("keyframes") or [])
    if not keyframes:
        raise ValueError("H3 needs at least a first frame")
    if len(keyframes) > 2:
        raise ValueError("H3 accepts at most a first and a last frame; split upstream")

    content: list[dict[str, Any]] = [{"type": "text", "text": str(shot.get("prompt") or "")}]
    roles = ["first_frame", "last_frame"]
    for reference, role in zip(keyframes, roles):
        content.append(_image_item(str(reference), role))

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
        self.base_url = (base_url or os.environ.get("MINIMAX_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")

    def _request(self, path: str, payload: dict | None = None, method: str = "GET") -> dict:
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
        with urllib.request.urlopen(request, timeout=120.0) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code"):
            message = str(base_resp.get("status_msg") or "")
            if "api key" in message.lower():
                raise RuntimeError(
                    f"{message}. MINIMAX_BASE_URL ({self.base_url}) and MINIMAX_API_KEY "
                    "must be from the same region — api.minimax.io pairs with a "
                    "platform.minimax.io key, api.minimaxi.com with a platform.minimaxi.com key."
                )
            raise RuntimeError(f"MiniMax API error {base_resp.get('status_code')}: {message}")
        return body

    def create(self, request: dict[str, Any]) -> str:
        body = self._request("/v2/video_generation", request, method="POST")
        task_id = body.get("task_id") or (body.get("task") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"no task_id in response: {body}")
        return str(task_id)

    def poll(self, task_id: str, interval: float = 10.0, timeout: float = 1800.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            body = self._request(f"/v2/query/video_generation/{task_id}")
            task = body.get("task") or body
            status = str(task.get("status") or "").lower()
            if status in {"failed", "cancelled"}:
                raise RuntimeError(f"H3 task {task_id} ended as {status}")
            url = (task.get("content") or {}).get("url")
            if url:
                return {"task_id": task_id, "url": url, "status": status or "success"}
            time.sleep(interval)
        raise TimeoutError(
            f"H3 task {task_id} still running after {timeout:.0f}s — "
            f"retrieve it later with GET /v2/query/video_generation/{task_id}"
        )

    def download(self, url: str, dest: Path) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=600.0) as response:
            dest.write_bytes(response.read())
        return dest


def strip_audio(path: Path) -> Path:
    """H3 voices are encoded per clip, so they change across shots. Drop the
    track by default and lay audio in post."""
    path = Path(path)
    out = path.with_name(path.stem + "_mute" + path.suffix)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(path), "-an", "-c:v", "copy", str(out)],
        check=True,
        capture_output=True,
    )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_h3_api.py -v`
Expected: PASS, 12 tests

- [ ] **Step 5: Commit**

```bash
git add skills/director-storyboard/scripts/h3_api.py tests/test_h3_api.py
git commit -m "feat: add MiniMax H3 API adapter"
```

---

### Task 4: `h3_local.py` — H3 through ComfyUI

**Files:**
- Create: `skills/director-storyboard/scripts/h3_local.py`
- Test: `tests/test_h3_local.py`

**Interfaces:**
- Consumes: `ComfyClient` (Round 1 Task 4), the graphs from Task 1.
- Produces:
  - `frames_for_seconds(seconds: float) -> int` — nearest valid H3 frame count
  - `fill_h3_graph(graph: dict, shot: dict, image_names: list[str], frames: int, seed: int) -> dict`

H3 local frame rule: `n % 17 == 5`, trained range 124–362 frames at 24 fps.

- [ ] **Step 1: Write the failing test**

Create `tests/test_h3_local.py`:

```python
import pytest

from h3_local import frames_for_seconds


def test_frame_count_satisfies_the_modulo_rule():
    for seconds in (6, 8, 10, 12, 15):
        assert frames_for_seconds(seconds) % 17 == 5


def test_frame_count_stays_in_the_trained_range():
    for seconds in (6, 8, 10, 12, 15):
        assert 124 <= frames_for_seconds(seconds) <= 362


def test_frame_count_is_near_the_request():
    # 8s at 24fps is 192 frames; nearest valid is within one 17-frame step
    assert abs(frames_for_seconds(8) - 192) <= 17


def test_below_trained_range_raises():
    with pytest.raises(ValueError, match="124"):
        frames_for_seconds(3)


def test_above_trained_range_raises():
    with pytest.raises(ValueError, match="362"):
        frames_for_seconds(20)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_h3_local.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'h3_local'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/h3_local.py`:

```python
"""H3 through a local ComfyUI.

Frame count is a hard constraint from comfy_extras/nodes_minimax_h3.py, not a
preference: n % 17 == 5, trained on 124-362 frames at 24 fps.
"""

from __future__ import annotations

import copy
from typing import Any

FPS = 24
FRAME_MODULO = 17
FRAME_REMAINDER = 5
FRAME_MIN = 124
FRAME_MAX = 362


def frames_for_seconds(seconds: float) -> int:
    target = float(seconds) * FPS
    steps = round((target - FRAME_REMAINDER) / FRAME_MODULO)
    frames = int(steps * FRAME_MODULO + FRAME_REMAINDER)
    if frames < FRAME_MIN:
        raise ValueError(
            f"{seconds:g}s is {frames} frames, below H3's trained floor of {FRAME_MIN} "
            f"({FRAME_MIN / FPS:.2f}s)"
        )
    if frames > FRAME_MAX:
        raise ValueError(
            f"{seconds:g}s is {frames} frames, above H3's trained ceiling of {FRAME_MAX} "
            f"({FRAME_MAX / FPS:.2f}s)"
        )
    return frames


def fill_h3_graph(
    graph: dict[str, Any],
    shot: dict[str, Any],
    image_names: list[str],
    frames: int,
    seed: int,
) -> dict[str, Any]:
    filled = copy.deepcopy(graph)

    for node in filled.values():
        class_type = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if class_type == "EmptyMiniMaxH3LatentAV":
            inputs["length"] = frames
        elif class_type == "KSampler":
            inputs["seed"] = seed
        elif class_type == "CLIPTextEncode" and "text" in inputs:
            inputs["text"] = str(shot.get("prompt") or "")

    load_nodes = sorted(
        (node_id for node_id, node in filled.items() if node.get("class_type") == "LoadImage"),
        key=lambda value: int(value) if str(value).isdigit() else 10**9,
    )
    for node_id, name in zip(load_nodes, image_names):
        filled[node_id]["inputs"]["image"] = name
    return filled
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_h3_local.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Verify the graph filler against the real workflow**

```bash
py -3 -c "import json,sys; sys.path.insert(0,'skills/director-storyboard/scripts'); from h3_local import fill_h3_graph, frames_for_seconds; g=json.load(open('skills/director-storyboard/workflows/h3_flf.api.json')); out=fill_h3_graph(g, {'prompt':'test'}, ['a.png','b.png'], frames_for_seconds(8), 500); n=[v for v in out.values() if v.get('class_type')=='EmptyMiniMaxH3LatentAV']; print('latent nodes', len(n), 'length', n[0]['inputs']['length'] if n else None)"
```

Expected: `latent nodes 1 length 192` (or the nearest valid count — must satisfy `% 17 == 5`).

If `latent nodes 0`, the node class name differs in the exported graph; read the actual class names and fix the filler, not the test:

```bash
py -3 -c "import json; g=json.load(open('skills/director-storyboard/workflows/h3_flf.api.json')); print(sorted({v.get('class_type') for v in g.values()}))"
```

- [ ] **Step 6: Commit**

```bash
git add skills/director-storyboard/scripts/h3_local.py tests/test_h3_local.py
git commit -m "feat: add H3-through-ComfyUI adapter"
```

---

### Task 5: `run_storyboard.py` — one CLI over every backend

**Files:**
- Create: `skills/director-storyboard/scripts/run_storyboard.py`

**Interfaces:**
- Consumes: `probe_backends.probe_comfyui`, `routing.route_storyboard`, `routing.estimate_cost`, `comfy_backend.run_storyboard`, `h3_api.H3ApiClient`, `h3_local.fill_h3_graph`.
- Produces: a CLI. No new importable API.

- [ ] **Step 1: Write the CLI**

Create `skills/director-storyboard/scripts/run_storyboard.py`:

```python
#!/usr/bin/env python3
"""Route a storyboard across LTX / H3-local / H3-API and run it.

    py -3 run_storyboard.py storyboard.json --dry-run
    py -3 run_storyboard.py storyboard.json --h3-backend api --yes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from comfy_client import DEFAULT_BASE_URL, ComfyClient
from probe_backends import probe_comfyui
from routing import estimate_cost, route_storyboard


def detect_available(comfy_url: str, h3_backend: str) -> dict[str, bool]:
    client = ComfyClient(comfy_url)
    comfy_up = client.alive()
    probed = probe_comfyui(client.object_info()) if comfy_up else {}
    available = {
        "ltx": bool(probed.get("timeline")),
        "h3_local": bool(probed.get("h3_local")),
        "h3_api": bool(os.environ.get("MINIMAX_API_KEY")),
    }
    if h3_backend == "api":
        available["h3_local"] = False
    elif h3_backend == "local":
        available["h3_api"] = False
    return available


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storyboard", type=Path)
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--h3-backend",
        choices=("ask", "local", "api"),
        default="ask",
        help="'ask' leaves the choice to the caller when both are available",
    )
    parser.add_argument("--resolution", choices=("768P", "2K"), default="768P")
    parser.add_argument("--keep-audio", action="store_true", help="keep H3's native audio track")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args(argv)

    run = json.loads(args.storyboard.read_text(encoding="utf-8"))
    available = detect_available(args.comfy_url, args.h3_backend)

    if not any(available.values()):
        print("No backend available. Start ComfyUI, or set MINIMAX_API_KEY.", file=sys.stderr)
        return 1

    if args.h3_backend == "ask" and available["h3_local"] and available["h3_api"]:
        print(
            "Both H3 backends are available. Re-run with --h3-backend local or "
            "--h3-backend api.\n"
            "Note: the H3 Community License excludes the US, EU, UK and South Korea "
            "from its Applicable Territory for locally run weights.",
            file=sys.stderr,
        )
        return 2

    plan = route_storyboard(run, available)
    image_count = sum(len(item.get("keyframes") or []) for item in run.get("segments") or [])
    cost = estimate_cost(plan, args.resolution, image_count)

    for item in plan:
        mode, backend = item["cell"]
        print(f"  segment {item['index'] + 1}: {mode}/{backend}  ({item['reason']})")
    print(f"\nH3 API billable: {cost['seconds']}s at {args.resolution} = ${cost['total_usd']:.2f}")

    if args.dry_run:
        return 0
    if cost["total_usd"] > 0 and not args.yes:
        print("\nRe-run with --yes to submit.", file=sys.stderr)
        return 3

    print("\nSubmitting is not wired up yet — see Task 6.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it routes and prices the real act3 storyboard**

Convert one of the existing H3 plans into this CLI's input shape and dry-run it:

```bash
py -3 -c "import json; p=json.load(open('C:/Users/AIBOX/dev/camera-lab/tasks/storyboards/h3/act3_lab_h3.json')); segs=[{'keyframes':[s['first']]+([s['last']] if s.get('last') else []),'duration_s':s['length']/24,'fast_camera':True,'prompt':s['prompt']} for s in p['shots']]; json.dump({'width':p['width'],'height':p['height'],'seed':p['seed'],'segments':segs}, open('/tmp/act3_routed.json','w',encoding='utf-8'), ensure_ascii=False)"
py -3 skills/director-storyboard/scripts/run_storyboard.py /tmp/act3_routed.json --h3-backend api --dry-run
```

Expected: 9 segments listed, and a total near `$6.20` at 768P (1847 frames ÷ 24 ≈ 77 s × $0.08). If the number is materially off, check the frame→second conversion before touching anything else.

- [ ] **Step 3: Commit**

```bash
git add skills/director-storyboard/scripts/run_storyboard.py
git commit -m "feat: add unified storyboard routing CLI"
```

---

### Task 6: Wire submission into the CLI

**Files:**
- Modify: `skills/director-storyboard/scripts/run_storyboard.py`

- [ ] **Step 1: Replace the "not wired up yet" branch**

Replace the final `print(...)` / `return 0` block in `main` with:

```python
    outputs: list[str] = []
    workflows = Path(__file__).parent.parent / "workflows"
    for item in plan:
        mode, backend = item["cell"]
        segment = (run.get("segments") or [])[item["index"]]
        if backend == "h3_api":
            from h3_api import H3ApiClient, build_request, strip_audio

            client = H3ApiClient()
            request = build_request(
                {**segment, "duration_s": item["duration_s"]},
                resolution=args.resolution,
            )
            task_id = client.create(request)
            result = client.poll(task_id)
            dest = args.storyboard.parent / "out" / f"segment_{item['index'] + 1:02d}.mp4"
            path = client.download(result["url"], dest)
            if not args.keep_audio:
                path = strip_audio(path)
            outputs.append(str(path))
        elif backend == "h3_local":
            from h3_local import fill_h3_graph, frames_for_seconds

            comfy = ComfyClient(args.comfy_url)
            graph_name = "h3_flf.api.json" if mode == "flf" else "h3_i2v.api.json"
            graph = json.loads((workflows / graph_name).read_text(encoding="utf-8"))
            names = [comfy.upload_image(Path(p)) for p in segment.get("keyframes") or []]
            filled = fill_h3_graph(
                graph,
                segment,
                names,
                frames_for_seconds(item["duration_s"]),
                int(run.get("seed") or 0),
            )
            outputs.append(comfy.submit(filled))
        else:
            from comfy_backend import run_storyboard as run_ltx

            comfy = ComfyClient(args.comfy_url)
            result = run_ltx(run, comfy, workflows / "ltx_director_2.api.json")
            outputs.extend(result.get("outputs") or [])

    print("\nOutputs:")
    for name in outputs:
        print(f"  {name}")
    return 0
```

- [ ] **Step 2: Dry-run still works**

Run: `py -3 skills/director-storyboard/scripts/run_storyboard.py /tmp/act3_routed.json --h3-backend api --dry-run`
Expected: same output as Task 5 Step 2, no submission.

- [ ] **Step 3: Submit exactly one short H3 API segment for real**

Build a one-segment storyboard at 4 seconds and run it:

```bash
py -3 -c "import json; json.dump({'width':1344,'height':768,'seed':500,'segments':[{'keyframes':['<abs path to one keyframe>'],'duration_s':4,'fast_camera':True,'prompt':'she turns her head sharply and looks back over her shoulder'}]}, open('/tmp/h3_smoke.json','w',encoding='utf-8'), ensure_ascii=False)"
py -3 skills/director-storyboard/scripts/run_storyboard.py /tmp/h3_smoke.json --h3-backend api --yes
```

Expected: one `.mp4` written under `/tmp/out/`, cost `$0.32`. Verify the audio track is gone:

```bash
ffprobe -v error -show_streams -select_streams a /tmp/out/segment_01_mute.mp4
```

Expected: no output (no audio streams).

Note: local keyframes must be reachable by the API. If the request fails because a local path is not a URL, that is the gap to close — either upload the image somewhere reachable or switch to base64, and record which one works in `backend-minimax-api.md`.

- [ ] **Step 4: Run the full suite**

Run: `py -3 -m pytest -v`
Expected: PASS, all tests from both rounds

- [ ] **Step 5: Commit**

```bash
git add skills/director-storyboard/scripts/run_storyboard.py
git commit -m "feat: submit routed segments to their backends"
```

---

### Task 7: References for H3 and routing

**Files:**
- Create: `skills/director-storyboard/references/routing.md`
- Create: `skills/director-storyboard/references/prompting-h3.md`
- Create: `skills/director-storyboard/references/backend-h3-local.md`
- Create: `skills/director-storyboard/references/backend-minimax-api.md`
- Modify: `skills/director-storyboard/references/backend-contract.md`

- [ ] **Step 1: Write `references/routing.md`**

Contains the 3×3 table with the two permanently-empty cells, the four rules verbatim from the spec, and this justification for the empty cells: `comfy/ldm/minimax/model.py:317` accepts `pixel_index` of only `0` and `frame_count - 1`, otherwise raising `ValueError("only first/last keyframe anchors are supported")`. H3 has no director timeline at the model level.

- [ ] **Step 2: Write `references/prompting-h3.md`**

This is a different contract from `prompting.md` and must say so in its first line. Content, all of it load-bearing:

- Text encoder is Qwen3-VL-32B; keyframes enter the encoder as vision blocks alongside the text (`<Picture 1>: <vision block> <prompt>`). The model can see the frame — do not re-describe what is already visible. Write only what changes: action, camera, light, sound.
- There is no chat template. Do not write instruction-voice ("Generate a video of…"); those words get encoded as picture content.
- There is no negative conditioning at all. Express every constraint positively ("no full body" → "only limbs enter frame, the torso stays out of shot").
- Name multiple references in the prompt as `<Picture i>`, numbered from 1 within each type.
- Lengthening a shot requires writing more action to fill it, or the model invents its own.
- No per-segment local prompts, no `strength`, no retake.

- [ ] **Step 3: Write `references/backend-h3-local.md`**

Frame rule `n % 17 == 5` with the 124–362 trained range; resolution is unconstrained (unlike the API); 15 steps is the production setting (30 steps costs 1.8× for little gain); model load time is negligible so restarting ComfyUI mid-batch is cheap; ComfyUI has crashed after H3 runs, so probe before each submit. Add the licensing note: Applicable Territory excludes the US, EU, UK and South Korea.

- [ ] **Step 4: Write `references/backend-minimax-api.md`**

Endpoints, auth, the request table, `role` values, input limits, the region/key pairing rule, pricing, and whatever Task 6 Step 3 established about local paths vs URLs vs base64.

- [ ] **Step 5: Add the two new adapters to `backend-contract.md`**

Append to its Adapters list:

```markdown
- `backend-h3-local.md` — MiniMax H3 through ComfyUI
- `backend-minimax-api.md` — MiniMax H3 through the official API
```

- [ ] **Step 6: Commit**

```bash
git add skills/director-storyboard/references/
git commit -m "docs: document routing, H3 prompting and both H3 adapters"
```

---

### Task 8: Update SKILL.md, sync the Codex variant

**Files:**
- Modify: `skills/director-storyboard/SKILL.md`
- Modify: `codex/director-storyboard/SKILL.md`
- Copy: the four new references into `codex/director-storyboard/references/`

- [ ] **Step 1: Add the routing step to `SKILL.md`**

Insert between the current "emit storyboard JSON" step and the run step:

- Probe backends first (`scripts/probe_backends.py`).
- Read the keyframes pairwise and mark segments with fast camera movement. **This judgement is the agent's, not the script's** — `fast_camera` is an input to routing, not an output of it.
- Apply the four rules from `references/routing.md`.
- If both H3 backends are available, ask the user local or API, and state the Applicable Territory exclusion when they pick local.
- Print the cost estimate and wait for confirmation before submitting.

Also add to the "Load only what the task needs" list: read `prompting-h3.md` instead of `prompting.md` whenever a segment routes to H3.

- [ ] **Step 2: Add a hard rule to the "Do not" section**

```markdown
- Do not carry LTX prompt structure into an H3 segment. No negative prompt, no
  `|`-separated local prompts, no `strength`. H3 accepts none of them and will
  encode the words as picture content.
```

- [ ] **Step 3: Mirror everything into the Codex variant**

```bash
cp skills/director-storyboard/references/routing.md codex/director-storyboard/references/
cp skills/director-storyboard/references/prompting-h3.md codex/director-storyboard/references/
cp skills/director-storyboard/references/backend-h3-local.md codex/director-storyboard/references/
cp skills/director-storyboard/references/backend-minimax-api.md codex/director-storyboard/references/
```

Then apply Steps 1 and 2's changes to `codex/director-storyboard/SKILL.md` in its condensed voice.

- [ ] **Step 4: Verify both variants cover routing**

```bash
grep -c "fast_camera\|routing" skills/director-storyboard/SKILL.md codex/director-storyboard/SKILL.md
```

Expected: both non-zero.

- [ ] **Step 5: Update the README description**

Change the `director-storyboard` row to mention H3 and backend routing.

- [ ] **Step 6: Run the full suite and commit**

```bash
py -3 -m pytest -v
git add skills/ codex/ README.md
git commit -m "docs: route across LTX and H3 in both skill variants"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| 路由表 (3×3, two empty cells) | 2, 7 step 1 |
| 路由规则 1–4 | 2 (tests pin each rule) |
| 后端契约 — 探测/提交/取结果 | 3, 4, 5, 6 |
| Adapter: MiniMax H3 API | 3, 7 step 4 |
| Adapter: H3 本地 | 4, 7 step 3 |
| H3 本地 vs API 探测在前询问在后 | 5 (`detect_available` + the `ask` branch) |
| 许可证 Applicable Territory 提示 | 5 step 1, 7 step 3, 8 step 1 |
| 时长 clamp [4,15]，<4s 不进 H3 | 2 (rule 3), 3 (`build_request`) |
| 声音默认剥掉 | 3 (`strip_audio`), 6 (`--keep-audio`) |
| 分辨率默认 768P/16:9 | 3 (`build_request` defaults) |
| 提示词两套契约不能混 | 7 step 2, 8 step 2 |
| 成本可见性 | 2 (`estimate_cost`), 5, 6 |
| 错误处理 — key 缺失/区域错配 | 3 (`H3ApiClient.__init__`, `_request`) |
| 错误处理 — failed/cancelled 不重试 | 3 (`poll` raises) |
| 错误处理 — 轮询超时保留 task_id | 3 (`poll` TimeoutError message) |
| 错误处理 — 超 15 秒报错不截断 | 3 (`build_request` raises) |
| 验证 — act3 dry-run 约 $6.2 | 5 step 2 |
| 验证 — 真实调用一个 4 秒段 + 剥音轨 | 6 step 3 |
| 待定：seed / prompt_optimizer | Task 6 step 3 is where a real response reveals them; they stay out of the schema until then |

**Placeholder scan:** No TBD/TODO. Two steps intentionally end in "record what you found" (Task 6 step 3 on local-path-vs-URL, Task 7 step 4) — those are empirical questions the official docs do not answer (`/docs/api-reference/*` currently 404s), and each names the exact file the finding goes into.

**Type consistency:** `Cell` is `tuple[str, str]` throughout; `route_segment` and `route_storyboard` both produce it, `estimate_cost` reads `item["cell"][1]`, and `run_storyboard.py` unpacks it as `mode, backend`. `H3_MIN_SECONDS` / `H3_MAX_SECONDS` are defined once in `routing.py` and imported by `h3_api.py` — no second copy. `frames_for_seconds` returns `int` in Task 4 and is passed to `fill_h3_graph(..., frames=int, ...)` in Task 6. `ComfyClient.upload_image` returns `str`, collected as `list[str]` for `fill_h3_graph` (H3) and `dict[int, str]` for `fill_director_graph` (LTX) — deliberately different shapes because H3 has positional first/last frames while Director keys by segment index.
