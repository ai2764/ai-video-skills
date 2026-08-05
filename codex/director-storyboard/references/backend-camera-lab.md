# Adapter: Camera Lab

Camera Lab server at `http://127.0.0.1:1234`, ComfyUI behind it.

Prefer this over the ComfyUI-direct adapter when it is running: its image
staging, subtitle bottom-matte handling and audio segment processing are
already tuned. The graph both produce is the same.

## 1. Probe capability

Server reachable, and the workflow id present in its `WORKFLOWS` registry:

| id | mode |
|---|---|
| `i2v_official_local` | `i2v` |
| `flf_ttp_control` | `flf` |
| `ltx_director_2` | `director_ref` |

## 2. Submit a generation

`POST /api/run`. For a Director timeline:

```json
{
  "workflow_id": "ltx_director_2",
  "camera_move": "director_ref",
  "global_prompt": "A continuous cinematic shot ...",
  "segments": [
    {"id": "s14", "type": "image", "duration": 3.0,
     "image_path": "<abs path under tasks/>", "strength": 0.84}
  ],
  "width": 1280,
  "height": 704,
  "seed": 620,
  "negative_prompt": "..."
}
```

For a single first/last-frame pair, `workflow_id: "flf_ttp_control"` with
`source_path`/`end_path` **and** `source_image`/`end_image` both set — the
server reads one for validation and the other for staging.

### Path restriction

Media must live under Camera Lab's `tasks/` tree. Anything else is rejected:

```
HTTP 500 {"error": "C:\\Users\\AIBOX\\Downloads\\motion-fix\\1.png"}
```

Copy guides into `tasks/camera_lab_uploads/` first.

## 3. Fetch the result

`GET /api/batches/<batch_id>` → `runs[0].status` / `.video`.

**`status: "error", error: "timed out"` is a client-side timeout, not a
failure.** Heavy jobs exceed the server's wait window while ComfyUI keeps
going. Check:

```bash
curl -s "http://127.0.0.1:8188/history/<prompt-id>"     # status_str: success?
ls  "<ComfyUI>/output/camera_lab/<batch-id>/"           # the file is usually here
```

A genuine failure carries `execution_error` with a node id and exception
message.

## Run artifacts worth knowing about

Each run writes `tasks/camera_lab_runs/<batch-id>/01_director/`:

- `api_prompt.json` — the exact graph submitted to ComfyUI
- `director_timeline.json` — the normalised timeline
- `submit.json`, `history.json`

`api_prompt.json` is the ground truth for verifying any other adapter. That is
where this skill's golden fixtures came from.

## Resolution snaps to a multiple of 64

The server halves each dimension, aligns to 32, doubles back. `720 → 704`,
`736 → 768`. Exact 1280x720 is unreachable — generate 1280x704, or 1280x768 and
crop.

## Prompt rule

**Never put `|` in a prompt.** `LTXDirector` splits local prompts on it →
`Number of segment_lengths (2) must match number of local prompts (3)`.
