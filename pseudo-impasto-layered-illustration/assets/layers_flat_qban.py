# -*- coding: utf-8 -*-
"""Q版平涂流量稿 · 分层核心 v2（13 层）

分层策略（赛璐璐本色）：
  · 上色层 = 平涂色块：mean-shift 平色 → 颜色 kmeans(k=6) → 连通块 →
    按 Q 版构图规律命名为 头发/皮肤/服饰/配饰×2（每层=该色的所有色块）
  · 阴影/高光 = 对「无效果图 t」做**逐像素**闭式反演（不再依赖区域分割的精度）：
      MULTIPLY: C = (t - b(1-e)) / (b·e)      SCREEN: C = (t - b) / (e(1-b))
    b 逐像素取自 t —— 分割只影响"层归属"，不影响还原精度。
  · 整体-暖调 = SOFT_LIGHT 0.15，二分反演。
  数学保证 全开合成 ≈ 成品；关掉效果层 = 干净平涂色块稿。

13 层（面板自上而下，★=默认隐藏）：
  ①线稿   线稿-完整                    ★ 统一线宽 2px
  ②草稿   草稿-淡描                    ★ 线稿浅灰+抖动
  ③细化   高光-强(SCREEN .95) 高光-整体(SCREEN .75) 整体-暖调(SOFT_LIGHT .15)
  ④阴影   阴影-重(MULTIPLY .75) 阴影-轻(MULTIPLY .40)
  ⑤上色   底色-头发/皮肤/服饰/配饰A/配饰B   NORMAL 1.00
  ⑥背景   背景-纯色
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
import cv2
from PIL import Image

import lineart_canny as LC

HERE = os.path.dirname(os.path.abspath(__file__))
W = H = 1024


# ---------------------------------------------------------------- 基础
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


# ---------------------------------------------------------------- 反演
def inv_multiply(t, b, e):
    eS = np.maximum(e, 1e-4)[..., None]
    return np.clip((t - b * (1 - eS)) / np.maximum(b * eS, 1e-4), 0, 1)


def inv_screen(t, b, e):
    eS = np.maximum(e, 1e-4)[..., None]
    return np.clip((t - b) / np.maximum(eS * (1 - b), 1e-4), 0, 1)


def inv_softlight(t, b, e):
    """SOFT_LIGHT 反演：对每个像素二分求 C（18 工程同款，26 次足够）"""
    lo = np.zeros_like(b)
    hi = np.ones_like(b)
    eS = e[..., None]

    def sl(bv, cv):
        out = np.where(
            cv <= 0.5,
            bv - (1 - 2 * cv) * bv * (1 - bv),
            bv + (2 * cv - 1) * ((np.where(bv <= 0.25, ((16 * bv - 12) * bv + 4) * bv, np.sqrt(bv)) ) - bv),
        )
        return out

    for _ in range(26):
        mid = (lo + hi) / 2
        approx = bv = None
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


# ---------------------------------------------------------------- 上色块
def color_blocks(rgb, char, K=8):
    """mean-shift 平色 → 颜色 kmeans → 连通块 → 5 个上色层（语义命名）。
    ⚠️ rgb 约定 0..1；内部自己 *255。"""
    u8 = np.clip(rgb * 255, 0, 255).astype(np.uint8)
    flat = cv2.pyrMeanShiftFiltering(u8, 9, 26, maxLevel=3).astype(np.float32)
    V = lum(flat / 255.)

    P = largest_components((char > 0.5).astype(np.uint8), min_area=W * H * 0.02)
    P = cv2.morphologyEx(P, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    pts = np.where(P > 0)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.5)
    _, labv, centers = cv2.kmeans(flat[pts].astype(np.float32), K, None, crit, 6, cv2.KMEANS_PP_CENTERS)
    lab = np.zeros((H, W), np.uint8)
    lab[pts] = (labv.ravel() + 1).astype(np.uint8)
    # 空间平滑：消掉簇间交错的小斑点，让每片色块成整片
    lab = cv2.medianBlur(lab, 31)
    lab = cv2.medianBlur(lab, 31)

    # 深色锚：先开运算去掉细线稿，留下眼睛这类深色团块；单团不得超过 2.5% 画布（防五官连线成片）
    dark = (P > 0) & (V < 0.34)
    dark_blobs = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    eye_seed = largest_components(dark_blobs, min_area=150)
    n_b, lab_b, st_b, _ = cv2.connectedComponentsWithStats(eye_seed, 8)
    for i in range(1, n_b):
        if st_b[i, 4] > W * H * 0.025:
            eye_seed[lab_b == i] = 0
    ys_e, xs_e = np.where(eye_seed > 0)
    have_eye = len(ys_e) > 300
    y_eye = float(np.median(ys_e)) if have_eye else H * 0.4
    y_eye_bot = float(np.percentile(ys_e, 88)) if have_eye else H * 0.62
    ring = np.zeros((H, W), bool)
    if have_eye:
        cv2.circle(ring, (int(xs_e.mean()), int(y_eye)), int(H * 0.13), True, -1)

    info = []
    for c in range(1, K + 1):
        blk = lab == c
        m = int(blk.sum())
        if m < 400:
            continue
        cy = float(np.where(blk)[0].mean())
        col = centers[c - 1] / 255.
        ringr = float((blk & ring).sum() / m)
        upr = float((np.where(blk)[0] < y_eye).mean())
        dn = float((np.where(blk)[0] > y_eye_bot).mean())
        vm = float(V[blk].mean())
        info.append(dict(c=c, m=m, cy=cy, col=col, ringr=ringr, up=upr, dn=dn, v=vm, mask=blk))
    info.sort(key=lambda d: -d["m"])

    # 命名：环带交叠高的暖亮色=皮肤；上部为主=头发；下部为主=服饰；其余=配饰
    used = set()
    layers = {}

    def take(pred, name):
        for d in info:
            if d["c"] in used:
                continue
            if pred(d):
                used.add(d["c"])
                layers[name] = d
                return True
        return False

    take(lambda d: d["ringr"] > 0.25 and d["v"] > 0.5 and d["col"][0] > d["col"][2], "底色-皮肤")
    take(lambda d: d["up"] > 0.55 and d["cy"] < y_eye, "底色-头发")
    take(lambda d: d["dn"] > 0.45, "底色-服饰")
    take(lambda d: True, "底色-配饰A")
    take(lambda d: True, "底色-配饰B")
    # 缺层补齐（保证五层都在，重投影才有完整判别力）
    if "底色-皮肤" not in layers and have_eye:
        m = (ring & (P > 0)).astype(np.uint8)
        if m.sum() > 800:
            layers["底色-皮肤"] = dict(col=np.median(rgb[m > 0].reshape(-1, 3), axis=0) / 255.,
                                       mask=m, c=-1)
    if "底色-头发" not in layers:
        m = ((P > 0) & (np.mgrid[0:H, 0:W][0] < y_eye)).astype(np.uint8)
        layers["底色-头发"] = dict(col=np.median(rgb[m > 0].reshape(-1, 3), axis=0) / 255.,
                                   mask=m, c=-1)
    if "底色-服饰" not in layers:
        cands = [(np.where(L["mask"] > 0)[0].mean(), nm)
                 for nm, L in layers.items() if nm.startswith("底色-配饰")]
        if cands:
            _, src = max(cands)
            layers["底色-服饰"] = layers.pop(src)
    # 没进前 5 的簇：按颜色就近并入已选层
    for d in info:
        if d["c"] in used or d["c"] < 0:
            continue
        best, bd = None, 1e9
        for nm, L in layers.items():
            if "cy" not in L:
                continue
            dd = float(np.linalg.norm(d["col"] - L["col"]) + abs(d["cy"] - L["cy"]) / H * 40)
            if dd < bd:
                best, bd = nm, dd
        if best is not None:
            layers[best]["mask"] = layers[best]["mask"] | d["mask"]
            used.add(d["c"])
    # 补漏：没被任何簇覆盖的人物像素 → 最近层
    covered = np.zeros((H, W), bool)
    for nm, L in layers.items():
        covered |= L["mask"] > 0
    miss = (P > 0) & (~covered)
    if miss.any():
        for nm, L in layers.items():
            L["mask"] = (L["mask"] | (miss & (lum(flat / 255.) > 0.5) if False else L["mask"])).astype(np.uint8)
        # 简单按 y 归入
        rr, cc = np.where(miss)
        for y, x in zip(rr, cc):
            nm = "底色-头发" if y < y_eye else ("底色-服饰" if y > y_eye_bot else "底色-皮肤")
            if nm in layers:
                layers[nm]["mask"][y, x] = 1
    if len(ys_e):
        # 眼睛深色若没被任何层收编，归配饰A
        if not any((layers[nm]["mask"] & eye_seed).any() for nm in layers):
            if "底色-配饰A" in layers:
                layers["底色-配饰A"]["mask"] |= eye_seed
    for nm in layers:
        m = cv2.morphologyEx(layers[nm]["mask"], cv2.MORPH_CLOSE,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
        layers[nm]["mask"] = largest_components(m, min_area=0)

    # 互斥投影：优先级 头发 > 皮肤 > 服饰 > 配饰A > 配饰B（先占的像素不让）
    prio = ["底色-头发", "底色-皮肤", "底色-服饰", "底色-配饰A", "底色-配饰B"]
    taken = np.zeros((H, W), bool)
    for nm in prio:
        if nm in layers:
            layers[nm]["mask"] = (layers[nm]["mask"] > 0) & (~taken)
            layers[nm]["mask"] = largest_components(layers[nm]["mask"].astype(np.uint8), min_area=0)
            taken |= layers[nm]["mask"] > 0
    # 最近色重投影：人物区每个像素归「颜色最近 + 空间加成」的层 —— 消灭斑驳，整片连贯
    act = [nm for nm in prio if nm in layers and (layers[nm]["mask"] > 0).any()]
    if len(act) >= 2:
        stack_d = []
        for nm in act:
            col = layers[nm]["col"]
            d = ((rgb - col.reshape(1, 1, 3)) ** 2).sum(-1)
            d -= gblur((layers[nm]["mask"] > 0).astype(np.float32), 81) * 5000.0   # 空间加成
            if nm == "底色-皮肤" and have_eye:
                d[ring] -= 3200.0                       # 眼周环带强归皮肤
            if nm == "底色-配饰A" and have_eye:
                d[eye_seed > 0] -= 3200.0               # 深色眼团归配饰A
                gz = cv2.dilate((eye_seed > 0).astype(np.uint8),
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (51, 51))) > 0
                d[gz] -= 12000.0                        # 虹膜/眼周整体归配饰A（五官层）
            stack_d.append(d)
        D = np.stack(stack_d)                           # (L, H, W)
        idx = D.argmin(0)
        for i, nm in enumerate(act):
            layers[nm]["mask"] = ((idx == i) & (P > 0)).astype(np.uint8)
        lab2 = np.zeros((H, W), np.uint8)
        for i, nm in enumerate(act):
            lab2[layers[nm]["mask"] > 0] = i + 1
        lab2 = cv2.medianBlur(lab2, 15)
        lab2[(P == 0)] = 0
        for i, nm in enumerate(act):
            layers[nm]["mask"] = ((lab2 == i + 1)).astype(np.uint8)
    # 重投影后重算每层固有色（层内中位色）—— 保证"关掉效果层"观感正确
    for nm, L in layers.items():
        if (L["mask"] > 0).sum() > 100:
            L["col"] = np.median(rgb[L["mask"] > 0].reshape(-1, 3), axis=0)
    return layers, V, P, flat, (y_eye, y_eye_bot, have_eye)


# ---------------------------------------------------------------- 主流程
def build(key, pick, alpha_png, verbose=True):
    rgb = load_rgb(pick) / 255.
    char = np.asarray(Image.open(alpha_png).convert("RGBA"), np.float32)[..., 3] / 255.0
    layers, V, P, flat, (y_eye, y_eye_bot, have_eye) = color_blocks(rgb, char)
    outdir = os.path.join(HERE, "图层", key)
    os.makedirs(outdir, exist_ok=True)

    # 背景主色
    bg_color = np.median(rgb[(P == 0)].reshape(-1, 3), axis=0)

    # 无效果图 t（背景 + 5 个色块层，逐像素 b）
    t = solid(bg_color)
    for nm in ("底色-配饰B", "底色-配饰A", "底色-服饰", "底色-皮肤", "底色-头发"):
        if nm in layers:
            a = soften(layers[nm]["mask"].astype(np.float32), 0.8)
            t = t * (1 - a[..., None]) + solid(layers[nm]["col"]) * a[..., None]

    Lrgb, Lt = lum(rgb), lum(t)
    diffL = Lrgb - Lt

    # 阴影两档（逐像素反演）
    m_heavy = largest_components(((diffL < -0.10) & (P > 0)).astype(np.uint8), min_area=24)
    a_heavy = soften(m_heavy, 1.1) * 0.75
    C_heavy = inv_multiply(rgb, t, a_heavy)
    m_light = largest_components(((diffL < -0.018) & ~(m_heavy > 0) & (P > 0)).astype(np.uint8), min_area=24)
    a_light = soften(m_light, 1.1) * 0.40
    C_light = inv_multiply(rgb, t, a_light)
    # 高光两档
    m_strong = largest_components(((diffL > 0.12) & (P > 0)).astype(np.uint8), min_area=16)
    a_strong = soften(m_strong, 1.0) * 0.95
    C_strong = inv_screen(rgb, t, a_strong)
    m_hi = largest_components(((diffL > 0.015) & ~(m_strong > 0) & (P > 0)).astype(np.uint8), min_area=24)
    a_hi = soften(m_hi, 1.1) * 0.75
    C_hi = inv_screen(rgb, t, a_hi)
    # 整体-暖调（SOFT_LIGHT 0.15，二分反演）
    a_warm = np.full((H, W), 0.15, np.float32)
    C_warm = inv_softlight(rgb, t, a_warm)

    # ---- 正向验证
    sbu = []
    order = ["底色-配饰B", "底色-配饰A", "底色-服饰", "底色-皮肤", "底色-头发"]
    for nm in order:
        if nm in layers:
            sbu.append(("NORMAL", solid(layers[nm]["col"]), soften(layers[nm]["mask"].astype(np.float32), 0.8)))
    sbu.append(("MULTIPLY", C_light, a_light))
    sbu.append(("MULTIPLY", C_heavy, a_heavy))
    sbu.append(("SOFT_LIGHT", C_warm, a_warm))
    sbu.append(("SCREEN", C_hi, a_hi))
    sbu.append(("SCREEN", C_strong, a_strong))
    recon = compose(solid(bg_color), sbu)
    err = float(np.abs(recon - rgb).mean())
    if verbose:
        print("  [%s] 还原误差 mean %.2f%%  p99 %.3f" % (key, err * 100, float(np.percentile(np.abs(recon - rgb), 99))))

    # ---- 落盘
    out = {"背景-纯色": (solid(bg_color), np.ones((H, W), np.float32))}
    for nm in ("底色-头发", "底色-皮肤", "底色-服饰", "底色-配饰A", "底色-配饰B"):
        if nm in layers:
            out[nm] = (solid(layers[nm]["col"]), soften(layers[nm]["mask"].astype(np.float32), 0.8))
    out.update({
        "阴影-轻": (C_light, a_light), "阴影-重": (C_heavy, a_heavy),
        "整体-暖调": (C_warm, a_warm),
        "高光-整体": (C_hi, a_hi), "高光-强": (C_strong, a_strong),
    })
    for nm, (c, a) in out.items():
        save_rgba(c, a, os.path.join(outdir, nm + ".png"))

    # 线稿 + 草稿
    cm = LC.charmask(alpha_png, H, W)
    sk, mag = LC.build_skel(np.clip(rgb * 255, 0, 255), cm)
    _, _, P3 = LC.split3(sk, mag)
    line = LC.aa(P3, 1.0)
    save_rgba(np.zeros((H, W, 3), np.float32), line, os.path.join(outdir, "线稿-完整.png"))
    LC.save_white(line, os.path.join(HERE, "线稿", "%s_线稿_白底.png" % key))
    draft = np.zeros_like(line)
    for dx, dy in ((-2, -1), (2, 1), (1, -2), (-1, 2), (0, 0)):
        draft = np.maximum(draft, np.roll(np.roll(line, dy, 0), dx, 1))
    save_rgba(np.array([0.55, 0.55, 0.58], np.float32), np.clip(draft * 0.8, 0, 1),
              os.path.join(outdir, "草稿-淡描.png"))

    # 分割预览
    if verbose:
        palette = [(230, 160, 90), (255, 225, 205), (120, 200, 120), (255, 100, 100), (100, 170, 220)]
        vis = np.full((H, W, 3), 245, np.uint8)
        for i, nm in enumerate(("底色-头发", "底色-皮肤", "底色-服饰", "底色-配饰A", "底色-配饰B")):
            if nm in layers:
                vis[layers[nm]["mask"] > 0] = palette[i]
        vis[P == 0] = (205, 205, 215)
        Image.fromarray(vis).save(os.path.join(HERE, "预览", "%s_分割预览.png" % key))
    return err


if __name__ == "__main__":
    themes = json.load(open(os.path.join(HERE, "themes.json"), encoding="utf-8"))
    keys = sys.argv[1:] or [t["key"] for t in themes]
    for t in themes:
        if t["key"] not in keys:
            continue
        print("== %s ==" % t["key"])
        build(t["key"], t["pick"], os.path.join(HERE, "图层", t["key"], "_alpha.png"))
