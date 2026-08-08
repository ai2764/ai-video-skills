# ai-video-skills

Agent skills for producing and repairing AI-generated video.

Each skill encodes a working method — what to do, in what order, and which
mistakes silently ruin the result. The rules come from failures observed on real
footage, not from theory: speed factors computed against the wrong denominator,
blur peaks that turned out to be clouds of dust, concurrently queued jobs
overwriting each other's inputs. The traps sections are the log of those.

## Skills

| Skill | Use when |
|---|---|
| [director-storyboard](skills/director-storyboard/SKILL.md) | A script plus keyframes needs to become a Director timeline — ordering frames, writing global and per-segment prompts, bridging keyframes, then routing each segment to LTX or MiniMax H3 and running it. Both models generate their own audio, so dialogue and effects come out of the same pass as the picture |
| [slowmo-redraw-repair](skills/slowmo-redraw-repair/SKILL.md) | A fast-motion span has collapsed into mush — limbs, weapons or faces falling apart while running, fighting or whip-panning |

## Layout

```
skills/<name>/            Claude / Grok format
  SKILL.md                the method
  references/             backend adapters, prompt contracts, operations
codex/<name>/             Codex format (condensed)
  SKILL.md
  agents/openai.yaml
  references/
scripts/                  stdlib-only helpers, shared by both variants
workflows/                API-format graphs the skills fill in
tests/                    pytest, shared across skills
```

Both variants of a skill describe the same method; only phrasing and density
differ. Keep them in step when editing.

`scripts/` and `workflows/` live at the root rather than inside a skill so the
two variants run **one** copy instead of two that drift apart. Commands inside
a `SKILL.md` are written relative to the repository root, which from a skill
directory is `../..`.

## Requirements

`ffmpeg` and `ffprobe` on PATH, and Python 3 — the scripts use the **standard
library only**, no install step.

Everything else is optional and detected at runtime, so a skill degrades to what
your machine actually has:

| For | You need |
|---|---|
| Running LTX shots | ComfyUI with the LTX nodes |
| Running MiniMax H3 locally | ComfyUI with the H3 nodes **and** the `minimax` text encoder weights |
| Running H3 through the hosted API | `MINIMAX_API_KEY`, plus `MINIMAX_BASE_URL` matching the key's region |
| Nicer LTX staging and audio handling | Camera Lab in front of ComfyUI (optional) |

`director-storyboard` ships a probe that reports which of these are present and
why the rest are unavailable:

```bash
py -3 scripts/probe_backends.py
```

Writing a storyboard needs none of it — only running one does.

## Install

Symlink the variant you want into your agent's skills directory.

```bash
# Claude / Grok
ln -s /path/to/ai-video-skills/skills/<name> ~/.claude/skills/<name>

# Codex
ln -s /path/to/ai-video-skills/codex/<name> ~/.codex/skills/<name>
```

On Windows use a junction: `mklink /J <link> <target>`.

The link points into the clone, so `../..` from the linked directory still
lands on the repository root and the shared `scripts/` and `workflows/` stay
reachable. Keep the clone in place — a copied-out `SKILL.md` has no helpers.

## Backends

Skills here are written against a **backend contract** rather than a specific
stack: read a job, run a generation, fetch a result. Everything else — frame
analysis, speed restoration, stitching — is `ffmpeg`/`ffprobe` and works
anywhere.

Each skill ships the contract plus at least one adapter. Adapters for ComfyUI on
its own and for Camera Lab + ComfyUI (LTX) are included — **ComfyUI alone is
enough**; Camera Lab is used when present because its staging and audio handling
are already tuned. To support another stack, write an adapter covering the
contract's operations plus that stack's path restrictions, prompt-syntax
restrictions and concurrency caveats.

Adapter equivalence is not assumed. `director-storyboard` pins it with a golden
`api_prompt.json` captured from a real Camera Lab run: the graph the ComfyUI
adapter builds must match it exactly, and that has been verified end to end
against a live ComfyUI.

Where more than one *model* can run a shot, a routing layer decides per segment
rather than per project — see `skills/director-storyboard/references/routing.md`.
Backends that bill per second never run without an explicit confirmation.

## Tests

```bash
py -3 -m pytest
```

158 tests, none of which touch a GPU or the network. The ones that matter most
pin adapter equivalence against captured fixtures and pin each routing rule
individually, so a rule cannot be changed by accident.

Requires `pytest` and, for the thumbnail tests, `ffmpeg`/`ffprobe` on PATH.

## Adding a skill

1. Write `skills/<name>/SKILL.md` — the method, its traps, and what it needs
   from a backend.
2. Write `codex/<name>/SKILL.md` and `codex/<name>/agents/openai.yaml`.
3. Put backend-specific detail in `references/`, never in the method itself.
4. Put helpers in the shared root `scripts/` and graphs in root `workflows/` —
   never inside a skill, where only one variant could reach them.
5. List it in the table above.

Keep the method free of any particular production: no film titles, character
names or project paths. A rule earned on one shoot is only worth writing down in
the form that transfers — "a reference constrains the angles and expressions it
actually contains", not "we needed another photo of her".

`docs/specs/` and `docs/plans/` hold the design and implementation history for
anyone who wants to know why something is shaped the way it is.
