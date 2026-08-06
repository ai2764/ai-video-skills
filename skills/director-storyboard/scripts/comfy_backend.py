"""Fill the Director graph and run it straight against ComfyUI.

This is the adapter that makes Camera Lab optional: everything Camera Lab's
server does for a Director run that actually matters to the graph is (a) stage
the guide images into ComfyUI's input dir and (b) write the LTXDirector inputs.
Both are here.
"""

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
    timeline: dict[str, Any],
    image_names: dict[int, str],
    width: int,
    height: int,
    ic_lora_name: str = "None",
    ic_lora_strength: float = 1.0,
) -> dict[str, Any]:
    """Return a copy of `graph` with the LTXDirector node filled in.

    `.update()` rather than assignment: the node's `model` / `clip` /
    `audio_vae` inputs are links to other nodes and must survive untouched.
    """
    filled = copy.deepcopy(graph)
    director = next(
        (node for node in filled.values() if node.get("class_type") == "LTXDirector"),
        None,
    )
    if director is None:
        raise RuntimeError("workflow does not contain an LTXDirector node")
    director.setdefault("inputs", {}).update(
        build_director_inputs(timeline, image_names, width, height)
    )

    strength = max(0.0, min(2.0, float(ic_lora_strength)))
    for node in filled.values():
        if node.get("class_type") == "LTXDirectorGuide":
            node.setdefault("inputs", {})["ic_lora_name"] = str(ic_lora_name)
            node["inputs"]["ic_lora_strength"] = strength
    return filled


def fill_missing_required(
    graph: dict[str, Any],
    object_info: dict[str, Any],
) -> list[str]:
    """Add required widget inputs the export dropped, using their declared defaults.

    Converting a UI workflow to API format maps positional `widgets_values`
    onto named inputs. Dynamic widget types (`COMFY_DYNAMICCOMBO_V3` and
    friends) do not always survive that mapping, and the graph then fails
    validation with `Required input is missing <name>` at submit time. Anything
    with a declared default can simply be restored.

    Mutates `graph`. Returns a list of `node/input` strings describing what was
    added, so a caller can report it rather than silently patching.
    """
    added: list[str] = []
    for node_id, node in graph.items():
        spec = object_info.get(str(node.get("class_type"))) or {}
        required = ((spec.get("input") or {}).get("required")) or {}
        inputs = node.setdefault("inputs", {})
        for name, declaration in required.items():
            if name in inputs:
                continue
            if not (isinstance(declaration, list) and len(declaration) > 1):
                continue
            spec = declaration[1]
            if not isinstance(spec, dict):
                continue
            if "default" in spec:
                value = spec["default"]
            elif spec.get("options"):
                # Plain COMBO lists strings; COMFY_DYNAMICCOMBO_V3 lists dicts
                # keyed by "key" and carries no default at all. First option is
                # what the UI would show.
                first = spec["options"][0]
                value = first.get("key") if isinstance(first, dict) else first
            else:
                continue
            inputs[name] = value
            added.append(f"{node_id}({node.get('class_type')}).{name}")
    return added


def stage_images(client: ComfyClient, timeline: dict[str, Any]) -> dict[int, str]:
    """Upload each segment's guide image, keyed by 1-based segment index."""
    names: dict[int, str] = {}
    for index, segment in enumerate(timeline.get("segments") or [], start=1):
        if str(segment.get("type") or "image") == "text":
            continue
        raw = segment.get("image_path")
        if not raw:
            continue
        path = Path(str(raw))
        if not path.exists():
            raise FileNotFoundError(f"segment {index} guide image is missing: {path}")
        names[index] = client.upload_image(path)
    return names


def run_director(
    timeline: dict[str, Any],
    client: ComfyClient,
    graph_path: Path,
    width: int,
    height: int,
    dry_run: bool = False,
    poll_seconds: float = 5.0,
    timeout_seconds: float = 3600.0,
) -> dict[str, Any]:
    graph = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    if dry_run:
        return {
            "dry_run": True,
            "graph": fill_director_graph(graph, timeline, {}, width, height),
        }

    image_names = stage_images(client, timeline)
    filled = fill_director_graph(graph, timeline, image_names, width, height)
    restored = fill_missing_required(filled, client.object_info())
    if restored:
        print(f"restored {len(restored)} dropped widget default(s): {', '.join(restored)}")
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
        "note": (
            f"still running; check /history/{prompt_id} and ComfyUI's output dir "
            "before resubmitting"
        ),
    }
