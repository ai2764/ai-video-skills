#!/usr/bin/env python3
"""Route a storyboard across LTX / H3-local / H3-API and run it.

    py -3 run_storyboard.py storyboard.json --dry-run
    py -3 run_storyboard.py storyboard.json --h3-backend api --yes

Probe first, route second, report cost, submit last. Nothing is submitted to a
paid backend without an explicit --yes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from comfy_client import DEFAULT_BASE_URL, ComfyClient
from probe_backends import probe_comfyui
from routing import estimate_cost, route_storyboard

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"

LICENCE_NOTE = (
    "Note: the MiniMax H3 Community License excludes the US, EU, UK and South "
    "Korea from its Applicable Territory for locally run weights. The hosted "
    "API is governed separately."
)


def detect_available(comfy_url: str, h3_backend: str) -> tuple[dict[str, bool], dict[str, str]]:
    client = ComfyClient(comfy_url)
    probed: dict[str, Any] = {}
    if client.alive():
        probed = probe_comfyui(client.object_info())
    reasons: dict[str, str] = dict(probed.get("reasons") or {})
    if not probed:
        reasons["comfyui"] = f"no response from {comfy_url}"

    available = {
        "ltx": bool(probed.get("timeline")),
        "h3_local": bool(probed.get("h3_local")),
        "h3_api": bool(os.environ.get("MINIMAX_API_KEY")),
    }
    if not available["h3_api"]:
        reasons["h3_api"] = "MINIMAX_API_KEY is not set"

    # An explicit choice narrows what routing may pick.
    if h3_backend == "api":
        available["h3_local"] = False
    elif h3_backend == "local":
        available["h3_api"] = False
    return available, reasons


def routing_view(storyboard: dict[str, Any]) -> dict[str, Any]:
    """Storyboard segments as routing sees them.

    A Director segment carries one guide image. An H3 pair needs two, so a
    segment's last frame is the *next* segment's guide. The final segment has no
    successor and is therefore i2v.
    """
    segments = storyboard.get("segments") or []
    view = []
    for index, segment in enumerate(segments):
        image = segment.get("image") or segment.get("image_path") or ""
        keyframes = [image] if image else []
        following = segments[index + 1] if index + 1 < len(segments) else None
        if following:
            nxt = following.get("image") or following.get("image_path") or ""
            if nxt:
                keyframes.append(nxt)
        view.append({
            "keyframes": keyframes,
            "duration_s": float(segment.get("duration") or segment.get("length_seconds") or 0),
            "fast_camera": bool(segment.get("fast_camera")),
            "prompt": segment.get("prompt") or segment.get("local_prompt") or "",
        })
    return {"segments": view}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storyboard", type=Path)
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--h3-backend",
        choices=("ask", "local", "api"),
        default="ask",
        help="'ask' stops and asks when both H3 backends are available",
    )
    parser.add_argument("--resolution", choices=("768P", "2K"), default="768P")
    parser.add_argument("--keep-audio", action="store_true", help="keep H3's native audio track")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args(argv)

    storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
    available, reasons = detect_available(args.comfy_url, args.h3_backend)

    if not any(available.values()):
        print("No backend available:", file=sys.stderr)
        for name, why in reasons.items():
            print(f"  {name}: {why}", file=sys.stderr)
        print("\nThe storyboard is still valid — start ComfyUI or set MINIMAX_API_KEY.",
              file=sys.stderr)
        return 1

    if args.h3_backend == "ask" and available["h3_local"] and available["h3_api"]:
        print("Both H3 backends are available. Re-run with --h3-backend local or "
              "--h3-backend api.", file=sys.stderr)
        print(LICENCE_NOTE, file=sys.stderr)
        return 2

    view = routing_view(storyboard)
    plan = route_storyboard(view, available)
    image_count = sum(1 for s in storyboard.get("segments") or []
                      if s.get("image") or s.get("image_path"))
    cost = estimate_cost(plan, args.resolution, image_count)

    print(f"storyboard: {args.storyboard}")
    for item in plan:
        mode, backend = item["cell"]
        print(f"  segment {item['index'] + 1}: {mode}/{backend}"
              f"  {item['duration_s']:g}s  ({item['reason']})")
    if cost["total_usd"] > 0:
        print(f"\nH3 API billable: {cost['seconds']}s at {args.resolution} "
              f"= ${cost['total_usd']:.2f}")
    else:
        print("\nNothing routes to a paid backend.")

    if args.dry_run:
        return 0
    if cost["total_usd"] > 0 and not args.yes:
        print("\nRe-run with --yes to submit.", file=sys.stderr)
        return 3

    return submit(storyboard, plan, args)


def submit(storyboard: dict[str, Any], plan: list[dict[str, Any]], args: Any) -> int:
    from director_timeline import storyboard_to_timeline

    segments = storyboard.get("segments") or []
    outputs: list[str] = []

    ltx_indices = [item["index"] for item in plan if item["cell"][1] == "ltx"]
    if ltx_indices:
        from comfy_backend import run_director

        # The Director timeline is one job covering its whole span; H3 segments
        # are separate jobs cut in afterwards.
        timeline = storyboard_to_timeline(storyboard)
        result = run_director(
            timeline,
            ComfyClient(args.comfy_url),
            WORKFLOWS / "ltx_director_2.api.json",
            width=int(storyboard.get("width") or 1280),
            height=int(storyboard.get("height") or 704),
        )
        outputs.extend(result.get("outputs") or [])
        if result.get("note"):
            print(result["note"], file=sys.stderr)

    for item in plan:
        mode, backend = item["cell"]
        if backend == "ltx":
            continue
        segment = segments[item["index"]]
        keyframes = [
            k for k in (
                segment.get("image") or segment.get("image_path") or "",
                (segments[item["index"] + 1].get("image")
                 if item["index"] + 1 < len(segments) else "") or "",
            ) if k
        ][: 2 if mode == "flf" else 1]

        if backend == "h3_api":
            from h3_api import H3ApiClient, build_request, strip_audio

            client = H3ApiClient()
            request = build_request(
                {
                    "keyframes": keyframes,
                    "duration_s": item["duration_s"],
                    "prompt": segment.get("prompt") or "",
                },
                resolution=args.resolution,
            )
            task_id = client.create(request)
            print(f"  segment {item['index'] + 1}: H3 task {task_id}")
            result = client.poll(task_id)
            dest = args.storyboard.parent / "out" / f"segment_{item['index'] + 1:02d}.mp4"
            path = client.download(result["url"], dest)
            if not args.keep_audio:
                path = strip_audio(path)
            outputs.append(str(path))
        else:
            from h3_local import fill_h3_graph, frames_for_seconds

            comfy = ComfyClient(args.comfy_url)
            graph_name = "h3_flf.api.json" if mode == "flf" else "h3_i2v.api.json"
            graph = json.loads((WORKFLOWS / graph_name).read_text(encoding="utf-8"))
            names = [comfy.upload_image(Path(k)) for k in keyframes]
            filled = fill_h3_graph(
                graph,
                segment,
                names,
                frames_for_seconds(item["duration_s"]),
                int(storyboard.get("seed") or 0),
            )
            outputs.append(comfy.submit(filled))

    print("\nOutputs:")
    for name in outputs:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
