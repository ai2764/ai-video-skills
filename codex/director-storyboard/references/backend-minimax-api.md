# Adapter: MiniMax H3 official API

Hosted H3. The one backend that does not need a GPU — and the only H3 route
available where the Community License does not grant local use (see
`backend-h3-local.md`).

## Configuration

Both values come from the environment, and **they must be from the same
region**:

| Region | `MINIMAX_BASE_URL` | Key from |
|---|---|---|
| International (default) | `https://api.minimax.io` | platform.minimax.io |
| Mainland China | `https://api.minimaxi.com` | platform.minimaxi.com |

`MINIMAX_API_KEY` has no default. A mismatched pair returns
`invalid api key (2049)`, which reads like a bad secret and is actually a bad
host.

**Verify a key without spending anything**: query a task id that does not
exist.

```bash
curl -s -H "Authorization: Bearer $MINIMAX_API_KEY" \
  "$MINIMAX_BASE_URL/v2/query/video_generation/probe-nonexistent"
```

- `record not found (1000)` → the key is valid for this host
- `invalid api key (2049)` → wrong host for this key, or a bad key

Observed: a `sk-api-…` pay-as-you-go key authenticated on `api.minimax.io` and
was rejected by `api.minimaxi.com`. Token Plan subscription keys (`sk-cp-…`) are
a separate credential and are not interchangeable with pay-as-you-go keys.

## 1. Probe capability

`MINIMAX_API_KEY` present → the i2v and flf cells are available. There is no
capability endpoint; a key that authenticates may still have no credit (below).

## 2. Submit a generation

`POST {base}/v2/video_generation`

| Field | Value |
|---|---|
| `model` | `"MiniMax-H3"` |
| `duration` | integer **4–15** seconds |
| `resolution` | `"768P"` or `"2K"` — nothing else |
| `ratio` | an aspect string, or `"adaptive"` with image input |
| `content[]` | multimodal array; items carry `type` and `role` |

`content` items: `{"type":"text","text":…}` (≤7000 chars) and
`{"type":"image_url","image_url":{"url":…},"role":…}`. Roles used here are
`first_frame` and `last_frame`; the API also defines `reference_image`,
`reference_video`, `reference_audio` and `base_video`.

Limits: 0/1/2 first-and-last frames, edges 256–5760, aspect 2:5–5:2, images
JPG/PNG/WEBP/HEIC/HEIF ≤30 MB, request body ≤64 MB.

### Local files work — as base64

The docs only show URLs. **A `data:image/png;base64,…` URI is accepted**:
verified against the live API, where such a request passed validation and
reached billing. `image_reference()` in `h3_api.py` inlines local paths
automatically. Watch the 64 MB request ceiling — base64 inflates a file by about
a third (a 1.88 MB PNG became a 2.51 MB URI).

### Never send LTX-shaped fields

No `negative_prompt`, no `strength`, no `|`-separated local prompts. H3 has no
negative conditioning, so those words do not get ignored — they get encoded as
picture content. See `prompting-h3.md`.

## 3. Fetch the result

`GET {base}/v2/query/video_generation/{task_id}`, roughly every 10 s. On success
the download URL is at `task.content.url` (served from
`video-product.cdn.minimax.io`). Terminal failure states are `failed` and
`cancelled` — report them, do not retry into more spend.

A polling timeout is **not** a lost job. Keep the task id and query it later.

## Measured behaviour

From a real 4-second 768P i2v run:

| Requested | Got |
|---|---|
| `resolution: "768P"`, `ratio: "16:9"` | **1344×768** (1.75, not exactly 16:9) |
| `duration: 4` | **4.458 s**, h264 + aac |

**Always measure the output**; do not report the requested numbers.

## Audio is stripped by default

H3 generates native stereo audio and **encodes a fresh voice per clip**, so a
character's voice changes from shot to shot. Dropping H3 segments into an
otherwise silent LTX cut then produces sound that appears and vanishes. Default
to `strip_audio()` (verified: aac stream → zero audio streams) and lay audio in
post. `--keep-audio` overrides.

## Error shapes

Two of them. `base_resp` on some paths, and a top-level object on 4xx/5xx:

```json
{"type":"error","error":{"type":"insufficient_balance_error",
 "message":"insufficient balance (1008)","http_code":"402"}}
```

| Code | Meaning | Not to be confused with |
|---|---|---|
| 1000 | record not found | — |
| 1008 | **insufficient balance** — account has no credit | a key problem |
| 2049 | invalid api key — usually wrong host for the key | a balance problem |

A balance rejection costs nothing and generates nothing.

## Pricing

768P `$0.08`/s, 2K `$0.13`/s. Input images: first 5 free, then `$0.04` each.
Input audio free. 768P→2K regeneration `$0.05`/s.

Print the estimate and get confirmation before submitting.
