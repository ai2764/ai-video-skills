# Generating audio: dialogue and effects

Video models that produce a synchronised audio track can be used as an audio
source: generate a short take and keep only the track. Read this when the
deliverable is sound rather than picture.

## Drop the resolution — the picture is a by-product

Nothing about the audio needs a large frame. Generating small and square is an
order-of-magnitude difference: a 3 s clip at 512×512 finished in ~1 min against
~7 min for the same length at delivery resolution. Keep duration short too; a
vocalisation needs 3 s, not 6.

Extract the track afterwards:

```bash
ffmpeg -v error -y -i take.mp4 -vn -acodec pcm_s16le -ar 48000 out.wav
```

## The voice changes between takes

Each clip is voiced independently. Two takes of the same character will not
sound like the same person, and there is no seed or setting that fixes it.

| Material | Safe to generate as separate takes? |
|---|---|
| Non-verbal effort, pain, breath, shouts | **Yes** — timbre differences do not read as a different person |
| Named words, whole lines, anything a viewer follows as speech | **No** — the change is obvious, especially in continuous dialogue |

So a fight vocalisation library can be batched freely. A monologue that exceeds
one take's duration cannot: either shorten it to fit a single take, or generate
the picture and lay a separately produced voice track over it.

## Ask for a dry, close signal

Library effects get cut into other shots, so ambience baked into them is a
liability. State the mix positively — models that lack negative conditioning
have no other way to be told:

> her voice close and dry and forward in the mix, no music, no room reverb, no
> other sound apart from her and the small impacts of the fight

## Derive the list from the script, not from a generic list

Read the shot list and pull the moments that actually need a sound: the
scripted lines first (they are usually written into the shot descriptions), then
the physical beats that imply a vocalisation — strikes landing, being knocked
down, lifting something heavy, running out of breath, a startled recoil.

Match the language to what the characters speak elsewhere in the film. Mixing
vocalisations from another language into a performance reads as a different
person, the same way a timbre change does.
