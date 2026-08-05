"""Director timeline -> LTXDirector node inputs.

Pure data transformation, no I/O. Mirrors camera-lab's
`build_ltx_director_v2_api` (server/camera_lab_server.py:1300) closely enough
that both backends produce the same graph; the golden fixture test is what
holds that claim up.

The input is a *director timeline* dict -- the normalised structure Camera Lab
writes to `director_timeline.json` -- not a raw run payload. The timeline
already carries frame counts (`segments[i]["frames"]`), the joined
`local_prompts` and `segment_lengths` strings, and the totals. Recomputing
those from a run payload is how the two backends drift apart, so don't.
"""

from __future__ import annotations

import json
from typing import Any

DIVISIBLE_BY = 32
IMG_COMPRESSION = 18


def align_dimension(value: int) -> int:
    """Camera Lab halves each dimension, aligns to 32, doubles back.

    Note this is applied *upstream* of the timeline -- by the time a run has a
    width, it is already aligned. `build_director_inputs` passes width and
    height through untouched. This helper is here for callers that need to
    align a raw request before building a run.
    """
    half = int(value) // 2
    aligned = max(DIVISIBLE_BY, round(half / DIVISIBLE_BY) * DIVISIBLE_BY)
    return aligned * 2


def build_segments(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    """One entry per timeline segment, without guide images attached yet."""
    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(timeline.get("segments") or [], start=1):
        seg_type = str(segment.get("type") or "image")
        start_frame = segment.get("guide_frame", segment.get("start_frame", 0))
        segments.append({
            "id": segment.get("id") or f"camera-lab-segment-{index}",
            "type": seg_type,
            "label": f"segment {index}",
            "start": max(0, int(start_frame)),
            "length": int(segment["frames"]),
            "prompt": segment.get("prompt") or "",
        })
    return segments


def attach_images(
    segments: list[dict[str, Any]],
    timeline: dict[str, Any],
    image_names: dict[int, str],
) -> list[dict[str, Any]]:
    """Bind each staged image to its segment, keyed by 1-based segment index."""
    raw = timeline.get("segments") or []
    for index, item in enumerate(segments, start=1):
        if item["type"] == "text" or index not in image_names:
            continue
        item["type"] = "image"
        item["imageFile"] = image_names[index]
        strength = raw[index - 1].get("strength")
        item["strength"] = 1.0 if strength in {None, ""} else float(strength)
    return segments


def build_director_inputs(
    timeline: dict[str, Any],
    image_names: dict[int, str],
    width: int,
    height: int,
) -> dict[str, Any]:
    """The inputs mapping to write onto the LTXDirector node.

    `width`/`height` are passed through as given -- they are already aligned by
    the time a timeline exists.
    """
    segments = attach_images(build_segments(timeline), timeline, image_names)
    audio_segments = list(timeline.get("audio_segments") or [])
    duration_frames = int(timeline["duration_frames"])
    duration_seconds = float(timeline["duration_seconds"])

    timeline_data: dict[str, Any] = {"segments": segments, "audioSegments": audio_segments}
    motion_segments = timeline.get("motion_segments") or []
    if motion_segments:
        timeline_data["motionSegments"] = motion_segments

    return {
        "global_prompt": timeline.get("global_prompt") or "",
        "start_second": 0,
        "end_second": duration_seconds,
        "duration_frames": duration_frames,
        "duration_seconds": duration_seconds,
        "start_frame": 0,
        "end_frame": duration_frames,
        "timeline_data": json.dumps(timeline_data, ensure_ascii=False),
        "overrideAudio": False,
        "inpaint_audio": bool(timeline.get("inpaint_audio", True)),
        "use_custom_audio": bool(audio_segments) or bool(timeline.get("retake_mode")),
        # Joined forms come straight from the timeline; rebuilding them is how
        # the two backends drift apart.
        "local_prompts": timeline.get("local_prompts") or "",
        "segment_lengths": timeline.get("segment_lengths") or "",
        "guide_strength": ",".join(
            str(item["strength"])
            for item in segments
            if item.get("type") != "text" and "strength" in item
        ),
        "frame_rate": int(timeline.get("fps") or 24),
        "custom_width": int(width),
        "custom_height": int(height),
        "display_mode": "seconds",
        "resize_method": "maintain aspect ratio",
        "divisible_by": DIVISIBLE_BY,
        "img_compression": IMG_COMPRESSION,
    }
