# -*- coding: utf-8 -*-
"""线稿 v2：Canny 边缘 + smooth_line 矢量平滑

输入：成品图 + 抠图 alpha（可选，用于人物/背景双阈值）
输出：图层/<key>/线稿-完整.png（透明黑线） + 线稿/<key>_线稿_白底.png

为什么不用 NoobAI 生成式线稿：
  - 之前候选图是带颜色/灰调的重绘插画，不是纯白底黑线稿。
  - Canny 提取 + 矢量 Chaikin 平滑可保证：纯白底、连续不断线、粗细一致。
"""
import os, sys, numpy as np, cv2
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lineart_canny as LC
import smooth_line as SL


def main(pick, alpha_png, key, width=2.5):
    rgb = np.asarray(Image.open(pick).convert("RGB"), np.float32)
    H, W = rgb.shape[:2]
    cm = LC.charmask(alpha_png, H, W, grow=25)
    # 默认参数：保完整结构
    sk, mag = LC.build_skel(rgb, cm, lo_c=32, hi_c=88, lo_b=72, hi_b=170, close=5, minlen=26)
    # 用矢量平滑渲染，统一线宽；加大 Chaikin/滑动平均让线条更圆润流动
    al1, al2, al3 = SL.split3_smooth(sk, mag, W, H, width=width,
                                       q_hi=65, q_mid=35, eps=1.8, iters=5, mavg=3)
    P3 = np.clip(al3, 0, 1)
    # 轻开运算去掉 Canny 毛刺，再骨架化重渲染以保持连续平滑
    P_bin = (P3 > 0.45).astype(np.uint8)
    P_bin = cv2.morphologyEx(P_bin, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    sk2 = LC.skeletonize(P_bin)
    sk2 = LC.prune(sk2, 20)
    al1, al2, al3 = SL.split3_smooth(sk2, mag, W, H, width=width,
                                       q_hi=65, q_mid=35, eps=1.8, iters=5, mavg=3)
    P = np.clip(al3, 0, 1)
    # 转透明黑线
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., 3] = (P * 255).astype(np.uint8)
    os.makedirs(os.path.join(HERE, "图层", key), exist_ok=True)
    Image.fromarray(rgba).save(os.path.join(HERE, "图层", key, "线稿-完整.png"))
    # 白底黑线版
    white = (255 * (1 - P[..., None])).astype(np.uint8)
    white = np.repeat(white, 3, axis=-1)
    os.makedirs(os.path.join(HERE, "线稿"), exist_ok=True)
    Image.fromarray(white).save(os.path.join(HERE, "线稿", "%s_线稿_白底.png" % key))
    # 统计
    binm = (P > 0.45).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(binm, 8)
    areas = st[1:, 4]
    small = int((areas < 20).sum()) if len(areas) else 0
    print("%s: 覆盖率 %.2f%%  分量数 %d  短线(<20) %d (%.1f%%)  最大段 %.1f%%"
          % (key, binm.mean() * 100, len(areas), small,
             small / len(areas) * 100 if len(areas) else 0,
             areas.max() / areas.sum() * 100 if len(areas) else 0))


if __name__ == "__main__":
    jobs = [
        ("古堡窗边双人.png", "图层/古堡窗边/_alpha.png", "古堡窗边"),
        ("月下露台双人.png", "图层/月下露台/_alpha.png", "月下露台"),
        ("古老图书馆双人.png", "图层/古老图书馆/_alpha.png", "古老图书馆"),
    ]
    for pick, alpha, key in jobs:
        main(pick, alpha, key, width=2.5)
