# slowmo-redraw-repair

An agent skill for repairing **structure collapse in fast-motion spans** of
generated video — the frames where a running character's hands, weapon or face
dissolve into semantic mush.

That damage is not motion blur. Deblur and upscale tools cannot recover
structure that the model never drew; both were tried and both failed. The fix is
to regenerate the span as **slow motion**, so per-frame displacement is small
enough for the model to draw coherent structure, then **drop frames to restore
the original speed**. Speeding up never reintroduces the mush.

The span is rebuilt as a chain of first-last-frame clips anchored on redrawn
keyframes, which keeps the result spliceable back into the untouched footage.

## Layout

```
SKILL.md                              Claude / Grok format
codex/SKILL.md                        Codex format (condensed)
codex/agents/openai.yaml              Codex interface manifest
references/backend-contract.md        The three operations a backend must provide
references/backend-camera-lab.md      Adapter: Camera Lab + ComfyUI (LTX)
```

Both variants describe the same method; only phrasing and density differ.

## Install

Symlink or junction the variant you want into your agent's skills directory.

```bash
# Claude / Grok
ln -s /path/to/slowmo-redraw-repair ~/.claude/skills/slowmo-redraw-repair

# Codex
ln -s /path/to/slowmo-redraw-repair/codex ~/.codex/skills/slowmo-redraw-repair
```

On Windows use a junction: `mklink /J <link> <target>`.

## Backends

The method is backend-agnostic. Only three operations are not: reading a source
job, running first-last-frame generation, and fetching a result. Everything else
is `ffmpeg` and `ffprobe`.

A Camera Lab + ComfyUI adapter ships in `references/`. To support another stack,
write an adapter covering those three operations plus its path restrictions,
prompt-syntax restrictions and concurrency caveats.

## Provenance

Every rule here comes from a failure observed while repairing real footage —
speed factors computed against the wrong denominator, blur peaks that turned out
to be clouds of dust, concurrently queued jobs silently overwriting each other's
anchors. The traps sections are the log of those, not hypotheticals.
