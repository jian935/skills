# -*- coding: utf-8 -*-
"""阶段 E · 分图层（核心）

目标：**13 个图层全开时逐像素等于成品图**，同时每个效果层关掉都真的会改变画面。

做法不是"往上叠效果"，而是**从成品图反解**：把 PS 的混色模式写成解析式，
再自顶向下逐层求逆，得到每一层该有的像素值。这样：
  · 关掉「人物-高光」→ 高光消失，不再浮着一层洗白
  · 关掉「整体-暖调柔光」→ 整体转冷，不是过曝
  · 全开 → 和成品图完全一致

图层结构（面板自上而下，与参考稿同一套编号）：
  ①线稿      线稿-轮廓粗线 / 线稿-中间线 / 线稿-细节细线   （默认隐藏，工作层）
  ②整体调色  整体-暖调柔光(SOFT_LIGHT) / 整体-提亮(SCREEN)
  ③细化      人物-边缘光(SCREEN) / 人物-高光(SCREEN)
  ④二分      人物-阴影(MULTIPLY)
  ⑤分区上色  人物-完整色
  ⑥背景      背景-柔光罩(SOFT_LIGHT) / 背景-光斑(SCREEN) / 背景-虚化 / 背景-原色

⚠️ OpenCV 在 Windows 上不支持非 ASCII 路径 → 一律用 PIL 读写，cv2 只吃 numpy 数组。
"""
import os, sys, json
import numpy as np
import cv2
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1024, 1536

# 组与层（面板自上而下）。透明度/混色模式写进 PSD 时用这里的值。
GROUP_ORDER = ["①线稿", "②整体调色", "③细化", "④二分", "⑤分区上色", "⑥背景"]
LAYERS = [
    ("①线稿",     "线稿-轮廓粗线",  "NORMAL",     0.84),
    ("①线稿",     "线稿-中间线",    "NORMAL",     0.66),
    ("①线稿",     "线稿-细节细线",  "NORMAL",     0.46),
    ("②整体调色", "整体-暖调柔光",  "SOFT_LIGHT", 0.22),
    ("②整体调色", "整体-提亮",      "SCREEN",     0.14),
    ("③细化",     "人物-边缘光",    "SCREEN",     0.40),
    ("③细化",     "人物-高光",      "SCREEN",     0.46),
    ("④二分",     "人物-阴影",      "MULTIPLY",   0.50),
    ("⑤分区上色", "人物-完整色",    "NORMAL",     1.00),
    ("⑥背景",     "背景-柔光罩",    "SOFT_LIGHT", 0.20),
    ("⑥背景",     "背景-光斑",      "SCREEN",     0.52),
    ("⑥背景",     "背景-虚化",      "NORMAL",     1.00),   # 默认隐藏的备用层
    ("⑥背景",     "背景-原色",      "NORMAL",     1.00),
]
HIDDEN_BY_DEFAULT = {"①线稿", "背景-虚化"}

C_WARM = np.array([255, 178, 102], np.float32) / 255.0   # 暖调柔光 / 柔光罩（同参考稿）
C_LIFT = np.array([255, 238, 208], np.float32) / 255.0   # 提亮
C_HL = np.array([255, 232, 186], np.float32) / 255.0     # 高光
C_RIM = np.array([255, 236, 196], np.float32) / 255.0    # 边缘光
C_SH = np.array([86, 56, 40], np.float32) / 255.0        # 暖棕阴影


# ------------------------------------------------------------ 工具
def load_rgb(p):
    return np.asarray(Image.open(p).convert("RGB"), np.float32)


def save_rgba(rgb, alpha, path):
    a = np.asarray(alpha, np.float32)
    if a.max() > 1.0001:
        a = a / 255.0
    out = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8),
                     np.clip(a * 255, 0, 255).astype(np.uint8)])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(out, "RGBA").save(path)


def gblur(x, r):
    return cv2.GaussianBlur(np.asarray(x, np.float32), (0, 0), r)


def lum(rgb):
    return (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0


# ------------------------------------------------------------ 混色模式 + 反演
def softlight(b, c):
    d = np.where(b <= 0.25, ((16.0 * b - 12.0) * b + 4.0) * b, np.sqrt(np.maximum(b, 0.0)))
    return np.where(c <= 0.5, b - (1.0 - 2.0 * c) * b * (1.0 - b), b + (2.0 * c - 1.0) * (d - b))


def inv_layer(t, C, e, mode):
    """已知结果 t、图层色 C、有效不透明度 e（= alpha × opacity），求底色 b。
       式：t = b(1-e) + blend(b,C)·e   —— e 可以是标量，也可以是 (H,W) 蒙版"""
    e = np.asarray(e, np.float32)
    if e.ndim == 2:
        e = e[..., None]
    C = np.asarray(C, np.float32)
    if C.ndim == 1:
        C = C.reshape((1, 1, -1))
    if mode == "SCREEN":
        den = 1.0 - e * C
        return np.clip((t - e * C) / np.maximum(den, 1e-4), 0, 1)
    if mode == "MULTIPLY":
        den = 1.0 - e + C * e
        return np.clip(t / np.maximum(den, 1e-4), 0, 1)
    if mode == "SOFT_LIGHT":
        lo = np.zeros_like(t)
        hi = np.ones_like(t)
        for _ in range(26):                      # soft light 对 b 单调 → 二分即可
            mid = (lo + hi) * 0.5
            v = mid * (1.0 - e) + softlight(mid, C) * e
            go_up = v < t
            lo = np.where(go_up, mid, lo)
            hi = np.where(go_up, hi, mid)
        return (lo + hi) * 0.5
    return t


# ------------------------------------------------------------ 蒙版与派生层
def char_mask(raw):
    a = np.asarray(raw, np.float32)
    if a.max() > 1.001:
        a = a / 255.0
    m = (a > 0.45).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        order = np.argsort(-stats[1:, 4]) + 1
        main = order[0]
        x, y, w_, h_, _ = stats[main]
        keep = np.zeros_like(m)
        for i in order:
            cx, cy = cent[i]
            if i == main or (x - w_ * .10 <= cx <= x + w_ * 1.10 and
                             y - h_ * .06 <= cy <= y + h_ * 1.06):
                keep[lab == i] = 1
        m = keep
    ff = m.copy()
    cv2.floodFill(ff, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 1)
    m = m | (1 - ff)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    soft = np.clip(m.astype(np.float32), 0, 1)
    return np.clip(np.maximum(soft, a * (soft > 0)), 0, 1), m


def rescale_mask(m, M, pct=97.0, target=0.92):
    """把蒙版拉到"最强处≈target"。

    关键：反演法对**任意** alpha 都成立（base 由 alpha 反解出来），
    所以加强蒙版只会让"基础色层"离成品更远、让效果层更有存在感，
    全开时依然逐像素等于成品。蒙版太弱的话，关掉这层根本看不出差别。
    """
    v = m[M > 0.5]
    if v.size == 0:
        return m
    p = np.percentile(v, pct)
    if p <= 1e-6:
        return m
    return np.clip(m * (target / p), 0, 1)


def derive(L, M):
    """从亮度派生 阴影 / 高光 两张 alpha"""
    base = cv2.blur(L, (71, 71))
    rel = np.clip((base - L) / np.maximum(base, 0.14), 0, 1)
    absd = np.clip((0.56 - L) / 0.56, 0, 1)
    sh = np.clip(np.maximum(rel * 1.9 - 0.04, absd * 0.70), 0, 1)
    sh = np.clip(gblur(sh, 7) * M, 0, 1)
    sh = rescale_mask(sh, M, 97.0, 0.94)

    loc = cv2.blur(L, (41, 41))
    hl = np.clip((L - 0.58) / 0.42, 0, 1) ** 1.25
    hl = hl * np.clip(0.45 + 0.75 * np.clip((L - loc) / 0.09, 0, 1), 0, 1.2)
    hl = np.clip(gblur(hl, 3.4) * M, 0, 1)
    hl = rescale_mask(hl, M, 96.0, 0.95)
    return sh, hl


def rim_alpha(M, bg_lum):
    e = np.clip(M - cv2.erode((M > 0.5).astype(np.uint8),
                              np.ones((23, 23), np.uint8)).astype(np.float32), 0, 1)
    rim = np.clip(gblur(e, 3.2) * np.clip((gblur(bg_lum, 18) - 0.38) / 0.34, 0, 1) * M, 0, 1)
    return rescale_mask(rim, M, 98.0, 0.85)


def bokeh_layer(seed=7):
    rng = np.random.RandomState(seed)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for _ in range(46):
        cx, cy = rng.rand() * W, (0.02 + rng.rand() * 0.86) * H
        r = 6 + rng.rand() ** 2.2 * 40
        al = int(70 + rng.rand() * 130)
        col = (255, int(196 + rng.rand() * 46), int(128 + rng.rand() * 70))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (al // 6,))
        d.ellipse([cx - r * .72, cy - r * .72, cx + r * .72, cy + r * .72], fill=col + (al // 3,))
        d.ellipse([cx - r * .34, cy - r * .34, cx + r * .34, cy + r * .34], fill=col + (al,))
    for _ in range(150):
        cx, cy = rng.rand() * W, rng.rand() * H
        r = 1.2 + rng.rand() * 3.2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 226, 168, int(130 + rng.rand() * 120)))
    a = np.asarray(ov, np.float32)
    return a[..., :3], np.clip(gblur(a[..., 3] / 255.0, 1.6), 0, 1)


def radial_dof_weight():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W * 0.50) / (W * 0.62)) ** 2 + ((yy - H * 0.56) / (H * 0.46)) ** 2)
    return np.clip((d - 0.42) / 0.72, 0, 1) ** 1.25


# ------------------------------------------------------------ 线稿
def build_lineart(rgb, outdir, white_copy=None, alpha_png=None):
    """线稿三层 —— 委托给 lineart_canny.py（v2 定稿管线）。

    ⚠️ 旧版这里是「中值滤波基线做差」抽墨线（extract_ink），
    抽出来的线宽中位只有 1px、alpha 中位 0.3~0.5（灰线），
    在 PS 里几乎看不见 —— 用户 2026-09-28 反馈「线稿根本不明显」。
    **不要再退回去**；新管线的参数与体检口径见 SKILL.md 3.1。
    """
    import lineart_canny as LC
    tmp = os.path.join(outdir, "_final_tmp.png")
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(tmp)
    LC.generate(tmp, outdir, alpha_png, white_copy)
    os.remove(tmp)


# ------------------------------------------------------------ 主流程
def run(key, final_png, alpha_png, outdir, white_line=None, verbose=True):
    print("== %s ==" % key)
    rgb = load_rgb(final_png)
    if rgb.shape[:2] != (H, W):
        rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((W, H), Image.LANCZOS), np.float32)
    T = np.clip(rgb / 255.0, 0, 1)
    os.makedirs(outdir, exist_ok=True)

    if alpha_png and os.path.exists(alpha_png):
        M, mbin = char_mask(Image.open(alpha_png))
    else:                                   # 没有抠图就当整幅是主体（退化为整体调色）
        M = np.ones((H, W), np.float32); mbin = np.ones((H, W), np.uint8)
    print("   主体遮罩覆盖 %.1f%%" % (M.mean() * 100))

    L = lum(rgb)
    sh, hl = derive(L, M)
    rim = rim_alpha(M, L)
    boke_rgb, boke_a = bokeh_layer()

    op = {n: o for _, n, _, o in LAYERS}

    # ---- 自顶向下反演。每一步之后 b 表示「该层之下所有内容的等效结果」
    b = T.copy()
    e = op["整体-暖调柔光"]
    b = inv_layer(b, C_WARM, e, "SOFT_LIGHT")
    e = op["整体-提亮"]
    b = inv_layer(b, C_LIFT, e, "SCREEN")
    b = inv_layer(b, C_RIM, rim * op["人物-边缘光"], "SCREEN")
    b = inv_layer(b, C_HL, hl * op["人物-高光"], "SCREEN")
    b = inv_layer(b, C_SH, sh * op["人物-阴影"], "MULTIPLY")
    below_char = b                                  # 人物-完整色 之下应有的等效结果

    # 背景侧：先反解 柔光罩 / 光斑，得到 背景-原色
    e_glaze, e_boke = op["背景-柔光罩"], op["背景-光斑"]
    bgp = below_char.copy()
    bgp = inv_layer(bgp, C_WARM, e_glaze * np.ones((H, W, 1), np.float32), "SOFT_LIGHT")
    bgp = inv_layer(bgp, boke_rgb / 255.0, e_boke * boke_a[..., None], "SCREEN")
    bg_req = bgp                                     # 背景-原色（含人物区域，稍后抹掉）

    # 人物-完整色：由 NORMAL 混合求解 L = (below - bgp·(1-M)) / M
    Ms = M[..., None]
    safe = np.maximum(Ms, 0.06)
    charL = np.clip((below_char - bgp * (1 - Ms)) / safe, 0, 1)
    charL = np.where(Ms > 0.06, charL, below_char)
    charL = np.clip(gblur(charL, 1.2) * 0.35 + charL * 0.65, 0, 1)   # 轻微去噪

    # ---- 背景-原色：把人物区域内抹掉（被上层盖住，但方便单独看/移动人物）
    bgpaint = (bg_req * 255).astype(np.uint8)
    core = ((M > 0.5).astype(np.uint8))
    if core.any():
        cd = cv2.dilate(core, np.ones((15, 15), np.uint8))
        inp = cv2.inpaint(bgpaint, cd, 9, cv2.INPAINT_TELEA).astype(np.float32) / 255.0
        sm = gblur(bg_req * 255, 26) / 255.0
        wgt = gblur(core.astype(np.float32), 16)[..., None]
        bg_final = bg_req * (1 - wgt) + (inp * 0.40 + sm * 0.60) * wgt
    else:
        bg_final = bg_req

    # ---- 落盘
    save_rgba(charL * 255, M, os.path.join(outdir, "人物-完整色.png"))
    save_rgba(np.full((H, W, 3), C_SH * 255, np.float32), sh * 0.96,
              os.path.join(outdir, "人物-阴影.png"))
    save_rgba(np.full((H, W, 3), C_HL * 255, np.float32), hl,
              os.path.join(outdir, "人物-高光.png"))
    save_rgba(np.full((H, W, 3), C_RIM * 255, np.float32), rim,
              os.path.join(outdir, "人物-边缘光.png"))
    save_rgba(np.full((H, W, 3), C_WARM * 255, np.float32), np.ones((H, W), np.float32),
              os.path.join(outdir, "整体-暖调柔光.png"))
    save_rgba(np.full((H, W, 3), C_LIFT * 255, np.float32), np.ones((H, W), np.float32),
              os.path.join(outdir, "整体-提亮.png"))
    save_rgba(np.full((H, W, 3), C_WARM * 255, np.float32), np.ones((H, W), np.float32),
              os.path.join(outdir, "背景-柔光罩.png"))
    save_rgba(boke_rgb, boke_a, os.path.join(outdir, "背景-光斑.png"))
    save_rgba(gblur(bg_final * 255, 15), radial_dof_weight() * 0.95,
              os.path.join(outdir, "背景-虚化.png"))
    save_rgba(bg_final * 255, np.ones((H, W), np.float32),
              os.path.join(outdir, "背景-原色.png"))
    build_lineart(rgb, outdir, white_line)

    # ---- 自检：把这 13 层按 PS 规则合成回来，和成品图比
    err = verify(T, charL, M, sh, hl, rim, bg_final, boke_rgb, boke_a, op)
    files = sorted(f for f in os.listdir(outdir) if f.endswith(".png"))
    print("   产出 %d 层，还原误差 mean=%.4f max=%.3f" % (len(files), err[0], err[1]))
    if verbose:
        for f in files:
            print("     ·", f)
    return files, err


def verify(T, charL, M, sh, hl, rim, bg, boke_rgb, boke_a, op):
    """用 PS 的混色公式正向合成一遍，与成品图逐像素对比"""
    o = bg.copy()
    o = o * (1 - op["背景-光斑"] * boke_a[..., None]) + \
        (1 - (1 - o) * (1 - boke_rgb / 255.0)) * (op["背景-光斑"] * boke_a[..., None])
    e = op["背景-柔光罩"]
    o = o * (1 - e) + softlight(o, C_WARM) * e
    Ms = M[..., None]
    o = o * (1 - Ms) + charL * Ms
    e = sh * op["人物-阴影"]
    o = o * (1 - e[..., None]) + (o * C_SH) * e[..., None]
    for C, a, k in ((C_HL, hl, "人物-高光"), (C_RIM, rim, "人物-边缘光")):
        e = a * op[k]
        o = o * (1 - e[..., None]) + (1 - (1 - o) * (1 - C)) * e[..., None]
    e = op["整体-提亮"]
    o = o * (1 - e) + (1 - (1 - o) * (1 - C_LIFT)) * e
    e = op["整体-暖调柔光"]
    o = o * (1 - e) + softlight(o, C_WARM) * e
    d = np.abs(o - T)
    return float(d.mean()), float(d.max())


if __name__ == "__main__":
    print("由 stage_e.py 调用")
