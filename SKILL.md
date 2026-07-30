---
name: slowmo-redraw-repair
description: Use when a generated video has mangled, smeared or dissolving structure in fast-motion spans — limbs, weapons or faces falling apart during running, fighting or whip-pan shots — and that span needs regenerating rather than filtering.
---

# Slow-Motion Redraw Repair

## Overview

Fast motion breaks video models: when per-frame displacement is large, the model
never draws coherent structure — hands, weapons and faces come out as semantic
mush. **This is not motion blur.** Deblur/upscale tools cannot recover structure
that was never drawn (verified: FlashVSR and IC-LoRA-MotionDeblur both fail).

**Core principle: make the model redraw the span in slow motion** — small
per-frame displacement, so it has room to draw structure — **then drop frames to
restore the original speed.** Speeding up never reintroduces the mush.

## Language

Use English by default while running this skill — for replies **and** for the
reasoning/thinking process — unless the user asks for another language.

## Diagnose before using

| Symptom | This skill? |
|---|---|
| Limbs/props dissolve into mush in fast frames | ✅ yes |
| True shutter smear on otherwise coherent structure | ❌ use a deblur IC-LoRA |
| Face identity drifts frame to frame | ❌ needs a reference-image v2v pass |
| Whole video merely soft / low-res | ❌ use an upscaler |

## What the backend must provide

Everything below is backend-agnostic except three operations. Read
`references/backend-contract.md` for the contract, then the adapter for your
stack (`references/backend-camera-lab.md` ships with this skill).

1. **Read a job** — given a job id, return the source video, its prompts, and
   the anchor times with their guide images.
2. **Run first-last-frame generation** — given a start image, an end image, a
   duration and a prompt, return a clip that begins on the first and lands on
   the last.
3. **Fetch the result** — a file path plus its real duration.

Steps 2, 6 and the analysis in step 4 are pure `ffmpeg`/`ffprobe` and need no
backend.

## Step 0 — Ask before anything else

**Do not extract frames before settling the redraw question.**

1. **Check your own tool list for an image-generation tool.** Do not self-assess
   in the abstract — either such a tool is available or it is not.
2. If unavailable: say so, extract frames, hand them to the user.
3. If available: ask the user whether you should redraw, or they will.
4. If you will redraw: locate the character/scene reference sheets (character
   design sheets / model sheets).
   **If you cannot find them, ask the user for them — never redraw without them.**

## Step 1 — Read the source job

Accept **either** a generation-backend job id **or** a batch/run id the backend
understands — whichever the user has to hand. Both are valid entry points.

Obtain: workflow type, global prompt, per-segment prompts, anchor frames and
their guide images, seed, width/height, fps.

## Step 2 — Pick the span and extract frames

Damage concentrates **away from anchors** (measured: anchor frames avg blur 5.12,
segment midpoints 5.66). Quantify with ffmpeg's `blurdetect` — higher = blurrier:

```bash
ffmpeg -i in.mp4 -vf "blurdetect=block_pct=80,metadata=print:key=lavfi.blur" -f null -
```

Windowing:

- **Multi-anchor job (Director-style)** — one window per gap between original
  anchors. If N exceeds the number of gaps, subdivide each gap evenly.
- **Single-anchor job (i2v-style)** — split the span evenly by duration.

Frame count N defaults to `ceil(span_seconds / 1.5)`; an explicit user N wins.
Never compare blur across shots with an absolute threshold — the level drifts
through a video. Use the segment's own guide image as the per-shot baseline.

**Blur peak locates the damage; it does not choose the anchor.** Frames filled
with dust, debris or smoke score highest and are useless to redraw — there is no
structure to repair. Inside each window pick a frame that is both damaged **and
legible as a story beat**: a clear silhouette, a readable pose, ideally against
sky or a clean background. When the two disagree, legibility wins.

Name frames `redraw_NN_t<seconds>s.png` so the timestamp survives the round trip.

## Step 3 — Redraw

**Hard requirement: preserve composition.** Start from the extracted frame and
repair it against the reference sheets — same framing, camera angle, pose, prop
placement, background. Only the broken structure gets rebuilt.

A redraw that reimagines the shot is worse than no redraw: the model then tears
between the video's motion and the image's composition. Generic img2img at high
denoise does **not** preserve composition; verify before trusting it.

The redraw need not be sharper than the guide image — it only needs coherent
structure.

## Step 4 — Build the FLF chain

Anchors = `[span start] + N redraws + [span end]`, chained pairwise into **N+1
first-last-frame jobs**, each covering one adjacent pair.

End anchors depend on the source job:

| Source job | Span start | Span end |
|---|---|---|
| Multi-anchor | the guide image at/nearest that frame | the guide image at/nearest that frame |
| Single-anchor | its source image (if span starts at 0), else extract | extract from video |

Using real frames/guides at both ends is what lets the result splice back into
the untouched footage. Check the extracted boundary frames with `blurdetect` too
— **a damaged boundary frame poisons the whole chain**; redraw it as well.

Pick a slow factor **per pair**, by that pair's action complexity:

| Action in the pair | Factor |
|---|---|
| Single slow beat — head turn, raise arm, walk | 3× |
| Displacement plus one action — running, repositioning | 5× |
| Compound motion — backpedal + turn + fire + handheld shake | 6–8× |

Then apply a floor so short pairs still get a usable clip:

```
factor  = max(complexity_factor, 3.0 / story_span)
request = story_span × factor          # keep every job within the backend's safe length
```

Without the floor a 0.2 s pair asks for a 1.6 s clip, too short for the two
anchors to breathe.

**When two anchors differ sharply in shot scale or camera position, write the
camera move into the prompt** — "pushes rapidly in to a tight close-up", "cranes
back out to a wide", "arcs 180 degrees around her". Left unsaid, the model either
hard-cuts or warps. Said explicitly, the scale change reads as deliberate
camerawork. This also turns a wide→close-up pair into a usable transition instead
of a mismatch.

## Step 5 — Run and verify

Before submitting: confirm every anchor file exists on disk.

Submit one job per pair. If the backend can run them concurrently, verify it
isolates each job's staged inputs — see the adapter's notes.

## Step 6 — Restore speed and stitch

**Measure the real output length — never assume the requested duration.**
Backends overshoot (9.5 s requested → 10.77 s delivered).

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 clip.mp4
```

Per clip: `factor = actual_duration / story_span`, then

```bash
ffmpeg -i clip.mp4 -vf "setpts=PTS/<factor>" -r <fps> -c:v libx264 -crf 14 out.mp4
```

Speed each clip by **its own** factor before concatenating — factors differ per
pair. Then concat, and inspect every seam (a frame either side).

**Short clips round up to whole frames, so the concat overshoots the target.**
Measure the concatenated length and apply one global correction:

```bash
ffmpeg -i concat.mp4 -vf "setpts=PTS/<concat_len ÷ target_len>" -r <fps> ... final.mp4
```

Speeding up is a free, repeatable post step: if the restored result reads too
fast or too slow, re-render at another factor instead of regenerating.

Slow-motion generation is a lottery. When a take disappoints, **re-run the chain
on a new seed** rather than rewriting prompts — and note that beats adjacent to
an anchor barely vary between seeds, so only the mid-pair material is actually
being re-rolled.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Speed factor from requested duration | Residual slow motion; once left 1.6× slow undetected |
| Speed factor from clip length ÷ target length | Same error — divide by the **story span** the anchors cover |
| Speeding up footage that was generated at normal speed | Unnatural fast-forward; only slow-motion output gets sped up |
| Anchoring on the blur peak without looking at it | Dust-and-debris frames win on score and cannot be redrawn |
| Redraw that changes composition | Model tears between video motion and image framing |
| Too few slow — 2× or less | Reads frantic after restore; beats have no room |
| Silent shot-scale jump between anchors | Model hard-cuts or warps instead of moving the camera |
| Trusting a parameter change without verifying it reached the backend | Whole comparison round is void |
| Treating a client-side timeout as a failed generation | The clip often exists; check the backend's own history and output dir |
