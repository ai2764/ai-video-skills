# Round 1: Migrate director-storyboard + ComfyUI direct adapter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `director-storyboard` out of `camera-lab` into this repo and give it a ComfyUI-direct backend, so that having ComfyUI installed is enough to run it — Camera Lab becomes optional.

**Architecture:** The skill is written against a backend contract (probe / submit / fetch), same as `slowmo-redraw-repair`. Two adapters ship in this round: ComfyUI-direct and Camera Lab. The ComfyUI adapter carries its own pre-converted API-format workflow graphs and fills them in; it never needs Camera Lab's `workflow_to_api` subgraph expansion. Correctness is pinned by a golden `api_prompt.json` captured from a real Camera Lab run.

**Tech Stack:** Python 3 (stdlib `urllib` only — no new runtime deps), pytest 9.x for tests, Markdown for the skill itself.

## Global Constraints

- Runtime scripts use the **standard library only**. No `requests`, no `httpx`. Camera Lab's own scripts use `urllib.request`; match that.
- ComfyUI default base URL is `http://127.0.0.1:8188`. Camera Lab default is `http://127.0.0.1:1234`.
- Both skill variants must describe the same method: `skills/director-storyboard/` (Claude/Grok, detailed) and `codex/director-storyboard/` (Codex, condensed). Keep them in step.
- Never put `|` inside a Director prompt — `LTXDirector` splits `local_prompts` on it.
- Resolution: Camera Lab halves each dimension, aligns to 32, doubles back (`720 → 704`, `736 → 768`). The ComfyUI adapter must reproduce this so both backends agree.
- Do not modify anything under `C:\Users\AIBOX\dev\camera-lab\server\`. Read from it, copy out of it, never write to it.
- Do not commit generated videos, storyboards, or captured run artifacts other than the small golden fixture named in Task 2.

---

## File Structure

```
skills/director-storyboard/
  SKILL.md                          method, backend-agnostic
  references/
    backend-contract.md             the three operations
    backend-comfyui.md              ComfyUI-direct adapter notes
    backend-camera-lab.md           Camera Lab adapter notes
    prompting.md                    LTX prompt contract (migrated as-is)
    storyboard.schema.json          migrated as-is
    example_storyboard.json         migrated as-is
  workflows/
    ltx_director_2.api.json         pre-converted, checked in
  scripts/
    comfy_client.py                 ComfyUI HTTP: object_info/prompt/history/upload
    director_timeline.py            storyboard JSON -> LTXDirector inputs
    comfy_backend.py                fill graph + submit + fetch
    probe_backends.py               which routing cells are available
codex/director-storyboard/
  SKILL.md
  agents/openai.yaml
  references/                       same files, condensed
tests/
  conftest.py
  fixtures/
    golden_director_api_prompt.json captured from a real Camera Lab run
    object_info_ltx.json            trimmed /object_info sample
  test_director_timeline.py
  test_comfy_client.py
  test_probe_backends.py
pyproject.toml                      pytest config only
```

Responsibility split: `comfy_client.py` knows HTTP and nothing about Director. `director_timeline.py` is pure data transformation with no I/O — that is what makes it cheaply testable against the golden fixture. `comfy_backend.py` joins the two. `probe_backends.py` only reads capability, never submits.

---

### Task 1: Repo scaffolding for Python + tests

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `skills/director-storyboard/scripts/__init__.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package path `skills.director_storyboard.scripts` is NOT used — scripts are loaded by path. `conftest.py` exposes fixture `fixtures_dir` returning `pathlib.Path` to `tests/fixtures/`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scaffolding.py`:

```python
from pathlib import Path


def test_fixtures_dir_exists(fixtures_dir):
    assert fixtures_dir.is_dir()
    assert fixtures_dir.name == "fixtures"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_scaffolding.py -v`
Expected: FAIL with `fixture 'fixtures_dir' not found`

- [ ] **Step 3: Write minimal implementation**

Create `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["skills/director-storyboard/scripts"]
```

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

Create the directory and an empty `skills/director-storyboard/scripts/__init__.py`:

```bash
mkdir -p tests/fixtures skills/director-storyboard/scripts
touch skills/director-storyboard/scripts/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_scaffolding.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/ skills/director-storyboard/scripts/__init__.py
git commit -m "chore: add pytest scaffolding"
```

---

### Task 2: Capture the golden fixtures from camera-lab

This task produces the ground truth every later filling test is checked against. Do not skip it and do not hand-write these files.

**Files:**
- Create: `tests/fixtures/golden_director_api_prompt.json`
- Create: `tests/fixtures/golden_director_run.json`
- Create: `tests/fixtures/object_info_ltx.json`
- Create: `skills/director-storyboard/workflows/ltx_director_2.api.json`

**Interfaces:**
- Consumes: nothing.
- Produces: the four files above. `golden_director_api_prompt.json` is a full ComfyUI API-format prompt with `LTXDirector` inputs already filled by Camera Lab. `golden_director_run.json` is the `run` payload that produced it. `object_info_ltx.json` is a trimmed `/object_info` containing at least the keys `LTXDirector`, `LTXDirectorGuide`, `CLIPLoader`.

- [ ] **Step 1: Find an existing Camera Lab director run that already dumped its prompt**

```bash
ls C:/Users/AIBOX/dev/camera-lab/tasks/camera_lab_runs/*/*/api_prompt.json | head -20
```

Pick one whose sibling `batch.json` has `runs[0].workflow_id == "ltx_director_2"` and at least 3 segments. Verify:

```bash
py -3 -c "import json,sys; b=json.load(open(sys.argv[1])); r=b['runs'][0]; print(r['workflow_id'], len(r.get('segments') or []))" <path-to-batch.json>
```

Expected output: `ltx_director_2 3` (or a larger segment count).

If no such run exists, produce one: start Camera Lab (`python scripts/start_camera_lab.py` in the camera-lab repo), submit a 3-keyframe storyboard through the existing skill, then re-run the search.

- [ ] **Step 2: Copy the two golden files in**

```bash
cp <path-to>/api_prompt.json tests/fixtures/golden_director_api_prompt.json
py -3 -c "import json,sys; b=json.load(open(sys.argv[1])); json.dump(b['runs'][0], open('tests/fixtures/golden_director_run.json','w'), ensure_ascii=False, indent=2)" <path-to-batch.json>
```

- [ ] **Step 3: Export the unfilled API-format graph**

`workflow_to_api` lives in camera-lab and handles subgraph expansion. Run it there once and check the result in here, so this repo never needs that code:

```bash
py -3 -c "import sys, json; sys.path.insert(0, 'C:/Users/AIBOX/dev/camera-lab'); sys.path.insert(0, 'C:/Users/AIBOX/dev/camera-lab/server'); from workflow_graph import workflow_to_api; data=json.load(open('C:/Users/AIBOX/dev/camera-lab/workflows/app/ltx_director_2.json', encoding='utf-8')); json.dump(workflow_to_api(data), open('C:/Users/AIBOX/dev/ai-video-skills/skills/director-storyboard/workflows/ltx_director_2.api.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)"
```

- [ ] **Step 4: Verify the exported graph matches the golden prompt's shape**

Run:

```bash
py -3 -c "import json; a=json.load(open('skills/director-storyboard/workflows/ltx_director_2.api.json')); g=json.load(open('tests/fixtures/golden_director_api_prompt.json')); ka=set(a); kg=set(g); print('only_in_export', sorted(ka-kg)[:10]); print('only_in_golden', sorted(kg-ka)[:10]); print('director_nodes', [n for n,v in a.items() if v.get('class_type')=='LTXDirector'])"
```

Expected: `only_in_export` and `only_in_golden` are both `[]`, and `director_nodes` lists exactly one node id.

If they differ, the golden run used a different workflow revision — pick a newer run and redo steps 1–3. Do not proceed with mismatched files.

- [ ] **Step 5: Capture a trimmed object_info**

With ComfyUI running on 8188:

```bash
py -3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8188/object_info')); keep={k:d[k] for k in ('LTXDirector','LTXDirectorGuide','CLIPLoader') if k in d}; json.dump(keep, open('tests/fixtures/object_info_ltx.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); print(sorted(keep))"
```

Expected: `['CLIPLoader', 'LTXDirector', 'LTXDirectorGuide']`

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/ skills/director-storyboard/workflows/
git commit -m "test: capture golden director prompt and object_info fixtures"
```

---

### Task 3: `director_timeline.py` — storyboard JSON to LTXDirector inputs

The pure-data core. No HTTP here.

**Files:**
- Create: `skills/director-storyboard/scripts/director_timeline.py`
- Test: `tests/test_director_timeline.py`

**Interfaces:**
- Consumes: `tests/fixtures/golden_director_run.json`, `tests/fixtures/golden_director_api_prompt.json`.
- Produces:
  - `align_dimension(value: int) -> int`
  - `build_segments(run: dict, fps: int = 24) -> list[dict]` — returns segment dicts with keys `id`, `type`, `label`, `start`, `length`, `prompt`, and for non-text segments `imageFile` and `strength`.
  - `build_director_inputs(run: dict, image_names: dict[int, str], fps: int = 24) -> dict` — returns the full `inputs` mapping to write onto the `LTXDirector` node.

- [ ] **Step 1: Write the failing test**

Create `tests/test_director_timeline.py`:

```python
import json

import pytest

from director_timeline import align_dimension, build_director_inputs, build_segments


def test_align_dimension_matches_camera_lab():
    # halve, align to 32, double back
    assert align_dimension(720) == 704
    assert align_dimension(736) == 768
    assert align_dimension(1280) == 1280


@pytest.fixture
def golden(fixtures_dir):
    run = json.loads((fixtures_dir / "golden_director_run.json").read_text(encoding="utf-8"))
    api = json.loads((fixtures_dir / "golden_director_api_prompt.json").read_text(encoding="utf-8"))
    director = next(n for n in api.values() if n.get("class_type") == "LTXDirector")
    return run, director["inputs"]


def test_segments_match_golden(golden):
    run, expected_inputs = golden
    expected_segments = json.loads(expected_inputs["timeline_data"])["segments"]
    image_names = {
        i: seg["imageFile"]
        for i, seg in enumerate(expected_segments, start=1)
        if seg.get("imageFile")
    }
    got = build_segments(run)
    assert len(got) == len(expected_segments)
    for a, b in zip(got, expected_segments):
        assert a["start"] == b["start"]
        assert a["length"] == b["length"]
        assert a["prompt"] == b["prompt"]


def test_director_inputs_match_golden(golden):
    run, expected_inputs = golden
    expected_segments = json.loads(expected_inputs["timeline_data"])["segments"]
    image_names = {
        i: seg["imageFile"]
        for i, seg in enumerate(expected_segments, start=1)
        if seg.get("imageFile")
    }
    got = build_director_inputs(run, image_names)
    for key in (
        "global_prompt",
        "local_prompts",
        "segment_lengths",
        "guide_strength",
        "duration_frames",
        "frame_rate",
        "custom_width",
        "custom_height",
    ):
        assert got[key] == expected_inputs[key], key
    assert json.loads(got["timeline_data"])["segments"] == expected_segments
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_director_timeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'director_timeline'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/director_timeline.py`:

```python
"""storyboard run payload -> LTXDirector node inputs.

Pure data transformation, no I/O. Mirrors camera-lab's
`build_ltx_director_v2_api` (server/camera_lab_server.py:1300) closely enough
that both backends produce the same graph; the golden fixture test is what
holds that claim up.
"""

from __future__ import annotations

import json
from typing import Any

FPS_DEFAULT = 24
DIVISIBLE_BY = 32


def align_dimension(value: int) -> int:
    """Camera Lab halves each dimension, aligns to 32, doubles back."""
    half = int(value) // 2
    aligned = max(DIVISIBLE_BY, round(half / DIVISIBLE_BY) * DIVISIBLE_BY)
    return aligned * 2


def build_segments(run: dict[str, Any], fps: int = FPS_DEFAULT) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(run.get("segments") or [], start=1):
        seg_type = str(segment.get("type") or "image")
        start_frame = segment.get("guide_frame", segment.get("start_frame", 0))
        item: dict[str, Any] = {
            "id": segment.get("id") or f"camera-lab-segment-{index}",
            "type": seg_type,
            "label": f"segment {index}",
            "start": max(0, int(start_frame)),
            "length": int(segment["frames"]),
            "prompt": segment.get("prompt") or "",
        }
        segments.append(item)
    return segments


def attach_images(
    segments: list[dict[str, Any]],
    run: dict[str, Any],
    image_names: dict[int, str],
) -> list[dict[str, Any]]:
    raw = run.get("segments") or []
    for index, item in enumerate(segments, start=1):
        if item["type"] == "text" or index not in image_names:
            continue
        item["type"] = "image"
        item["imageFile"] = image_names[index]
        strength = raw[index - 1].get("strength")
        item["strength"] = 1.0 if strength in {None, ""} else float(strength)
    return segments


def build_director_inputs(
    run: dict[str, Any],
    image_names: dict[int, str],
    fps: int = FPS_DEFAULT,
) -> dict[str, Any]:
    segments = attach_images(build_segments(run, fps), run, image_names)
    duration_frames = sum(int(item["length"]) for item in segments)
    width = align_dimension(int(run["width"]))
    height = align_dimension(int(run["height"]))
    timeline_data = {"segments": segments, "audioSegments": []}
    return {
        "global_prompt": run.get("global_prompt") or "",
        "start_second": 0,
        "end_second": duration_frames / float(fps),
        "duration_frames": duration_frames,
        "duration_seconds": duration_frames / float(fps),
        "start_frame": 0,
        "end_frame": duration_frames,
        "timeline_data": json.dumps(timeline_data, ensure_ascii=False),
        "overrideAudio": False,
        "inpaint_audio": bool(run.get("inpaint_audio", True)),
        "use_custom_audio": False,
        "local_prompts": "|".join(str(item["prompt"]) for item in segments),
        "segment_lengths": ",".join(str(int(item["length"])) for item in segments),
        "guide_strength": ",".join(
            str(item["strength"])
            for item in segments
            if item.get("type") != "text" and "strength" in item
        ),
        "frame_rate": fps,
        "custom_width": width,
        "custom_height": height,
        "display_mode": "seconds",
        "resize_method": "maintain aspect ratio",
        "divisible_by": DIVISIBLE_BY,
        "img_compression": 18,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_director_timeline.py -v`
Expected: PASS

If `test_director_inputs_match_golden` fails on `local_prompts` or `segment_lengths`, the separator guess is wrong — read the actual value out of the fixture and fix the join, do not change the assertion:

```bash
py -3 -c "import json; g=json.load(open('tests/fixtures/golden_director_api_prompt.json')); d=next(n for n in g.values() if n.get('class_type')=='LTXDirector'); print(repr(d['inputs']['local_prompts'])[:300]); print(repr(d['inputs']['segment_lengths']))"
```

- [ ] **Step 5: Commit**

```bash
git add skills/director-storyboard/scripts/director_timeline.py tests/test_director_timeline.py
git commit -m "feat: build LTXDirector inputs from a storyboard run"
```

---

### Task 4: `comfy_client.py` — ComfyUI HTTP client

**Files:**
- Create: `skills/director-storyboard/scripts/comfy_client.py`
- Test: `tests/test_comfy_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class ComfyClient(base_url: str = "http://127.0.0.1:8188")`
  - `.alive() -> bool`
  - `.object_info() -> dict`
  - `.upload_image(path: pathlib.Path, subfolder: str = "") -> str` — returns the name ComfyUI stored it under
  - `.submit(graph: dict) -> str` — returns `prompt_id`
  - `.history(prompt_id: str) -> dict`
  - `.outputs(prompt_id: str) -> list[str]` — output filenames, empty while still running

- [ ] **Step 1: Write the failing test**

Create `tests/test_comfy_client.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_comfy_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'comfy_client'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/comfy_client.py`:

```python
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8") or "{}")

    def alive(self) -> bool:
        try:
            self._get("/system_stats", timeout=8.0)
            return True
        except Exception:
            return False

    def object_info(self) -> dict:
        return self._get("/object_info", timeout=60.0)

    def upload_image(self, path: Path, subfolder: str = "") -> str:
        path = Path(path)
        boundary = f"----ai-video-skills-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts: list[bytes] = []
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'.encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(path.read_bytes())
        parts.append(b"\r\n")
        if subfolder:
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(b'Content-Disposition: form-data; name="subfolder"\r\n\r\n')
            parts.append(subfolder.encode())
            parts.append(b"\r\n")
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(b'Content-Disposition: form-data; name="overwrite"\r\n\r\n')
        parts.append(b"true\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        request = urllib.request.Request(
            self.base_url + "/upload/image",
            data=body,
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
            first = sorted(node_errors)[0]
            raise RuntimeError(f"ComfyUI rejected the graph at node {first}: {result.get('error')}")
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI returned no prompt_id: {result}")
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict:
        return self._get(f"/history/{prompt_id}", timeout=30.0)

    def outputs(self, prompt_id: str) -> list[str]:
        entry = (self.history(prompt_id) or {}).get(prompt_id) or {}
        names: list[str] = []
        for node_output in (entry.get("outputs") or {}).values():
            for key in _OUTPUT_KEYS:
                for item in node_output.get(key) or []:
                    name = item.get("filename")
                    if name:
                        names.append(name)
        return names
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_comfy_client.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add skills/director-storyboard/scripts/comfy_client.py tests/test_comfy_client.py
git commit -m "feat: add stdlib ComfyUI HTTP client"
```

---

### Task 5: `probe_backends.py` — report which routing cells are available

**Files:**
- Create: `skills/director-storyboard/scripts/probe_backends.py`
- Test: `tests/test_probe_backends.py`

**Interfaces:**
- Consumes: `ComfyClient` from Task 4.
- Produces:
  - `probe_comfyui(object_info: dict) -> dict` — returns `{"timeline": bool, "i2v": bool, "flf": bool, "h3_local": bool, "reasons": dict[str, str]}`
  - `main(argv: list[str] | None = None) -> int` — CLI printing JSON

`h3_local` is reported in this round but never routed to; Round 2 consumes it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_probe_backends.py`:

```python
import json

from probe_backends import probe_comfyui

H3_NODES = (
    "EmptyMiniMaxH3LatentAV",
    "MiniMaxH3ImageToVideo",
    "MiniMaxH3ReferenceToVideo",
    "MiniMaxH3SigmaShift",
)


def test_ltx_available_from_real_object_info(fixtures_dir):
    info = json.loads((fixtures_dir / "object_info_ltx.json").read_text(encoding="utf-8"))
    result = probe_comfyui(info)
    assert result["timeline"] is True


def test_h3_local_false_when_nodes_absent():
    result = probe_comfyui({"LTXDirector": {}})
    assert result["h3_local"] is False
    assert "MiniMaxH3ImageToVideo" in result["reasons"]["h3_local"]


def test_h3_local_false_when_weights_missing():
    info = {name: {} for name in H3_NODES}
    info["CLIPLoader"] = {"input": {"required": {"type": [["stable_diffusion", "ltxv"]]}}}
    result = probe_comfyui(info)
    assert result["h3_local"] is False
    assert "minimax" in result["reasons"]["h3_local"]


def test_h3_local_true_when_nodes_and_weights_present():
    info = {name: {} for name in H3_NODES}
    info["CLIPLoader"] = {"input": {"required": {"type": [["stable_diffusion", "minimax"]]}}}
    result = probe_comfyui(info)
    assert result["h3_local"] is True


def test_timeline_false_without_director_node():
    result = probe_comfyui({})
    assert result["timeline"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_probe_backends.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'probe_backends'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/probe_backends.py`:

```python
"""Report which cells of the routing table this machine can actually run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from comfy_client import DEFAULT_BASE_URL, ComfyClient

H3_NODES = (
    "EmptyMiniMaxH3LatentAV",
    "MiniMaxH3ImageToVideo",
    "MiniMaxH3ReferenceToVideo",
    "MiniMaxH3SigmaShift",
)


def _clip_loader_types(object_info: dict[str, Any]) -> list[str]:
    node = object_info.get("CLIPLoader") or {}
    required = ((node.get("input") or {}).get("required") or {})
    entry = required.get("type")
    if isinstance(entry, list) and entry and isinstance(entry[0], list):
        return [str(item) for item in entry[0]]
    return []


def probe_comfyui(object_info: dict[str, Any]) -> dict[str, Any]:
    reasons: dict[str, str] = {}

    timeline = "LTXDirector" in object_info
    if not timeline:
        reasons["timeline"] = "LTXDirector node not installed"

    ltx_basic = timeline
    if not ltx_basic:
        reasons["i2v"] = reasons["flf"] = "no LTX nodes found"

    missing_h3 = [name for name in H3_NODES if name not in object_info]
    if missing_h3:
        h3_local = False
        reasons["h3_local"] = "missing nodes: " + ", ".join(missing_h3)
    elif "minimax" not in _clip_loader_types(object_info):
        h3_local = False
        reasons["h3_local"] = (
            "H3 nodes present but CLIPLoader has no 'minimax' type — weights not installed"
        )
    else:
        h3_local = True

    return {
        "timeline": timeline,
        "i2v": ltx_basic,
        "flf": ltx_basic,
        "h3_local": h3_local,
        "reasons": reasons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", DEFAULT_BASE_URL))
    args = parser.parse_args(argv)

    client = ComfyClient(args.comfy_url)
    if not client.alive():
        print(json.dumps({"comfyui": False, "reason": f"no response from {args.comfy_url}"}, indent=2))
        return 1
    result = probe_comfyui(client.object_info())
    result["comfyui"] = True
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_probe_backends.py -v`
Expected: PASS, 5 tests

- [ ] **Step 5: Run it for real against the running ComfyUI**

Run: `py -3 skills/director-storyboard/scripts/probe_backends.py`
Expected: JSON with `"comfyui": true` and `"timeline": true`. On this machine `h3_local` should be `true` (H3 weights are installed); on a machine without them it should be `false` with a reason.

- [ ] **Step 6: Commit**

```bash
git add skills/director-storyboard/scripts/probe_backends.py tests/test_probe_backends.py
git commit -m "feat: probe ComfyUI for available workflow cells"
```

---

### Task 6: `comfy_backend.py` — fill the graph and run it

**Files:**
- Create: `skills/director-storyboard/scripts/comfy_backend.py`
- Test: `tests/test_comfy_backend.py`

**Interfaces:**
- Consumes: `build_director_inputs` (Task 3), `ComfyClient` (Task 4).
- Produces:
  - `fill_director_graph(graph: dict, run: dict, image_names: dict[int, str]) -> dict` — returns a new graph with `LTXDirector` inputs replaced
  - `stage_images(client: ComfyClient, run: dict) -> dict[int, str]`
  - `run_storyboard(run: dict, client: ComfyClient, graph_path: pathlib.Path, dry_run: bool = False) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_comfy_backend.py`:

```python
import json

import pytest

from comfy_backend import fill_director_graph


@pytest.fixture
def golden(fixtures_dir):
    run = json.loads((fixtures_dir / "golden_director_run.json").read_text(encoding="utf-8"))
    api = json.loads((fixtures_dir / "golden_director_api_prompt.json").read_text(encoding="utf-8"))
    return run, api


def test_fill_reproduces_golden_director_inputs(golden, fixtures_dir):
    run, golden_api = golden
    template = json.loads(
        (fixtures_dir.parent.parent / "skills/director-storyboard/workflows/ltx_director_2.api.json")
        .read_text(encoding="utf-8")
    )
    expected = next(n for n in golden_api.values() if n.get("class_type") == "LTXDirector")["inputs"]
    image_names = {
        i: seg["imageFile"]
        for i, seg in enumerate(json.loads(expected["timeline_data"])["segments"], start=1)
        if seg.get("imageFile")
    }
    filled = fill_director_graph(template, run, image_names)
    got = next(n for n in filled.values() if n.get("class_type") == "LTXDirector")["inputs"]
    assert got["local_prompts"] == expected["local_prompts"]
    assert got["segment_lengths"] == expected["segment_lengths"]
    assert json.loads(got["timeline_data"])["segments"] == json.loads(expected["timeline_data"])["segments"]


def test_fill_does_not_mutate_the_template(golden, fixtures_dir):
    run, _ = golden
    template = json.loads(
        (fixtures_dir.parent.parent / "skills/director-storyboard/workflows/ltx_director_2.api.json")
        .read_text(encoding="utf-8")
    )
    before = json.dumps(template, sort_keys=True)
    fill_director_graph(template, run, {})
    assert json.dumps(template, sort_keys=True) == before


def test_fill_raises_without_director_node():
    with pytest.raises(RuntimeError, match="LTXDirector"):
        fill_director_graph({"1": {"class_type": "KSampler", "inputs": {}}}, {"width": 1280, "height": 704, "segments": []}, {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_comfy_backend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'comfy_backend'`

- [ ] **Step 3: Write minimal implementation**

Create `skills/director-storyboard/scripts/comfy_backend.py`:

```python
"""Fill the Director graph and run it straight against ComfyUI."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from comfy_client import ComfyClient
from director_timeline import build_director_inputs


def fill_director_graph(
    graph: dict[str, Any],
    run: dict[str, Any],
    image_names: dict[int, str],
) -> dict[str, Any]:
    filled = copy.deepcopy(graph)
    director = next(
        (node for node in filled.values() if node.get("class_type") == "LTXDirector"),
        None,
    )
    if director is None:
        raise RuntimeError("workflow does not contain an LTXDirector node")
    director.setdefault("inputs", {}).update(build_director_inputs(run, image_names))

    ic_lora_name = str(run.get("ic_lora_name") or "None")
    ic_lora_strength = max(0.0, min(2.0, float(run.get("ic_lora_strength") or 1.0)))
    for node in filled.values():
        if node.get("class_type") == "LTXDirectorGuide":
            node.setdefault("inputs", {})["ic_lora_name"] = ic_lora_name
            node["inputs"]["ic_lora_strength"] = ic_lora_strength
    return filled


def stage_images(client: ComfyClient, run: dict[str, Any]) -> dict[int, str]:
    """Upload every segment image into ComfyUI's input dir, keyed by 1-based index."""
    names: dict[int, str] = {}
    for index, segment in enumerate(run.get("segments") or [], start=1):
        raw = segment.get("image_path")
        if not raw:
            continue
        path = Path(str(raw))
        if not path.exists():
            raise FileNotFoundError(f"segment {index} image is missing: {path}")
        names[index] = client.upload_image(path)
    return names


def run_storyboard(
    run: dict[str, Any],
    client: ComfyClient,
    graph_path: Path,
    dry_run: bool = False,
    poll_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    if dry_run:
        filled = fill_director_graph(graph, run, {})
        return {"dry_run": True, "graph": filled}

    image_names = stage_images(client, run)
    filled = fill_director_graph(graph, run, image_names)
    prompt_id = client.submit(filled)

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        outputs = client.outputs(prompt_id)
        if outputs:
            return {"prompt_id": prompt_id, "outputs": outputs}
        time.sleep(poll_seconds)
    # A client-side timeout is not a failed generation.
    return {
        "prompt_id": prompt_id,
        "outputs": [],
        "note": "still running; check /history/{id} and ComfyUI's output dir".format(id=prompt_id),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_comfy_backend.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Run the full suite**

Run: `py -3 -m pytest -v`
Expected: PASS, all tests from Tasks 1, 3, 4, 5, 6

- [ ] **Step 6: Commit**

```bash
git add skills/director-storyboard/scripts/comfy_backend.py tests/test_comfy_backend.py
git commit -m "feat: fill and submit the Director graph directly to ComfyUI"
```

---

### Task 7: End-to-end check against a real ComfyUI

No new code. This is the gate that proves the adapter actually equals Camera Lab.

**Files:**
- Modify: none (findings go into `references/backend-comfyui.md` in Task 8)

- [ ] **Step 1: Dry-run the golden storyboard**

```bash
py -3 -c "import json,sys; sys.path.insert(0,'skills/director-storyboard/scripts'); from pathlib import Path; from comfy_backend import run_storyboard; from comfy_client import ComfyClient; run=json.load(open('tests/fixtures/golden_director_run.json',encoding='utf-8')); out=run_storyboard(run, ComfyClient(), Path('skills/director-storyboard/workflows/ltx_director_2.api.json'), dry_run=True); print(len(json.dumps(out['graph'])), 'bytes of graph')"
```

Expected: a byte count printed, no exception.

- [ ] **Step 2: Submit for real with the golden run's images**

Confirm ComfyUI is up (`py -3 skills/director-storyboard/scripts/probe_backends.py`), then run the same command without `dry_run=True`. Note the `prompt_id`.

- [ ] **Step 3: Compare against the Camera Lab original**

Extract the first and last frame of both the new output and the video from the golden Camera Lab run:

```bash
ffmpeg -ss 0 -i <new-output>.mp4 -frames:v 1 -update 1 /tmp/new_first.png
ffmpeg -ss 0 -i <golden-camera-lab>.mp4 -frames:v 1 -update 1 /tmp/old_first.png
```

Expected: both first frames bind to the same keyframe. They will not be pixel-identical (different sampling run), but the composition, wardrobe and framing must match. If the new clip's first frame is a black 512×512 placeholder, the image staging failed — check that `stage_images` returned names and that they appear in the submitted graph's `timeline_data`.

- [ ] **Step 4: Record what you found**

Write the observed `prompt_id`, output path, and any discrepancy into a scratch note; Task 8 folds it into the adapter reference. Do not commit the videos.

---

### Task 8: Write SKILL.md and the reference set

**Files:**
- Create: `skills/director-storyboard/SKILL.md`
- Create: `skills/director-storyboard/references/backend-contract.md`
- Create: `skills/director-storyboard/references/backend-comfyui.md`
- Create: `skills/director-storyboard/references/backend-camera-lab.md`
- Copy: `skills/director-storyboard/references/prompting.md`
- Copy: `skills/director-storyboard/references/storyboard.schema.json`
- Copy: `skills/director-storyboard/references/example_storyboard.json`

**Interfaces:**
- Consumes: the scripts from Tasks 3–6, findings from Task 7.
- Produces: the skill itself.

- [ ] **Step 1: Copy the three unchanged references**

```bash
cp C:/Users/AIBOX/dev/camera-lab/.claude/skills/director-storyboard/references/prompting.md skills/director-storyboard/references/
cp C:/Users/AIBOX/dev/camera-lab/.claude/skills/director-storyboard/references/storyboard.schema.json skills/director-storyboard/references/
cp C:/Users/AIBOX/dev/camera-lab/.claude/skills/director-storyboard/references/example_storyboard.json skills/director-storyboard/references/
```

Then edit `storyboard.schema.json` and change `"$id"` from `camera-lab/director-storyboard` to `ai-video-skills/director-storyboard`.

- [ ] **Step 2: Write `references/backend-contract.md`**

Three operations, matching the shape `slowmo-redraw-repair` already uses:

```markdown
# Backend contract

The skill needs three operations from whatever runs your video model.

## 1. Probe capability

**In:** nothing, or a backend base URL.
**Out:** which cells of the routing table are runnable, and why the rest are not.

Probe before asking the user anything. A question whose answer is already
determined by what is installed is a question not worth asking.

## 2. Submit a generation

**In:** mode (`i2v` / `flf` / `timeline`), keyframe paths, per-segment prompts,
duration, width/height, seed. Timeline mode additionally takes each segment's
`start`, `length` and `strength`.
**Out:** a job id.

## 3. Fetch the result

**In:** a job id. **Out:** a file path plus its real duration.

A client-side timeout is not a failed generation. Check the backend's own job
history and output directory before retrying.

## Adapters

- `backend-comfyui.md` — ComfyUI direct. Needs only ComfyUI.
- `backend-camera-lab.md` — Camera Lab in front of ComfyUI. Preferred when present.
```

- [ ] **Step 3: Write `references/backend-comfyui.md`**

Must contain, at minimum: the probe table (which `object_info` keys light which cell), the note that `LTXDirectorGuide` is fixed at 2 nodes and segment count lives entirely in `timeline_data`, the `segments[]` item shape, the `|` separator trap, the align-to-32 rule, and the staging requirement that images go through `/upload/image` first. Fold in whatever Task 7 turned up.

- [ ] **Step 4: Write `references/backend-camera-lab.md`**

Condense Steps 6 and the resolution section of the old `SKILL.md` (`C:/Users/AIBOX/dev/camera-lab/.claude/skills/director-storyboard/SKILL.md`, lines 113–133 and 258–305): `POST /api/run` with `workflow_id=ltx_director_2`, status at `/api/batches/<batch_id>`, uploads staged under `tasks/camera_lab_uploads/`, and the client-timeout caveat.

- [ ] **Step 5: Write `SKILL.md`**

Start from the old one (`C:/Users/AIBOX/dev/camera-lab/.claude/skills/director-storyboard/SKILL.md`) and make exactly these changes:

1. Frontmatter `name: director-storyboard`; description mentions storyboard analysis, keyframe bridging, and that it runs on ComfyUI with or without Camera Lab.
2. Keep Steps 1–5 (gather inputs, analyze, map beats, write prompts, emit JSON) essentially unchanged — that is the method and it is backend-independent.
3. Replace Step 6 ("Run the workflow") with: probe backends first, pick an adapter, then submit. Point at `scripts/probe_backends.py` and the two adapter references rather than hardcoding Camera Lab.
4. Move the resolution-snapping paragraph (old lines 113–133) into the adapter references; leave a one-line pointer in `SKILL.md`.
5. Delete the "Camera Lab server running" prerequisite; replace with "ComfyUI running, Camera Lab optional".

- [ ] **Step 6: Verify the skill has no stale Camera Lab requirement**

Run:

```bash
grep -rn "camera.lab\|/api/batches\|camera_lab_uploads" skills/director-storyboard/SKILL.md
```

Expected: no matches in `SKILL.md` itself (matches inside `references/backend-camera-lab.md` are correct and expected).

- [ ] **Step 7: Commit**

```bash
git add skills/director-storyboard/
git commit -m "docs: write director-storyboard skill against the backend contract"
```

---

### Task 9: Codex variant, README, and retire the old copies

**Files:**
- Create: `codex/director-storyboard/SKILL.md`
- Create: `codex/director-storyboard/agents/openai.yaml`
- Create: `codex/director-storyboard/references/` (same filenames, condensed)
- Modify: `README.md`
- Delete: the three skill directories in `camera-lab`

- [ ] **Step 1: Write the Codex variant**

Base it on the condensed version already in camera-lab (`C:/Users/AIBOX/dev/camera-lab/.codex/skills/director-storyboard/SKILL.md`, 65 lines) plus the backend-contract change from Task 8. Copy `agents/openai.yaml`'s shape from `codex/slowmo-redraw-repair/agents/openai.yaml`.

- [ ] **Step 2: Verify both variants describe the same method**

Run:

```bash
grep -c "probe\|backend" skills/director-storyboard/SKILL.md codex/director-storyboard/SKILL.md
```

Expected: both non-zero. Read both side by side once and confirm no step exists in one and not the other.

- [ ] **Step 3: Add the skill to README**

In the Skills table, add:

```markdown
| [director-storyboard](skills/director-storyboard/SKILL.md) | Turning a script plus keyframes into a Director timeline — storyboard analysis, keyframe bridging, and running it on ComfyUI with or without Camera Lab |
```

- [ ] **Step 4: Run the full suite one more time**

Run: `py -3 -m pytest -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit this repo**

```bash
git add codex/ README.md
git commit -m "docs: add Codex variant of director-storyboard and list it"
```

- [ ] **Step 6: Retire the old copies in camera-lab**

Only after the end-to-end check in Task 7 passed. In the camera-lab repo:

```bash
git rm -r .codex/skills/director-storyboard .grok/skills/director-storyboard
rm -rf .claude/skills/director-storyboard
git commit -m "chore: move director-storyboard to ai-video-skills"
```

`.claude/` is untracked in camera-lab, hence the plain `rm` for that one.

- [ ] **Step 7: Verify the skill still resolves for the agent**

Junction the new location in (Windows):

```bash
cmd /c mklink /J "C:\Users\AIBOX\dev\camera-lab\.claude\skills\director-storyboard" "C:\Users\AIBOX\dev\ai-video-skills\skills\director-storyboard"
```

Expected: `Junction created`. Confirm the skill loads by invoking `/director-storyboard` in a fresh session.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| 仓库形态 (repo layout) | 1, 8, 9 |
| ComfyUI 直连 adapter — 探测 | 5 |
| ComfyUI 直连 adapter — 提交 (segments array) | 3, 6 |
| ComfyUI 直连 adapter — 取结果 | 4 (`outputs`), 6 |
| ComfyUI adapter 注意事项 (upload, node-id max, autogrow) | 8 step 3 |
| Camera Lab adapter | 8 step 4 |
| 路由表 LTX 列 | 5 (probe), 8 |
| 验证 — probe on three machine types | 5 step 5, 9 |
| 验证 — ComfyUI 直连对比 Camera Lab 首尾帧 | 7 |
| 验证 — 两个变体同步 | 9 step 2 |
| 迁移后删除旧目录 | 9 step 6 |

Deferred to Round 2 by design: routing rules, H3 local, H3 API, cost reporting, `prompting-h3.md`, `run_storyboard.py` unified CLI.

**Not covered and deliberately so:** the spec lists `ltx23_i2v.api.json` and `ltx23_flf.api.json` in the file structure. This round ships only `ltx_director_2.api.json`, because i2v/flf single-shot runs are only reachable through the routing layer, which is Round 2. Round 2's plan must export those two graphs the same way Task 2 exports the Director one.

**Type consistency:** `build_director_inputs(run, image_names, fps)` is defined in Task 3 and called with the same signature in Task 6. `ComfyClient.upload_image` returns `str` in Task 4 and is collected into `dict[int, str]` in Task 6's `stage_images`. `probe_comfyui(object_info)` takes a dict in Task 5 and is called with `client.object_info()` in its own `main`.
