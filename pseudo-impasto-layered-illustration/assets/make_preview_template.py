# -*- coding: utf-8 -*-
"""分层预览 + 关层对比

两张图：
  预览/{key}_分层预览.png  —— 成品 + 13 个图层逐层缩略（含混色模式/不透明度）
  预览/{key}_关层对比.png  —— 关掉某个效果层前后各 1/3 画面，证明"层是真的有用"
"""
import os, sys, json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
try:
    import layers as LY            # 你的工程里：把 layers_template.py 复制成 layers.py 再改配色
except ImportError:
    import layers_template as LY   # 直接跑模板时回落

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT = "C:/Windows/Fonts/msyh.ttc"
W, H = LY.W, LY.H
BLEND_S = {"NORMAL": "正常", "SCREEN": "滤色", "MULTIPLY": "正片叠底", "SOFT_LIGHT": "柔光"}


def load_layer(d):
    a = np.asarray(Image.open(d).convert("RGBA"), np.float32) / 255.0
    return a[..., :3], a[..., 3]


def compose(folder, skip=()):
    """按 PS 规则自下而上合成（与 layers.verify 同一套公式）"""
    out = np.zeros((H, W, 3), np.float32)
    for _, name, mode, op in reversed(LY.LAYERS):          # LAYERS 是自上而下
        if name in skip or name in HIDDEN(name):
            continue
        c, a = load_layer(os.path.join(folder, name + ".png"))
        e = a * op
        if mode == "NORMAL":
            out = out * (1 - e[..., None]) + c * e[..., None]
        elif mode == "MULTIPLY":
            out = out * (1 - e[..., None]) + (out * c) * e[..., None]
        elif mode == "SCREEN":
            out = out * (1 - e[..., None]) + (1 - (1 - out) * (1 - c)) * e[..., None]
        elif mode == "SOFT_LIGHT":
            out = out * (1 - e[..., None]) + LY.softlight(out, c) * e[..., None]
    return np.clip(out, 0, 1)


def HIDDEN(name):
    return set()


def sheet_layers(key, folder, final_png):
    tiles = []
    for g, name, mode, op in LY.LAYERS:
        c, a = load_layer(os.path.join(folder, name + ".png"))
        chk = ((np.indices((H // 16, W // 16)).sum(0) % 2) * 40 + 90).astype(np.float32)[..., None]
        chk = np.repeat(np.repeat(chk, 16, 0), 16, 1) / 255.0
        vis = c * a[..., None] + chk * (1 - a[..., None])
        tiles.append((name, mode, op, Image.fromarray((vis * 255).astype(np.uint8)).resize((260, 390))))

    fw, fh = 300, 450
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (260 + 10) + 10 + fw + 20, max(rows * (390 + 30) + 40, fh + 40)),
                      (26, 26, 30))
    d = ImageDraw.Draw(sheet)
    ft = ImageFont.truetype(FONT, 20)
    fs = ImageFont.truetype(FONT, 15)
    d.text((10, 10), "%s · 13 图层逐层预览（白底=成品）" % key, fill=(255, 226, 150), font=ft)
    for i, (name, mode, op, t) in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = 10 + c * (260 + 10), 42 + r * (390 + 30)
        sheet.paste(t, (x, y))
        d.text((x + 2, y + 392), "%s  [%s %d%%]" % (name, BLEND_S[mode], int(op * 100)),
               fill=(160, 215, 255), font=fs)
    fx = cols * (260 + 10) + 20
    fin = Image.open(final_png).convert("RGB").resize((fw, fh))
    sheet.paste(fin, (fx, 42))
    d.text((fx, 44 + fh), "成品（13 层全开）", fill=(255, 226, 150), font=fs)
    out = os.path.join(ROOT, "预览", "%s_分层预览.png" % key)
    sheet.save(out)
    print("  ", out)
    return out


def toggle_rows(key, folder, final_png):
    base = compose(folder)
    fin = np.asarray(Image.open(final_png).convert("RGB"), np.float32) / 255.0
    fin = cv2.resize(fin, (W, H), interpolation=cv2.INTER_LANCZOS4)
    demos = ["人物-阴影", "人物-高光", "整体-暖调柔光", "背景-光斑", "①线稿"]
    rows = [("全开（=成品）", base, fin)]
    for name in demos:
        if name.startswith("①"):
            b2 = base.copy()          # 线稿默认隐藏 → 打开它
            for g, nm, mode, op in LY.LAYERS:
                if g != "①线稿":
                    continue
                c, a = load_layer(os.path.join(folder, nm + ".png"))
                e = a * op
                b2 = b2 * (1 - e[..., None]) + c * e[..., None]
            rows.append(("打开「%s」" % name, b2, fin))
        else:
            rows.append(("关掉「%s」" % name, compose(folder, skip=(name,)), fin))
    tw, th = 330, 495
    sheet = Image.new("RGB", (2 * tw + 30, len(rows) * (th + 30) + 44), (26, 26, 30))
    d = ImageDraw.Draw(sheet)
    ft = ImageFont.truetype(FONT, 20)
    fs = ImageFont.truetype(FONT, 16)
    d.text((12, 10), "关层对比（左：改动后 / 右：成品）—— 层是真的在起作用", fill=(255, 226, 150), font=ft)
    for i, (lab, a, b) in enumerate(rows):
        y = 44 + i * (th + 30)
        d.text((12, y), lab, fill=(160, 215, 255), font=fs)
        sheet.paste(Image.fromarray((a * 255).astype(np.uint8)).resize((tw, th)), (12, y + 20))
        sheet.paste(Image.fromarray((b * 255).astype(np.uint8)).resize((tw, th)), (tw + 24, y + 20))
    out = os.path.join(ROOT, "预览", "%s_关层对比.png" % key)
    sheet.save(out)
    print("  ", out)
    return out


if __name__ == "__main__":
    keys = sys.argv[1:] or [t["key"] for t in json.load(open(os.path.join(ROOT, "themes.json"), encoding="utf-8"))]
    themes = {t["key"]: t for t in json.load(open(os.path.join(ROOT, "themes.json"), encoding="utf-8"))}
    for k in keys:
        print("==", k)
        folder = os.path.join(ROOT, "图层", k)
        fin = os.path.join(ROOT, themes[k]["pick"])
        sheet_layers(k, folder, fin)
        toggle_rows(k, folder, fin)
