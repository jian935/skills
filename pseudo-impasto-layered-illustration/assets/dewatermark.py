# -*- coding: utf-8 -*-
"""去掉出图平台打在右下角的半透明水印。

水印在半透明的浅色文字，直接 inpaint 会把叶片纹理糊掉。
改成：先用 cv2.inpaint 打底，再用**水平镜像的邻近区域**做补丁，
羽化融合 —— 底部两侧都是落叶地面，镜像补丁接得上。
"""
import os, sys
import numpy as np
import cv2
from PIL import Image, ImageFilter

# 水印包围盒（针对 1024x1536 出图，按比例给）
REL = (0.860, 0.944, 0.998, 0.998)      # x0,y0,x1,y1 相对坐标
PAD = 10


def clean(path, out=None, box=None):
    im = Image.open(path).convert("RGB")
    W, H = im.size
    a = np.asarray(im, np.uint8)
    x0, y0, x1, y1 = box or (int(REL[0] * W), int(REL[1] * H), int(REL[2] * W), int(REL[3] * H))
    x0, y0 = max(0, x0 - PAD), max(0, y0 - PAD)
    x1, y1 = min(W, x1 + PAD), min(H, y1 + PAD)

    # 1) inpaint 打底
    m = np.zeros((H, W), np.uint8)
    m[y0:y1, x0:x1] = 255
    base = cv2.inpaint(a, m, 14, cv2.INPAINT_TELEA)

    # 2) 镜像补丁：以画布竖直中线镜像到左侧同位
    sw, sh = x1 - x0, y1 - y0
    sx = W - x1
    patch = a[y0:y1, max(0, sx):max(0, sx) + sw][:, ::-1]
    if patch.shape[:2] != (sh, sw):
        patch = np.asarray(Image.fromarray(patch).resize((sw, sh), Image.LANCZOS))

    # 3) 羽化遮罩融合（边缘 30% 渐变）
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    fx = np.clip(np.minimum(xx, sw - 1 - xx) / (sw * 0.28), 0, 1)
    fy = np.clip(np.minimum(yy, sh - 1 - yy) / (sh * 0.28), 0, 1)
    w = (fx * fy) ** 0.7
    w = cv2.GaussianBlur(w, (0, 0), 2.0)[..., None]

    out_a = base.copy()
    out_a[y0:y1, x0:x1] = (base[y0:y1, x0:x1] * (1 - w) + patch * w).astype(np.uint8)
    res = Image.fromarray(out_a).filter(ImageFilter.GaussianBlur(0.0))
    dst = out or path
    res.save(dst, quality=97)
    print("  去水印 %s  区域=(%d,%d)-(%d,%d)" % (os.path.basename(dst), x0, y0, x1, y1))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        clean(p)
