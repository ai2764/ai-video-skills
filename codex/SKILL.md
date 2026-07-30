---
name: slowmo-redraw-repair
description: Repair mangled, smeared or dissolving structure in a fast-motion span of generated video — limbs, weapons or faces falling apart during running, fighting or whip-pan shots. Use for motion damage repair, slow-motion regeneration, keyframe redraw chains, or $slowmo-redraw-repair.
---

# Slow-Motion Redraw Repair

Fast motion breaks video models: at large per-frame displacement the model never
draws coherent structure. This is not motion blur — deblur and upscale tools
cannot recover structure that was never drawn. Regenerate the span in slow
motion, then drop frames to restore speed.

Reply and reason in English while running this skill unless asked otherwise.

## Do not use when

Shutter smear on coherent structure (use a deblur IC-LoRA), face identity drift
(reference-image v2v pass), or a merely soft video (upscaler).

## Workflow

1. **Settle the redraw question first.** Check your tool list for an
   image-generation tool. Without one, extract frames and hand them over. With
   one, ask whether to redraw. Redrawing requires the character design sheets —
   ask for them if absent.
2. **Read the source job.** Accept a backend job id or a batch id. Obtain the
   video, prompts, anchor times with guide images, seed, resolution, fps.
3. **Locate damage and pick frames.** Score with
   `blurdetect=block_pct=80` (higher = blurrier). Window per anchor gap,
   subdividing when N exceeds the gap count; single-anchor jobs split evenly.
   `N = ceil(span / 1.5)` unless the user says otherwise. Blur peak locates
   damage but does not choose the anchor — dust and debris frames score highest
   and cannot be redrawn. Pick a frame that is damaged **and** legible as a
   story beat; legibility wins ties. Name them `redraw_NN_t<sec>s.png`.
4. **Redraw preserving composition.** Repair the extracted frame against the
   design sheets — same framing, angle, pose, background. A reimagined shot is
   worse than none: the model then tears between the video's motion and the
   image's framing.
5. **Chain first-last-frame pairs.** Anchors are span start, the N redraws, span
   end; that is N+1 pairs. Take end anchors from the job's own guide images when
   they exist, otherwise extract — real frames at both ends are what let the
   result splice back in. Check boundary frames for damage too.
6. **Choose a slow factor per pair** by action complexity — 3× a single beat,
   5× displacement plus one action, 6–8× compound motion — then floor it:
   `factor = max(complexity, 3.0 / story_span)`. Request
   `story_span × factor`, within the backend's safe length. When two anchors
   differ in shot scale, write the camera move into the prompt or the model will
   cut or warp.
7. **Restore and stitch.** Measure each clip
   (`ffprobe -show_entries format=duration`) — backends overshoot the request.
   Speed each by its own `actual / story_span`, concat, then apply one global
   correction for frame-rounding drift. Inspect every seam.

Re-roll disappointing takes with a new seed rather than rewriting prompts; only
mid-pair material actually varies.

## Backend

Three operations are backend-specific: read a job, run first-last-frame
generation, fetch a result. See `references/backend-contract.md`, then the
adapter for your stack (`references/backend-camera-lab.md`).

Everything else is `ffmpeg`/`ffprobe`.

## Traps

- Speed factor must divide by the **story span the anchors cover**, not the
  requested duration and not the target length.
- Never speed up footage generated at normal speed.
- 2× or less reads frantic after restore.
- Verify a changed parameter reached the backend before drawing conclusions.
- A client-side timeout is not a failed generation — check the backend's history
  and output directory.
