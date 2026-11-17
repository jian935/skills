# -*- coding: utf-8 -*-
"""30 批线稿：LineartAnime @2048 + 眼部 Canny 补虹膜 + 草稿层
这类珠光排线风虹膜是亮色大圆，informative-drawings 会把瞳孔丢掉
→ 在自动定位的眼框内用 Canny 从彩稿补回虹膜/瞳孔/睫线。

用法: python gen_lineart30.py <彩稿.png> <key>   （在 ComfyUI 的嵌入式 Python 环境里执行）
产出: 线稿/<key>_线稿_白底.png  图层/<key>/{线稿-完整,草稿-淡描}.png
"""
import os, sys
import numpy as np
import cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def detect_eyes(rgb, P):
    """在人物区脸带找左右虹膜：暗(V<0.55)且饱和(sat>0.18)的紧凑簇，
    水平严格对齐。虹膜深色高饱和；花瓣/唇/浅发亮色被 V 阈排除。"""
    H, W = rgb.shape[:2]
    L = rgb[..., 0] * .299 + rgb[..., 1] * .587 + rgb[..., 2] * .114
    mx = rgb.max(-1); mn = rgb.min(-1); sat = mx - mn
    ys, xs = np.where(P > 0)
    if len(ys) < 500:
        return []
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    zone = np.zeros((H, W), bool)
    zone[int(y0 + 0.22 * (y1 - y0)):int(y0 + 0.52 * (y1 - y0)),
         int(x0 + 0.28 * (x1 - x0)):int(x0 + 0.72 * (x1 - x0))] = True
    cand = ((P > 0) & zone & (L < 0.55) & (sat > 0.18)).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, lab, st, cent = cv2.connectedComponentsWithStats(cand, 8)
    items = []
    for i in range(1, n):
        area = st[i, 4]
        if area < 150 or area > 6000:
            continue
        w_, h_ = st[i, 2], st[i, 3]
        if h_ == 0:
            continue
        ar = w_ / h_
        if ar > 2.6 or ar < 0.35:
            continue
        if max(w_, h_) > 0.055 * H:
            continue
        items.append((st[i, 0], st[i, 1], w_, h_, cent[i], area))
    best = None
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            ax, ay = a[4]; bx, by = b[4]
            if abs(ay - by) > 0.022 * H:
                continue
            d = abs(ax - bx)
            if not (0.06 * W < d < 0.26 * W):
                continue
            score = abs(ay - by) * 3 + abs(d - 0.13 * W) * 0.5
            if best is None or score < best[0]:
                best = (score, a, b)
    if best is None:
        return []
    _, a, b = best
    boxes = []
    for c in (a, b):
        cx, cy = int(c[4][0]), int(c[4][1])
        r = int(max(c[2], c[3]) * 0.75 + 30)
        boxes.append((max(0, cx - r), max(0, cy - int(r * 0.75)),
                      min(W, cx + r), min(H, cy + int(r * 0.85))))
    return boxes


def main(img_path, key):
    from controlnet_aux import LineartAnimeDetector
    det = LineartAnimeDetector.from_pretrained("lllyasviel/Annotators")
    img = Image.open(img_path).convert("RGB")
    W, H = img.size
    # 竖版图直接高分辨率检测会爆内存 → 方形填充后检测再裁回
    S = max(W, H)
    sq = Image.new("RGB", (S, S), (255, 255, 255))
    sq.paste(img, ((S - W) // 2, 0))
    la = det(sq, detect_resolution=2048, image_resolution=2048)
    g = 255.0 - np.asarray(la.convert("L"), np.float32)   # 黑底白线 → 反相
    if g.shape[:2] != (S, S):
        g = cv2.resize(g, (S, S), interpolation=cv2.INTER_AREA)
    g = g[(S - H) // 2:(S - H) // 2 + H, (S - W) // 2:(S - W) // 2 + W].copy()
    # 2048 原生输出已干净：轻平滑 + 温和反锐化，不再 erode/重阈值
    g = cv2.GaussianBlur(g, (0, 0), 0.8)
    blur = cv2.GaussianBlur(g, (0, 0), 1.6)
    g = np.clip(g - 0.6 * (g - blur), 0, 255)
    lo, hi = np.percentile(g, 1), np.percentile(g, 99.5)
    ink = np.clip((hi - g) / max(hi - lo, 1e-6), 0, 1)
    core = (ink > 0.32).astype(np.uint8)
    core = cv2.morphologyEx(core, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    b = cv2.resize(core.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA)
    ink = np.clip(cv2.GaussianBlur(b, (0, 0), 0.7) * 1.25, 0, 1)   # 用户要求线稿不能太厚
    core = (b > 0.5).astype(np.uint8)

    # ---- 脸部中央带 Canny 补虹膜/五官细节（informative-drawings 会丢亮色虹膜）----
    # 带 = 人物 bbox y 24%~46%、x 30%~70%；Canny 结果用暗色掩膜门控（排除淡色皮肤噪声），
    # 与 LA 线取 max —— 重叠线无害，虹膜/睫毛/唇线被补回。
    rgb = np.asarray(img, np.float32) / 255.0
    L = rgb[..., 0] * .299 + rgb[..., 1] * .587 + rgb[..., 2] * .114
    alpha = np.zeros((H, W), np.float32)
    ap = os.path.join(HERE, "图层", key, "_alpha.png")
    if os.path.exists(ap):
        alpha = np.asarray(Image.open(ap).convert("RGBA"), np.float32)[..., 3] / 255.0
    P = (alpha > 0.5).astype(np.uint8)
    band = np.zeros((H, W), bool)
    ys, xs = np.where(P > 0)
    fullbody = len(sys.argv) > 3 and sys.argv[3] == "fullbody"
    manual_boxes = None
    iris_boxes = None
    if len(sys.argv) > 3 and sys.argv[3].startswith("boxes="):
        manual_boxes = [tuple(int(v) for v in s.split(","))
                        for s in sys.argv[3][6:].split(";")]
    elif len(sys.argv) > 3 and sys.argv[3].startswith("iris="):
        iris_boxes = [tuple(int(v) for v in s.split(","))
                      for s in sys.argv[3][5:].split(";")]
    if manual_boxes:
        dark = (L < 0.72).astype(np.uint8)
        dark = cv2.dilate(dark, np.ones((5, 5), np.uint8))
    else:
        dark = (L < 0.78).astype(np.uint8) if fullbody else (L < 0.62).astype(np.uint8)
        dark = cv2.dilate(dark, np.ones((5, 5) if fullbody else (9, 9), np.uint8))
    gray = cv2.cvtColor(np.clip(rgb * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    if iris_boxes:
        # 手动虹膜：显式 cx,cy,rx,ry（从原稿实测坐标），画环 + 瞳孔
        for (cx, cy, rx, ry) in iris_boxes:
            n_seg = 28
            rr = 1.0 + 0.022 * np.sin(np.linspace(0, 2 * np.pi * 2, n_seg) + cx * 0.1)
            pts = []
            for i in range(n_seg):
                t = 2 * np.pi * i / n_seg
                pts.append((cx + rx * rr[i] * np.cos(t),
                            cy + ry * rr[i] * np.sin(t)))
            pts = np.array(pts, np.int32)
            cv2.polylines(ink, [pts], True, 0.9, 3)
            cv2.ellipse(ink, (int(cx), int(cy)), (max(2, int(rx * 0.30)), max(2, int(ry * 0.34))),
                        0, 0, 360, 0.95, -1)          # 瞳孔
            # 上缘高光留白（右上一个小弧的缺口感）：擦一小段
            hx, hy = int(cx + rx * 0.45), int(cy - ry * 0.55)
            cv2.ellipse(ink, (hx, hy), (max(2, int(rx * 0.22)), max(2, int(ry * 0.16))),
                        0, 0, 360, -0.6, -1)
            cv2.polylines(core, [pts], True, 1, 3)
    else:
        lo_c, hi_c = (45, 120) if (fullbody or manual_boxes) else (50, 130)
        e = cv2.Canny(gray, lo_c, hi_c).astype(np.float32) / 255.0
        if manual_boxes:
            gate = np.zeros((H, W), bool)
            for (bx0, by0, bx1, by1) in manual_boxes:
                gate[by0:by1, bx0:bx1] = True
            e = e * (gate & (dark > 0))
        else:
            e = e * (band & (dark > 0))
        e = cv2.GaussianBlur(e, (0, 0), 0.5)
        ink = np.maximum(ink, e)
        core = np.maximum(core, (e > 0.5).astype(np.uint8))

    os.makedirs(os.path.join(HERE, "线稿"), exist_ok=True)
    white = np.clip((1 - ink) * 255, 0, 255).astype(np.uint8)
    Image.fromarray(white, "L").convert("RGB").save(
        os.path.join(HERE, "线稿", "%s_线稿_白底.png" % key))
    outdir = os.path.join(HERE, "图层", key)
    os.makedirs(outdir, exist_ok=True)
    rgba = np.dstack([np.zeros((H, W, 3), np.uint8),
                      np.clip(ink * 255, 0, 255).astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(os.path.join(outdir, "线稿-完整.png"))
    draft = np.zeros_like(ink)
    for dx, dy in ((-2, -1), (2, 1), (1, -2), (-1, 2), (0, 0)):
        draft = np.maximum(draft, np.roll(np.roll(ink, dy, 0), dx, 1))
    dcol = np.zeros((H, W, 3), np.uint8); dcol[:] = (140, 140, 148)
    drgba = np.dstack([dcol, np.clip(draft * 0.8 * 255, 0, 255).astype(np.uint8)])
    Image.fromarray(drgba, "RGBA").save(os.path.join(outdir, "草稿-淡描.png"))
    print("  [%s] 线稿：墨量 %.2f%%" % (key, float((core > 0).mean()) * 100))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
