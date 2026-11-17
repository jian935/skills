---
name: comfyui-anime-pipeline
description: ComfyUI 本地 AI 绘画管线操作手册——API 调用、国内镜像下模型、ControlNet 线稿上色、LayerDiffuse 兼容坑。适用于本地 ComfyUI 部署的使用与扩展；安装目录由环境变量 `COMFY_ROOT` 指定。
---

# ComfyUI 动漫绘画管线

## 不适用

- **没有独立显卡的机器**：本手册的配置与实测都在 8GB 显存档位，纯 CPU 出图的时间成本不可接受。
- **要求完全可复现**：采样器、模型版本、节点更新都会改变结果，同一 seed 不保证跨版本一致。
- **商用授权敏感的场景**：底模、ControlNet、LayerDiffuse 等权重各有自己的许可，需逐个确认，本仓库不代为授权。

> 下文写的 `%COMFY_ROOT%` 指 ComfyUI 安装根目录（含 `ComfyUI/` 与 `python_embeded/`），
> 未设置时，把下文出现的 `%COMFY_ROOT%` 替换成你自己的安装路径。

## 环境布局
- 主程序: `%COMFY_ROOT%\ComfyUI`，嵌入式 Python: `%COMFY_ROOT%\python_embeded\python.exe`
- 启动: `cd "$COMFY_ROOT" && HF_ENDPOINT=https://hf-mirror.com ./python_embeded/python.exe -s ComfyUI/main.py`（后台运行，探活 `http://127.0.0.1:8188`）
  ⚠️ 探活必须 `curl --noproxy "*"`：当 shell 里设了 http_proxy 时，curl 会走代理访问 8188 并拿到代理错误页，造成「COMFY_UP」假阳性（2026-10-04 踩过）；Python 侧一律用 `ProxyHandler({})` 的无代理 opener。
- 模型目录: `models/checkpoints`（底模）、`models/controlnet`、`models/layer_model`（LayerDiffuse 权重）

## API 调用模式（Python）
```python
import json, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 关键: 绕开系统代理, 否则 localhost 被 VPN 代理截胡返回 502
def api(path, data=None):
    req = urllib.request.Request("http://127.0.0.1:8188" + path,
        data=json.dumps(data).encode() if data else None,
        headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=60) as r:
        return json.load(r)
# 提交: api("/prompt", {"prompt": wf, "client_id": "wb"}) → 轮询 /history/<prompt_id>
```
- 工作流报错看 `/history` 的 `status.messages` 里 `execution_error` 的 `exception_message`，很精确。
- 节点参数格式拿不准时 GET `/object_info`（同样要用无代理 opener）。

## NoobAI-XL vpred 底模参数（已验证 25s/张 832x1216 @ RTX 4060 8GB）
- CheckpointLoaderSimple 后必须接 `ModelSamplingDiscrete(sampling="v_prediction", zsnr=True)`，否则出图过曝
- KSampler: euler_ancestral / normal / cfg 5.5 / steps 26
- 负面词基线: `worst quality, low quality, bad anatomy, watermark`

## ControlNet union promax（线稿→上色，已验证 35s/张）
- 模型: `controlnet-union-sdxl-1.0-promax.safetensors`（models/controlnet/）
- `SetUnionControlNetType` 的 type 必须填组名字符串: `"canny/lineart/anime_lineart/mlsd"`（不是单个 "lineart_anime"）
- 推荐参数: strength 0.75, end_percent 0.8；latent 用 `EmptySD3LatentImage` 尺寸与输入线稿匹配
- 输入线稿放 `ComfyUI/input/`，LoadImage 引用文件名

## LayerDiffuse（已装但有限制）
- 权重手动下载到 `models/layer_model/`: `layer_xl_transparent_attn.safetensors`(743MB) + `vae_transparent_decoder.safetensors`(208MB)，节点就不会联网下载
- **已打两处兼容补丁**（针对 ComfyUI 0.37 新核心）:
  1. `layered_diffusion.py` 的 `LayeredDiffusionDecodeRGBA.decode`: `JoinImageWithAlpha().join_image_with_alpha()` 已废除 → 内联 `torch.cat([image[...,:3], alpha.unsqueeze(-1)], -1)`
  2. `lib_layerdiffusion/utils.py` 的 `to_lora_patch_dict`: 老式 "lora" patch 类型已从核心移除 → 把 16 段 rank 权重预乘成单 diff: `patch_flat[k] = (a @ b,)`（index0=[out,rank] × index1=[rank,in]）
- **硬限制**: LayerDiffuse 只兼容接近 SDXL base 的 eps 模型；**NoobAI/Illustrious/Animagine 等重训动漫模型全不兼容**（潜空间问题，GitHub issue huchenlei/ComfyUI-layerdiffuse#124），表现为生成正常图但 alpha 全 0/纯色背景。别再对 vpred 模型调试它。
- **透明分层的可行路径**: 生成主体图（提示词 simple background）→ 云端抠图（buddy-image-processing matting，8 秒）→ 真 RGBA。边缘质量很好，已验证。

## ⚠️ NoobAI 做不了「色 → 线稿」（2026-09-28 实测，别再试）
想把一张彩稿 img2img 重画成线稿，denoise 扫了三档全失败：
| denoise | 结果 |
|---|---|
| 0.60 | 完全保住颜色，出成一张**平涂彩稿**（不是线稿） |
| 0.84 | 线条碎裂、只剩黑斑 |
| 0.93 | 直接崩成黑块/抽象色块 |

- 负面堆 `color, colored, shading, gradient, greyscale` + cfg 提到 7.5 **都没用** —— img2img 的颜色带过去太多了。
- **正解是算法抽取**：`ink = clip((median(L,9) - L) / (0.30*B + 0.10), 0, 1)`，
  阈值 0.30、去掉 <12px 连通块。好处是**与彩稿逐像素对齐**（模型重画必然错位）。
  按线宽分「粗/中/细」三层交付，三层并集 = 完整墨线。
- 意外收获：denoise 0.60 那张"平涂彩稿"本身可用作**平涂/上色参考**，构图与彩稿一致。

## 云端出图工具必须「一次一张」（重要）
同一消息并行发多个出图请求，完成时间落在**同一秒**时返回同名文件 →
**后写覆盖前写，图直接丢**。给每个调用单独 `output_dir` 也拦不住。
- 一条消息只发一个出图调用，拿到 localPath **立刻重命名**，再发下一张。
- 本次因此损失 4 张图（2 次并行 × 每次丢 2）。

## Wan2.2 TI2V 5B 图生视频（已验证 15~60s/49帧 480x832 @ RTX 4060 8GB）
- 模型三件套: `models/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors` + `models/vae/wan2.2_vae.safetensors` + `models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`（CLIPLoader type="wan"）
- 节点链: UNETLoader → ModelSamplingSD3(shift=8) → KSampler(euler/simple/cfg 1.0/steps 15) → VAEDecode → **CreateVideo(fps=24)** → SaveVideo
- **SaveVideo 坑（ComfyUI 0.37）**: 输入类型是 VIDEO 不是 IMAGE，VAEDecode 后必须接 `CreateVideo` 节点转换；且 `format` 是必填动态级联参数，API 提交时直接给 `{"format": "auto", "codec": "auto"}`，否则报 missing argument 'format'
- `Wan22ImageToVideoLatent`: width/height 必须 32 的倍数，length 必须 4k+1（如 49）；start_image 接 LoadImage，尺寸不符会自动缩放
- 8GB 显存实测: 49 帧 480x832/15 步，首次含加载约 60s，模型驻留缓存后约 15s；fp16 权重靠内存卸载（需 ≥22GB 空闲内存）
- 首图/尾图竖版分辨率参考: 480x832（竖）/ 832x480（横），与 SDXL 出图 832x1216 同比例
- 输出落盘: `ComfyUI/output/<filename_prefix>/*.mp4`；history 里 outputs 的 key 是 "images" 但内容是 mp4（animated: true）

## Z-Image-Turbo 写实关键帧（已验证 55s/2张 768x1344 @ RTX 4060 8GB）
- 节点链: UNETLoader(`z_image_turbo_bf16`) → ModelSamplingAuraFlow(**shift=3**) → KSampler(steps 8, cfg 1.0, `res_multistep`/`simple`, denoise 1.0)；CLIPLoader(`qwen_3_4b`, type=`lumina2`)；VAELoader(`ae.safetensors`)，负面用 `ConditioningZeroOut`（turbo 模型负面置空）
- 中文短剧写实人像提示词要带上: `cinematic still from a chinese live-action drama` + 年龄/皱纹/衣着细节 + `warm desk lamp as key light` + `warm tungsten light against dark teal shadows` + `35mm film photography, realistic skin texture, natural film grain` + 竖版 `vertical composition`
- batch_size=2 同种子可一次出两版候选，肉眼挑更好的一版再进视频环节（省一次迭代）

## 角色一致性：三视图 + 定妆图锚定法（Z-Image 已实测）
Z-Image 不支持 IPAdapter / SDXL ControlNet（不在同一潜空间），所以**一致性只能靠提示词锚定**，做法是抽出一段固定角色描述 `CHAR` + 固定画风描述 `STYLE`，所有出图复用同一段文本：

- CHAR 模板（从参考图里提炼可复述的硬特征，越具体越稳）: `1girl, chinese young woman, early 20s, delicate oval face, long dark wavy hair with center part, gentle brown eyes, natural makeup, realistic skin texture, skin pores, slim figure, cream-white ribbed knit tank top, light beige linen trousers`
- STYLE 模板: `masterpiece, best quality, RAW photo, cinematic photo, 35mm lens, f/1.8, shallow depth of field, film grain, photorealistic, cinematic lighting, film color grading, atmospheric, moody`
- **三视图提示词配方**（横构图 1344x768 刚好放三个视角）: `character design reference sheet, full body turnaround, three views of the same girl side by side: front view, side profile view, back view, identical character, consistent design and clothing, neutral standing pose, arms relaxed by sides, {CHAR}, plain light grey studio background, even soft studio lighting, {STYLE}` —— 实测一次就能出标准正/侧/背同人同装设定表
- 出片顺序: ① 三视图定形象 → ② 用 {CHAR}+场景描述出竖版定妆/关键帧（768x1344）→ ③ 关键帧进 Wan2.2 图生视频
- 注意事项: 三视图和关键帧是两次独立生成，"一致性"来自 CHAR 文本而非同一潜码，服装/发型/气质能对得上，但**脸部细节会有微差**；要真正锁脸必须上 IPAdapter（需换 SDXL 底模）
- 耗时参考: Z-Image 批量 4 张（2横2竖）约 100s；Wan 5s/448x768/10步 ≈ 105s

## 古装动漫·角色三视图配方（NoobAI，已验证 25~30s/张 1344x768）
横构图 1344x768 正好并排放下三格（正/侧/背）。配方分四段拼：
1. **版式**: `character design reference sheet, full body turnaround, three views of the same character side by side: front view, side view, back view, identical character, consistent face and costume, standing straight, arms relaxed at sides, feet visible, full body shot`
2. **角色硬特征**（越具体越稳）: 如 `1boy, chinese fantasy male, ancient chinese costume, xianxia, long black hair tied in a high ponytail, sharp sword eyebrows, star-like bright eyes, handsome face, dark navy blue hanfu robe with silver line embroidery, black leather belt with a jade pendant`
3. **纯白背景**: `pure white background, plain white background, simple background, isolated on white`（只写 "white background" 容易出浅灰渐变）
4. **质量**: `ultra detailed, delicate details, 4k, absurdres, highres, masterpiece, best quality, newest, clean lineart`
负面必加: `3d, cg, realistic, photorealistic, photo, gradient background, grey background, colored background, scenery, extra characters, multiple boys, cropped, out of frame, cut off, bad anatomy, bad hands, watermark, text`

- ⚠️ **坑 1 — 道具被负面吃掉**: 负面写 `weapon` 会把佩剑一起去掉。要佩剑须在正面词显式写 `a long ancient sword hanging at his left waist`；即使这样也常画成"剑单独竖在旁边不佩戴"，换 2~3 个种子才出可用的一版。
- ⚠️ **坑 2 — 加细节词会退成灰阶线稿**: 正面加 `detailed shading, soft shading` + 提步数（26→32），彩色三视图会丢主色变黑白设定稿。**要保色：别堆 shading 词，直接用已出彩色版的同种子 + steps 提到 34 精修**（同种子构图不变）。
- ⚠️ **坑 3 — 一格被道具顶掉**: 常见失败是出现"3 格人 + 1 格道具"（如飘着的玉簪/单独的剑）。多出种子筛，别指望一次到位。
- 建议每角色出 **3 个种子**筛 1，再对胜出的种子提步数精修一次；比反复改提示词高效。
- 拼候选对比图: PIL 三行四列 + `C:\Windows\Fonts\msyh.ttc` 中文标注（见 workspace `11-manju/make_compare.py`）。

### ⚠️ 用户反馈"五官不完整 / 比例崩"时的正解（已实战验证）
**根因**：全身三视图并排三格时，每格的头只有 ~60~100px 像素，五官细节预算不足。硬加 `detailed face, open eyes, visible pupils` 反而会让模型画成**惨白脸 + 红眼 + 咧嘴笑**的诡异面具（比不加更糟）。这是**画幅问题，不是提示词问题**。

**正解：设定稿 = 两行拼合，不要指望一行三格同时满足造型和五官**
1. 第一行「全身三视图」：只用温和的脸部词，负责**造型 / 配色 / 全身比例 / 脚部完整**。
2. 第二行「头部特写三视图」：`三 head portraits ... side by side: front view face, side profile face, back of head, close-up bust portrait, head and shoulders` → 每个头 ~400px 宽，五官必然清晰。
3. 用 PIL 上下拼成一张设定稿（脚本 `11-manju/make_charsheet.py`，参数：全身图 头图 角色名 输出路径）。这是行业标准设定稿排版。

**配套的 5 个新坑（都很容易踩）**
1. **负面标签会**稀释**：写到 100+ 个标签时明显失灵（实测"blank face 已在负面但脸仍空白"）。控制在 **30 个以内**，最关键的排最前。
2. **古装女主的强先验是大红**：`chinese fantasy female` 即使写 `pale cyan` 也会被吃掉。必须**把颜色词前置到最前面**：`1girl, solo, colored, pale cyan hanfu dress, light blue robe, pastel color palette, ...`，负面加 `red, red clothing, crimson, scarlet, vermilion, dominant gold, orange, brown, dark clothing, black robe`。
3. **`high topknot` 会画成"烟囱"**：头顶一根黑色圆柱/帽子。用 `hair tied up in a topknot with a short ponytail` 更稳，负面加 `tall hairstyle, chimney hair, hat, cap`。
4. **头部特写反复退成灰阶线稿**：`plain white collar` + 纯白背景会让整张图降饱和。正面词开头必须写 `colored, fair skin, natural skin tone`，负面加 `greyscale, monochrome, lineart, sketch, uncolored`。
5. **分视角单独出图会丢一致性**：为提分辨率而"正/侧/背各自单独出 832x1216 再拼"时，**袍色在三个视角间会不一致**（深藏青 vs 纯黑）。除非逐张锁色，否则不如单图三格。
6. **`detailed shading, soft shading, clean lineart` 会让彩色三视图退成灰阶线稿**（反复复现）。要保色就别堆这些词；宁可复用已出彩色种子的构图、只把 steps 提到 34。

**验证过的头部特写可用配方**（上色 + 三视图完整）
```
character design reference sheet, three head portraits of the same character side by side:
front view face, side profile face, back of head, close-up bust portrait, head and shoulders,
identical character, colored, fair skin, natural skin tone,
detailed face, beautiful detailed eyes with highlights, light amber iris, long eyelashes,
thin eyebrows, small mouth, pink lips, defined nose, gentle soft smile,
{long hair / topknot 描述}, plain white inner robe collar,
pure white background, upper body, ultra detailed face, 4k, absurdres, masterpiece, best quality, clean lineart
negative: greyscale, monochrome, lineart, sketch, uncolored, white skin, short hair, crown, elaborate headdress,
          forehead mark, heavy makeup, mature woman, man, boy, four heads, extra heads, full body,
          deformed face, asymmetrical face, cross-eyed, blank face, no eyes, no mouth, + 30 标签内的基线
```

## 竖版漫剧·分镜关键帧批量配方（NoobAI，已验证 768x1344 约 20s/张）

**铁律 0：开新剧先核对剧本题材与角色提示词原文。**
本次实战踩过一次严重事故——用户给了现代校园剧本 + 校服三视图提示词，我却拿上一部古装剧的 `jobs_*.json` 当模板改，
结果两个主角全出成汉服，连"剧本存档"都写成了不存在的古装玄幻，直到做分镜时才被发现，整套角色重做。
**新剧 = 全新 CHAR 文本，禁止继承上一剧的 job 配置。**

**画幅**：竖版漫剧统一 `768x1344`（9:16），后续喂 Wan2.2 时等比缩到 `704x1280`。
**步数**：32 步 / cfg 5.5 / euler_ancestral / normal。

**通用结构**（每格都必须四段齐全，缺一段就容易崩）
```
{画风句}, {镜头景别}, {主体与动作}, {环境/背景描述}, {光照描述}, detailed background, colored illustration, anime screenshot
```
画风句固定复用：`fresh japanese webcomic flat color, clean line art, flat cel shading, soft natural lighting, bright and well lit, high detail, 8k, absurdres, masterpiece, best quality, newest`

### ⚠️ 物件特写 / 空镜会崩成纯色（已实战验证）
写"橘子糖""攥紧书包带""笔尖书写"这类**短提示词 + 无环境描述**时，NoobAI 在竖幅里直接退化成
一整块纯色 / 空白 / 一根线。三轮才定位清楚。正解：
1. 补齐**环境 + 背景**（"wooden school desk top in a bright classroom""classroom behind her"）
2. 正面加 `detailed background, colored illustration, anime screenshot`
3. 负面加 `blank image, empty frame, plain white background, monochrome, greyscale, lineart, sketch, uncolored`
4. 别用 `empty scene, no humans` 当主体——空镜也要写满树叶/桌椅的细节词

### ⚠️ 负面词反噬（同样三轮才定位）
- 把 `white background, simple background, plain background, solid background` 放进负面 → 画面整体变暗、偏霓虹蓝紫
- 把 `border, frame, multiple panels, collage` 放进负面 → 模型把画面缩成一张带**黑边框**的"照片"
- **纠正**：这些词不要进负面。要控画幅用正面的景别词（wide shot / close-up），不用负面的边框词。

### 昼夜分组的负面词（关键）
不要一套负面吃全天。按镜头分组，否则白天镜头会被压暗、夜晚镜头会过曝：
```
NEG_BASE   = 用户基线 + worst/low quality + blank image/empty frame/plain white background
             + monochrome/greyscale/lineart/sketch/uncolored
             + bad anatomy/bad proportions/extra limbs/fused fingers/deformed hands
             + faceless/no eyes/no mouth/blank face + signature/logo/username/black bars/letterbox
NEG_BRIGHT = NEG_BASE + dark, dim, underexposed, night, neon lights, blue lighting, purple lighting, heavy shadows, vignette, black background
NEG_DUSK   = NEG_BASE + night, neon lights, blue lighting, purple lighting, black background, gloomy
```
- 白天 / 黄昏暖光 / 室内明亮 → `NEG_BRIGHT`
- 夜景台灯 / 暮色街道 / 夕阳渐沉 → `NEG_DUSK`

### 群像镜头要拆掉 `extra people`
用户给的通用负面常含 `extra people`，但教室、走廊、礼堂这类**群像镜头必须保留背景同学**。
这三格把 `extra people` 换成 `duplicated main character, extra protagonists`，其余镜头保持原样。

### 景别必须显式压制
特写镜头只写 `close-up` 不够——模型仍会画全身立绘。要正面写
`close-up, portrait, upper body, head and shoulders`，负面补 `full body, standing pose, legs, full length shot`。

### 小道具画不出来？用后期合成，别死磕提示词
`橘子糖` 这种小物件试了 **9 个种子 × 3 种构图**依然失败（退化成大圆饼/抽象色块）——NoobAI 对小目标基本无解。
已验证的兜底方案（workspace `make_p04.py` + `paint_candy.py`）：
1. **色键抠图**：底图若是纯色背景，取角落像素 `a[3,3]` 当背景色，
   `dist = |pixel - bg|.max(axis=2)`，`alpha = clip((dist-30)/34, 0, 1)`；再按 alpha 反混背景色去色溢，
   最后 `MinFilter(3)` + 轻高斯收缩边缘去残留镶边。**纯色底抠图效果非常干净**。
2. **换背景板**：用同场景其他格的无人物区域裁成同比例当背景，重虚化（radius 8）+ 压对比，
   主体立刻"站进场景里"。⚠️ 别用**含人物的**格子做背景板——虚化后会变成巨大的鬼脸。
3. **矢量补画小道具**：`paint_candy.py` 用 PIL 在 4 倍超采样画布上画（椭圆糖体+两侧扭结+高光+暗部+描边+闪粉），
   再 `resize(LANCZOS)` 缩回，风格与 flat color + lineart 完全吻合，比模型出图可控得多。

### 排版核对
出完用 `make_contact.py out.png "标题" 5 "img|标注" ...` 拼总表整体看，
一次就能发现"某几格崩了/偏色/景别跑偏"，比逐张读图省 10 倍时间。

## 正反面提示词出图（txt2img.py）
- 用法 A（批量，推荐）: `python txt2img.py jobs.json`，jobs.json 里每项 `{name, model, positive, negative, width, height, batch, seed}`
- 用法 B（单条）: `python txt2img.py --model anime --positive "..." --negative "..." --size 832x1216`
- `model=anime` → NoobAI-XL vpred（**负面提示词生效**）: CheckpointLoaderSimple → ModelSamplingDiscrete(v_prediction, zsnr=True) → KSampler(euler_ancestral/normal/cfg 5.5/26步)，默认 832x1216，VAE 取 checkpoint 自带
- `model=real` → Z-Image-Turbo（**负面提示词完全无效**）: UNETLoader(z_image_turbo_bf16) → ModelSamplingAuraFlow(shift=3) → KSampler(res_multistep/simple/cfg 1.0/8步)，CLIPLoader(qwen_3_4b, type=lumina2)，VAELoader(ae)，默认 768x1344
- ⚠️ **关键坑**: distill/turbo 模型（Z-Image、各种 Lightning）cfg=1，负面走 `ConditioningZeroOut`，负面提示词在数学上不起作用——用户写了也白写，必须提前说明。要让"正+负"都生效只能换 **eps 真实底模**；ModelScope 可下: `ModelsLab/RealVisXL_V5.0_Lightning`、`tonera/RealVisXL_V4.0`、`Leosam1/LEOSAM_s_HelloWorld_XL_HelloWorld_XL_7.0`
- 写实出图速度参考: Z-Image 768x1344 约 35s/张（批量第二张起更快）；NoobAI 832x1216 约 25~30s/张
- 用户写的写实提示词（RAW photo/35mm/film grain）在 Z-Image 上效果良好，风格偏柔和电影感；要求"超高清锐利"时需注意其原生质感偏 soft

## 步数调优（已实测，默认用 10 步）
A/B 对比条件: 同一关键帧/同种子/448x768/117帧，只改步数，数据取自服务器日志的逐帧 it/s：

| 步数 | 采样耗时 | 整条耗时 | 清晰度(Laplacian方差) | 逐帧位移 |
|---|---|---|---|---|
| **10 步** | 46s (5.5s/it) | **101s** | 249 | **1.23px** |
| 15 步 | 86s (6.4s/it) | 146s | 249（=100%） | 1.98px |

- **结论: 默认 10 步**。省 31% 总耗时、清晰度完全持平、而且抖动反而更小（步数少 = 漂移/幻觉少）。仅当特写脸部需要额外保真时才回 15 步。
- 注意低步数会改变构图轨迹（同为 10 步 vs 15 步景别不同），但这不是画质问题，两种都可用。
- 逐帧采样耗时随帧数近似线性: 117帧≈6.4s/it、241帧≈14s/it（448x768）；分辨率越高同样线性放大。
- 耗时结构: 采样只占 ~60%，其余是模型搬运 + VAE 解码（117帧解码约 40s），所以步数减半不会让总时长减半。

## 批量出片器（wan_i2v_batch.py）
- 用法: `python wan_i2v_batch.py jobs.json`，jobs.json 是 job 列表（name/image/prompt/seconds/width/height/seed/steps 可选）
- 特性: 一次性把全部任务灌进 ComfyUI 队列（队列自动串行，人不用守），统一轮询并汇报成功/失败
- 分钟数自动换算帧数并对齐 4k+1；锁镜头提示词和负面词已内置，默认 10 步
- **注意计时口径**: 每个 job 打印的耗时从"提交时刻"算起，含排队等待；要拿真实渲染时长请用 `后一个完成时间 - 前一个完成时间`，或直接看服务器日志的 `Prompt executed in X seconds`

## 10 秒长镜头（已验证 320s/241帧 448x768 @ RTX 4060 8GB）
- 时长换算: N 秒 = `N*24` 帧再补到 **4k+1**（5s→121帧，10s→241帧）
- 帧数翻倍不只是耗时翻倍（注意力对 token 数超线性）: 121帧/512x896≈195s → 241帧/448x768≈320s；10 秒建议降到 **448x768**，512x896 在 8GB 上有 OOM 风险
- **锁镜头提示词模板**（实测把逐帧位移从 2.0px 压到 0.32px）: 开头写死 `locked-off tripod camera, completely static framing, no camera movement, no shake`，结尾 `subtle natural body motion only`，负面加 `camera shake, handheld, jitter`
- 台词口型: Wan 只能生成"说话动作"，加 `her lips move naturally as she speaks softly` + 情绪描述；**无音轨**，真实配音需另接 TTS，字幕需后期合成
- 抖动质检（量化，比目测靠谱）: 用相位相关测逐帧整体位移，下采样 2x + FFT
  ```python
  F=np.fft.fft2(a)*np.conj(np.fft.fft2(b)); R=F/np.maximum(np.abs(F),1e-9)
  r=np.abs(np.fft.ifft2(R)); dy,dx=np.unravel_index(np.argmax(r),r.shape)  # 需做频谱环绕修正
  ```
  实测基线: 锁死镜头 mean≈0.3px；有轻微漂移 mean≈2px。注意别用"亮度重心位移"做指标（分母趋零会溢出）

## 画面稳定性诊断：区分「镜头抖」与「五官抖」（两个独立问题）
**结论先行**: 镜头抖已可解决（提示词 + 低步数，实测 0.3px）；五官抖在 5B/低分辨率配置下**无法根治**，只能缓解。
- **镜头抖** → 相位相关测逐帧全局位移（方法见上节），基线：锁死 0.3px / 轻漂移 2px
- **五官抖** → 全局位移补偿后，测脸部区域的**时域二阶差分** `abs(f[1:-1] - 0.5*(f[:-2]+f[2:]))` 在脸框内的均值（0-255 灰阶）。
  实测基线: 脸区 **3.8~6.5**；帧间视觉一致时应接近 0~1。数值越高 = 五官/纹理在逐帧重画
- 量化脚本（workspace）: `analyze_temporal.py`（镜头位移 + 脸区闪烁 + 对照背景）、`analyze_face_v3.py`、`temporal_denoise_test.py`（时域滤波 A/B）
- ⚠️ **陷阱 1**: 用整数像素 `np.roll` 做全局补偿会**注入自己的亚像素闪烁**，补偿后测得的闪烁值反而偏高且不可比 —— 要绝对值就用原始帧测
- ⚠️ **陷阱 2**: 「脸部残余位移 vs 首帧」把真实头部动作也算成抖动，不严谨；分离抖动应看「轨迹 − 平滑趋势」的高频分量
- ⚠️ **陷阱 3**: 高通图直接做 NCC 太脆（1~2px 亚像素错位就归零），要测结构一致性必须先模糊+降采样（如缩到 24x24）再 NCC
- **根因（5B 无法根治）**: ① 无身份约束，文本条件不绑定帧间人脸，每帧重新"画"一次 ② 448/512 短边时人脸只占约 120~180px，细节预算不足 ③ 5B 是 Wan2.2 系列最小一档 ④ cfg=1 蒸馏采样，负面词无效
- **三档对策**（按性价比）:
  1. **免成本**: 短边提到 512x896、提示词去掉 `film grain`（颗粒逐帧重随机 → 闪烁感）、后期时域降噪、单条压到 5s、锁定种子
  2. **对症（推荐）**: ComfyUI 装 **ReActor** 换脸节点 + `inswapper_128.onnx`，用三视图定妆脸逐帧替换 → 全片同一张脸（短剧行业标准做法）
  3. **提画质**: 换 Wan2.2 **14B / GGUF 量化**，8GB 靠 block swap 可跑
- **后期时域降噪配方**（PyAV 实现；**ffmpeg 可用时**：venv 里 `pip install imageio-ffmpeg`，用 `imageio_ffmpeg.get_ffmpeg_exe()` 取二进制（v7.1），抽帧 / tile 拼图 / hqdn3d / vidstab 都能用）:
  3 点权重 `0.2*f[t-1] + 0.6*f[t] + 0.2*f[t+1]`，实测脸部闪烁 **3.77 → 1.66（−56%）**，清晰度抖动 std 37.7 → 24.8，无明显拖影。

## 漫剧 5 秒镜头标准配方（已验证 195s/条）
- 全流程: Z-Image 768x1344 出关键帧 → 拷进 `ComfyUI/input/` → Wan2.2 TI2V 5B 图生视频 512x896 / **121帧（=5s@24fps）** / 15 步 / shift 8 / cfg 1.0
- 耗时参考: 关键帧 25s/张；121 帧 i2v 约 195s（含加载），49 帧约 15~60s
- 质检方法: 用 ComfyUI 自带 PyAV 抽帧看变化 —— `av.open(mp4)` → decode → `frame.to_image().save()`，抽查首/中/尾三帧确认无面部崩坏
- 参考图（手机截图）复刻要点: 竖版 9:16、单侧暖色台灯打光、暗部偏青、中近景、暗调环境衬托主体

## 竖版成片一键批量管线（wan_ep01_video.py，2026-09-27 验证）
关键帧目录直接进片，**不需要手动拷图到 ComfyUI/input**（脚本走 `/upload/image` 上传）。
- 用法: `python wan_ep01_video.py [--only p01_classroom,p02_glance] [--w 704 --h 1280] [--steps 15] [--seconds 3] [--list]`
- 流程: 本地 PNG → 等比缩放到 32 对齐的目标尺寸 → multipart 上传到 ComfyUI input → 依次入队 → 轮询 → 用 `/view?type=output` 回传 MP4 到本地
- **只用 `--only` 跑单格做基准测试**，再决定全量参数；测完必须清洗掉测试产物，否则和正式版同名难分辨
- 对应质检脚本 `check_videos.py [name...]`：ffmpeg 抽每格首/中/末帧横向拼 `_contact/video_contact.png`，几秒看完所有镜头有没有崩

### 尺寸对齐必须用 round，不能用 floor
- 768x1344 → 目标框 704x1280 时：`round` 得 **704x1216**（比例偏差 1.3%，可用）；`floor` 得 **416x768**（比例偏差 5%，画面被压窄）
- 公式：`w = round(w0*sc/32)*32`，`h = round(h0*sc/32)*32`，`sc = min(tw/w0, th/h0)`

### 耗时经验公式（RTX 4060 Laptop 8GB，含模型搬运+VAE 解码）
- 448x768 / 10步 / 45帧 = **60s**；704x1216 / 15步 / 69帧 = **435s**
- 近似 **∝ 像素数 × 步数**：704x1216x15 是 448x768x10 的约 7 倍算力 → 实测耗时 7.25 倍，可直接拿来估算整片工期
- 15 格竖版漫剧（2~5s/格，共约 1150 帧）在 704x1216/15步 下约 **2 小时**；8GB 显存峰值 6.2G/8.2G，**不 OOM**
- 缩小尺寸/步数是唯一有效的提速手段（10 步 vs 15 步 ≈ 省 1/3 时间）

### ⚠️ 静物/道具镜头会「凭空长物体」（本轮主要坑）
倒计时牌、试卷堆这类**静的物件特写**，5B 极易在半途长出莫名其妙的几何体、飘落碎片。
- **根因不是负面词失灵，而是正向提示词自己招来的**：写了 `a page tears off and drifts down through the air` → 模型真的往画面里塞了一堆飘落物 + 桌上多出白色块状物。
- `cfg=1.0` 蒸馏采样下负面提示词**数学上无效**，加 `no new objects` 到负面完全没用，只能**从正向收敛**。
- **改法**：把「引入新物体的动作」换成「物体保持原样的微动」——
  `✗ stacks of papers rising higher / a page tears off and drifts down`
  `→ ✓ the stacks stay in place, the top loose pages flutter slightly in a draft, the pile keeps its shape`
- 另一处 `eyelashes flutter` 会让角色**闭着眼不动**好几帧，LOCK 里补上 `the character face and body stay consistent` 后消失。

### 锁镜头 + 稳定 LOCK 模板（本轮实测可用）
```
locked-off tripod camera, completely static camera, subtle natural motion only,
the background stays exactly the same, the character face and body stay consistent,
same art style and same color palette throughout, clean flat color anime,
no new objects appear, objects keep their shape.
<本镜头的具体微动描述>
```
- 注意：负面词（`camera shake, jitter, blur...`）在 cfg=1.0 下**写了也不会生效**，别把希望寄托在负面；镜头稳不稳由**正向**的 `locked-off / static camera` 决定。
- 逐格运动提示词写法：主语 + 慢速副词（slowly / gently / faintly）+ 幅度限定（a short distance / slightly / trembling faintly），不要写"从 A 变成 B"的强状态转移。

### 后期：镜头时长延展（慢放 + 冻帧）与配音合片

关键帧素材通常只有 2~5s，但台词（尤其旁白）需要更长的时间去承载。做法是**按台词需求重新定时每个镜头**，素材不够长时先慢放再冻帧补齐。

**⚠️ 核心坑：`setpts` 紧邻 `tpad` 会让补帧被静默吞掉。**
```
✗ setpts=PTS/0.8, tpad=stop_mode=clone:stop_duration=2.5   → 输出 4.83s（tpad 完全没补）
✓ setpts=PTS/0.8, fps=24, tpad=stop_mode=clone:stop_duration=2.5  → 输出 7.34s（正确）
```
在两者之间插一个 `fps` 就正常。也可以把 `tpad` 放前面、`setpts` 放后面（此时 pad 时长要按原时间轴折算）。**排查方法：`ffmpeg -i out.mp4` 看 Duration 对不对**，别只看有没有报错——它不报错，只是默默少了一段。

推荐的完整单镜链：
```
setpts=PTS/{r}, fps=24, tpad=stop_mode=clone:stop_duration={need},
trim=duration={td}, setpts=PTS-STARTPTS, scale=W:H, setsar=1
```
- `r = max(0.80, min(1.0, src/td))`：慢放不低于 0.8x（再慢动作会凝滞）；`need = td - src/r` 才是要冻的秒数
- `trim` 放最后精确裁到目标时长，避免浮点误差累积导致逐镜头偏移
- 微动镜头（呼吸/发丝/光影）慢放到 0.8x 观感反而更柔，是加分项；走路/位移类镜头慎用

**台词排轴**
- edge-tts（`pip install edge-tts`，已装 7.2.8）出 mp3 后**必须裁首尾静音**再排轴：实测「嗯？」原始 2.09s、实际语音 1.08s，不裁会在台词间留下莫名空档（16 句共虚增 12.4s）
- 裁法：转 24k 单声道 wav → 10ms 窗 RMS 包络 → 相对峰值 −42dB 取首尾（留 50ms 头 / 120ms 尾）→ 边缘 12/45ms 淡入淡出防爆音
- 中文音色：苏晓（少女→成年）用 `zh-CN-XiaoxiaoNeural`，靠 rate/pitch 做年龄与情绪分层（少女段 `+6~8Hz/+2%`，成年旁白 `−12%/−2Hz`）；林屿（安静寡言少年）用 `zh-CN-YunxiNeural` 再 `rate −14%/pitch −10Hz` 压掉阳光感
- 音量：环境音底噪铺到 −30dB 左右（很轻），台词保持原始响度，混完检查峰值，>0.97 再整体限幅
- 环境音可纯程序合成（numpy + FFT 频域带通，不需要 scipy）：蝉鸣=4.2kHz 载波×34Hz 颤音调制、风=粉红噪声 1/f 后带通 60~900Hz 缓慢起伏、人声嘈杂=180~1800Hz 粉红噪声，按段落叠加即可
- ⚠️ **别把带慢速调制的信号当唯一底噪**（比如只铺"风"）：它的调制低谷会落在某一整段上，那段就近乎静音（实测 RMS 0.0074 vs 周围 0.10），听感像音轨断了。正确做法是**先铺一层恒定床噪声**（带通白噪声，固定峰值约 0.07），再按段落叠加蝉鸣/风/人声这些场景层，最后统一压到合适电平。
- 逐段验响度：把成片解码成 f32le 单声道，按 5s 窗算 RMS 打出来扫一眼，哪个窗口比别人低一个数量级就是漏了。片头片尾静默是正常的，中段掉下去就是 bug。
- 收尾统一增益：`gain = min(2.5, 0.92/peak)`，峰值顶到 0.92 左右，既不削顶响度也够（实测 RMS 0.08→0.11）。

## 漫剧管线现状（2026-09-26 打通情况盘点）
- ✅ 已通: 关键帧文生图（NoobAI）→ 图生视频（Wan2.2 TI2V 5B）→ mp4
- ❌ 缺口: 角色一致性手段（loras/ipadapter/clip_vision 全空），多分镜同角色暂只能靠提示词+固定种子
- 漫剧分镜素材在 `ComfyUI/input/`: `drama_key_*.png`、`zq_*.png`（moon/piano/violin/table 场景）

## 模型下载（ModelScope 国内镜像 ~26MB/s，无需 VPN）
- 搜索: PUT `https://modelscope.cn/api/v1/dolphin/models`，body 里关键词字段是 **`Name`**（Search/Query 都无效返回热门榜）
- 文件列表: GET `/api/v1/models/<owner>/<name>/repo/files?Recursive=true`
- 下载: `https://modelscope.cn/models/<owner>/<name>/resolve/master/<path>`
- 单文件 checkpoint（CheckpointLoaderSimple 可用）优先找 `.safetensors` 单文件；diffusers 目录格式的仓不能直接用

## 服务器运维
- **启动方式（重要）**: 必须用工具的后台任务方式（run_in_background）常驻启动：
  `cd /d/ComfyUI && HF_ENDPOINT=https://hf-mirror.com ./python_embeded/python.exe -s ComfyUI/main.py --listen 127.0.0.1 --port 8188`
  ⚠️ **不要用 `nohup ... > log &`**：进程会被回收（日志 0 字节、tasklist 里没有 python），表现为"启动成功但端口永远探不到"。首次启动约 60~90s 就绪。
- 重启: `netstat -ano | grep :8188` 找 PID → `taskkill //F //PID <pid>` → 重新后台启动 → 轮询探活（curl 加 `--noproxy "*"`）
- 改了 custom_nodes 代码必须重启服务器才生效
- 提交任务后队列空了但没输出 = 任务失败，去 `/history` 查错误，不要傻等超时
- **界面全屏（用户常问）**: 前端 1.52.7 **没有全屏快捷键**，入口只在**左上角菜单的最底部一项** `menu.fullscreen`（图标 `lucide--fullscreen`，源码在 `assets/GraphView-*.js`）。更彻底的做法是浏览器 **F11**。WorkBuddy 内置预览面板不保证响应 F11，要全屏建议在系统浏览器打开 `http://127.0.0.1:8188`。

## 横版 16:9 电影感短片管线（2026-09-28 狼牙山五壮士 10s 试稿验证）

### ⚠️ 关键帧上传前必须先按目标比例中心裁切
`fit()` 是「取短边等比缩放」，直接拿 1344x768 去凑 1280x704 会得到 **1216x704（比例 1.727）**——
既不是 16:9，也不是 Wan2.2 原生横版 1280x704。后续按固定尺寸解码的合成脚本会**字节错位读到花屏**。
正解：上传前先 `crop` 到目标比例（`want = tw/th`，宽了裁左右、高了裁上下），再 `fit()` 就能精确命中 1280x704。
- Wan2.2 TI2V 5B 原生横版 = **1280x704**（1.818）；交付真 16:9 = 从 1280x704 中心裁 1252x704 再缩到 1280x720（误差 2%，无畸变）。
- 耗时参考（RTX 4060 8GB，15 步，含模型加载）：1280x704 / 73 帧 = **9 分钟**；97 帧 ≈ 17 分钟。
  实测约 **7.4s/帧**（比按像素数推算的 6.6s/帧 略高，估算工期按 7.4 更准）。显存峰值 7.2G/8.2G，不 OOM。

### 运镜交给后期数字推拉，不要在模型里生成
5B 生成运镜会带几何漂移。改用 **numpy 逐帧裁剪 + LANCZOS 重采样**做缓推/横移/拉远：
绝对平滑、零漂移，而且省一次重渲。缓动别用线性，用 `smoothstep` 或 `u**1.35` 才有"呼吸感"。
代价是端部约 6% 的轻微上采样，配 `UnsharpMask(radius=1.1, percent=42, threshold=3)` 补回锐度。
（参考实现 `15-langyashan/build_film.py` 的 `resample()`：以源图里最大的 16:9 矩形为基准，
按 `z` 放大裁剪，`cx/cy` 控云台位移。）

### 5 人以上群体中景：小脸必糊 → 改侧后方视角
704p 短边下人脸只有几十像素，加上 5B 无身份约束 + cfg=1 负面失效，正面群像的脸必然又糊又闪。
**正解是构图层面绕开**：改成"侧后方视角"——人物背对/侧对镜头、望向远处。
既贴合作品本身的叙事（如"警惕望向山下"），又天然不需要画出清晰的脸。这不是妥协，是更专业的镜头语言。
- 多人提示词必须写清 **年龄/身高/体型各不相同、衣服打补丁做旧、姿态自然散开不摆拍**，
  否则 NoobAI 会出成"整齐一列像男团合影"，必被打回重做。

### edge-tts 旁白排轴：让逗号停顿落在镜头切换点上
不要盲猜起始时间。做法：先出 mp3 → 裁首尾静音 → **用 10ms 窗 RMS 包络找静音段（>90ms）打印出来**，
再据此挑 `NARR_START`，使某个逗号后的停顿正好覆盖镜头切换点。
实测「1941年，狼牙山棋盘陀，…」rate=−12% 时全长 6.07s，`NARR_START=0.45` 时"棋盘陀"念完在 2.97s，
停顿 2.97~3.25s 正好盖住 3.00s 的切点 —— 听感上极其工整。

### 程序合成电影感配乐（无版权依赖，纯 numpy）
分层：① 低音持续音（基频 + 2/3 次谐波轻微堆叠）② 失谐锯齿弦垫（±0.35Hz 三份失谐 + 慢渐强）
③ 小二度张力音（3.2s 起缓缓渗入）④ 噪声 riser ⑤ 收束定音鼓（正弦微降调 + 快起振 + 指数衰减 + 敲击瞬态）。
统一走**自造脉冲响应的 FFT 卷积混响**（指数衰减白噪声 + 预延迟），湿信号按 x 的 RMS 归一，避免改变整体响度。
- ⚠️ **riser 千万不要用"逐样点扫频"**：`fq[None,:] - c[:,None]` 会生成 (m × m/2) 的巨型矩阵，
  140k 样点 = 80GB 内存直接崩。拆成 4 个固定频带 + 错峰包络（每带延迟 0.26s）效果一样。
- ⚠️ **一条带慢速调制的音轨不能当唯一底噪**（谷底会落在整段上，听感像音轨断了）：
  先铺一层**恒定床噪声**，再叠场景层，最后统一压到峰值 0.92。
- 逐段验响度：按 1s 窗打 RMS，哪个窗口比邻居低一个数量级就是漏了。

## 2026-10-05 装机验收：RMBG / SeedVR2 / RIFE / IPAdapter / LatentSync（8GB 实测）

### 装机清单（全部 0 积分，权重在 `%COMFY_ROOT%\models`）
- 抠图：1038lab/ComfyUI-RMBG + RMBG-2.0 ✅ 验证通过
- 超分：numz/ComfyUI-SeedVR2_VideoUpscaler + seedvr2_ema_3b_fp8 ✅ 验证通过
- 插帧：Fannovel16/ComfyUI-Frame-Interpolation + rife49.pth ✅ 节点就绪
- 一致性：cubiq/ComfyUI_IPAdapter_plus + CLIP-ViT-H-14 + ip-adapter-plus_sdxl ✅ 节点就绪
- 口型：ShmuelRonen/ComfyUI-LatentSyncWrapper + LatentSync-1.6 ⚠️ 8GB 跑不动（见下）
- I/O：Kosinkadink/ComfyUI-VideoHelperSuite
- 权重下载脚本 `%COMFY_ROOT%\_wb_download.py`（HF 镜像）、节点脚本 `_wb_install_nodes.sh`

### RMBG 节点坑
- API 调用必须显式传全部 optional 参数（process_res/sensitivity/mask_blur/mask_offset/invert_output/refine_foreground/background/background_color），缺一个就 KeyError。
- **invert_output 语义反直觉**：实测"手+园林背景"图 RMBG-2.0 默认保留背景、抠掉主体，必须 invert_output=True。每次用先小图验证方向。
- 透明输出链：RMBG → JoinImageWithAlpha(image, mask) → SaveImage = 真 RGBA PNG。

### SeedVR2 8GB 可行配置（960 目标必 OOM）
- DiT loader：blocks_to_swap=15, offload_device=cpu；VAE loader：encode_tiled/decode_tiled=True
- Upscaler：resolution=720, batch_size=1, color_correction=lab
- 实测 480x660→720x990，1s 素材 ≈90s。只适合短镜头。
- 需要 matplotlib（requirements 里有但容易漏装）。

### VHS API 提交坑
- VHS_LoadVideo 必填 frame_load_cap/select_every_nth/skip_first_frames/custom_width/custom_height（UI disable 标志不豁免 API 校验）。
- VHS_LoadAudio 的 audio_file 必须传绝对路径（validate_path 用 os.path.isfile）。
- 保存视频用 VHS_VideoCombine（format=video/h264-mp4）；**不要用 CreateVideo/SaveVideo**——torchaudio 2.13 保存路径依赖 torchcodec（未装，ImportError）。

### LatentSync 1.6：8GB 显存不可用（已打补丁保住可维护性）
- unet 权重 5GB fp32，模型常驻 ~6.7GB 后必 OOM，fraction 0.95 也救不回。上次跑通的显存下限经验是 12GB+。
- 已打补丁（备份 nodes.py.bak/.bak2）：
  1. 缓存目录 `~/.latentsync16_models` → `%COMFY_ROOT%\_cache`（别写 C 盘）
  2. `torchaudio.save` → soundfile 直写（绕开 torchcodec）
  3. `torchvision.io.write_video`（0.28 已删）→ imageio.mimsave
  4. DeepCache 会复制一份 UNet，<14GB 显存自动跳过
  5. 低端档 BATCH_SIZE=2 + 混合精度；memory fraction 0.95
  6. 它自带的 pip 依赖检查子流程会被 HTTP 代理卡死——手动放标记文件 `%COMFY_ROOT%\_cache\.latentsync16_dependencies_installed` 跳过
- ffmpeg 需在 PATH：`%COMFY_ROOT%\_bin\ffmpeg.exe`，启动 ComfyUI 时挂上。
- **卡通 Q 版脸 LatentSync 检测不到**（训练于真人脸），Q 版数字人口型仍走程序化驱动或云端。
- 下一步候选：MuseTalk（~2GB，8GB 可跑）替代 LatentSync 做真人口型。

## IPAdapter 风格锚定（NoobAI vpred，2026-10-07 实测）
权重: `models/ipadapter/ip-adapter-plus_sdxl_vit-h.safetensors` + `models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`。
链: IPAdapterModelLoader → CLIPVisionLoader → IPAdapterAdvanced(model, ipadapter, clip_vision, image, ...) 接在 ModelSamplingDiscrete 之后、KSampler 之前。

- **"style transfer precise" + weight 0.8 会毁图**：构图搅成万花筒/珍珠光泽 Q 版（vpred 上复现）。别用大权重。
- **可用配方：weight_type="style transfer"，weight=0.25，embeds_scaling="V only"** —— 只锚画风基因（上色质感/装饰密度/边框构图习惯），文字提示词负责内容。0.25 档出图稳定且明显带参考气质。
- weight_type="linear"+K+V 也试过（0.4），出的图结构碎裂，禁用。
- 参考图里的具象元素会串味（ref 有恶魔角 → 出图长恶魔角）：负面加 horns/demon/pointy ears 可压。
- 风格由 IPA 扛后，正面词只写内容+少量构图词（art nouveau frame / english text / cursive handwriting）即可；发色等强先验要 1.2~1.3 加权，否则被参考色带跑。
- 参考图是手机截图时先裁黑边（按行列灰度均值>24 找内容区）再 upload。
