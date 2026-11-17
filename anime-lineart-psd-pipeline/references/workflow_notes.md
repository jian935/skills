# Anime Lineart PSD Pipeline — 参数与排坑

## 环境要求

- Python 3.11+（venv 或系统 Python 均可），需要 `pywin32` / `rembg` / `opencv-python` / `Pillow` / `numpy`
- 依赖包：`rembg`, `onnxruntime`, `opencv-python`, `Pillow`, `numpy`, `psd_tools`, `pywin32`
- 本地 ComfyUI 已启动 `http://127.0.0.1:8188`
- ComfyUI 模型：`NoobAI-XL-Vpred-v1.0.safetensors`, `controlnet-union-sdxl-1.0-promax.safetensors`
- rembg 本地权重：`~/.u2net/isnet-anime.onnx`

## 线稿参数调参

默认在 `make_lineart_v2.py`：

```python
LC.build_skel(rgb, cm, lo_c=32, hi_c=88, lo_b=72, hi_b=170, close=5, minlen=26)
SL.split3_smooth(sk, mag, W, H, width=2.5, q_hi=65, q_mid=35, eps=1.8, iters=5, mavg=3)
```

- 线稿太碎/短线多：`minlen` 加大，`eps` 减小，`iters` 减小。
- 线稿太平滑/丢细节：`eps` 减小，`iters` 减小，`minlen` 减小。
- 线稿太粗/太密：`width` 减小到 2.0，或改用 `al2`（主轮廓+中等细节）。
- 背景杂乱：在 `P` 之后乘以人物掩膜 `char`，只保留人物区线条。

## 常见失败

1. **NoobAI 线稿出彩色插画**：ComfyUI 缺少 `comfyui_controlnet_aux` 预处理器，NoobAI 会把结构提示词重绘成带灰调/上色的插画。解决：改用 Canny+`smooth_line.py` 提取线稿，或安装 `comfyui_controlnet_aux`。
2. **PSD 线稿层显示旧版**：build_psd.py 可能有缓存。解决：重建前确认 `图层/<key>/线稿-完整.png` 时间戳最新，build 后立刻用 psd_tools 回读 alpha 占比验证。
3. **PS COM 连接失败**：Photoshop 未启动或上次崩溃残留。`ps_conn.ensure()` 会尝试重启；如仍失败，手动 taskkill Photoshop.exe 再试。
4. **C 盘空间暴涨**：PS COM 批量保存大 PSD 时会在 `%LOCALAPPDATA%\Temp\Photoshop Temp*` 产生大量暂存。治本：PS 首选项里把暂存盘改到 E 盘。

## 交付文件命名

沿用 `OUT_DIR/<主体>_<类型>.<ext>`：

- `<主体>_分层.psd`
- `<主体>_成稿.png`
- `<主体>_线稿_白底.png`
- `<主体>_分割预览.png`
- `<主体>_分层_预览.jpg`
- `<主体>_分层_线稿预览.jpg`
