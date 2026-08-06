"""H3 through a local ComfyUI.

The frame count is a hard constraint out of `comfy_extras/nodes_minimax_h3.py`,
not a preference: `n % 17 == 5`, trained on 124-362 frames at 24 fps. Asking for
anything outside that range runs the model outside what it was trained on.

Unlike the API, resolution here is unconstrained -- `_empty_av_latent()` uses the
given `height // 16, width // 16` with no normalisation.

Licensing: the H3 Community License excludes the US, EU, UK and South Korea from
its Applicable Territory for locally run weights. Say so when a user picks this
backend; it is their call, not a gate.
"""

from __future__ import annotations

import copy
from typing import Any

FPS = 24
FRAME_MODULO = 17
FRAME_REMAINDER = 5
FRAME_MIN = 124
FRAME_MAX = 362

H3_NODE = "MiniMaxH3ImageToVideo"


def frames_for_seconds(seconds: float) -> int:
    """Nearest valid H3 frame count to `seconds` at 24 fps."""
    target = float(seconds) * FPS
    steps = round((target - FRAME_REMAINDER) / FRAME_MODULO)
    frames = int(steps * FRAME_MODULO + FRAME_REMAINDER)
    if frames < FRAME_MIN:
        raise ValueError(
            f"{seconds:g}s is {frames} frames, below H3's trained floor of "
            f"{FRAME_MIN} ({FRAME_MIN / FPS:.2f}s)"
        )
    if frames > FRAME_MAX:
        raise ValueError(
            f"{seconds:g}s is {frames} frames, above H3's trained ceiling of "
            f"{FRAME_MAX} ({FRAME_MAX / FPS:.2f}s)"
        )
    return frames


def fill_h3_graph(
    graph: dict[str, Any],
    shot: dict[str, Any],
    image_names: list[str],
    frames: int,
    seed: int,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Return a copy of `graph` set up for one shot.

    `image_names` is positional: first frame, then last frame. The i2v graph has
    no `last_frame` input, so a second name is simply unused there.

    Nothing writes a negative prompt: H3 has no negative conditioning, and the
    graph keeps a `ConditioningZeroOut` placeholder with `cfg=1.0` instead.
    """
    if len(image_names) > 2:
        raise ValueError("H3 takes at most two images: a first and a last frame")

    filled = copy.deepcopy(graph)
    h3_id = next(
        (nid for nid, node in filled.items() if node.get("class_type") == H3_NODE),
        None,
    )
    if h3_id is None:
        raise RuntimeError(f"workflow does not contain a {H3_NODE} node")

    h3_inputs = filled[h3_id].setdefault("inputs", {})
    h3_inputs["prompt"] = str(shot.get("prompt") or "")
    h3_inputs["length"] = int(frames)
    if width is not None:
        h3_inputs["width"] = int(width)
    if height is not None:
        h3_inputs["height"] = int(height)

    for node in filled.values():
        if node.get("class_type") == "KSampler":
            node.setdefault("inputs", {})["seed"] = int(seed)

    # Bind images through the H3 node's own links rather than by guessing which
    # LoadImage is which -- the i2v graph drops one of them.
    for role, name in zip(("first_frame", "last_frame"), image_names):
        link = h3_inputs.get(role)
        if not (isinstance(link, list) and link):
            continue
        loader = filled.get(str(link[0]))
        if loader is not None:
            loader.setdefault("inputs", {})["image"] = name
    return filled
