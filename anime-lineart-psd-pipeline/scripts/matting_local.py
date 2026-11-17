# -*- coding: utf-8 -*-
"""本地 rembg 抠图（isnet-anime），深背景/深色服装场景专用，不依赖云端。
用法: python matting_local.py <原图.png> <输出alpha.png>
"""
import os, sys
import numpy as np
from PIL import Image
import rembg
from rembg import new_session, remove

W, H = 1024, 1536


def matte(img_path, out_path):
    im = Image.open(img_path).convert("RGB")
    sess = new_session("isnet-anime")
    out = remove(im, session=sess)
    if out.size != (W, H):
        out = out.resize((W, H), Image.LANCZOS)
    alpha = np.asarray(out.split()[3], np.uint8)
    out2 = np.dstack([np.zeros((H, W, 3), np.uint8), alpha])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Image.fromarray(out2, "RGBA").save(out_path)
    cov = (alpha > 102).mean() * 100
    print("  [%s] 人物区 %.1f%%" % (os.path.basename(img_path), cov))
    return cov


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python matting_local.py <原图> <输出alpha.png>")
        sys.exit(1)
    matte(sys.argv[1], sys.argv[2])
