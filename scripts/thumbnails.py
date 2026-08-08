#!/usr/bin/env python3
"""Downscale keyframes before the agent reads them.

A full-resolution keyframe read costs roughly 1.5k tokens and stays in context
for the rest of the session. Reading a 512px thumbnail instead costs a fraction
of that and loses nothing storyboard decisions actually turn on -- composition,
blocking, shot scale, wardrobe, palette. Open an original only when a decision
depends on fine detail the thumbnail cannot settle: legible on-screen text, a
facial micro-expression, a small prop.

`pair_sheet` puts two adjacent keyframes side by side in one image, so judging
the camera move between them costs one read instead of two.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

LONG_EDGE_DEFAULT = 512
CONTACT_LONG_EDGE_DEFAULT = 320


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def _require(path: Path) -> Path:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"keyframe does not exist: {path}")
    return path


def _probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip().rstrip(",")
    width, height = (int(value) for value in out.split(",")[:2])
    return width, height


def _cell_size(source: Path, long_edge: int) -> tuple[int, int]:
    """A fixed cell matching the source's aspect, both sides even."""
    width, height = _probe_size(source)
    if width >= height:
        cell_w = long_edge
        cell_h = max(2, round(long_edge * height / width))
    else:
        cell_h = long_edge
        cell_w = max(2, round(long_edge * width / height))
    return cell_w - cell_w % 2, cell_h - cell_h % 2


def _fit(cell_w: int, cell_h: int) -> str:
    """Scale into the cell without distorting, then pad out to fill it.

    Uniform cells are what keeps hstack/xstack from failing when the inputs
    are not all the same shape.
    """
    return (
        f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
        f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def thumbnail(src: Path, dest_dir: Path, long_edge: int = LONG_EDGE_DEFAULT) -> Path:
    src = _require(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{src.stem}_thumb.png"
    scale = (
        f"scale='if(gt(iw,ih),{long_edge},-2)':'if(gt(iw,ih),-2,{long_edge})'"
    )
    _run(["ffmpeg", "-y", "-i", str(src), "-vf", scale, "-frames:v", "1", str(out)])
    return out


def pair_sheet(
    first: Path,
    second: Path,
    dest_dir: Path,
    long_edge: int = LONG_EDGE_DEFAULT,
) -> Path:
    first, second = _require(first), _require(second)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{first.stem}__{second.stem}_pair.png"
    cell_w, cell_h = _cell_size(first, long_edge)
    fit = _fit(cell_w, cell_h)
    _run([
        "ffmpeg", "-y", "-i", str(first), "-i", str(second),
        "-filter_complex", f"[0:v]{fit}[a];[1:v]{fit}[b];[a][b]hstack=inputs=2",
        "-frames:v", "1", str(out),
    ])
    return out


def contact_sheet(
    paths: list[Path],
    dest_dir: Path,
    columns: int = 4,
    long_edge: int = CONTACT_LONG_EDGE_DEFAULT,
) -> Path:
    paths = [_require(path) for path in paths]
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "contact_sheet.png"
    cell_w, cell_h = _cell_size(paths[0], long_edge)
    fit = _fit(cell_w, cell_h)

    inputs: list[str] = []
    for path in paths:
        inputs += ["-i", str(path)]

    count = len(paths)
    if count == 1:
        _run(["ffmpeg", "-y", *inputs, "-vf", fit, "-frames:v", "1", str(out)])
        return out

    chains = "".join(f"[{i}:v]{fit}[s{i}];" for i in range(count))
    labels = "".join(f"[s{i}]" for i in range(count))
    layout = "|".join(
        f"{(index % columns) * cell_w}_{(index // columns) * cell_h}"
        for index in range(count)
    )
    filtergraph = f"{chains}{labels}xstack=inputs={count}:layout={layout}:fill=black"
    _run(["ffmpeg", "-y", *inputs, "-filter_complex", filtergraph, "-frames:v", "1", str(out)])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--long-edge", type=int, default=LONG_EDGE_DEFAULT)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument(
        "--mode",
        choices=("thumbs", "pairs", "contact"),
        default="thumbs",
        help="pairs makes one side-by-side sheet per adjacent pair",
    )
    args = parser.parse_args(argv)

    if args.mode == "thumbs":
        made = [thumbnail(path, args.dest, args.long_edge) for path in args.images]
    elif args.mode == "pairs":
        if len(args.images) < 2:
            parser.error("--mode pairs needs at least two images")
        made = [
            pair_sheet(a, b, args.dest, args.long_edge)
            for a, b in zip(args.images, args.images[1:])
        ]
    else:
        made = [contact_sheet(args.images, args.dest, args.columns, args.long_edge)]

    for path in made:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
