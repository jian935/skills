# -*- coding: utf-8 -*-
"""线稿三层生成器（伪厚涂 PSD 用）—— 自包含版，只依赖 numpy / opencv / PIL

用法：
    python lineart_canny.py <成品图> <输出目录> [--charmask <抠图alpha.png>] [--white <白底图.png>]

产出：线稿-轮廓粗线.png / 线稿-中间线.png / 线稿-细节细线.png（透明底纯黑线，RGBA）
      以及可选的「白底黑线」校验图。

设计要点（改参数前先读）：
  · 双阈值 Canny：主体区 32/88 保细节，背景区 72/170 只留大结构
  · 骨架化后按**骨架连通域长度**剪枝，不要剪肥掩膜
  · 拉直必须走「加粗→模糊→阈值→再骨架化」；直接对 1px 骨架模糊+阈值会把斜线整条删掉
  · 三级线宽**递进完整**：P1=主轮廓5px / P2=+中线3px / P3=全部=完整线稿（单开细线层即完整）
"""
import os
import sys
import argparse
import numpy as np
import cv2
from PIL import Image

NAMES = ["线稿-轮廓粗线", "线稿-中间线", "线稿-细节细线"]


# ---------------------------------------------------------------- 基础
def skeletonize(m):
    """Zhang-Suen 细化（numpy 向量化，1024x1536 约 20~40 轮）"""
    im = (m > 0).astype(np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = np.pad(im, 1)
            P2, P3, P4 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:]
            P5, P6, P7 = p[2:, 2:], p[2:, 1:-1], p[2:, :-2]
            P8, P9 = p[1:-1, :-2], p[:-2, :-2]
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                c1, c2 = P2 * P4 * P6, P4 * P6 * P8
            else:
                c1, c2 = P2 * P4 * P8, P2 * P6 * P8
            rm = (im == 1) & (B >= 2) & (B <= 6) & (A == 1) & (c1 == 0) & (c2 == 0)
            if rm.any():
                im[rm] = 0
                changed = True
    return im


def prep_gray(rgb, rounds=2, sc=34):
    """轻滤波：双边×rounds + 中值3。下重手（sc>=50 或 median 5）会把细节抹光"""
    f = np.clip(rgb, 0, 255).astype(np.uint8)
    for _ in range(rounds):
        f = cv2.bilateralFilter(f, 9, sc, 9)
    f = cv2.medianBlur(f, 3)
    return (f[..., 0] * .299 + f[..., 1] * .587 + f[..., 2] * .114).astype(np.float32) / 255.0


def grad_mag(fg):
    gx = cv2.Sobel(fg, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(fg, cv2.CV_32F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


def prune(sk, minlen):
    n, lab, st, _ = cv2.connectedComponentsWithStats(sk.astype(np.uint8), 8)
    keep = np.zeros_like(sk, np.uint8)
    for i in range(1, n):
        if st[i, 4] >= minlen:
            keep[lab == i] = 1
    return keep


def straighten(sk, dil=1, blur=1.1, t=0.5):
    """拉直锯齿：加粗→模糊→阈值→再骨架化。连通性靠把原骨架并回来保证"""
    m = cv2.dilate(sk.astype(np.uint8),
                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dil * 2 + 1,) * 2))
    b = cv2.GaussianBlur(m.astype(np.float32), (0, 0), blur)
    m2 = np.maximum((b > t).astype(np.uint8), sk.astype(np.uint8))
    return skeletonize(m2)


def charmask(alpha_png, H, W, grow=20):
    """抠图 alpha → 主体掩膜（外扩 grow 像素 + 羽化，用作"主体/背景"双阈值切换）"""
    if not alpha_png or not os.path.exists(alpha_png):
        return np.ones((H, W), np.float32)
    a = np.asarray(Image.open(alpha_png).convert("RGBA"), np.float32)[..., 3] / 255.0
    if a.shape != (H, W):
        a = cv2.resize(a, (W, H), interpolation=cv2.INTER_LINEAR)
    m = (a > 0.4).astype(np.uint8)
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow * 2 + 1,) * 2))
    return np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), grow + 1), 0, 1)


# ---------------------------------------------------------------- 主链路
def build_skel(rgb, cm, lo_c=32, hi_c=88, lo_b=72, hi_b=170, close=5, minlen=30):
    fg = prep_gray(rgb)
    g8 = (fg * 255).astype(np.uint8)
    m = np.where(cm > 0.5, cv2.Canny(g8, lo_c, hi_c), cv2.Canny(g8, lo_b, hi_b)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close)))
    sk = prune(skeletonize(m), minlen)
    sk = prune(straighten(sk, 1, 1.1, 0.5), minlen)
    return sk, grad_mag(fg)


def split3(sk, mag, r=1, q_hi=65.0, q_mid=35.0):
    """**统一线宽** v4 —— 最终定稿语义（用户 09-29 第三次打回：「我要的是粗细一致」）。

    沿革（三次验收教训）：
    ❌ v1 按像素互斥分档：弱线穿过粗线膨胀带时像素被划给粗/中层，
       细节细线层只剩孤立碎段 —— 验收「细线层不完整」打回。
    ❌ v2 按线互斥归档：细线层仍只有约 1/3 的线 —— 「细线层不能全部显示」再打回。
    ❌ v3 递进完整：每层都完整了，但线宽仍分 5/3/1 三级 —— 「我要的是粗细一致」三打回。
    ✅ v4 统一线宽：**所有线条一律 2r+1 px（默认 3px，椭圆核对角实宽≈2px）**，
       三层只在「包含多少条线」上递进：P1 主轮廓 / P2 +细节 / P3 = 完整线稿。
       实测参考图 green_lineart 线宽中位 2.0px / p75 2.8px，与 v4 输出一致。
    白底层/轻线版直接用 P3；轻版 = 同一套线换浅灰（RGB≈140），**不要**把轻版做细。
    """
    m_on = np.where(sk > 0, mag, 0).astype(np.float32)
    m_s = cv2.dilate(m_on, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    v = m_s[sk > 0]
    if v.size == 0:
        z = np.zeros(sk.shape, np.uint8)
        return z, z.copy(), z.copy()
    t_hi, t_mid = np.percentile(v, q_hi), np.percentile(v, q_mid)
    hi = (sk > 0) & (m_s >= t_hi)
    md = (sk > 0) & ~hi & (m_s >= t_mid)
    lo = (sk > 0) & ~hi & ~md
    K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r * 2 + 1,) * 2)
    P1 = cv2.dilate(hi.astype(np.uint8), K)
    P2 = cv2.dilate((hi | md).astype(np.uint8), K)
    P3 = cv2.dilate((hi | md | lo).astype(np.uint8), K)
    return P1, P2, P3


def aa(mask, gain=1.5, blur=0.6):
    """抗锯齿定稿：max(mask, blur*gain) —— 线芯纯实心、羽化只在外侧。

    ❌ 单纯 blur*gain：1px 细线模糊后峰值只剩 ~0.45，怎么提 gain 都发灰
      （实测中间线 alpha 中位 0.20、细节线 0.16，PS 里"不明显"被打回）。
    """
    m = mask.astype(np.float32)
    return np.clip(np.maximum(m, cv2.GaussianBlur(m, (0, 0), blur) * gain), 0, 1)


def save_black(alpha, path):
    H, W = alpha.shape
    out = np.dstack([np.zeros((H, W, 3), np.uint8),
                     (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)


def save_white(alpha, path):
    v = (255 - np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.dirname(path)) or ".", exist_ok=True)
    Image.fromarray(np.dstack([v, v, v])).save(path)


def generate(final_png, outdir, alpha_png=None, white_png=None, verbose=True):
    rgb = np.asarray(Image.open(final_png).convert("RGB"), np.float32)
    H, W = rgb.shape[:2]
    cm = charmask(alpha_png, H, W)
    sk, mag = build_skel(rgb, cm)
    L1, L2, L3 = split3(sk, mag)
    full = np.clip(aa(L1, 1.0) + aa(L2, 1.0) + aa(L3, .95), 0, 1)
    for nm, m in zip(NAMES, (L1, L2, L3)):
        save_black(aa(m, 1.0 if nm != NAMES[2] else .95), os.path.join(outdir, nm + ".png"))
    if white_png:
        save_white(full, white_png)
    if verbose:
        binm = (full > 0.45).astype(np.uint8)
        d = cv2.distanceTransform(binm, cv2.DIST_L2, 5)
        n, _, st, _ = cv2.connectedComponentsWithStats(binm, 8)
        cont = st[1:, 4].max() / max(st[1:, 4].sum(), 1) if n > 1 else 0
        ov = int(((L1 > 0) & (L2 > 0)).sum() + ((L1 > 0) & (L3 > 0)).sum() + ((L2 > 0) & (L3 > 0)).sum())
        print("覆盖率 %.2f%%  中位线宽 %.1fpx  最大段 %.0f%%  三层重叠 %d px"
              % (binm.mean() * 100, np.median(d[binm > 0]) * 2, cont * 100, ov))
        print("覆盖率应在 6~16%%，中位线宽 2.5~3.0px，最大段 ≥45%%，重叠必须为 0")
    return full


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("final")
    ap.add_argument("outdir")
    ap.add_argument("--charmask", default=None)
    ap.add_argument("--white", default=None)
    a = ap.parse_args()
    generate(a.final, a.outdir, a.charmask, a.white)
