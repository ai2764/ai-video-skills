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
| [slowmo-redraw-repair](skills/slowmo-redraw-repair/SKILL.md) | A fast-motion span has collapsed into mush — limbs, weapons or faces falling apart while running, fighting or whip-panning |

## Layout

```
skills/<name>/            Claude / Grok format
  SKILL.md
  references/
codex/<name>/             Codex format (condensed)
  SKILL.md
  agents/openai.yaml
  references/
```

Both variants of a skill describe the same method; only phrasing and density
differ. Keep them in step when editing.

## Install

Symlink the variant you want into your agent's skills directory.

```bash
# Claude / Grok
ln -s /path/to/ai-video-skills/skills/slowmo-redraw-repair \
      ~/.claude/skills/slowmo-redraw-repair

# Codex
ln -s /path/to/ai-video-skills/codex/slowmo-redraw-repair \
      ~/.codex/skills/slowmo-redraw-repair
```

On Windows use a junction: `mklink /J <link> <target>`.

## Backends

Skills here are written against a **backend contract** rather than a specific
stack: read a job, run a generation, fetch a result. Everything else — frame
analysis, speed restoration, stitching — is `ffmpeg`/`ffprobe` and works
anywhere.

Each skill ships the contract plus at least one adapter. A Camera Lab + ComfyUI
(LTX) adapter is included. To support another stack, write an adapter covering
the contract's operations plus that stack's path restrictions, prompt-syntax
restrictions and concurrency caveats.

## Adding a skill

1. Write `skills/<name>/SKILL.md` — the method, its traps, and what it needs
   from a backend.
2. Write `codex/<name>/SKILL.md` and `codex/<name>/agents/openai.yaml`.
3. Put backend-specific detail in `references/`, never in the method itself.
4. List it in the table above.
