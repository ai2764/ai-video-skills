---
name: director-storyboard
description: Turn scripts and ordered or unordered keyframes into LTX Director 2 timeline prompts, storyboard JSON, and optional runs. Runs on ComfyUI alone; uses Camera Lab when present. Use for 分镜, storyboard analysis, keyframe bridging, Director variants, extensions, retakes, or $director-storyboard.
---

# Director Storyboard

Build one Director timeline from a plot and visual targets. Do not treat the
result as stitched independent I2V clips.

The generation backend is pluggable — see `references/backend-contract.md`.
ComfyUI on its own is enough.

## Workflow

1. Collect the plot, images, target duration, resolution, seed, and whether to
   write only or also run.
2. Inspect and order the images by story and visual continuity. State the order
   when it was inferred.
3. Decide whether the timeline is continuous or uses motivated cuts.
4. Map one dominant beat to each segment and describe the bridge into the next
   keyframe.
5. Write storyboard JSON under `tasks/`, validate it, and recheck every input
   path immediately before submission.
6. When requested, probe backends, pick an adapter, submit, and report the job
   id and the verified output path.

## Read images cheaply

**Always read thumbnails, never the originals.** Before opening any keyframe:

```bash
py -3 scripts/thumbnails.py <images...> --dest <tmp>/thumbs
```

A 512px thumbnail carries composition, blocking, shot scale, wardrobe and
palette — everything storyboard decisions turn on. Open an original only for
fine detail a thumbnail cannot settle: legible on-screen text, a facial
micro-expression, a small prop.

To compare two adjacent keyframes, make one side-by-side sheet rather than
opening both — this is also how you judge the camera move between them:

```bash
py -3 scripts/thumbnails.py a.png b.png --dest <tmp>/pairs --mode pairs
```

Cheap reads are not free reads. Mine descriptive filenames first, open style
anchors (1–3 frames) plus any frame whose filename is ambiguous in a way that
changes the prompt, and derive the rest. Say which frames you skipped and what
you assumed about them.

## Prompt contract

- Global prompt: persistent identity, wardrobe, location, lighting, visual
  style, camera progression, and continuity.
- Local prompt: positive present-tense action in this order when useful:
  **shot scale → subject action → camera motion → environmental motion →
  landing state**.
- Keep one dominant beat per segment. Use dialogue in quotation marks.
- Put prohibitions in `negative_prompt`, not as `No ...` instructions inside
  local prompts.
- Treat images as visual targets. Explicitly write the motion between targets.
- Add visible movement to every segment; do not lower guide strength merely to
  fix a slideshow result.
- Default image strength: `0.78–0.85`. Allow roughly 1.5–2.5 seconds for a
  micro-action, 2.5–4 seconds for a gesture or short walk, and 4–6 seconds for
  a major pose plus camera transition.
- **Never put `|` in a prompt.** LTXDirector splits local prompts on it.

## Running

Probe before asking the user anything:

```bash
py -3 scripts/probe_backends.py
```

It reports which modes are runnable and why the rest are not. Then read the
adapter for whatever is available — Camera Lab when reachable (its staging and
audio handling are already tuned), otherwise ComfyUI direct.

A client-side timeout is not a failed generation. Check the backend's own job
history and output directory before resubmitting.

## Load only what the task needs

- `references/prompting.md` when composing, comparing, or repairing prompts,
  timing, strengths, or anti-slideshow motion.
- `references/backend-contract.md` before touching any backend.
- `references/backend-comfyui.md` or `references/backend-camera-lab.md` for the
  stack actually present.
- `references/storyboard.schema.json` only when writing or validating JSON.
- `references/example_storyboard.json` only when no existing storyboard
  provides a usable structure.

Do not load all references by default.

## Required safeguards

- Keep identity, wardrobe, geography, lighting, and object design consistent
  unless the script deliberately changes them.
- Ensure the negative prompt does not forbid a required event.
- Give complex actions enough time and avoid multi-event monologues in short
  segments.
- Never invent ComfyUI paths or claim generation succeeded without API
  confirmation and fresh file verification.
- Do not commit storyboards, uploads, manifests, generated videos, or logs under
  `tasks/`.
