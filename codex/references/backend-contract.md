# Backend contract

The skill needs three operations from whatever runs your video model. Everything
else is `ffmpeg`/`ffprobe`.

## 1. Read a job

**In:** a job id (generation-backend id, or a batch/run id — accept either).

**Out:**

| Field | Used for |
|---|---|
| source video path | frame extraction, blur analysis |
| global prompt | carried into every repair clip so the span still matches its surroundings |
| per-segment prompts | describing each pair's action |
| anchor times + guide images | window boundaries (step 2) and end anchors (step 4) |
| seed | reproducing / deliberately re-rolling a take |
| width, height, fps | matching the repair output to the source |

If the backend cannot report anchors, treat the job as single-anchor: windows
split evenly by duration, end anchors extracted from the video.

## 2. Run first-last-frame generation

**In:** start image, end image, duration, prompt, negative prompt, seed,
width/height.

**Out:** a clip that begins on the start image and lands on the end image.

Requirements:

- Both endpoints must actually bind. Verify once on a new backend by checking
  the first and last frame of the output against the two anchors — if all clips
  in a batch look alike, the backend is probably not isolating their inputs.
- Note the backend's safe maximum duration. Split long spans into more pairs
  rather than one long job.
- Output duration will not equal the request. Always measure.

Three-image (first-middle-last) generation, where available, halves the job count
when anchors happen to come in threes. The two-image chain handles any N
uniformly — prefer it unless you have a reason not to.

## 3. Fetch the result

**In:** the job id. **Out:** a file path plus its real duration.

A client-side timeout is not a failed generation. Check the backend's own job
history and output directory before retrying — the clip is often already there,
merely not copied back.

## Adapters

- `backend-camera-lab.md` — Camera Lab + ComfyUI (LTX)

To add a backend, write an adapter covering the three operations above, plus any
path restrictions, prompt-syntax restrictions and concurrency caveats.
