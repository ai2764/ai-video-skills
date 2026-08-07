# Director operations

Read this file only when submitting, extending, retaking, or troubleshooting a
storyboard.

## Storyboard fields

- **Image segment**: `"image": "path"`. Aliases: `image_path`, `local_prompt`,
  `length_seconds`.
- **Text bridge**: omit the image, keep prompt and timing.
- **Video guide**: `"video": "path.mp4"` (alias `video_path`) uses an existing
  take as a timeline guide — the standard way to extend a good take. Use
  strength near `1.0` across its original duration, then add new tail segments
  after it.
- **Audio**: top-level
  `"audio_segments": [{"audio", "start", "duration", "volume", "trimStart"}]`,
  normally with `"inpaint_audio": true`.
- **Routing hint**: `"fast_camera": true` on a segment marks it for H3. You set
  this after reading the keyframes; nothing derives it.

**A text-only tail after a strength-1.0 video guide is usually ignored.** Anchor
a new tail event with a matching image guide at about `0.75–0.8`.

## Before every submission

1. Parse the JSON.
2. Confirm every referenced file exists — recheck immediately before submitting,
   not when the storyboard was written.
3. Confirm duration, resolution, seed, strengths, and negative prompt.
4. Dry-run whenever the payload or any path changed.
5. If anything routes to a paid backend, print the cost and get a yes.

### Print what will actually be generated, not what you meant to change

Two failure modes worth a hard check each, because both cost a full generation
to discover:

**After editing dialogue, print the resulting line and read it.** A
search-and-replace that misses — because the source string was wrapped across
lines, or the phrasing differed slightly — leaves the old text in place and the
job still submits. Assert on the result, and print it:

```python
assert "old wording" not in prompt
print([l for l in prompt.splitlines() if '"' in l])
```

**Assert keyframe binding before submitting.** Confirm the first and last frame
resolved to the files intended, in that order:

```python
assert (bound_first, bound_last) == (first_path.name, last_path.name)
```

Discovering a reversed pair after a twenty-minute generation is avoidable.

After submission, report the job id and where to watch it. Claim completion only
once the backend reports done **and** the output file exists on disk. Verify with
`ffprobe`; extract frames only to check a specific seam or reported defect.

## Variants

One seed per take. Record segment, seed, job id, dialogue and output path in a
takes manifest so the editor can pick shots.

## Retakes and extensions

Retakes are an **LTX Director** capability. H3 has none — no retake, no
strength, no per-segment prompts. A shot that may need partial re-rolling should
stay on LTX for that reason alone.

- A retake **replaces a window; it cannot extend duration.**
- Start the retake *before* the artifact first appears. If an artifact already
  exists at the retake boundary, it usually persists into the new take.
- To extend, guide with the good video and anchor the new event with a matching
  image. Do not rely on a text-only tail.

## Failure handling

- If no backend is reachable, still deliver validated storyboard JSON and state
  exactly what is missing.
- Do not invent model or ComfyUI locations.
- Do not delete or recycle runs unless the user explicitly asks.
- Do not resubmit merely to poll an existing job.
- A client-side timeout is not a failed generation — check the backend's own
  history and output directory first.
