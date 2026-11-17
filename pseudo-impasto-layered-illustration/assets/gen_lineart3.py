# -*- coding: utf-8 -*-
"""参考图风格线稿（27b 批定稿）：LineartAnime（informative-drawings anime）
直接从彩稿抽线 —— 线条天然连续闭合，对齐用户给的填色书参考。
→ 自适应拉伸 → 小断口桥接 → 实心化（线芯 alpha=1、边缘 AA）。
不写草稿层（草稿效果用户已验收，保留原文件）。

用法: 用 ComfyUI 内嵌 python 跑:
  python gen_lineart3.py <彩稿.png> <key>   （在 ComfyUI 的嵌入式 Python 环境里执行）
产出:
  线稿/<key>_线稿_白底.png   图层/<key>/线稿-完整.png
"""
import os, sys
import numpy as np
import cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def solidify(ink):
    """27b：封闭连续 + 墨色饱满。
    ① 3x3 闭运算两轮桥接 ≤2px 小断口（眼睛高光等小白区不受影响）；
    ② 二值核心 + 0.7px 高斯回羽化：线芯 alpha=1（完全不透），仅边缘留 AA。"""
    core = (ink > 0.30).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    soft = cv2.GaussianBlur(core.astype(np.float32), (0, 0), 0.7)
    return np.clip(soft * 1.35, 0, 1), core


def main(img_path, key):
    from controlnet_aux import LineartAnimeDetector
    det = LineartAnimeDetector.from_pretrained("lllyasviel/Annotators")
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    la = det(img, detect_resolution=1536, image_resolution=1536)
    g = 255.0 - np.asarray(la.convert("L"), np.float32)   # 库输出黑底白线，反相回白底黑线
    if g.shape[:2] != (1536, 1536):
        g = cv2.resize(g, (1536, 1536), interpolation=cv2.INTER_AREA)
    # 27c：先轻度平滑原始灰阶——发梢/衣纹里的锯齿状碎笔在平滑后连成顺滑长线，
    # 再反锐化压深，阈值化就不会切出「虚线感」碎段（对齐参考图的连贯笔触）。
    g = cv2.GaussianBlur(g, (0, 0), 1.2)
    # 原始灰阶连续干净但线极细极淡（1~2px、灰 150~230）：
    # ① 反锐化把线压深；② 3x3 最小值滤波（对白底=线增粗变黑）；低阈值一网打尽。
    # （密集发丝区略黏连可接受——参考图眼睛/睫毛同样是浓黑；剔块会切碎发丝，禁用）
    blur = cv2.GaussianBlur(g, (0, 0), 2.0)
    g = np.clip(g - 0.8 * (g - blur), 0, 255)
    g = cv2.erode(g, np.ones((3, 3), np.uint8))
    lo, hi = np.percentile(g, 1), np.percentile(g, 99.5)
    ink = np.clip((hi - g) / max(hi - lo, 1e-6), 0, 1)
    core = (ink > 0.25).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=2)
    # 回到成图分辨率：面积平均下采样 + 回羽化（线芯满墨、边缘 AA）
    b = cv2.resize(core.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA)
    ink = np.clip(cv2.GaussianBlur(b, (0, 0), 0.7) * 1.45, 0, 1)
    core = (b > 0.5).astype(np.uint8)

    H, W = ink.shape
    os.makedirs(os.path.join(HERE, "线稿"), exist_ok=True)
    white = np.clip((1 - ink) * 255, 0, 255).astype(np.uint8)
    Image.fromarray(white, "L").convert("RGB").save(
        os.path.join(HERE, "线稿", "%s_线稿_白底.png" % key))
    outdir = os.path.join(HERE, "图层", key)
    os.makedirs(outdir, exist_ok=True)
    rgba = np.dstack([np.zeros((H, W, 3), np.uint8),
                      np.clip(ink * 255, 0, 255).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(os.path.join(outdir, "线稿-完整.png"))
    print("  [%s] LineartAnime 线稿：墨量 %.2f%%" % (key, float((core > 0).mean()) * 100))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
