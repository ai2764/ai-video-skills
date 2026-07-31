# Adapter: Camera Lab + ComfyUI (LTX)

Camera Lab server at `http://127.0.0.1:1234`, ComfyUI behind it.

## 1. Read a job

By ComfyUI job id:

```bash
grep -rl "<job-id>" tasks/camera_lab_runs/*/*/submit.json   # → batch.json alongside
```

By Camera Lab batch id: read `tasks/camera_lab_runs/<batch-id>/batch.json`
directly — it is the same file and a perfectly good entry point.

Fallback: `GET http://127.0.0.1:8188/history/<job-id>`.

`batch.json` → `runs[0]` carries `workflow_id`, `global_prompt`, `segments[]`
(each with `start`, `duration`, `image_path`, `prompt`), `seed`, `width`,
`height`, `prompt_id`.

`workflow_id: "ltx_director_2"` is multi-anchor; `i2v_official_local` and the
`bernini_*` modes are single-anchor.

## 2. Run first-last-frame generation

`POST /api/run`:

```json
{
  "workflow_id": "flf_ttp_control",
  "camera_move": "flf_ttp_control",
  "source_path": "<abs path to start anchor>",
  "end_path":    "<abs path to end anchor>",
  "middle_path": "",
  "source_image": "<same as source_path>",
  "end_image":    "<same as end_path>",
  "middle_image": "",
  "duration": 9.2,
  "width": 1280,
  "height": 704,
  "seed": 620,
  "prompt": "<global identity/scene + slow-motion phrasing + this pair's action>",
  "negative_prompt": "...",
  "variant_name": "repair_c1"
}
```

Both `*_path` and `*_image` must be set — the server reads one for validation
and the other for staging.

Three-image FML: `workflow_id: "fml_two_segment_flf"`, additionally takes
`middle_path`/`middle_image`, runs two stages internally.

## 3. Fetch the result

`GET /api/batches/<batch-id>` → `runs[0].status` / `.video`.

**`status: "error", error: "timed out"` is a client-side timeout, not a failure.**
Heavy jobs (reference-conditioned v2v, long clips) exceed the server's wait
window while ComfyUI keeps going. Check:

```bash
curl -s "http://127.0.0.1:8188/history/<prompt-id>"     # status_str: success?
ls  "<ComfyUI>/output/camera_lab/<batch-id>/"           # the file is usually here
```

A genuine failure carries `execution_error` with a node id and exception message.

## Path restriction

Media must live under Camera Lab's `tasks/` tree:

```
HTTP 500 {"error": "C:\\Users\\AIBOX\\Downloads\\motion-fix\\1.png"}
```

Copy anchors into `tasks/camera_lab_uploads/` first.

## Prompt rules

- **Never put `|` in a prompt.** LTXDirector splits local prompts on it →
  `Number of segment_lengths (2) must match number of local prompts (3)`.
- Slow-motion phrasing that measurably helped:
  `extreme slow motion phantom high-speed camera footage, luxuriously slow,
  every frame razor sharp, dust hanging almost frozen in the air, unhurried
  deliberate movement`
- Negative additions for this task:
  `motion blur, smeared frames, ghosting, soft focus, fast motion,
  normal speed motion, hurried motion`
- Carry the source job's identity/wardrobe/location sentence verbatim so the
  repaired span still matches the surrounding footage.

## Resolution snaps to a multiple of 64

The server halves each dimension, aligns to 32, doubles back. `720 → 704`,
`736 → 768`. Exact 1280x720 is unreachable — generate 1280x704 (matching most
existing footage) or 1280x768 and crop.

## Duration limits

- ≤12 s per job is the verified safe envelope on a 24 GB card.
- Longer spans: split into more pairs rather than one long job.
- Output length overshoots the request; always `ffprobe` the result.

## Concurrency caveat

Camera Lab stages FLF/i2v anchors into ComfyUI's input directory. Older builds
named them `{run_id}_source.png` / `{run_id}_end.png` — and every run in flight
uses run_id `01_prompt`, so **concurrently queued jobs overwrote each other's
anchors and all sampled whichever job staged last**. The symptom is a batch of
clips that all look the same despite different anchors.

Fixed by prefixing the batch id (matching the director timeline naming). Verify
on an unfamiliar build:

```bash
ls "<ComfyUI>/input/" | grep _source.png     # names should carry the batch id
```

or dump `api_prompt.json` from each run and compare the `LoadImage` filenames.

## Checking results

```bash
# per-frame blur (higher = blurrier)
ffmpeg -i clip.mp4 -vf "blurdetect=block_pct=80,metadata=print:key=lavfi.blur" -f null -

# real duration
ffprobe -v error -show_entries format=duration -of csv=p=0 clip.mp4

# one frame at a timestamp (-update 1 avoids the "same filename" muxer error)
ffmpeg -ss 2.9 -i clip.mp4 -frames:v 1 -update 1 frame.png
```

Do not extract frames from output just to admire them — that burns context.
Extract only to check a seam, a boundary anchor, or a specific reported defect.

## Approaches that do not work for this problem

Recorded so they are not rediscovered:

| Tool | Result |
|---|---|
| FlashVSR 2× upscale | Sharpens static detail; structure damage untouched |
| IC-LoRA MotionDeblur | Faithfully reproduces the mush; trained for shutter smear, not structure collapse |
| Retake window on the original video | Retake conditions on the base video; damage already in frame persists |
| Generic img2img on extracted frames | Reimagines composition, does not repair it |

The common thread: nothing that *filters* the existing pixels can help, because
the structure was never drawn. Only regeneration with enough per-frame time
budget does.
