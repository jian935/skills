---
name: anime-lineart-psd-pipeline
description: 将动漫/二次元风格成图转成约 20 层可上色 PSD 的完整本地流水线：ComfyUI 出图 → rembg 抠图 → Canny+矢量平滑生成白底线稿 → 明度/色调分层 → Photoshop COM 组装分层 PSD。适用于线稿风、平涂风、赛璐珞上色稿的 PSD 交付。
---

# Anime Lineart PSD Pipeline

## When to Use

用户需要把一张动漫/二次元风格的成图，或者从提示词生成的成图，做成：
- 约 20 层的可上色 PSD
- 白底 + 纯黑平滑线稿（连续不断线、无短线）
- 底色按明度/色调拆分
- 高光、阴影、冷暖调色层

触发词：「分层 PSD」「线稿 PSD」「可上色」「赛璐珞/平涂」「smooth lineart」「coloring book」「20 层 PSD」。

## What This Skill Does

1. **成图生成**（可选）：用本地 ComfyUI + NoobAI-XL-Vpred 按提示词出 1024×1536 竖版成图。
2. **本地抠图**：用 rembg + isnet-anime.onnx 对深色服装/深色背景鲁棒地抠出人物 alpha。
3. **线稿生成**：Canny 边缘 + `smooth_line.py` 矢量 Chaikin 平滑，输出统一 2.5px 黑线、纯白底、连续无短线。
4. **20 层分层**：底色按 8 档明度（极暗/墨色/深蓝/暗蓝/深灰/中灰/浅灰/亮银）+ 皮肤 + 高光 3 层 + 阴影 3 层 + 冷暖调色 2 层。
5. **PSD 组装**：Photoshop COM 自动置入图层、设混合模式/不透明度、保存 PSD 到 `OUT_DIR`。

## Workflow

1. 确认 ComfyUI 已启动在 `127.0.0.1:8188`，且已下载 `NoobAI-XL-Vpred-v1.0.safetensors` 与 `controlnet-union-sdxl-1.0-promax.safetensors`。
2. 在工作目录（如 `WORK_DIR/<项目名>/`）放置成图 `<主题>.png`。
3. 运行 `python gen_illustration.py` 生成成图（可选，用户已提供则跳过）。
4. 运行 `python matting_local.py <图>.png <alpha.png>` 生成抠图掩码。
5. 运行 `python make_lineart_v2.py` 生成白底黑线线稿。
6. 运行 `python layers_20.py <图>.png <alpha.png> <主题>` 生成底色/高光/阴影层。
7. 运行 `python build_psd.py <主题> <docname>` 组装 PSD。
8. 复制 `<主题>_成稿.png`、`<主题>_线稿_白底.png`、`<主题>_分割预览.png` 等到交付目录。

## Important Notes

- **不要直接复用 NoobAI 的生成式线稿**：NoobAI 在缺少 lineart 预处理器时，会把结构提示词重绘成带颜色/灰调的插画，不是纯白底黑线稿。
- **平滑线稿的关键参数**：`smooth_line.split3_smooth(..., eps=1.8, iters=5, mavg=3, width=2.5)`，出 2.5px 均匀线，短线占比可压到 0%。
- **PSD 最底层为纯白**：`build_psd.py` 新建文档用 `DocumentFill.WHITE`，并保留「背景-白色」像素层，避免透明棋盘格。
- **线稿层默认隐藏**：打开 PSD 默认显示上色+阴影+高光效果；需要看线稿时打开「①线稿」组即可，下方已是白底。
- ⛔ **顶层不得放不透明「成图」整图**（2026-10-13 用户明令：成图必须由下层逐级演化而来）。
  本管线的「背景-原色」在不透明最底层做画布底，这是允许的；但**禁止**再在最顶放一张不透明成品图当"成图"。
  需要"全开=成品逐像素一致"时，用顶层半透明补差层：
  `a = clip(|target-mid|max/0.10, 0, 1)`、`C = clip(mid + (target-mid)/a)`，NORMAL 100%。

## Resources

### scripts/

- `gen_illustration.py`：ComfyUI NoobAI 出图，支持 CFG7 + DPM++ 2M Karras。
- `matting_local.py`：rembg isnet-anime 本地抠图。
- `make_lineart_v2.py`：Canny + 矢量平滑生成白底黑线线稿。
- `layers_20.py`：20 层明度/色调/高光/阴影分层。
- `build_psd.py`：Photoshop COM 自动组装 PSD。
- `ps_conn.py`：连接 Photoshop，支持自动查找路径、重启 PS。

### references/

- `workflow_notes.md`：参数说明与常见失败原因。

