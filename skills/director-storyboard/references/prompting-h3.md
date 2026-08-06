# Prompting H3

**This is a different contract from `prompting.md`. Do not mix them.** Every
LTX habit — negative prompts, `|`-separated local prompts, guide strength — is
either ignored or actively harmful here.

## The model can see the keyframe

H3's text encoder is Qwen3-VL-32B, and keyframes enter it as vision blocks
alongside the text (`<Picture 1>: <vision block> <prompt>`). The model already
knows what is in frame.

So **do not re-describe what is visible**. Write only what changes: action,
camera, light, sound. A paragraph re-establishing her wardrobe and the room
spends the prompt budget telling the model what it can already see.

## There is no chat template

Do not write instruction voice. "Generate a video of a woman turning" puts the
words *generate*, *video* and *of* into the picture description. Write the shot,
not a request for the shot.

## There is no negative conditioning at all

None. `I2V_GUARD`-style negative-word technique does not exist here. Express
every constraint positively:

| Instead of | Write |
|---|---|
| no full body | only limbs enter frame, the torso stays out of shot |
| don't show her face | the camera stays behind her head throughout |
| no camera shake | the camera is locked off on a tripod |

The graph keeps a `ConditioningZeroOut` placeholder with `cfg=1.0` where a
negative would go. Nothing you write there reaches the model.

## Name multiple references explicitly

Refer to supplied material as `<Picture i>`, `<Video k>`, `<Audio j>`, numbered
from 1 **within each type**.

## Length must be paid for in action

Lengthening a shot without writing more action leaves the model to invent
something for the empty time. If you go from 6 s to 12 s, write what fills the
extra six seconds. This is the same failure mode as naming a subject that is not
in the frame: unspecified time gets filled with invention.

## What H3 does not have

No per-segment local prompts — the conditioning is Qwen3-VL's hidden state over
the whole text, with no time index. "At second 3 she reloads, at second 7 the
creature lunges" is not directable; later actions in the prompt merely tell the
model roughly what happens, not when.

No `strength`. No retake. No negative prompt.

If a shot needs several timed events, or needs one span re-rolled while the rest
stays, it belongs on LTX Director, not H3.

## One prompt holds one running instruction

Observed across two takes of the same shot, same refs, same seed:

| Prompt asked for | What came out |
|---|---|
| camera pulls back **and** a ridge chases her | pull-back happened; the ridge read as static terrain |
| pack closes on her **and** camera pulls back | chase was perfect; the camera never pulled back |

Two instructions that both have to run for the whole shot, and H3 keeps one.
This follows from having no time index: it cannot allocate "camera does this
throughout while that also happens throughout."

**Decide which one the shot is actually about and write only that.** If you
genuinely need both, the camera move belongs to LTX Director, or you anchor the
framing change with a `last_frame` instead of describing it.

Staged actions in sequence are different and do work — see below.

## Write pursuit as closing distance, not as a direction

The single highest-value fix found so far.

- ✗ `Behind her a ridge of earth ploughs forward, chasing her line` — the model
  rendered a furrow in the ground. A position word describes *where a thing is*,
  which is a property of terrain.
- ✓ `The gap between them and her shrinks from shot to shot: they start far back
  on the slope, then they are on the flat behind her, then the leading one is
  close enough that its shadow reaches her heels, and it keeps closing`

Give a quantity that changes across named waypoints. The same trick works for
anything relational: looming, receding, closing in, falling behind.

## Sequenced actions work; their timing does not

`Then the mound bursts open and the creatures tear out of the soil` landed at
about 6.7 s of a 10 s shot — correct order, good placement, **not controllable**.
`then` is a hint about ordering that the model resolves however it likes.

So: stage two beats if you must, but never promise a cue point. If a beat has to
land on a specific frame, that is a `last_frame` anchor or two separate shots.

## Screen-space directions are understood

`a mound swells up at the very bottom edge of the frame, close to the camera,
and ploughs up the screen away from us and toward her` produced exactly that.
Frame-relative language (bottom edge, up the screen, toward camera) is read
reliably — use it instead of world-relative language when composition matters.

H3 generates native stereo audio, and the voice is encoded fresh per clip — a
character's voice changes between shots. Write sound cues if you want them, but
expect to strip the track when cutting H3 segments into an otherwise silent
edit. See `backend-minimax-api.md`.
