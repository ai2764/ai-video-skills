# Routing: which backend runs which segment

| mode | LTX | H3 local | H3 API |
|---|---|---|---|
| **i2v** single first frame | `ltx23_i2v` | `MiniMaxH3ImageToVideo` | `content:[first_frame]` |
| **flf** first + last frame | `ltx23_flf` | same + `last_frame` | `content:[first_frame, last_frame]` |
| **timeline** many keyframes, per-segment direction | `ltx_director_2` | — | — |

The two empty cells are permanent, not unimplemented.
`comfy/ldm/minimax/model.py:317` accepts a `pixel_index` of only `0` or
`frame_count - 1` and otherwise raises
`ValueError("only first/last keyframe anchors are supported")`. H3 has no
director timeline at the model level, and no per-segment local prompts, no
`strength` and no retake either.

The LTX column has two implementations behind it — Camera Lab when reachable,
ComfyUI direct otherwise. Routing does not distinguish them; the adapter layer
does.

## The four rules, in order

**1. Keyframe count picks the row.** 1 → `i2v`; 2 → `flf`; ≥3 → `timeline`.
With only one keyframe use i2v, not a one-segment Director run.

**2. Fast camera movement picks the column — and H3 must earn it.** Segments
whose adjacent keyframes show large displacement or a big angle change go to H3;
the rest stay on LTX. The judgement is **per segment**, not per storyboard.

H3 is roughly **an order of magnitude slower** than LTX for the same shot
(measured on one 6 s shot: LTX Director 1.3 min against 4.0–7.4 min for H3), and
both generate audio, so H3 is not a general-purpose upgrade. Send a segment to
H3 only when it needs something LTX cannot do:

- structure holding together through violent motion
- one unbroken take longer than an LTX segment comfortably carries
- an identity locked by reference images

A locked-off shot of someone talking has none of those. Default it to LTX.

**This judgement is the agent's, not the script's.** `fast_camera` is an *input*
to routing. Read the keyframes pairwise (see the thumbnail rules in `SKILL.md`)
and set it.

**3. Duration vetoes H3.** Under 4 seconds or over 15, the segment goes back to
LTX no matter how fast the camera moves. The API takes an integer 4–15 s; the
local stack is stricter still (`n % 17 == 5`, trained on 124–362 frames = 5.17
–15.08 s at 24 fps).

This rule fires more often than it looks. Fast action is frequently *short*
action — a leap, a lunge, a whip-pan — and those are exactly the shots that fall
under the floor. When it fires, the fix is not to stretch the shot to reach 4
seconds; it is to accept LTX for that beat, or repair it afterwards
(`slowmo-redraw-repair`).

**4. ≥3 keyframes plus fast camera splits into pairs.** H3 has no timeline, so
route the adjacent pairs as `flf` rather than leaving the span in Director —
fast camera movement is exactly where Director breaks down, and leaving it there
is choosing a known failure.

## A storyboard segment is not an H3 pair

A Director segment carries **one** guide image; an H3 `flf` shot needs **two**.
A segment's last frame is the *next* segment's guide image. The final segment
has no successor, so it is `i2v`.

## Cost

Only `h3_api` costs money — LTX and local H3 are electricity.

768P `$0.08`/s, 2K `$0.13`/s, input images free for the first 5 then `$0.04`
each. Print the estimate and wait for confirmation before submitting. Never
submit to a paid backend on your own initiative.
