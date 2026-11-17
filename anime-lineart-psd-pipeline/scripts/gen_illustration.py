# -*- coding: utf-8 -*-
"""ComfyUI NOOBAI txt2img 成图（新提示词，CFG=7, DPM++ 2M Karras）
直接生成三张：古堡窗边 / 月下露台 / 古老图书馆
"""
import json, sys, urllib.request, time, os

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path, data=None, timeout=180):
    req = urllib.request.Request("http://127.0.0.1:8188" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=timeout) as r:
        return json.load(r)


NEG_SHARED = ("lowres, ugly, deformed, bad anatomy, extra limbs, missing fingers, blurry, "
              "3d, realistic, photo, photograph, real photo, watermark, text, words, logo, signature, "
              "messy lines, overexposed, bright background, cartoon chibi, disfigured, "
              "oversaturated colors, ugly hands, mutated face, distorted hands, bad perspective, "
              "flat boring texture")

POS = {
    "古堡窗边双人": ("masterpiece, best quality, ultra-detailed, 1boy,1girl,couple, intimate pose, "
        "face close to each other, young man with short silver hair, purple eyes, "
        "noble military tailcoat with gold embroidery, chains and gem decorations. "
        "Girl with long wavy black hair, burgundy gothic bonnet decorated with red roses and lace, "
        "vintage gothic lolita dress, off shoulder, lace frills, white gloves. "
        "Dark castle interior, stained glass window, candlelight, red roses, delicate line art, "
        "anime illustration, soft cel shading, rich texture, gorgeous ornament, "
        "dark vintage atmosphere, medium shot, sharp clean outlines"),
    "月下露台双人": ("masterpiece, best quality, ultra-detailed, 1boy,1girl,couple, gentle interaction, "
        "boy with pale ash short hair, cold grey eyes, dark green noble suit, "
        "cloak with silver embroidery, gem brooch. "
        "Girl with long dark brown curly hair, dark green vintage bonnet, "
        "decorated with green roses and pearl chains, gothic lolita long dress, "
        "layers of lace and satin, long white opera gloves. "
        "Castle balcony, full moon, dark night sky, climbing roses, crystal ornaments, "
        "delicate clean linework, detailed fabric texture, anime illustration, subtle shading, "
        "elegant melancholy mood, medium shot"),
    "古老图书馆双人": ("masterpiece, best quality, ultra-detailed, 1boy,1girl,couple, leaning close together, "
        "boy with light silver-grey short hair, blue eyes, dark grey formal noble outfit, "
        "silver chain accessories. "
        "Girl with long black hair with purple highlights, purple gothic bonnet with violet flowers "
        "and lace feathers, elaborate goth lolita dress, ruffle sleeves, "
        "crystal and ribbon decorations, white long gloves. "
        "Ancient library background, tall bookshelves, dim candle light, purple roses, "
        "intricate line art, smooth cel shading, anime style, "
        "rich detail on clothing lace and gem, romantic dark atmosphere"),
}

SEEDS = {"古堡窗边双人": 20260930, "月下露台双人": 20260931, "古老图书馆双人": 20260932}


def build_wf(seed, pos, out_prefix, steps=30, cfg=7.0, w=1024, h=1536):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "NoobAI-XL-Vpred-v1.0.safetensors"}},
        "2": {"class_type": "ModelSamplingDiscrete",
              "inputs": {"model": ["1", 0], "sampling": "v_prediction", "zsnr": True}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": pos}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEG_SHARED}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0], "filename_prefix": "illust/%s" % out_prefix}},
    }


def run_one(name):
    seed = SEEDS[name]
    prefix = "illu_%s" % name
    r = api("/prompt", {"prompt": build_wf(seed, POS[name], prefix), "client_id": "wb_illu"})
    pid = r["prompt_id"]
    for _ in range(360):
        time.sleep(5)
        h = api("/history/%s" % pid)
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                # 取节点8的输出
                outs = h[pid].get("outputs", {})
                for k, v in outs.items():
                    for im in v.get("images", []):
                        if im["filename"].startswith("illu_%s" % name):
                            return pid, im["filename"], im["subfolder"]
                return pid, None, None
            for m in st.get("messages", []):
                if m[0] == "execution_error":
                    raise RuntimeError(m[1].get("exception_message", "unknown"))
    raise TimeoutError("timeout %s" % pid)


def download(name, fn, sub):
    from urllib.parse import quote
    url = "http://127.0.0.1:8188/view?filename=%s&subfolder=%s&type=output" % (quote(fn), quote(sub))
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "%s.png" % name)
    for _ in range(10):
        try:
            urllib.request.urlretrieve(url, dst)
            return dst
        except Exception:
            time.sleep(3)
    raise RuntimeError("下载失败 %s" % name)


if __name__ == "__main__":
    order = list(POS.keys())
    only = sys.argv[1:] or order
    HERE0 = os.path.dirname(os.path.abspath(__file__))
    for name in order:
        if name not in only:
            continue
        print(">>> 生成 %s (seed=%d)" % (name, SEEDS[name]))
        res = run_one(name)
        if res is None:
            print("    !! 生成失败或无输出", name); continue
        pid, fn, sub = res
        dst = download(name, fn, sub)
        print("    已保存 ->", dst, os.path.getsize(dst) // 1024, "KB")
    print("全部成图完成")
