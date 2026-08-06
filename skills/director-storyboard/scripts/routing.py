"""Which cell of the mode x backend table each segment goes to.

Pure functions: no I/O, and no image analysis. `fast_camera` is set upstream by
the agent after reading the keyframes; this module only consumes the verdict.

    mode \\ backend   LTX          H3 local     H3 API
    i2v              yes          yes          yes
    flf              yes          yes          yes
    timeline         yes          --           --

The two empty cells are permanent. `comfy/ldm/minimax/model.py:317` accepts a
`pixel_index` of only `0` or `frame_count - 1` and raises
`ValueError("only first/last keyframe anchors are supported")` otherwise. H3 has
no director timeline at the model level, and no per-segment prompts, strength or
retake either.
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
    """Rule 1: the number of keyframes picks the row."""
    if keyframe_count <= 1:
        return "i2v"
    if keyframe_count == 2:
        return "flf"
    return "timeline"


def _h3_eligible(duration: float, fast_camera: bool) -> bool:
    """Rules 2 and 3: fast camera wants H3, but H3 cannot do under 4s or over 15s."""
    return bool(fast_camera) and H3_MIN_SECONDS <= duration <= H3_MAX_SECONDS


def route_segment(segment: dict[str, Any], available: dict[str, bool]) -> Cell:
    if not any(available.values()):
        raise ValueError("no backend is available")

    keyframes = segment.get("keyframes") or []
    duration = float(segment.get("duration_s") or 0)
    mode = _mode_for(len(keyframes))

    if _h3_eligible(duration, segment.get("fast_camera")):
        # Rule 4: H3 has no timeline mode. A >=3-keyframe span must already have
        # been split into adjacent pairs upstream by `split_for_h3`, so route the
        # pair-level mode rather than the timeline one.
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
        fast = bool(segment.get("fast_camera"))
        if cell[1] != "ltx":
            reason = "fast camera movement"
        elif fast and duration < H3_MIN_SECONDS:
            reason = f"fast camera but only {duration:g}s — under H3's {H3_MIN_SECONDS}s floor"
        elif fast and duration > H3_MAX_SECONDS:
            reason = f"fast camera but {duration:g}s — over H3's {H3_MAX_SECONDS}s ceiling"
        elif fast:
            reason = "fast camera but no H3 backend available"
        else:
            reason = "no fast camera movement"
        plan.append({
            "index": index,
            "cell": cell,
            "reason": reason,
            "duration_s": duration,
        })
    return plan


def split_for_h3(run: dict[str, Any], indices: list[int]) -> list[dict[str, Any]]:
    """Rule 4: turn a >=3-keyframe segment into adjacent first/last pairs.

    Duration is shared evenly across the pairs, so the total is preserved.
    """
    pairs: list[dict[str, Any]] = []
    segments = run.get("segments") or []
    for index in indices:
        segment = segments[index]
        keyframes = list(segment.get("keyframes") or [])
        if len(keyframes) < 3:
            pairs.append({**segment, "source_index": index})
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
    """Only `h3_api` segments cost money. LTX and local H3 are electricity."""
    if resolution not in PRICE_PER_SECOND:
        raise ValueError(
            f"unknown resolution {resolution!r}; H3 accepts only "
            f"{' or '.join(PRICE_PER_SECOND)}"
        )
    billable = [item for item in plan if tuple(item.get("cell") or (None, None))[1] == "h3_api"]
    seconds = sum(int(round(float(item.get("duration_s") or 0))) for item in billable)
    video_usd = round(seconds * PRICE_PER_SECOND[resolution], 4)
    image_usd = round(max(0, image_count - FREE_IMAGES) * PRICE_PER_EXTRA_IMAGE, 4)
    return {
        "seconds": seconds,
        "video_usd": video_usd,
        "image_usd": image_usd,
        "total_usd": round(video_usd + image_usd, 4),
    }
