#!/usr/bin/env python3
"""Report which cells of the routing table this machine can actually run.

Probe before asking the user anything. A question whose answer is already
determined by what is installed is a question not worth asking.
"""

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
    required = (node.get("input") or {}).get("required") or {}
    entry = required.get("type")
    if isinstance(entry, list) and entry and isinstance(entry[0], list):
        return [str(item) for item in entry[0]]
    return []


def probe_comfyui(object_info: dict[str, Any]) -> dict[str, Any]:
    reasons: dict[str, str] = {}

    timeline = "LTXDirector" in object_info
    if not timeline:
        reasons["timeline"] = "LTXDirector node not installed"
        reasons["i2v"] = reasons["flf"] = "no LTX nodes found"

    missing_h3 = [name for name in H3_NODES if name not in object_info]
    if missing_h3:
        h3_local = False
        reasons["h3_local"] = "missing nodes: " + ", ".join(missing_h3)
    elif "minimax" not in _clip_loader_types(object_info):
        h3_local = False
        reasons["h3_local"] = (
            "H3 nodes present but CLIPLoader offers no 'minimax' type "
            "— the text encoder weights are not installed"
        )
    else:
        h3_local = True

    return {
        "timeline": timeline,
        "i2v": timeline,
        "flf": timeline,
        "h3_local": h3_local,
        "reasons": reasons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfy-url", default=os.environ.get("COMFY_URL", DEFAULT_BASE_URL))
    args = parser.parse_args(argv)

    client = ComfyClient(args.comfy_url)
    if not client.alive():
        print(json.dumps(
            {"comfyui": False, "reason": f"no response from {args.comfy_url}"},
            indent=2,
        ))
        return 1
    result = probe_comfyui(client.object_info())
    result["comfyui"] = True
    result["h3_api"] = bool(os.environ.get("MINIMAX_API_KEY"))
    if not result["h3_api"]:
        result["reasons"]["h3_api"] = "MINIMAX_API_KEY is not set"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
