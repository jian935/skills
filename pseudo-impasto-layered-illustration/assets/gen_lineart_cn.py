# -*- coding: utf-8 -*-
"""ControlNet 结构引导 + NoobAI 重新绘制干净线稿（生成式线稿，非像素抽取）"""
import json, sys, urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path, data=None, timeout=120):
    req = urllib.request.Request("http://127.0.0.1:8188" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=timeout) as r:
        return json.load(r)


POS_BASE = ("masterpiece, best quality, newest, absurdres, highres, "
            "monochrome, greyscale, lineart, line art, white background, coloring book page, "
            "clean line art, no shading, no screentone, black lines, thick black outline, "
            "1boy, 1girl, couple, close pose, intimate interaction, "
            "elegant gothic lolita dress, royal prince outfit, bonnet hat, long hair, "
            "roses, rose bouquet, ornate frills and ribbons, jewelry ornaments, "
            "detailed background with rose arch and chains")
NEG = ("worst quality, low quality, bad anatomy, bad hands, extra limbs, "
       "color, colored, shading, screentone, halftone, crosshatch, gradient, "
       "grey background, colored background, dark background, "
       "blue lines, pale lines, light lines, sketch, rough draft, unfinished, "
       "messy lines, broken lines, watermark, text, signature")


def build_wf(seed, canny_lo=60, canny_hi=140, cn_strength=0.7, cn_end=0.85):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "NoobAI-XL-Vpred-v1.0.safetensors"}},
        "2": {"class_type": "ModelSamplingDiscrete",
              "inputs": {"model": ["1", 0], "sampling": "v_prediction", "zsnr": True}},
        "3": {"class_type": "LoadImage", "inputs": {"image": "gothic_couple_02.png"}},
        "4": {"class_type": "Canny", "inputs": {"image": ["3", 0], "low_threshold": 0.24,
                                                "high_threshold": 0.55, "L2gradient": False}},
        "5": {"class_type": "ControlNetLoader",
              "inputs": {"control_net_name": "controlnet-union-sdxl-1.0-promax.safetensors"}},
        "6": {"class_type": "SetUnionControlNetType",
              "inputs": {"control_net": ["5", 0], "type": "canny/lineart/anime_lineart/mlsd"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": POS_BASE}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": NEG}},
        "9": {"class_type": "ControlNetApplyAdvanced",
              "inputs": {"positive": ["7", 0], "negative": ["8", 0], "control_net": ["6", 0],
                         "image": ["4", 0], "strength": cn_strength,
                         "start_percent": 0.0, "end_percent": cn_end}},
        "10": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
        "11": {"class_type": "KSampler",
               "inputs": {"model": ["2", 0], "positive": ["9", 0], "negative": ["9", 1],
                          "latent_image": ["10", 0], "seed": seed, "steps": 26, "cfg": 5.5,
                          "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1.0}},
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["1", 2]}},
        "13": {"class_type": "SaveImage",
               "inputs": {"images": ["12", 0], "filename_prefix": "genline/s%03d" % seed}},
    }


def run(seed, **kw):
    r = api("/prompt", {"prompt": build_wf(seed, **kw), "client_id": "wb"})
    pid = r["prompt_id"]
    import time
    for _ in range(300):
        time.sleep(5)
        h = api("/history/%s" % pid)
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("completed"):
                return pid
            msgs = st.get("messages", [])
            for m in msgs:
                if m[0] == "execution_error":
                    raise RuntimeError(m[1].get("exception_message", "unknown"))
    raise TimeoutError("timeout pid=%s" % pid)


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260929
    kw = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    pid = run(seed, **kw)
    h = api("/history/%s" % pid)
    outs = h[pid]["outputs"]
    for k, v in outs.items():
        for im in v.get("images", []):
            print("OUT", im["filename"], im["subfolder"], im["type"])
