---
name: director-storyboard
description: >
  Turn a plot/script plus a set of keyframe images into an LTX Director v2
  storyboard (global prompt + timed local prompts + image guides), then run it.
  Runs on ComfyUI alone; uses Camera Lab when it is present. Use when the user
  wants storyboard analysis, script-to-timeline prompting, keyframe bridging,
  auto-run Director, or runs /director-storyboard.
metadata:
  short-description: "Script + keyframes → Director timeline run"
---

# /director-storyboard — Script + Images → Director Run

You convert a **script / plot** and a **set of keyframe images** into a
Director-ready storyboard, then optionally run it.

## When to use

- User provides a script/story + stills and wants Director prompts
- User wants two (or more) keyframes bridged with continuous motion
- User asks to auto-run LTX Director 2 from images + prompts
- Slash: `/director-storyboard`

## Pipeline

```text
script + images
    → (this skill) understand shots, order keyframes, write prompts
    → storyboard JSON
    → probe which backends this machine has
    → submit through the chosen adapter
```

The generation backend is pluggable — see `references/backend-contract.md`.
ComfyUI on its own is enough; Camera Lab is used when available because its
image staging and audio handling are already tuned.

## Where the helpers live

`scripts/` and `workflows/` sit at the **repository root**, beside `skills/`
and `codex/`, so both skill variants use one copy rather than two that drift.
Every command below is written relative to that root — from this file's own
directory that is `../..`. Resolve it once at the start of a run and reuse it.

## Step 1 — Gather inputs

Collect:

1. **Script / plot** (scene beats, dialogue, camera intent)
2. **Image set** (ordered keyframes, or unsorted — then you must sort them)
3. Optional: target duration, resolution, seed, negative prompt
4. Whether to **only write** the JSON or **also run** the workflow

If images are unordered, infer order from the script and from visual continuity
(same character, lighting, location progression). State the ordering explicitly.

### Always read thumbnails, never the originals

Before opening any keyframe, run it through `scripts/thumbnails.py`:

```bash
py -3 scripts/thumbnails.py <images...> --dest <tmp>/thumbs
```

A 512px thumbnail carries everything storyboard decisions turn on —
composition, blocking, shot scale, wardrobe, palette — at a fraction of the
cost. On a real 3-frame set: 7.2 MB of originals became 747 KB of thumbnails.
Open an original only when a decision depends on fine detail the thumbnail
cannot settle: legible on-screen text, a facial micro-expression, a small prop.

To compare two adjacent keyframes, make one side-by-side sheet instead of
opening both — this is also how you judge the camera move between them:

```bash
py -3 scripts/thumbnails.py a.png b.png --dest <tmp>/pairs --mode pairs
```

For a first pass over a whole set, one contact sheet costs a single read:

```bash
py -3 scripts/thumbnails.py <images...> --dest <tmp>/sheet --mode contact --columns 4
```

Cheap reads are not free reads — the selectivity rules below still apply.

### Read images selectively — do not open the whole set

Every full-size keyframe read costs ~1.5k tokens and stays in context for the
rest of the session. On a 20–30 frame project that alone can dominate the run.
Descriptive
filenames (`02_kneels_and_opens_the_cloaking_device.png`,
`05_approaching_the_entrance.png`) already carry the beat,
the action and the shot size — mine them first, then open only:

1. **Style anchors (1–3 frames)** — enough to write the global prompt: face,
   wardrobe, location, lighting, palette. Usually the first frame, one mid frame,
   and the last frame.
2. **Frames whose filename is ambiguous in a way that changes the prompt** —
   e.g. "cloaking device activates": full transparency vs. refractive camouflage
   decides both the local prompt and what the negative prompt must forbid.

Skip the rest and derive their local prompts from filename + script + continuity.
When you skip frames, say so, and name the assumption you made about them.

Other token discipline in this pipeline:

- After a run, `grep` the batch id and video path out of the runner output —
  never read the whole log.
- Do not extract or inspect frames from generated video to "verify" a take;
  report the batch id and path and let the user watch it.

## Step 2 — Analyze as a continuous Director shot

Director v2 is **not** “stitch many I2V clips”. It is:

| Layer | Role |
|---|---|
| **Global prompt** | Persistent identity, wardrobe, location, lighting, style |
| **Local segment prompt** | What happens in *this* time window only |
| **Keyframe image** | Visual guide at that time (model is *pulled toward* the frame) |

Rules:

1. Prefer **one continuous cinematic shot** per storyboard unless the user wants hard cuts.
2. Keep **identity + wardrobe + location + lighting** stable across keyframes.
3. Keyframes are **targets the generation should reach**, not only start frames.
4. Between two keyframes, the local prompt must describe the **bridge motion**
   (how pose/camera gets from A to B), not just re-describe stills.
5. Give enough duration for the action (do not pack complex motion into 2s).

Read `references/prompting.md` for LTX + Prompt Relay guidance.

## Step 3 — Map script beats → timeline segments

For N keyframe images:

1. Align each image to a script beat (or mark as bridge-only text segment).
2. Set `start` / `duration` in seconds so segments cover the full shot without large empty gaps
   (gaps get absorbed into neighboring local-prompt lengths).
3. Default strengths: **0.78–0.85** for important keyframes. Do **not** drop below ~0.75
   to fix a static / slideshow feel — that trades away keyframe fidelity. Fix static shots
   in the prompts instead (see *Anti-slideshow rules* below).
4. First image usually at `start: 0`. Last image near the end of the timeline
   (or own segment near the end) so the shot lands on that composition.

Suggested timing defaults when user does not specify:

| Transition | Duration between keyframes |
|---|---|
| Micro expression / head turn | 1.5–2.5s |
| Walk a few steps / simple gesture | 2.5–4s |
| Full pose + camera track | 4–8s |

### Resolution snaps to a multiple of 64

The requested size is **silently rewritten** — no error, no warning. Each
dimension is halved, aligned to 32 (`round(v/32)*32`), then doubled back, so the
effective grid is **64**. This happens on both backends; see the adapter notes
for where each one applies it.

| Requested | Actual | Why |
|---|---|---|
| 720 | **704** | 360 → 352 → 704 |
| 736 | **768** | 368 → 384 → 768 (ties round to even) |

Legal heights at 1280 wide: 640, **704**, **768**, 832. **736 is not reachable** — it
snaps up to 768.

Exact 1280x720 cannot be generated at all. Either accept 1280x704 / 1280x768, or
generate 1280x768 and crop 24px off top and bottom (`ffmpeg -vf crop=1280:720:0:24`);
cropping is lossless, whereas scaling 704→720 stretches the subject vertically by 2.3%.

Always `ffprobe` the output when the user asked for a specific size, and report the
real numbers rather than the requested ones.

## Step 4 — Write prompts

### Global prompt (English, one paragraph)

Structure (LTX official style):

1. Continuous shot + subject identity
2. Wardrobe / appearance
3. Location + time of day / weather
4. Lighting + color palette
5. Continuity constraints (same person, coherent motion)

Do **not** put beat-by-beat action only in global. Global is the anchor.

### Local prompts (per segment)

- Present-tense **verbs** (turns, walks, raises, camera tracks…)
- Explicit **camera** (static / slow push-in / tracks right / handheld)
- Only the events that happen in this segment
- Adjacent segments must **relay** — same world, progressive action
- Dialogue in quotation marks if needed
- Keep each segment focused (one dominant beat)

### Anti-slideshow rules

Multi-cut storyboards (several close-ups, reused reaction images) read as a slideshow
unless every beat visibly moves:

- Every segment prompt must contain ongoing motion: light flicker/shift, wind in hair,
  breathing, drifting dust/smoke, churning clouds, falling debris.
- The camera is never locked — give each beat a drift, push-in, or tremble.
- When reusing a keyframe for a reaction insert, advance its state (light change, tighter
  framing, deeper emotion) instead of re-describing the still.
- Add static terms to the negative prompt: `slideshow, still photograph, freeze frame,
  static image, motionless scene`.
- Keep strength high (0.78–0.85) and let the prompt carry the motion.

### Treadmill rules (moving but going nowhere)

Distinct from slideshow: the character animates convincingly — legs cycling, arms
swinging — but never leaves the spot. Stronger verbs do not fix this. The model reads
displacement off the **background**, so give it moving reference points:

- Name what recedes: "the doorway shrinks behind her", "the sign slides out of the left
  edge of frame", "floor markings stream past beneath her boots".
- Name what approaches: "the far door grows larger in frame as she nears it".
- State the ground covered inside the window: "strides several full steps deeper into the
  corridor, covering real ground within this shot".
- Lock the screen direction (left→right, or into depth) and have the camera **track**
  rather than sit still.
- In close-ups of a walking character, keep the background streaming backward — otherwise
  the insert reads as the character having stopped.
- Negative prompt: `walking in place, treadmill effect, stationary character,
  no forward movement`.

If it still stalls after this, stop adding words — lengthen the segment so there is time
to cross ground, or let a dolly-in carry the displacement instead of the character.

### Negative prompt — check the backend actually has one

**Not every backend accepts a negative prompt, and the ones that do not fail
silently.** Write the field, get no error, and assume a constraint is in place
that was never applied.

| Backend | Negative prompt |
|---|---|
| LTX i2v / flf | **Yes** — the graphs carry `CLIPTextEncode` nodes for it |
| LTX Director timeline | **No** — the `LTXDirector` node has no negative input at all; the graph derives its negative from `ConditioningZeroOut`. The `negative_prompt` field in the storyboard is ignored on this path |
| MiniMax H3 (local and API) | **No** — no negative conditioning exists in the model |

Check the node's declared inputs before relying on it:

```bash
py -3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8188/object_info/<NodeName>')); i=d['<NodeName>']['input']; print(list((i.get('required') or {})) + list((i.get('optional') or {})))"
```

**Where there is no negative, every constraint must be phrased positively** —
state what *is* in the frame rather than what is not. "No full body" becomes
"only limbs enter frame, the torso stays out of shot".

Default negative where the backend supports one:

```text
blurry, distorted face, identity change, clothing change, flicker, jump cut, text overlay, watermark
```

## Step 5 — Emit storyboard JSON

Write a file (prefer under `tasks/` — gitignored) matching
`references/storyboard.schema.json`.

Minimal shape:

```json
{
  "global_prompt": "A continuous cinematic shot of ...",
  "negative_prompt": "blurry, distorted face, ...",
  "width": 768,
  "height": 512,
  "seed": null,
  "segments": [
    {
      "id": "s1",
      "image": "C:/path/or/repo/relative/frame_01.png",
      "prompt": "Medium shot. She stands under the umbrella...",
      "start": 0.0,
      "duration": 3.0,
      "strength": 0.8
    },
    {
      "id": "s2",
      "image": "C:/path/or/repo/relative/frame_02.png",
      "prompt": "She turns right and walks toward the crosswalk...",
      "start": 3.0,
      "duration": 4.0,
      "strength": 0.75
    }
  ]
}
```

Notes:

- `image` may be absolute or repo-relative. Each adapter stages its own copies
  where its backend can read them — see the adapter notes; a path you can read
  is not automatically a path the backend can read.
- Text-only bridge segments are allowed: omit `image`, keep `prompt` + timing.
- Field aliases accepted by the runner: `image_path`, `local_prompt`, `length_seconds`.
- **Video segments**: `"video": "path.mp4"` (alias `video_path`) uses an existing take as
  a timeline guide — the standard way to extend a good take: video segment at
  strength ~1.0 covering its original duration, then new tail segments after it.
- A **text-only tail after a strength-1.0 video guide is often ignored** (the new event
  never happens). Anchor the new event with an image guide — extract a frame from a
  previous good run (`ffmpeg -ss <t> -i take.mp4 -frames:v 1 guide.png`) and use it with
  strength ~0.75–0.8.
- **Audio segments**: top-level `"audio_segments": [{"audio", "start", "duration",
  "volume", "trimStart"}]`, usually with `"inpaint_audio": true`.
- Where the backend has a negative prompt, it must not forbid an event a segment
  requires (e.g. remove `ship explodes` from the negative before adding an
  explosion beat). Where it has none, the field is inert — see *Negative prompt*
  above.

Also show the user a short markdown table:

| # | start–end | image | local prompt (1 line) |
|---|---|---|---|

## Step 6 — Run the workflow (when requested)

Prerequisites:

1. ComfyUI running with the LTX Director nodes (Camera Lab optional)
2. Storyboard JSON written to disk

### Probe first

Never assume a backend. Ask the machine:

```bash
py -3 scripts/probe_backends.py
```

It reports which cells are runnable and why the rest are not. Do not ask the
user a question the probe has already answered.

### Then route each segment

Two models are available, and they are not interchangeable. Read
`references/routing.md` for the table and the four rules. In short:

- **Keyframe count picks the mode**: 1 → i2v, 2 → flf, ≥3 → timeline.
- **Fast camera movement picks the model.** Segments whose adjacent keyframes
  show large displacement or a big angle change go to H3, which holds structure
  better through violent motion; everything else stays on LTX. Decide this
  **per segment**, not per storyboard.
- **Under 4 seconds vetoes H3** no matter how fast the camera moves.
- **H3 can never run the timeline mode** — it takes first/last anchors only.

To judge camera movement, build one side-by-side sheet per adjacent keyframe
pair and read those (see the thumbnail rules above):

```bash
py -3 scripts/thumbnails.py <keyframes in order> --dest <tmp>/pairs --mode pairs
```

**This judgement is yours, not the script's.** `fast_camera` is an input to
routing — set it on each segment before routing.

If a segment routes to H3, read `references/prompting-h3.md` **instead of**
`prompting.md`. The two prompt contracts are incompatible.

If both H3 backends are available, ask the user local or API, and state the
Community License territory exclusion (US / EU / UK / South Korea) when they
pick local.

### Then pick an adapter

| Situation | Adapter |
|---|---|
| Camera Lab reachable | `references/backend-camera-lab.md` — prefer it for LTX; its image staging, subtitle matte and audio handling are already tuned |
| Only ComfyUI | `references/backend-comfyui.md` — the skill fills and submits the graph itself |
| H3 on this machine | `references/backend-h3-local.md` |
| H3 hosted | `references/backend-minimax-api.md` — **costs money**; print the estimate and get confirmation before submitting |

The two LTX adapters produce the same graph. That equivalence is pinned by a
golden `api_prompt.json` captured from a real Camera Lab run and verified end to
end against a live ComfyUI.

`scripts/run_storyboard.py` does probe → route → cost → submit in one pass:

```bash
py -3 scripts/run_storyboard.py storyboard.json --dry-run
py -3 scripts/run_storyboard.py storyboard.json --h3-backend api --yes
```

### Report after submit

- the job id (`prompt_id` for ComfyUI, `batch_id` for Camera Lab)
- where to watch it
- output path once it lands, verified on disk

**A client-side timeout is not a failed generation.** Check the backend's own
history and output directory before resubmitting.

Notes:

- On Windows, if `python` resolves to the Microsoft Store stub ("Python was not
  found"), use `py -3` instead.
- **Variant takes for editing**: rerun the same storyboard with different seeds
  (one take per seed) and log every take (segment, seed, job id, dialogue) in a
  takes manifest so the editor can pick shots.

If no backend is available, still deliver the storyboard JSON and report exactly
what is missing.

## Quality checklist before run

- [ ] Same character / wardrobe / location across keyframes (or deliberate cut explained)
- [ ] Global anchors identity; locals carry motion only
- [ ] Bridge between every pair of keyframes is described
- [ ] Durations match action complexity
- [ ] Strengths not all 1.0 unless user wants hard stickiness
- [ ] Paths resolve; images exist — **re-verify right before every submit**, including
      re-runs of old storyboards (users rename/replace keyframe files between runs)
- [ ] Negative prompt does not forbid any event required by a segment
- [ ] Total duration is intentional (sum of segments / last end time)

## Retakes (fixing part of a take)

`py -3 tasks/storyboards/_submit_retake.py <config.json>` replaces a time window of an
existing video (config: `base_video`, `duration`, `retake_start`, `retake_length`,
`retake_prompt`, `global_prompt`, `negative_prompt`, `seed`, `retake_strength`).

Hard-won limits:

- The window must start **before the artifact first appears**. Retake conditions on the
  base video — an artifact already in frame at window start persists regardless of seed.
- Strong model priors (e.g. an open wound drifting red) usually survive retakes even with
  clean conditioning and heavy negatives. Instead: re-run the batch with the shot ending
  earlier (stop at the peak, before the drift), or anchor the fix with a corrected guide
  image extracted from a good take.
- Retake cannot extend duration. To extend a take, use a video segment + tail segments
  (see Step 5 notes).

## Do not

- Invent ComfyUI model paths or claim generation succeeded without API confirmation
- Put large multi-event monologues into a 2s segment
- Change identity mid-timeline without user intent
- Commit generated videos, uploads, or `tasks/` outputs
- Skip writing the JSON to disk when the user asked to run (runner needs a file or CLI args)
- **Write a reaction the character cannot physically have.** Establish whether
  they can see, hear, move and speak in this moment before writing how they
  respond; a blinded character reacting visually contradicts the story.
- **Leave the receiving side of an action blank.** If something is struck,
  dragged or torn, write its reaction too, or it will stand there unaffected.
- **Carry LTX prompt structure into an H3 segment.** No negative prompt, no
  `|`-separated local prompts, no `strength`. H3 accepts none of them and will
  encode the words as picture content instead of ignoring them.
- **Submit to the hosted H3 API without showing the cost and getting a yes.**

## References

Load only what the task needs — do not read all of these by default.

- `references/prompting.md` — LTX Director prompting + keyframe bridging
- `references/prompting-h3.md` — H3 prompting. A **different contract**; read
  this instead of `prompting.md` for any segment routed to H3
- `references/routing.md` — the mode × backend table and the four rules
- `references/storyboard.schema.json` — machine schema
- `references/example_storyboard.json` — sample payload
- `references/operations.md` — submitting, variants, retakes, extensions, troubleshooting
- `references/audio-sfx.md` — when the deliverable is sound: dialogue and effect libraries
- `references/backend-contract.md` — what the skill needs from a backend
- `references/backend-comfyui.md` — ComfyUI direct adapter
- `references/backend-camera-lab.md` — Camera Lab adapter
- `references/backend-h3-local.md` — H3 on a local GPU (check licence territory)
- `references/backend-minimax-api.md` — hosted H3 (costs money per second)

Scripts:

- `scripts/run_storyboard.py` — probe → route → cost → submit, in one pass
- `scripts/probe_backends.py` — which cells this machine can run
- `scripts/thumbnails.py` — cheap keyframe reads (thumbs / pairs / contact sheet)
- `scripts/comfy_backend.py` — fill and submit the Director graph
- `scripts/routing.py` — the four rules and the cost estimate
- `scripts/h3_api.py` / `scripts/h3_local.py` — the two H3 backends
