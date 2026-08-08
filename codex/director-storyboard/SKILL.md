---
name: director-storyboard
description: Turn scripts and ordered or unordered keyframes into LTX Director 2 timeline prompts, storyboard JSON, and optional runs. Runs on ComfyUI alone; uses Camera Lab when present. Use for storyboard analysis, keyframe bridging, Director variants, extensions, retakes, or $director-storyboard.
---

# Director Storyboard

Build one Director timeline from a plot and visual targets. Do not treat the
result as stitched independent I2V clips.

The generation backend is pluggable — see `references/backend-contract.md`.
ComfyUI on its own is enough.

## Where the helpers live

`scripts/` and `workflows/` sit at the **repository root**, beside `skills/`
and `codex/`, so both skill variants use one copy. Every command below is
written relative to that root — from this file's own directory that is `../..`.
Resolve it once at the start of a run and reuse it.

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
- Put prohibitions in `negative_prompt` **only where the backend has one**. LTX
  i2v/flf do; the LTX Director timeline node and H3 do not, and silently ignore
  the field. Where there is none, phrase every constraint positively — state what
  is in frame, not what is absent.
- Treat images as visual targets. Explicitly write the motion between targets.
- Add visible movement to every segment; do not lower guide strength merely to
  fix a slideshow result.
- Default image strength: `0.78–0.85`. Allow roughly 1.5–2.5 seconds for a
  micro-action, 2.5–4 seconds for a gesture or short walk, and 4–6 seconds for
  a major pose plus camera transition.
- **Never put `|` in a prompt.** LTXDirector splits local prompts on it.

## Routing and running

Probe before asking the user anything:

```bash
py -3 scripts/probe_backends.py
```

Then route each segment across two models (`references/routing.md`):

- Keyframe count picks the mode: 1 → i2v, 2 → flf, ≥3 → timeline.
- Fast camera movement picks the model — those segments go to H3, the rest stay
  on LTX. Decide **per segment**. Judge it from side-by-side pair sheets
  (`--mode pairs` above); `fast_camera` is an input you set, not something the
  script derives.
- H3 is about an order of magnitude slower than LTX for the same shot and both
  generate audio, so H3 must earn it: structure through violent motion, one long
  unbroken take, or an identity locked by references. A locked-off talking shot
  has none of those — default it to LTX.
- Under 4 seconds vetoes H3 regardless of camera movement.
- H3 can never run timeline mode — first/last anchors only.

For any segment routed to H3, read `references/prompting-h3.md` **instead of**
`prompting.md`: H3 has no negative conditioning, no per-segment local prompts,
no strength and no retake, and its encoder already sees the keyframe.

If both H3 backends are available, ask local or API, and state the Community
License territory exclusion (US / EU / UK / South Korea) when they pick local.
The hosted API costs money — print the estimate and get a yes before submitting.

`scripts/run_storyboard.py` does probe → route → cost → submit in one pass.

A client-side timeout is not a failed generation. Check the backend's own job
history and output directory before resubmitting.

## Load only what the task needs

- `references/prompting.md` when composing, comparing, or repairing prompts,
  timing, strengths, or anti-slideshow motion.
- `references/backend-contract.md` before touching any backend.
- `references/operations.md` when submitting, extending, retaking or troubleshooting.
- `references/audio-sfx.md` when generating dialogue or sound effects rather than picture.
- `references/routing.md` before deciding which model runs a segment.
- `references/prompting-h3.md` for any segment routed to H3 — not `prompting.md`.
- `references/backend-comfyui.md`, `references/backend-camera-lab.md`,
  `references/backend-h3-local.md` or `references/backend-minimax-api.md` for the
  stack actually present.
- `references/storyboard.schema.json` only when writing or validating JSON.
- `references/example_storyboard.json` only when no existing storyboard
  provides a usable structure.

Do not load all references by default.

## Required safeguards

- Keep identity, wardrobe, geography, lighting, and object design consistent
  unless the script deliberately changes them.
- Where a negative prompt exists, ensure it does not forbid a required event.
- Confirm what the character can physically do in this moment (sighted, free,
  conscious, face visible) before writing their reaction.
- Give complex actions enough time and avoid multi-event monologues in short
  segments.
- Never invent ComfyUI paths or claim generation succeeded without API
  confirmation and fresh file verification.
- Do not commit storyboards, uploads, manifests, generated videos, or logs under
  `tasks/`.
