# director-storyboard: migration into ai-video-skills, with H3 and backend routing

Design date: 2026-08-04

## Background

`director-storyboard` currently lives inside the `camera-lab` repository (three
copies, under `.claude` / `.codex` / `.grok`) and hardcodes execution to Camera
Lab's `/api/run`. Three things force a change of shape:

1. **It has to work for people without Camera Lab.** Having ComfyUI installed
   should be enough.
2. **It has to be able to call MiniMax-H3.** Fast camera movement is where LTX
   Director breaks down — the structural collapse that `slowmo-redraw-repair`
   exists to repair — and H3 holds together better through sustained large
   motion.
3. **H3 has to be reachable through the API, chosen by the user.** The H3
   Community License (effective 2026-08-02) defines an `Applicable Territory`
   that excludes the United States, the European Union, the United Kingdom and
   South Korea; in those jurisdictions it does not license using, running,
   modifying or distributing the weights, nor using the outputs of locally-run
   weights, and self-hosting requires separate authorisation from
   `model@minimax.io`. The hosted API is governed by the platform's own terms, a
   separate document. The skill must not assume the user's jurisdiction, so both
   routes have to be supported.

## Goals

- Move the skill into `ai-video-skills` and organise it around that repo's
  existing backend-contract-plus-adapter pattern.
- Add a ComfyUI-direct adapter so Camera Lab becomes optional rather than
  required.
- Put a routing layer in front: three modes (i2v / flf / timeline) against three
  backends (LTX / H3 local / H3 API).
- Base routing on what the user's ComfyUI actually has installed, plus the
  agent's reading of the keyframes — the primary signal being fast camera
  movement.
- Report cost before dispatching. Never spend money unprompted.

## Non-goals

- No H3 reference-to-video (ref2va) path in this design.
- No changes to `camera-lab`'s server code. The Camera Lab adapter only
  documents the existing call pattern. (Retiring the three old skill
  directories there is the closing step of this design — see *Repository
  shape* — and nothing else in that repo is touched.)
- No WAN2.2 Bernini workflows.

## Repository shape

Following the layout `slowmo-redraw-repair` already uses:

```
skills/director-storyboard/
  SKILL.md                       the method itself, backend-agnostic
  references/
    backend-contract.md          the backend contract
    backend-comfyui.md           ComfyUI-direct adapter (new)
    backend-camera-lab.md        Camera Lab adapter (distilled from the current SKILL.md)
    backend-minimax-api.md       MiniMax H3 API adapter (new)
    routing.md                   the table and the rules
    prompting.md                 LTX prompt contract (carried over)
    prompting-h3.md              H3 prompt contract (new; a different contract from LTX)
    storyboard.schema.json       carried over
    example_storyboard.json      carried over
  workflows/
    ltx_director_2.api.json      the API-format graph the skill ships
    ltx23_i2v.api.json
    ltx23_flf.api.json
    h3_i2v.api.json
    h3_flf.api.json
  scripts/
    probe_backends.py
    run_storyboard.py
codex/director-storyboard/       Codex variant (same method, lower density)
  SKILL.md
  agents/openai.yaml
  references/
```

Once the migration is verified, the three old skill directories in `camera-lab`
are removed and the README's skill table gains a row.

## Routing table

| Mode | LTX | H3 local | H3 API |
|---|---|---|---|
| **i2v** single first frame | `ltx23_i2v` | `MiniMaxH3ImageToVideo` | `content:[first_frame]` |
| **flf** first and last frame | `ltx23_flf` | same plus last_frame | `content:[first_frame, last_frame]` |
| **timeline** many keyframes, per-segment direction | `ltx_director_2` | — | — |

The two empty cells are permanent, not unimplemented: `comfy/ldm/minimax/model.py:317`
accepts a `pixel_index` of only `0` or `frame_count - 1` and otherwise raises
`ValueError("only first/last keyframe anchors are supported")`. H3 has no
director timeline at the model level, and no per-segment local prompts, no
`strength` and no retake. That is the floor the whole table rests on.

**The LTX column has two implementations behind it**, and they look identical to
the user: Camera Lab when it is reachable, ComfyUI direct otherwise. Routing does
not distinguish them; only the adapter layer does.

The three LTX entries correspond to `i2v_official_local` / `flf_ttp_control` /
`ltx_director_2` in Camera Lab's `WORKFLOWS` registry
(`camera_lab_server.py:342`), with modes `i2v` / `flf` / `director_ref`. The
ComfyUI adapter ships equivalent API-format graphs.

## Routing rules

Applied in order:

1. **Keyframe count picks the row.** 1 → i2v; 2 → flf; 3 or more → timeline.
   (Consistent with the existing finding: with a single keyframe use i2v rather
   than a one-segment Director run; the criterion is frame count, not duration.)
2. **Fast camera movement picks the column.** Judge displacement and angle
   change between adjacent keyframes; large changes go to H3, everything else
   stays on LTX. The granularity is **per segment** — send only the hard spans
   to H3.
3. **A duration floor overrides both.** Segments under 4 seconds go back to LTX.
   The API takes an integer 4–15 seconds; the local stack is stricter still
   (frame count `n % 17 == 5`, trained range 124–362 frames = 5.17–15.08 s at
   24 fps). Short segments cannot be expressed.
4. **Three or more keyframes judged as fast camera** are split into adjacent
   first/last pairs and sent to H3 as flf, rather than left in Director. Fast
   camera movement is precisely where Director fails, so leaving it there is
   choosing a known failure.

## Backend contract

Three operations; everything else is `ffmpeg` / `ffprobe`.

### 1. Probe capability

**In:** nothing, or a backend base URL.
**Out:** which cells of the routing table are runnable, and why the rest are not.

The skill does not open by asking "local or API" — it probes first, then asks
only if the answer is still open.

### 2. Submit a generation

**In:** mode (i2v / flf / timeline), keyframe paths, per-segment prompts,
duration, dimensions, seed; timeline mode additionally takes each segment's
`start`, `length` and `strength`.
**Out:** a job id.

### 3. Fetch the result

**In:** a job id. **Out:** a file path and its real duration.

A client-side timeout is not a failed generation — check the backend's own
history and output directory before retrying. (Carried over from the
`slowmo-redraw-repair` contract.)

## Adapter: ComfyUI direct

This is the adapter that makes "ComfyUI is enough" true.

**Probe:** fetch `GET /object_info`.

| Signal | Lights up |
|---|---|
| LTX Director nodes present | timeline / LTX |
| LTX i2v and flf nodes present | i2v, flf / LTX |
| All four of `EmptyMiniMaxH3LatentAV`, `MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`, `MiniMaxH3SigmaShift` **and** `minimax` among `CLIPLoader`'s types | i2v, flf / H3 local |

Nodes present without `minimax` in `CLIPLoader` means the weights are missing —
report that rather than lighting the cell.

**Submit:** fill the shipped `workflows/*.api.json` and `POST /prompt`. In
timeline mode the `LTXDirector` node consumes a `segments` JSON array, each
entry shaped like:

```json
{"id": "...", "type": "image", "label": "segment 1", "start": 0,
 "length": 121, "prompt": "...", "imageFile": "...", "strength": 0.82}
```

That is the output shape of `director_reference_timeline_segments`
(`camera_lab_server.py:1183`). **No nodes need adding or removing to change the
segment count** — filling the array is enough, structurally the same job as
filling an H3 graph.

**Fetch:** `GET /history/{prompt_id}`, take the file from the output directory.

**Traps:** images must be staged into ComfyUI's `input/` first; node ids must be
compared numerically, not as strings (`max("10","9") == "9"` silently overwrites
node 10, and the error then surfaces downstream rather than at the cause);
autogrow inputs need their full dotted path (`ref_images.ref_image_0`) — a bare
name passes `/prompt` validation and only fails at execution time.

## Adapter: Camera Lab

The existing channel, preserved: `POST /api/run` (`workflow_id=ltx_director_2`
and friends), status at `/api/batches/<batch_id>`, uploads staged under
`tasks/camera_lab_uploads/`. Dimensions are halved, aligned to 32, then doubled
back. Probe by reachability plus the `WORKFLOWS` listing.

Where Camera Lab is installed, prefer it for LTX — its image preprocessing,
subtitle bottom matte and audio segment handling are already tuned. Otherwise
fall back to ComfyUI direct.

## Adapter: MiniMax H3 API

- Create: `POST {MINIMAX_BASE_URL}/v2/video_generation`
- Query: `GET {MINIMAX_BASE_URL}/v2/query/video_generation/{task_id}`, roughly
  every 10 seconds
- Auth: `Authorization: Bearer {MINIMAX_API_KEY}`
- On success the download URL is at `task.content.url`; terminal failure states
  are `failed` and `cancelled`

Request body:

| Field | Value |
|---|---|
| `model` | `"MiniMax-H3"` |
| `duration` | integer 4–15 (seconds) |
| `resolution` | `"768P"` or `"2K"` |
| `ratio` | an aspect string, or `"adaptive"` with image input |
| `content[]` | multimodal array; elements carry `type` and `role` |

`content` elements: `{"type":"text","text":...}` (≤7000 characters) and
`{"type":"image_url","image_url":{"url":...},"role":...}`. The roles used here
are `first_frame` and `last_frame`; `reference_image` / `reference_video` /
`reference_audio` / `base_video` are out of scope.

Input limits: 0/1/2 first-and-last frames, edges 256–5760, aspect 2:5–5:2,
images JPG/PNG/WEBP/HEIC/HEIF ≤30 MB, request body ≤64 MB (send large assets as
URLs rather than base64).

**Region and key must be paired**: `api.minimax.io` with a platform.minimax.io
key, `api.minimaxi.com` with a platform.minimaxi.com key; a mismatch returns
`Invalid API key`. Both therefore come from the environment:
`MINIMAX_BASE_URL` (default `https://api.minimax.io`) and `MINIMAX_API_KEY`.

**Probe:** `MINIMAX_API_KEY` present lights the H3 API column for i2v and flf.

Pricing: 768P `$0.08`/s, 2K `$0.13`/s; input images free for the first 5 then
`$0.04` each; input audio free; 768P→2K regeneration `$0.05`/s.

## H3 local vs API: probe first, ask second

| Probe result | Behaviour |
|---|---|
| Both available | **Ask the user: local or API** |
| Only the API available | Use it, no question |
| Only local available | Use it, no question |
| Neither | Report what is missing; do not pretend it can run |

When the user picks local, add one sentence noting that the Community License's
Applicable Territory excludes the United States, the European Union, the United
Kingdom and South Korea. That is a factual notice, not a gate; the decision is
theirs.

## Handling the three hard constraints

**Duration.** Round segment durations to whole seconds and clamp to [4, 15].
Segments under 4 seconds never enter the H3 candidate set (rule 3). Over 15
seconds, raise and require splitting rather than truncating silently.

**Audio.** H3 produces native stereo audio, but **strip it by default**. Each
clip's voice is encoded independently, so a character's voice changes between
shots; dropping per-segment audio into an otherwise silent LTX cut produces
sound that appears and vanishes shot to shot. Lay audio in post. Keeping it
requires an explicit flag.

**Resolution.** Default to `resolution: "768P"` with `ratio: "16:9"` (≈1366×768,
the closest match to the 1344×768 Director commonly uses), then scale the output
to the timeline's dimensions. 2K costs 60% more and needs scaling anyway, so it
is not the default.

## Two prompt contracts that must not be mixed

Everything in the LTX contract (global prompt, per-segment local prompts,
`strength`, `negative_prompt`) is inapplicable to H3, so they need separate
reference files:

- **H3's text encoder is Qwen3-VL-32B, and keyframes enter it as vision blocks
  alongside the text** (`<Picture 1>: <vision block> <prompt>`). The model can
  see the frame, so do not re-describe what is already visible — write only what
  changes: action, camera, light, sound.
- **There is no chat template.** Do not write instruction voice ("Generate a
  video of..."); those words get encoded as picture content.
- **There is no negative conditioning at all.** Express every constraint
  positively ("no full body" → "only limbs enter frame, the torso stays out of
  shot").
- Refer to supplied material as `<Picture i>`, numbered from 1 within each type.
- **Lengthening a shot requires writing more action**, or the model invents
  something to fill the time.

## Cost visibility

Before dispatching, print the bill:

```
segments 3 and 7 judged fast-camera -> H3 API
8s + 10s = 18s at 768P
2 input images (within the free allowance)
estimated $1.44
```

Submit only after confirmation. Never dispatch automatically.

## Error handling

- ComfyUI unreachable: affects only the local paths and the probe; the API path
  continues. Report and degrade, never silently.
- `MINIMAX_API_KEY` missing, or a region mismatch (`Invalid API key`): report
  directly, and state that base URL and key must come from the same region.
- Task returns `failed` or `cancelled`: report the task id and status; do not
  retry into more spend.
- Poll timeout: keep the task id and explain it can be retrieved later.
- All three backends unavailable: report what each is missing, and still deliver
  the storyboard JSON.

## Verification

- `probe_backends.py` reports the correct set of available cells on three kinds
  of machine: one with Camera Lab, one with only ComfyUI plus LTX, and one with
  only `MINIMAX_API_KEY`.
- `run_storyboard.py --dry-run` prints the request body and the cost estimate
  without sending anything.
- Dry-run an existing multi-shot H3 plan (9 shots / 1847 frames / 77 s) and
  check the frame-to-second conversion and the cost estimate (768P, about
  `$6.2`).
- The first real API call is a single 4-second segment: confirm
  `task.content.url` downloads and that audio stripping works.
- Run a 3-keyframe timeline through the ComfyUI-direct adapter and compare its
  boundary frames against the same parameters through Camera Lab, confirming the
  `segments` array is filled equivalently.
- Both variants (`skills/` and `codex/`) describe the same method; changes stay
  in step.

## Open

`seed` and `prompt_optimizer` behaviour on the H3 API: the official guides
mention them but give no parameter table, and the `/docs/api-reference/*` pages
currently 404. Confirm through dry-run plus a real call during implementation;
until then they stay out of the plan schema.
