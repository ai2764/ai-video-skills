# Adapter: H3 through local ComfyUI

MiniMax H3 open weights running on your own GPU. No per-second cost, but a heavy
stack (~35 GB) and a licence that does not cover everyone.

## Licence: check your jurisdiction

The **MiniMax H3 Community License** (effective 2026-08-02) defines an
`Applicable Territory` that **excludes the United States, the European Union,
the United Kingdom and South Korea**. In those jurisdictions the licence does
not grant the right to use, run, modify, distribute or host the weights — nor to
use the outputs of locally-run weights. Self-hosting there requires separate
authorisation from MiniMax (`model@minimax.io`).

The hosted API is governed by the platform's own terms, a separate document, and
is the route that stays available where this licence does not reach.

**State this when a user picks the local backend. It is their call, not a gate.**

## 1. Probe capability

`GET /object_info` must contain all four nodes:

- `EmptyMiniMaxH3LatentAV`
- `MiniMaxH3ImageToVideo`
- `MiniMaxH3ReferenceToVideo`
- `MiniMaxH3SigmaShift`

**and** `CLIPLoader`'s `type` list must contain `minimax`. Nodes without that
type mean the code is installed and the text-encoder weights are not — report
"weights missing", do not light the cell.

## 2. Submit a generation

### Frame count is a hard constraint

From `comfy_extras/nodes_minimax_h3.py`: `n % 17 == 5`, trained on **124–362
frames** at 24 fps = 5.17–15.08 s. Outside that range you are running the model
outside its training. `frames_for_seconds()` snaps to the nearest valid count and
raises rather than silently clamping.

Note this floor is **higher than the API's**: the API accepts 4 s, local needs
5.17 s.

### Resolution is not constrained

Unlike the API's two fixed rungs, `_empty_av_latent()` uses the given
`height // 16, width // 16` with no normalisation. Any size works.

But **dropping resolution saves less time than you would expect**: 672×384 (a
quarter of the pixels) took 5.9 min against 9.6 min for 1344×768 — only 39% off,
because most of the cost is not spatial (temporal attention, the audio branch,
text encoding, VAE decode).

### Where the parameters live

In the shipped graph, `length`, `prompt`, `width` and `height` are all on the
**`MiniMaxH3ImageToVideo`** node — not on `EmptyMiniMaxH3LatentAV`. Images bind
through that node's own `first_frame` / `last_frame` links; follow the links
rather than guessing which `LoadImage` is which, because the i2v graph drops one
of them.

### First and last frames are treated differently

The first frame is **stretched** (`crop="disabled"`); the last frame is
**centre-cropped to preserve aspect**. A first frame whose aspect does not match
the canvas will be distorted.

## 3. Fetch the result

Same as the ComfyUI adapter: `GET /history/{prompt_id}`, filenames under
`outputs`.

## Cost in time

Same shot, same seed, 175 frames: 30 steps 17.3 min → **15 steps 9.6 min**. 15
steps is the production setting. Estimate from **frame count, not screen
seconds**.

Model loading is nearly free (cold 9.7 min vs warm 9.6), so restarting ComfyUI
between jobs is cheap.

## Stability

ComfyUI has died after H3 runs. Probe before each submit rather than assuming
the server that accepted the last job is still there.
