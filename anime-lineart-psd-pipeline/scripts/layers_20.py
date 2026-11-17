# -*- coding: utf-8 -*-
"""哥特洛丽塔双人 · 分层核心（13 层，Q 版管线适配版）

与 19-qban-flow/layers_flat.py 的差异：
  · 画幅 1024x1536
  · 背景-纯色 → **背景-原色**（原图全幅不透明做底层，本图背景是复杂场景不是纯色）
  · 无效果图 t = 原图背景 + 人物区平涂色块（效果层只作用于人物区）
  · 整体-暖调 alpha = 0.15 × 人物区软边（不再全画幅）
  · 线稿走 smooth_line.split3_smooth（平滑矢量线，2026-09-29 定稿）
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cv2
from PIL import Image

import lineart_canny as LC
import smooth_line as SM

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1024, 1536


def load_rgb(p):
    return np.asarray(Image.open(os.path.join(HERE, p)).convert("RGB"), np.float32)


def gblur(a, s):
    return cv2.GaussianBlur(a.astype(np.float32), (0, 0), s)


def solid(color):
    c = np.zeros((H, W, 3), np.float32)
    c[:] = np.asarray(color, np.float32).reshape(1, 3)
    return c


def save_rgba(color, alpha, path):
    c = color if np.asarray(color).ndim == 3 else solid(color)
    out = np.dstack([np.clip(c * 255, 0, 255).astype(np.uint8),
                     (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)


def largest_components(mask, min_area=0):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    out = np.zeros_like(mask, np.uint8)
    for i in range(1, n):
        if st[i, 4] >= min_area:
            out[lab == i] = 1
    return out


def soften(mask, blur=1.0):
    return np.clip(gblur(mask.astype(np.float32), blur), 0, 1)


def lum(a):
    return a[..., 0] * .299 + a[..., 1] * .587 + a[..., 2] * .114


def inv_multiply(t, b, e):
    eS = np.maximum(e, 1e-4)[..., None]
    return np.clip((t - b * (1 - eS)) / np.maximum(b * eS, 1e-4), 0, 1)


def inv_screen(t, b, e):
    eS = np.maximum(e, 1e-4)[..., None]
    return np.clip((t - b) / np.maximum(eS * (1 - b), 1e-4), 0, 1)


def inv_softlight(t, b, e):
    lo = np.zeros_like(b)
    hi = np.ones_like(b)
    eS = e[..., None]

    def sl(bv, cv):
        return np.where(
            cv <= 0.5,
            bv - (1 - 2 * cv) * bv * (1 - bv),
            bv + (2 * cv - 1) * ((np.where(bv <= 0.25, ((16 * bv - 12) * bv + 4) * bv, np.sqrt(bv))) - bv),
        )

    for _ in range(26):
        mid = (lo + hi) / 2
        val = b * (1 - eS) + sl(b, mid) * eS
        hi = np.where(val < t, mid, hi)
        lo = np.where(val < t, lo, mid)
    return np.clip((lo + hi) / 2, 0, 1)


def compose(base, stack_bottom_up):
    out = base.copy()
    for mode, color, alpha in stack_bottom_up:
        e = alpha[..., None]
        if mode == "NORMAL":
            out = out * (1 - e) + color * e
        elif mode == "MULTIPLY":
            out = out * (1 - e) + (out * color) * e
        elif mode == "SCREEN":
            out = out * (1 - e) + (1 - (1 - out) * (1 - color)) * e
        elif mode == "SOFT_LIGHT":
            cv_ = color
            bv = out
            sl = np.where(
                cv_ <= 0.5,
                bv - (1 - 2 * cv_) * bv * (1 - bv),
                bv + (2 * cv_ - 1) * ((np.where(bv <= 0.25, ((16 * bv - 12) * bv + 4) * bv, np.sqrt(bv))) - bv),
            )
            out = out * (1 - e) + sl * e
    return np.clip(out, 0, 1)


TONAL = [("底色-亮银", 0.72, 9.0), ("底色-浅灰", 0.58, 9.0),
         ("底色-中灰", 0.45, 9.0), ("底色-深灰", 0.33, 9.0),
         ("底色-暗蓝", 0.24, 9.0), ("底色-深蓝", 0.16, 9.0),
         ("底色-墨色", 0.08, 9.0), ("底色-极暗", -1.0, 9.0)]


def lineart_sparse(rgb255, cm):
    """哥特双人专用线稿：蕾丝纹理尺度小（4~8px），大 σ 预模糊融掉纹理、保留结构。
    参数由 线稿试验/线密_总表2、3 三轮横评定档（I 档 = P2 强档）。"""
    f = np.clip(rgb255, 0, 255).astype(np.uint8)
    for _ in range(2):
        f = cv2.bilateralFilter(f, 9, 40, 9)
    g = cv2.GaussianBlur(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), (0, 0), 2.0)
    m = np.where(cm > 0.5, cv2.Canny(g, 55, 125), cv2.Canny(g, 85, 185)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE,
                         cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    sk = LC.prune(LC.skeletonize(m), 60)
    sk = LC.prune(LC.straighten(sk, 1, 1.1, 0.5), 60)
    mag = LC.grad_mag(g.astype(np.float32) / 255.)
    a1, a2, a3 = SM.split3_smooth(sk, mag, W, H)
    return a2          # P2 = 强+中档，密度与可读性平衡


def color_blocks(rgb, char, K=8):
    """哥特双人版：皮肤（暖色+脸部种子）优先，其余按**色调四分**（白银/灰蓝/深蓝/墨色）。
    本图人物服饰与背景同为蓝黑系、蕾丝花纹密，解剖语义命名不可靠。rgb 0..1"""
    u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)
    flat = cv2.pyrMeanShiftFiltering(u8, 9, 26, maxLevel=3).astype(np.float32)
    V = lum(flat / 255.)

    P = largest_components((char > 0.5).astype(np.uint8), min_area=W * H * 0.02)
    P = cv2.morphologyEx(P, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))

    R, B = rgb[..., 0], rgb[..., 2]
    # ---- 皮肤：暖色（R>B）+ 亮度中高，脸部种子在画面上部
    warm = (P > 0) & (R - B > 0.025) & (V > 0.55)
    warm_u8 = cv2.morphologyEx(warm.astype(np.uint8), cv2.MORPH_OPEN,
                               cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, labw, stw, _ = cv2.connectedComponentsWithStats(warm_u8, 8)
    skin = np.zeros((H, W), np.uint8)
    for i in range(1, n):
        x, y, w, h, area = stw[i]
        if area < 260:
            continue
        if (y + h / 2) < H * 0.60 or area > W * H * 0.004:   # 脸在上部，或足够大（手）
            skin[labw == i] = 1
    skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    skin = largest_components(cv2.medianBlur(skin, 21), min_area=300)
    have_skin = skin.sum() > 2000
    face_seed = largest_components(((skin > 0) & (np.mgrid[0:H, 0:W][0] < H * 0.5)).astype(np.uint8), min_area=500)

    # ---- 其余人物像素 → kmeans → 色调桶
    rest = (P > 0) & (skin == 0)
    pts = np.where(rest)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.5)
    _, labv, centers = cv2.kmeans(flat[pts].astype(np.float32), K, None, crit, 6, cv2.KMEANS_PP_CENTERS)
    lab = np.zeros((H, W), np.uint8)
    lab[pts] = (labv.ravel() + 1).astype(np.uint8)
    lab = cv2.medianBlur(lab, 31)
    lab = cv2.medianBlur(lab, 31)

    layers = {}
    if have_skin:
        layers["底色-皮肤"] = skin
    for nm, thr, _ in TONAL:
        m = np.zeros((H, W), np.uint8)
        cols = []
        for c in range(1, K + 1):
            blk = lab == c
            if blk.sum() < 400:
                continue
            col = centers[c - 1] / 255.
            v = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
            lo = thr if thr >= 0 else -1.0
            hi = TONAL[TONAL.index([t for t in TONAL if t[0] == nm][0]) - 1][1] if nm != TONAL[0][0] else 9.0
            if lo <= v < hi:
                m |= blk.astype(np.uint8)
                cols.append(col)
        m = cv2.medianBlur(m, 21)
        layers[nm] = m

    # 色调桶互斥（kmeans 边界像素可能同时进两桶：按 白银>灰蓝>深蓝>墨色 先占）
    taken = np.zeros((H, W), bool)
    for nm in [t[0] for t in TONAL]:
        layers[nm] = ((layers[nm] > 0) & (~taken) & (P > 0) & (skin == 0)).astype(np.uint8)
        taken |= layers[nm] > 0
    if have_skin:
        layers["底色-皮肤"] = ((skin > 0) & (P > 0)).astype(np.uint8)

    # 每层固有色（中位）
    infos = {}
    for nm, m in layers.items():
        if m.sum() > 100:
            infos[nm] = np.median(rgb[m > 0].reshape(-1, 3), axis=0)
    # 没覆盖到的人物像素 → 就近色调（按亮度）
    covered = np.zeros((H, W), bool)
    for nm, m in layers.items():
        covered |= m > 0
    miss = (P > 0) & (~covered)
    if miss.any():
        vm = V.copy()
        tgt = np.full((H, W), -1, np.int32) * 0
        bounds = [9.0] + [t[1] for t in TONAL[:-1]]
        names = [t[0] for t in TONAL]
        for i, nm in enumerate(names):
            lo = bounds[i + 1] if i + 1 < len(bounds) else -1
            hi = bounds[i]
            layers[nm] |= ((miss & (vm >= lo) & (vm < hi)).astype(np.uint8)) if nm in layers else 0

    # 最近色重投影（空间加成；皮肤拿脸部种子强加成）
    act = [nm for nm in (["底色-皮肤"] + [t[0] for t in TONAL]) if nm in layers and (layers[nm] > 0).any()]
    if len(act) >= 2:
        stack_d = []
        for nm in act:
            col = infos.get(nm, np.array([0.5, 0.5, 0.5], np.float32))
            d = ((rgb - col.reshape(1, 1, 3)) ** 2).sum(-1)
            d -= gblur((layers[nm] > 0).astype(np.float32), 81) * 5000.0
            if nm == "底色-皮肤" and face_seed.sum() > 300:
                gz = cv2.dilate(face_seed, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))) > 0
                d[gz] -= 3500.0
            stack_d.append(d)
        D = np.stack(stack_d)
        idx = D.argmin(0)
        for i, nm in enumerate(act):
            layers[nm] = ((idx == i) & (P > 0)).astype(np.uint8)
        lab2 = np.zeros((H, W), np.uint8)
        for i, nm in enumerate(act):
            lab2[layers[nm] > 0] = i + 1
        lab2 = cv2.medianBlur(lab2, 15)
        lab2[(P == 0)] = 0
        for i, nm in enumerate(act):
            layers[nm] = (lab2 == i + 1).astype(np.uint8)
    for nm in layers:
        if (layers[nm] > 0).sum() > 100:
            infos[nm] = np.median(rgb[layers[nm] > 0].reshape(-1, 3), axis=0)
        layers[nm] = dict(col=infos.get(nm, np.array([0.5, 0.5, 0.5], np.float32)),
                          mask=layers[nm], c=-1)
    return layers, V, P, flat, (0, 0, have_skin)


def build(img_path, alpha_path, out_key, verbose=True):
    rgb = np.asarray(Image.open(img_path).convert("RGB"), np.float32) / 255.
    char = np.asarray(Image.open(alpha_path).convert("RGBA"), np.float32)[..., 3] / 255.0
    layers, V, P, flat, (y_eye, y_eye_bot, have_eye) = color_blocks(rgb, char)
    outdir = os.path.join(HERE, "图层", out_key)
    os.makedirs(outdir, exist_ok=True)
    Psoft = soften((P > 0).astype(np.float32), 2.0)

    # 无效果图 t：背景 = 原图（复杂背景保真），人物区 = 平涂色块
    t = rgb.copy()
    order = ["底色-极暗", "底色-墨色", "底色-深蓝", "底色-暗蓝", "底色-深灰",
             "底色-中灰", "底色-浅灰", "底色-亮银", "底色-皮肤"]
    for nm in order:
        if nm in layers:
            a = soften(layers[nm]["mask"].astype(np.float32), 0.8)
            t = t * (1 - a[..., None]) + solid(layers[nm]["col"]) * a[..., None]

    Lrgb, Lt = lum(rgb), lum(t)
    diffL = Lrgb - Lt

    m_heavy = largest_components(((diffL < -0.10) & (P > 0)).astype(np.uint8), min_area=24)
    a_heavy = soften(m_heavy, 1.1) * 0.75
    C_heavy = inv_multiply(rgb, t, a_heavy)
    m_light = largest_components(((diffL < -0.018) & ~(m_heavy > 0) & (P > 0)).astype(np.uint8), min_area=24)
    a_light = soften(m_light, 1.1) * 0.40
    C_light = inv_multiply(rgb, t, a_light)
    m_strong = largest_components(((diffL > 0.12) & (P > 0)).astype(np.uint8), min_area=16)
    a_strong = soften(m_strong, 1.0) * 0.95
    C_strong = inv_screen(rgb, t, a_strong)
    m_hi = largest_components(((diffL > 0.015) & ~(m_strong > 0) & (P > 0)).astype(np.uint8), min_area=24)
    a_hi = soften(m_hi, 1.1) * 0.75
    C_hi = inv_screen(rgb, t, a_hi)
    a_warm = np.full((H, W), 0.15, np.float32) * Psoft      # 只作用人物区
    C_warm = inv_softlight(rgb, t, np.maximum(a_warm, 1e-3))
    m_detail_sh = largest_components(((diffL < -0.004) & ~(m_heavy > 0) & ~(m_light > 0) & (P > 0)).astype(np.uint8), min_area=16)
    a_detail_sh = soften(m_detail_sh, 1.0) * 0.22
    C_detail_sh = inv_multiply(rgb, t, a_detail_sh)
    m_detail_hi = largest_components(((diffL > 0.004) & ~(m_strong > 0) & ~(m_hi > 0) & (P > 0)).astype(np.uint8), min_area=16)
    a_detail_hi = soften(m_detail_hi, 1.0) * 0.45
    C_detail_hi = inv_screen(rgb, t, a_detail_hi)
    a_cold = np.full((H, W), 0.12, np.float32) * Psoft
    C_cold = inv_softlight(rgb, t, np.maximum(a_cold, 1e-3))

    sbu = []
    for nm in order:
        if nm in layers:
            sbu.append(("NORMAL", solid(layers[nm]["col"]), soften(layers[nm]["mask"].astype(np.float32), 0.8)))
    sbu.append(("MULTIPLY", C_light, a_light))
    sbu.append(("MULTIPLY", C_heavy, a_heavy))
    sbu.append(("MULTIPLY", C_detail_sh, a_detail_sh))
    sbu.append(("SOFT_LIGHT", C_warm, a_warm))
    sbu.append(("SOFT_LIGHT", C_cold, a_cold))
    sbu.append(("SCREEN", C_hi, a_hi))
    sbu.append(("SCREEN", C_strong, a_strong))
    sbu.append(("SCREEN", C_detail_hi, a_detail_hi))
    recon = compose(rgb, sbu)                                # 底 = 背景原色
    err = float(np.abs(recon - rgb).mean())
    if verbose:
        print("  [%s] 还原误差 mean %.2f%%  p99 %.3f" % (out_key, err * 100, float(np.percentile(np.abs(recon - rgb), 99))))

    out = {"背景-原色": (rgb, np.ones((H, W), np.float32))}
    for nm in order:
        if nm in layers:
            out[nm] = (solid(layers[nm]["col"]), soften(layers[nm]["mask"].astype(np.float32), 0.8))
    out.update({
        "阴影-轻": (C_light, a_light), "阴影-重": (C_heavy, a_heavy),
        "阴影-细节": (C_detail_sh, a_detail_sh),
        "整体-暖调": (C_warm, a_warm),
        "整体-冷调": (C_cold, a_cold),
        "高光-整体": (C_hi, a_hi), "高光-强": (C_strong, a_strong),
        "高光-细节": (C_detail_hi, a_detail_hi),
    })
    for nm, (c, a) in out.items():
        save_rgba(c, a, os.path.join(outdir, nm + ".png"))

    # 平滑线稿 + 草稿（哥特双人定稿参数，见 lineart_sparse）
    cm = LC.charmask(alpha_path, H, W)
    P3 = lineart_sparse(np.clip(rgb * 255, 0, 255), cm)
    save_rgba(np.zeros((H, W, 3), np.float32), P3, os.path.join(outdir, "线稿-完整.png"))
    os.makedirs(os.path.join(HERE, "线稿"), exist_ok=True)
    LC.save_white(P3, os.path.join(HERE, "线稿", "%s_线稿_白底.png" % out_key))
    draft = np.zeros_like(P3)
    for dx, dy in ((-2, -1), (2, 1), (1, -2), (-1, 2), (0, 0)):
        draft = np.maximum(draft, np.roll(np.roll(P3, dy, 0), dx, 1))
    save_rgba(np.array([0.55, 0.55, 0.58], np.float32), np.clip(draft * 0.8, 0, 1),
              os.path.join(outdir, "草稿-淡描.png"))

    if verbose:
        palette = {"底色-皮肤": (255, 225, 205), "底色-亮银": (245, 245, 250),
                   "底色-浅灰": (205, 215, 230), "底色-中灰": (150, 165, 190),
                   "底色-深灰": (110, 125, 155), "底色-暗蓝": (80, 100, 160),
                   "底色-深蓝": (55, 75, 140), "底色-墨色": (35, 38, 55),
                   "底色-极暗": (20, 20, 30)}
        vis = np.full((H, W, 3), 245, np.uint8)
        for nm, pc in palette.items():
            if nm in layers:
                vis[layers[nm]["mask"] > 0] = pc
        vis[P == 0] = (205, 205, 215)
        os.makedirs(os.path.join(HERE, "预览"), exist_ok=True)
        Image.fromarray(vis).save(os.path.join(HERE, "预览", "%s_分割预览.png" % out_key))
    return err


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python layers_20.py <原图.png> <alpha.png> <out_key>")
        sys.exit(1)
    img_path, alpha_path, out_key = sys.argv[1], sys.argv[2], sys.argv[3]
    print("== %s ==" % out_key)
    build(img_path, alpha_path, out_key)
