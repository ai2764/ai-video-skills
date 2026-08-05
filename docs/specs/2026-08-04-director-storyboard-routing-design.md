# director-storyboard：迁入 ai-video-skills，加入 H3 与后端路由

设计日期：2026-08-04

## 背景

`director-storyboard` 现在住在 `camera-lab` 仓库里（`.claude` / `.codex` /
`.grok` 三份），并且把执行写死到 Camera Lab 的 `/api/run`。三件事要求它改形：

1. **要让没有 Camera Lab 的人也能用**。只要装了 ComfyUI 就该跑得起来。
2. **要能调 MiniMax-H3**。快速运镜段落是 LTX Director 的失效区（结构崩坏正是
   `slowmo-redraw-repair` 的触发场景），H3 在连续大幅运动上更稳。
3. **H3 要能走 API，而且由使用者选**。H3 Community License（2026-08-02 生效）的
   `Applicable Territory` 排除美国、欧盟、英国、韩国；在这些辖区不授权使用、运行、
   修改、分发权重，连本地跑出的输出都不授权使用，自托管需单独向
   `model@minimax.io` 申请。官方 API 走 platform.minimax.io 的平台服务条款，是
   另一份文件，不受该条款约束。但 skill 不替使用者假定所在地，本地与 API 都要支持。

## 目标

- skill 迁到 `ai-video-skills`，按该仓库既有的 backend contract + adapter 组织。
- 新增 ComfyUI 直连 adapter，使 Camera Lab 成为可选而非必需。
- 前置一个工作流路由层：i2v / flf / 时间轴 三种模式 × LTX / H3本地 / H3 API 三种后端。
- 路由依据来自使用者机器上的 ComfyUI 实际配置，以及 skill 对关键帧的判读
  （主要判据是快速运镜）。
- 分派前报账，不自动烧钱。

## 非目标

- 不做 H3 的 reference-to-video（ref2va）路径。
- 不改 `camera-lab` 的服务端代码。Camera Lab adapter 只是把现有调用方式写成
  文档。（`camera-lab` 里那三份旧 skill 目录的清理是本设计的收尾动作，见"仓库
  形态"，除此之外不动该仓库。）
- 不做 WAN2.2 Bernini 系列工作流。

## 仓库形态

沿用 `slowmo-redraw-repair` 的布局：

```
skills/director-storyboard/
  SKILL.md                       方法本身，backend-agnostic
  references/
    backend-contract.md          后端契约
    backend-comfyui.md           ComfyUI 直连 adapter（新）
    backend-camera-lab.md        Camera Lab adapter（由现有 SKILL.md 提炼）
    backend-minimax-api.md       MiniMax H3 API adapter（新）
    routing.md                   路由表与规则
    prompting.md                 LTX 提示词契约（沿用现有）
    prompting-h3.md              H3 提示词契约（新，与 LTX 是两套）
    storyboard.schema.json       沿用现有
  workflows/
    ltx_director_2.api.json      自带的 API-format 图
    ltx23_i2v.api.json
    ltx23_flf.api.json
    h3_i2v.api.json
    h3_flf.api.json
  scripts/
    probe_backends.py
    run_storyboard.py
codex/director-storyboard/       Codex 变体（同法，密度更低）
  SKILL.md
  agents/openai.yaml
  references/
```

`camera-lab` 里现有的三份 skill 目录在迁移完成后删除，README 的 Skills 表加一行。

## 路由表

| 模式 | LTX | H3 本地 | H3 API |
|---|---|---|---|
| **i2v** 单首帧 | `ltx23_i2v` | `MiniMaxH3ImageToVideo` | `content:[first_frame]` |
| **flf** 首尾帧 | `ltx23_flf` | 同上 + last_frame | `content:[first_frame, last_frame]` |
| **时间轴** 多关键帧分段指挥 | `ltx_director_2` | ✗ | ✗ |

右下两格永久为空，不是未实现：`comfy/ldm/minimax/model.py:317` 中 `pixel_index`
只接受 `0` 和 `frame_count - 1`，其余抛
`ValueError("only first/last keyframe anchors are supported")`。H3 在模型层面没有
导演台，也没有分段局部提示词、`strength`、retake。这是路由表的地基，不是取舍。

**LTX 列内含两条子路径**，对使用者是同一列，对 adapter 是两个实现：装了 Camera
Lab 就走它，没装就走 ComfyUI 直连（见下方两个 adapter 小节）。路由规则不区分这
两条——只有 adapter 层区分。

LTX 三条对应 Camera Lab `WORKFLOWS` 注册表（`camera_lab_server.py:342`）里的
`i2v_official_local` / `flf_ttp_control` / `ltx_director_2`，`mode` 分别为
`i2v` / `flf` / `director_ref`。ComfyUI adapter 自带等价的 API-format 图。

## 路由规则

skill 按顺序过这四条：

1. **关键帧数量定行**：1 张 → i2v；2 张 → flf；≥3 张 → 时间轴。
   （与既有结论一致：只有一张关键帧时走 i2v，不要用单段 Director，判据是帧数
   不是时长。）
2. **快速运镜定列**：判读相邻关键帧之间的位移与视角变化，变化大的段落走 H3 列，
   其余留 LTX 列。粒度是**逐段**，只把快运镜那几段发给 H3。
3. **时长下限一票否决**：段落 < 4 秒强制回 LTX。H3 API 的 `duration` 是整数
   4–15 秒；H3 本地更严（帧数 `n % 17 == 5`，训练区间 124–362 帧 =
   5.17–15.08 秒）。短段凑不出。
4. **≥3 张关键帧且判为快运镜**：按相邻帧对拆成多个 H3 flf 调用，而不是整条留在
   Director。理由是快运镜正是 Director 会崩的地方，留着等于明知会崩。

## 后端契约

三个操作，其余都是 `ffmpeg`/`ffprobe`。

### 1. 探测能力

**In:** 无（或后端 base URL）。
**Out:** 路由表里哪些格子可用，以及不可用的原因。

skill 不在开场问"本地还是 API"，先探测再问。

### 2. 提交一次生成

**In:** 模式（i2v / flf / 时间轴）、关键帧路径、每段 prompt、时长、尺寸、seed；
时间轴模式另加每段的 `start` / `length` / `strength`。
**Out:** 一个 job id。

### 3. 取结果

**In:** job id。**Out:** 文件路径与真实时长。

客户端超时不等于生成失败——先查后端自己的历史与输出目录，再考虑重试。（沿用
`slowmo-redraw-repair` 契约里的这条。）

## Adapter：ComfyUI 直连

这是"有 ComfyUI 就能用"的那条。

**探测**：拉 `GET /object_info`。

| 判据 | 点亮 |
|---|---|
| 有 LTX Director 节点 | 时间轴 / LTX |
| 有 LTX i2v / flf 所需节点 | i2v、flf / LTX |
| 有 `EmptyMiniMaxH3LatentAV`、`MiniMaxH3ImageToVideo`、`MiniMaxH3ReferenceToVideo`、`MiniMaxH3SigmaShift` 四个节点，**且** `CLIPLoader` 的 type 下拉里有 `minimax` | i2v、flf / H3 本地 |

节点在但 `CLIPLoader` 无 `minimax`，说明权重没装，报"缺权重"而不是点亮。

**提交**：把自带的 `workflows/*.api.json` 填参后 `POST /prompt`。时间轴模式下，
LTXDirector 节点吃的是一个 `segments` JSON 数组，每项形如：

```json
{"id": "...", "type": "image", "label": "segment 1", "start": 0,
 "length": 121, "prompt": "...", "imageFile": "...", "strength": 0.82}
```

这是 `camera_lab_server.py:1183` `director_reference_timeline_segments` 的输出
形状。**不需要动态增删节点图**，填数组即可——与 `run_h3_plan.py` 填 H3 图同构。

**取结果**：`GET /history/{prompt_id}`，从输出目录取文件。

**注意事项**：图片必须先拷进 ComfyUI 的 `input/`；节点号取 max 时要按数值比较，
不是字符串（`max("10","9") == "9"` 会覆盖 10 号节点，且报错出现在下游而非现场）；
autogrow 类输入必须用点号全路径（如 `ref_images.ref_image_0`），裸名能通过
`/prompt` 校验但执行时才炸。

## Adapter：Camera Lab

保留现有通道：`POST /api/run`（`workflow_id=ltx_director_2` 等），状态查
`/api/batches/<batch_id>`，上传件放 `tasks/camera_lab_uploads/`。尺寸规则是每边
折半后对齐到 32。探测方式是服务是否可达 + `WORKFLOWS` 列表。

装了 Camera Lab 时优先用它跑 LTX（它的图片预处理、字幕底边 matte、音频段处理已经
调过）；没装则退到 ComfyUI 直连。

## Adapter：MiniMax H3 API

- 创建：`POST {MINIMAX_BASE_URL}/v2/video_generation`
- 查询：`GET {MINIMAX_BASE_URL}/v2/query/video_generation/{task_id}`，约 10 秒一次
- 鉴权：`Authorization: Bearer {MINIMAX_API_KEY}`
- 成功时从 `task.content.url` 取下载地址；终止态还有 `failed` / `cancelled`

请求体：

| 字段 | 值 |
|---|---|
| `model` | `"MiniMax-H3"` |
| `duration` | 整数 4–15（秒） |
| `resolution` | `"768P"` 或 `"2K"` |
| `ratio` | 比例档位或 `"adaptive"`（有图输入时用 adaptive） |
| `content[]` | 多模态数组，元素带 `type` 与 `role` |

`content` 元素：`{"type":"text","text":...}`（≤7000 字符）、
`{"type":"image_url","image_url":{"url":...},"role":...}`。本设计用到的 `role`
是 `first_frame` / `last_frame`；另有 `reference_image` / `reference_video` /
`reference_audio` / `base_video` 不在范围内。

输入限制：首尾帧 0/1/2 张，边长 256–5760，比例 2:5–5:2；图片
JPG/PNG/WEBP/HEIC/HEIF ≤30MB；请求体 ≤64MB（大素材传 URL 而非 base64）。

**区域与密钥必须配对**：国际版 `api.minimax.io` 配 platform.minimax.io 的 key，
国内版 `api.minimaxi.com` 配 platform.minimaxi.com 的 key，错配报 Invalid API
key。因此两者都从环境变量读：`MINIMAX_BASE_URL`（默认
`https://api.minimax.io`）、`MINIMAX_API_KEY`。

**探测**：`MINIMAX_API_KEY` 存在即点亮 i2v / flf 的 H3 API 列。

价格：768P `$0.08`/秒，2K `$0.13`/秒；输入图前 5 张免费，之后 `$0.04`/张；输入
音频免费。768P→2K 重生成 `$0.05`/秒。

## H3 本地 vs API：探测在前，询问在后

| 探测结果 | 行为 |
|---|---|
| 两条都可用 | **这时才问使用者跑本地还是 API** |
| 只有 API 可用 | 不问，走 API |
| 只有本地可用 | 不问，走本地 |
| 都不可用 | 报告缺什么，不假装能跑 |

使用者选"本地"时，skill 补一句 Community License 的 Applicable Territory 排除
美国 / 欧盟 / 英国 / 韩国。这是事实提示，不是拦截；是否继续由使用者判断。

## 三条硬约束的处置

**时长**：段落时长（秒）四舍五入到整数并 clamp 到 [4, 15]。< 4 秒的段不进 H3
候选（路由规则 3）。超 15 秒报错要求先拆段，不静默截断。

**声音**：H3 出片自带原生立体声，但**默认剥掉音轨，只取画面**。理由是 H3 每条片子
的嗓音是独立编码的，跨镜必然换声；逐段插进一部 LTX 片子里会造成"第 3 秒突然有
环境声、第 5 秒又没了"的跳变。音频统一后期铺。要保留必须显式指定。

**分辨率**：默认 `resolution: "768P"` + `ratio: "16:9"`（≈1366×768，最接近
Director 常用的 1344×768），出片后统一缩到时间轴尺寸。2K 贵 60% 且要再缩一次，
不设为默认。

## 提示词：两套契约不能混

LTX 那套（global prompt + 分段 local prompt + `strength` + `negative_prompt`）
在 H3 上一条都不成立，必须分开成两份 reference：

- **H3 的文本编码器是 Qwen3-VL-32B，关键帧作为视觉块和文字一起进编码器**
  （`<Picture 1>: <vision block> <prompt>`）。模型看得见画面，所以不要重复描述
  画面里已有的东西，只写变化：动作、运镜、光线、声音。
- **没有 chat template**，别写指令腔（"Generate a video of..."），那些字会被当
  画面内容编码。
- **完全没有负面 conditioning**。所有约束改正面表述（"禁止露出全身" →
  "只有肢体入画，躯干始终在画外"）。
- 多参考素材在提示词里用 `<Picture i>` 指名，序号按类型各自从 1 起算。
- **拉长时长必须同时补写动作**，否则空出来的时间模型自己编。

## 成本可见性

分派前 skill 必须报账，形如：

```
第 3、7 段判为快运镜 → H3 API
时长 8s + 10s = 18s，768P
输入图 2 张（免费额度内）
预估 $1.44
```

等使用者确认后才发请求。不自动提交。

## 错误处理

- ComfyUI 不可达：只影响本地路径与探测，API 路径照常；报告并降级，不静默。
- `MINIMAX_API_KEY` 缺失或区域错配（Invalid API key）：直接报，指明 base URL 与
  key 必须同区。
- 任务返回 `failed` / `cancelled`：报出 task_id 与状态，不重试烧钱。
- 轮询超时：保留 task_id，说明可稍后用查询接口取回。
- 三个后端全不可用：报告各自缺什么，仍然交付 storyboard JSON。

## 验证

- `probe_backends.py` 在三种机器上给出正确的可用格子：装了 Camera Lab 的、
  只装 ComfyUI + LTX 的、只有 `MINIMAX_API_KEY` 的。
- `run_storyboard.py --dry-run` 打印将要发送的请求体与预估费用，不发请求。
- 用现有 `camera-lab/tasks/storyboards/h3/act3_lab_h3.json`（9 镜 / 1847 帧 /
  77 秒）做 dry-run，核对帧→秒换算与费用估算（768P 约 `$6.2`）。
- H3 API 真实调用先只跑一个 4 秒段，确认 `task.content.url` 能下载、剥音轨生效。
- ComfyUI 直连跑一条 3 关键帧的时间轴，与同参数的 Camera Lab 产出对比首尾帧，
  确认 `segments` 数组填法等价。
- 两个变体（`skills/` 与 `codex/`）描述同一方法，改动保持同步。

## 待定

`seed` 与 `prompt_optimizer` 在 H3 API 上的确切行为：官方 guides 页提到存在但未
给参数表，`/docs/api-reference/*` 子页当前 404。实现时以 dry-run 加真实调用确认，
确认前不写进 plan schema。
