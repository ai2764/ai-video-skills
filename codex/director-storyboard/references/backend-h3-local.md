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

Estimate from **frame count, not screen seconds**, and expect the curve to bend
upward — cost is **superlinear in frames**, so long takes are disproportionately
expensive:

| Frames | Seconds | Wall clock (15 steps) |
|---|---|---|
| 141 | 5.9 | ~7 min |
| 243 | 10.1 | ~16 min |
| 311 | 13.0 | ~26 min |
| 362 | 15.1 | ~38 min |

Doubling the frames roughly quintuples the wait at the top of the range. A shot
near the 15 s ceiling is the worst value on the whole curve — split it, or send
it to the hosted API.

Steps scale as expected: same shot and seed at 175 frames, 30 steps 17.3 min →
**15 steps 9.6 min**. 15 steps is the production setting.

Model loading is nearly free (cold 9.7 min vs warm 9.6), so restarting ComfyUI
between jobs is cheap.

## Acceleration

`ComfyUI-Spectrum-MiniMax-H3` forecasts post-transformer features and skips
selected evaluations. Splice `SpectrumApplyMiniMaxH3` onto the model link
between `MiniMaxH3SigmaShift` and the sampler; author defaults work as shipped.

Measured at 141 frames, same seed and prompt: **15 steps 7 min → 4 min (~1.75×)**,
and 30 steps came in at 7.4 min — i.e. double the steps for what one pass used
to cost. Compatible with pruned int8 weights, no weight swap needed.

Distilled turbo LoRAs go further (4–8 steps) but reportedly at the cost of audio
quality, which matters if the shot carries dialogue or generated sound. Cache- or
block-reuse accelerators trade visible quality for speed; if one is tried, move
its reuse threshold **down** (0.05–0.1) rather than accepting a default.

## First/last frames and references are mutually exclusive

Two different nodes, loading two different sets of UNET weights:

| Node | Takes | Does not take |
|---|---|---|
| `MiniMaxH3ImageToVideo` | `first_frame`, `last_frame` | any reference input |
| `MiniMaxH3ReferenceToVideo` | `ref_images`, `ref_videos`, `ref_audios` | any first/last frame |

So locally you choose **either** pinned framing **or** a locked identity, never
both. Verify on an unfamiliar build rather than assuming:

```bash
py -3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8188/object_info')); [print(n, list((d[n]['input'].get('required') or {})) + list((d[n]['input'].get('optional') or {}))) for n in d if 'MiniMaxH3' in n]"
```

Practical split: a shot whose framing changes (someone entering, a move from one
composition to another) needs first/last frames. A locked-off shot whose framing
can be rebuilt from a prompt can go to references and keep the identity.

## What a reference can and cannot fix

**A reference constrains the angles and expressions it actually contains.**
Supply one neutral front-facing portrait and the model has nothing to draw on
for a profile or a broad laugh; it extrapolates, and extrapolation is where
faces distort. Typical symptoms are exactly that specific: features collapsing
whenever the head turns away, and mouths ballooning on extreme expressions.

This is a **material gap, not a parameter problem** — more steps, a different
seed and acceleration nodes all leave it untouched. Cover the range instead:

- a front portrait for the neutral baseline
- a three-quarter view for anything involving turning
- the extreme expressions the shot actually calls for (a broad smile, a shout)

all matching the wardrobe, hair state and lighting of the scene.

**A reference cannot add detail the framing has no room for.** A character forty
pixels tall in a wide shot gains nothing from a face reference — references are
never upscaled and there are no pixels to carry the detail. If identity must
read, change the shot size.

**Character sheets are usually the wrong source.** Multi-view sheets put the
face at a fraction of the frame, add annotation text, and typically show a
different outfit and hairstyle from any given scene. Crop the hero art out when
it is large and clean; otherwise generate a purpose-made reference.

## Reference images: measured behaviour

`MiniMaxH3ReferenceToVideo` with no first/last frame — composition comes purely
from the refs and the prompt.

**Design sheets are safer than expected.** Eight refs including sheets covered in
Chinese annotation, callout lines, spec tables and threat-rating bars produced a
clean frame: no text, no layout artifacts, and no aircraft even though an
aircraft sheet was among the refs. Telling the model in the prompt to *take
their shapes, materials and colours and ignore their layout* appears to be
enough. Cropping the hero art out of a sheet is still better where it is easy.

**Ref count costs time, roughly linearly.** Same shot, same steps:

| Refs | Frames | Time |
|---|---|---|
| 3 | 192 | 11 min |
| 8 | 243 | 20.5 min |

**A ref cannot add detail the framing has no room for.** A full-body character
ref does nothing for a subject who is forty pixels tall in a wide shot — refs
are never upscaled, and there are no pixels to carry the detail. If identity
must read, change the shot size; no ref will rescue a silhouette.

**Prefer flf when you have two keyframes.** ref2v has to invent the composition;
first/last frames pin it. A corridor shot with both frames given ran in 7.5
minutes with no refs at all and bound both ends exactly.

## Stability

ComfyUI has died after H3 runs. Probe before each submit rather than assuming
the server that accepted the last job is still there.

**A single failed liveness check does not mean the server is down.** Under full
GPU load `/system_stats` can miss a short timeout, and a probe that treats one
miss as "dead" will restart ComfyUI and kill the job that was running. Require
several consecutive failures before concluding anything, and never auto-restart
without first checking the queue is empty.
