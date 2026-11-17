# -*- coding: utf-8 -*-
"""平滑线稿渲染 v1 —— 骨架 → 矢量路径 → 样条平滑 → 超采样抗锯齿

背景（2026-09-29 用户反馈）：旧 render3 输出是「骨架像素用 3x3 椭圆核膨胀」，
放大看是像素锯齿/楼梯感；参考图 green_lineart 是手绘的**平滑圆润曲线**。
用户问「像这种平滑度的线稿你还是没办法做吗，你可以自行添加相应的插件」。

本模块方案（纯 numpy/cv2，不依赖新插件）：
  1. 骨架像素建 8 邻接图 → 走出有序路径（锚点=度≠2 的像素，闭合环单独走）
  2. 每条路径 cv2.approxPolyDP 去抖 → 滑动平均 → Chaikin 角切割 x3（收敛到二次 B 样条）
  3. 4x 超采样画布上 cv2.polylines(LINE_AA) + 圆头端点 → INTER_AREA 缩回 → 天生抗锯齿
线宽仍然**统一**（默认 3px），三层语义不变：P1 主轮廓 / P2 加细节 / P3 完整线，
分档沿用 split3 的梯度分位逻辑，只是从「像素膨胀」换成「路径整条绘制」。
"""
import numpy as np
import cv2

SS = 4          # 超采样倍数
WIDTH = 2.5     # 统一线宽（有效像素；参考图 green_lineart 中位 2.0，旧版输出 2.0）
EPS = 1.4       # approxPolyDP 容差（去楼梯抖动；1.1=保守 1.8=激进）
CHAIKIN = 3     # 角切割次数
MAVG = 2        # 滑动平均遍数（越大越"流"，2=三档横评定档）


# ---------------------------------------------------------------- 路径提取
def skeleton_paths(sk):
    """骨架 uint8(0/1) → [(pts Nx2 float32(x,y), closed)]，坐标为像素级。"""
    sk = (sk > 0).astype(np.uint8)
    Hh, Ww = sk.shape
    ys, xs = np.nonzero(sk)
    N = len(ys)
    if N == 0:
        return []
    idx = np.full(sk.shape, -1, np.int32)
    idx[ys, xs] = np.arange(N)

    ia_list, ib_list = [], []
    for dy, dx in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
        y0, y1 = max(0, -dy), min(Hh, Hh - dy)
        x0, x1 = max(0, -dx), min(Ww, Ww - dx)
        both = (sk[y0:y1, x0:x1] > 0) & (sk[y0 + dy:y1 + dy, x0 + dx:x1 + dx] > 0)
        ia_list.append(idx[y0:y1, x0:x1][both])
        ib_list.append(idx[y0 + dy:y1 + dy, x0 + dx:x1 + dx][both])
    IA = np.concatenate([np.concatenate(ia_list), np.concatenate(ib_list)])
    IB = np.concatenate([np.concatenate(ib_list), np.concatenate(ia_list)])
    order = np.argsort(IA, kind="stable")
    IA, IB = IA[order], IB[order]
    deg = np.bincount(IA, minlength=N)
    start = np.zeros(N + 1, np.int64)
    start[1:] = np.cumsum(deg)

    def nbrs(i):
        return IB[start[i]:start[i + 1]]

    visited = np.zeros(N, bool)
    paths = []

    def walk(a, n0, stop):
        """从锚点 a 经 n0 走到 stop（None=走到下一个度≠2 锚点）。"""
        path = [a, n0]
        visited[n0] = True
        prev, cur = a, n0
        while cur != stop and (stop is not None or deg[cur] == 2):
            nxt = -1
            for m in nbrs(cur):
                if m != prev:
                    nxt = m
                    break
            if nxt < 0:
                break
            if deg[cur] == 2:
                visited[cur] = True
            path.append(nxt)
            prev, cur = cur, nxt
            if len(path) > 4 * N:
                break
        return path

    # 1) 从锚点（度≠2）出发
    for a in np.where(deg != 2)[0].tolist():
        for n in nbrs(a).tolist():
            if not visited[n]:
                paths.append(walk(a, n, None))
    # 2) 剩余未访问的度2像素 = 闭合环
    for s in range(N):
        if visited[s] or deg[s] != 2:
            continue
        ns = nbrs(s).tolist()
        if not ns:
            continue
        p = walk(s, ns[0], s)
        if len(p) >= 3:
            paths.append(p)
        visited[s] = True

    out = []
    for p in paths:
        if len(p) < 2:
            continue
        pts = np.stack([xs[p], ys[p]], 1).astype(np.float32)
        closed = p[0] == p[-1] if len(p) > 2 else False
        out.append((pts, closed))
    return out


# ---------------------------------------------------------------- 平滑
def _chaikin(p, closed):
    n = len(p)
    if closed and n >= 3:
        q = 0.75 * p + 0.25 * np.roll(p, -1, axis=0)
        r = 0.25 * p + 0.75 * np.roll(p, -1, axis=0)
        out = np.empty((2 * n, 2), np.float32)
        out[0::2], out[1::2] = q, r
        return out
    if n < 3:
        return p
    q = 0.75 * p[:-1] + 0.25 * p[1:]
    r = 0.25 * p[:-1] + 0.75 * p[1:]
    out = np.empty((2 * (n - 1) + 2, 2), np.float32)
    out[0], out[-1] = p[0], p[-1]
    out[1:-1:2], out[2:-1:2] = q, r
    return out


def _movavg(p, closed):
    k = np.array([0.25, 0.5, 0.25], np.float32)
    if closed and len(p) >= 3:
        return (0.25 * np.roll(p, 1, 0) + 0.5 * p + 0.25 * np.roll(p, -1, 0)).astype(np.float32)
    if len(p) < 3:
        return p
    e = np.vstack([p[:1], p, p[-1:]]).astype(np.float32)
    out = np.empty_like(p)
    for c in range(2):
        out[:, c] = np.convolve(e[:, c], k, "valid")
    out[0], out[-1] = p[0], p[-1]
    return out


def smooth_path(pts, closed, eps=EPS, iters=CHAIKIN, mavg=MAVG):
    if len(pts) < 3:
        return pts
    ap = cv2.approxPolyDP(pts.reshape(-1, 1, 2).astype(np.float32), eps, closed)
    p = ap.reshape(-1, 2).astype(np.float32)
    if len(p) < 3:
        return pts
    for _ in range(mavg):
        p = _movavg(p, closed)
    for _ in range(iters):
        p = _chaikin(p, closed)
    return p


# ---------------------------------------------------------------- 分档 + 渲染
def tier_map(sk, mag, q_hi=65.0, q_mid=35.0, dwin=31):
    """与 lineart_canny.split3 同源的分位分档：0=强(主轮廓) 1=中 2=弱"""
    m_on = np.where(sk > 0, mag, 0).astype(np.float32)
    m_s = cv2.dilate(m_on, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dwin, dwin)))
    v = m_s[sk > 0]
    tier = np.full(sk.shape, -1, np.int8)
    if v.size == 0:
        return tier
    t_hi, t_mid = np.percentile(v, q_hi), np.percentile(v, q_mid)
    on = sk > 0
    tier[on & (m_s >= t_hi)] = 0
    tier[on & (m_s < t_hi) & (m_s >= t_mid)] = 1
    tier[on & (tier < 0)] = 2
    return tier


def _subpaths_by_tier(paths, tiermap, min_run=6, eps=EPS, iters=CHAIKIN, mavg=MAVG):
    """把每条路径按 tier 游程切分（短游程并入前段）→ 逐段平滑。
    返回 {tier: [(pts, closed)]}，pts 已平滑（坐标为浮点）。"""
    buckets = {0: [], 1: [], 2: []}
    for pts, closed in paths:
        n = len(pts)
        t = tiermap[pts[:, 1].astype(np.int64), pts[:, 0].astype(np.int64)]
        # 游程
        runs = []
        s = 0
        for i in range(1, n + 1):
            if i == n or t[i] != t[s]:
                runs.append([int(t[s]), s, i - 1])
                s = i
        # 短游程并入前一段
        merged = []
        for r in runs:
            if merged and (r[2] - r[1] + 1) < min_run:
                merged[-1][2] = r[2]
            else:
                merged.append(r)
        for k, (tt, a, b) in enumerate(merged):
            a2 = max(0, a - 1) if k > 0 else a      # 与前段共享 1px 保证连续
            b2 = min(n - 1, b + 1) if k < len(merged) - 1 else b
            sub = pts[a2:b2 + 1]
            cl = closed and a2 == 0 and b2 == n - 1
            buckets[int(tt)].append((smooth_path(sub.copy(), cl, eps, iters, mavg), cl))
    return buckets


def render_paths(subpaths, W, H, width=WIDTH, ss=SS):
    """超采样画线 → 缩回 → 0..1 alpha。subpaths: [(pts, closed)]"""
    if not subpaths:
        return np.zeros((H, W), np.float32)
    canvas = np.zeros((H * ss, W * ss), np.uint8)
    th = max(1, int(round(width * ss)))
    rad = th / 2.0
    for pts, closed in subpaths:
        if len(pts) < 2:
            continue
        pp = np.round(pts * ss).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [pp], bool(closed), 255, thickness=th, lineType=cv2.LINE_AA)
        for e in (pp[0, 0], pp[-1, 0]):          # 圆头端点
            cv2.circle(canvas, (int(e[0]), int(e[1])), int(round(rad)), 255, -1, lineType=cv2.LINE_AA)
    al = cv2.resize(canvas.astype(np.float32) / 255.0, (W, H), interpolation=cv2.INTER_AREA)
    return np.clip(al, 0, 1)


def split3_smooth(sk, mag, W, H, width=WIDTH, q_hi=65.0, q_mid=35.0, eps=EPS, iters=CHAIKIN, mavg=MAVG):
    """平滑版三层线稿。返回 (al1, al2, al3)——已是抗锯齿最终 alpha，不要再过 aa()。
    P1 = 主轮廓(强)  P2 = 强+中  P3 = 全部 = 完整线稿。"""
    sk8 = (sk > 0).astype(np.uint8)
    paths = skeleton_paths(sk8)
    if not paths:
        z = np.zeros((H, W), np.float32)
        return z, z.copy(), z.copy()
    tm = tier_map(sk8, mag, q_hi, q_mid)
    buckets = _subpaths_by_tier(paths, tm, eps=eps, iters=iters, mavg=mavg)
    al1 = render_paths(buckets[0], W, H, width)
    al2 = render_paths(buckets[0] + buckets[1], W, H, width)
    al3 = render_paths(buckets[0] + buckets[1] + buckets[2], W, H, width)
    # 平滑每条路径
    return al1, al2, al3
