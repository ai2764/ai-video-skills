# Adapter: ComfyUI direct

ComfyUI at `http://127.0.0.1:8188`, nothing in front of it. This is the adapter
that makes Camera Lab optional.

The skill ships the graph (`workflows/ltx_director_2.api.json`, already in API
format) and fills it in. That export matches a real Camera Lab run node for
node — 32 nodes, one `LTXDirector`, two `LTXDirectorGuide` — and the filled
`timeline_data` is byte-identical to what Camera Lab produces. The golden
fixtures under `tests/fixtures/` are what keep it that way.

## 1. Probe capability

```bash
py -3 scripts/probe_backends.py
```

Reads `GET /object_info`:

| Key present | Lights |
|---|---|
| `LTXDirector` | timeline, i2v, flf |
| all four of `EmptyMiniMaxH3LatentAV`, `MiniMaxH3ImageToVideo`, `MiniMaxH3ReferenceToVideo`, `MiniMaxH3SigmaShift` **and** `minimax` in `CLIPLoader`'s `type` list | H3 local |

H3 nodes present but no `minimax` in `CLIPLoader` means the nodes are installed
and the text-encoder weights are not. Report that, do not light the cell.

## 2. Submit a generation

Two steps, both in `scripts/comfy_backend.py`.

**Stage the guides.** Images must go through `POST /upload/image` first — a path
on your disk is not a path ComfyUI can load. `stage_images()` uploads each
segment's `image_path` and returns the names to reference, keyed by 1-based
segment index.

**Fill the graph.** `fill_director_graph()` writes the `LTXDirector` node's
inputs from a director timeline.

### The segment count lives in one string

`LTXDirectorGuide` is **fixed at two nodes** — they are the two sampling
stages, not one node per segment. Every segment lives inside the `LTXDirector`
node's `timeline_data` input, which is a JSON *string*:

```json
{"segments": [
  {"id": "s14_tear_eagle", "type": "image", "label": "segment 1",
   "start": 0, "length": 72, "prompt": "...",
   "imageFile": "camera_lab_..._timeline_01.png", "strength": 0.84}
 ],
 "audioSegments": []}
```

`start` is the cumulative frame position, `length` the segment's frame count.
**No node needs to be added or removed to change the segment count.**

### Fill, do not replace

Use `.update()` on the node's `inputs`. `model`, `clip` and `audio_vae` are
links to other nodes (`["10", 0]` form) and must survive untouched. Replacing
the whole `inputs` dict silently disconnects the graph.

### Separators are not interchangeable

- `local_prompts` — joined with **`|`**
- `segment_lengths` — joined with **`,`**
- `guide_strength` — joined with **`,`**

**Never put `|` inside a prompt.** `LTXDirector` splits on it and you get
`Number of segment_lengths (2) must match number of local prompts (3)`.

Take these joined strings from the timeline rather than rebuilding them; that
is where the two backends drift apart.

### Width and height pass through

By the time a timeline exists, the dimensions are already aligned. Do not align
again inside the filler. `align_dimension()` in `director_timeline.py` is for
callers building a run from a raw request.

## 3. Fetch the result

`GET /history/{prompt_id}` → `outputs` → filenames. They arrive under different
keys depending on the save node, so check `gifs`, `videos`, `images` and
`audio`. An empty list means still running, not failed.

## Traps

**Node ids are numbers, not strings.** When inserting a node, take `max()`
numerically: `max("10", "9") == "9"` string-wise, which silently overwrites node
10. The error then surfaces at a *downstream* node ("received IMAGE, expected
LATENT"), nowhere near the cause.

**Autogrow inputs need dotted paths.** Inputs like `ref_images.ref_image_0` must
be written with the full path. A bare `ref_image_0` **passes `/prompt`
validation** (returns `node_errors: {}`) and only explodes at execution time
with `execute() got an unexpected keyword argument` — because
`build_nested_inputs()` only reassembles keys registered in `dynamic_paths`.

**Concurrent runs can share staged filenames.** If two jobs stage guides under
the same names, they overwrite each other and every clip samples whichever
staged last. The symptom is a batch of clips that all look the same despite
different anchors. Check with:

```bash
ls "<ComfyUI>/input/" | grep _source
```

Names should carry a per-run prefix.
