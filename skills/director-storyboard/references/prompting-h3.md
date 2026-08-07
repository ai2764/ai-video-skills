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

## Write the performance, not the mechanics

The most common way a shot comes out dead is a prompt that lists muscle
movements. "The brow softens, the jaw unlocks, the eyelids lift" describes a
face moving; it does not tell the model what the person is *doing*.

Write the intent, then let the mechanics follow:

| Mechanics | Performance |
|---|---|
| her brow softens, her jaw unlocks | she is enduring this, not just suffering it — jaw clamped against a sound she refuses to let out |
| her eyes open | behind the lids she is not there yet, eyes unfocused; then the pupils snap down and catch, and she is suddenly present |
| he salutes | the looseness drops out of him in an instant and the salute is crisp, no performance in it |

This matters more, not less, when the face is hidden. Under a helmet, a mask, a
visor or sunglasses, the performance has to move into breathing, head angle,
shoulders and hands — name those explicitly or the shot will be inert.

## Establish what the character can do before writing what they do

Check the character's state at this moment in the story before writing a single
reaction. Blinded, deafened, injured, restrained, masked, unconscious — each one
closes off a channel, and writing a reaction through a closed channel produces a
shot that contradicts the story.

A character who cannot see must react by hearing and touch: the light going, the
sound arriving, the ground shaking — head turning to aim an ear rather than a
face. Written as a visual reaction instead, they will look straight at the thing
they cannot see.

## Every party to an action needs its own performance

If a shot has someone acting and someone receiving, write both. A prompt that
covers the shooter — muzzle flash, recoil, spent cases — and says nothing about
what is being shot will produce a target that stands there unaffected.

Give the receiving side its own beats: impact, recoil, flinch, shielding,
retreat, sound. The same applies to machines and environments — something being
struck, dragged or torn should visibly resist and fail.

## The state of an action controls how much of it you get

The model reads the aspect of the verb. `The muzzle flash dies and the last case
spins away` describes a burst that has already finished, and yields exactly one
shot. To get a sustained action, write it as ongoing and mark its end
explicitly: "the muzzle flashing four or five times in quick succession... only
then does she stop firing".

## Do not use speech verbs for description

Reserve "say / read / tell / whisper / call" for lines that are actually
spoken, and always with the line in quotes. A speech verb followed by a clause
in the description will be spoken aloud — H3 has no chat template, and quotes
are the only signal separating dialogue from narration.

Observed: `as she reads that it is gone` produced spoken dialogue in the output.
Write `her eyes scan the dark indicators once` instead.

When only one line should be spoken, say so: "She speaks exactly one word and no
more... that single word is the only speech in the entire shot."

## Count the words before choosing a duration

Natural conversational delivery runs about 150 words per minute — roughly 2.5
words per second. Multiply before committing:

| Words | Natural duration |
|---|---|
| 20 | ~8 s |
| 37 | ~15 s |
| 78 | ~31 s |

H3 tops out at 15 s, so anything past ~37 words needs splitting — and splitting
dialogue across takes changes the voice (see below). Compressing instead of
splitting produces newsreader pace, which is usually not what was asked for.

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
