# Backend contract

The skill needs three operations from whatever runs your video model.
Everything else — ordering keyframes, writing prompts, timing segments — is
backend-independent and lives in `SKILL.md`.

## 1. Probe capability

**In:** nothing, or a backend base URL.
**Out:** which generation modes are runnable, and why the rest are not.

Probe before asking the user anything. A question whose answer is already
determined by what is installed is a question not worth asking.

`scripts/probe_backends.py` implements this for ComfyUI.

## 2. Submit a generation

**In:** mode (`i2v` / `flf` / `timeline`), keyframe paths, per-segment prompts,
duration, width/height, seed. Timeline mode additionally takes each segment's
`start`, `length` and `strength`.

**Out:** a job id.

Requirements:

- Guide images must be staged where the backend can see them. A path the
  *skill* can read is not automatically a path the *backend* can read.
- Verify once on an unfamiliar backend that guides actually bind: check the
  first frame of the output against the first keyframe. If every clip in a
  batch looks alike, the backend is probably not isolating their inputs.

## 3. Fetch the result

**In:** a job id. **Out:** a file path plus its real duration.

**A client-side timeout is not a failed generation.** Check the backend's own
job history and output directory before retrying — the clip is often already
there, merely not copied back.

Output duration will not always equal the request. Always measure:

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 clip.mp4
```

## Adapters

- `backend-comfyui.md` — ComfyUI direct. Needs only ComfyUI.
- `backend-camera-lab.md` — Camera Lab in front of ComfyUI. Preferred when present.
- `backend-h3-local.md` — MiniMax H3 on your own GPU. Check the licence territory.
- `backend-minimax-api.md` — MiniMax H3 hosted. Costs money per second.

Which one runs a given segment is decided in `routing.md`.

To add a backend, write an adapter covering the three operations above, plus
that stack's path restrictions, prompt-syntax restrictions and concurrency
caveats.
