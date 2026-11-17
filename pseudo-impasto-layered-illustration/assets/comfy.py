# -*- coding: utf-8 -*-
"""ComfyUI 客户端与工作流构造（伪厚涂管线的出图侧）"""
import json, os, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:8188"
CKPT = "NoobAI-XL-Vpred-v1.0.safetensors"
CNET = "controlnet-union-sdxl-1.0-promax.safetensors"
COMFY_ROOT = os.environ.get("COMFY_ROOT", r"D:\ComfyUI")
OUTDIR = os.path.join(COMFY_ROOT, "ComfyUI", "output")
INDIR = os.path.join(COMFY_ROOT, "ComfyUI", "input")
_op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(path, data=None, timeout=300):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"})
    try:
        with _op.open(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8", "replace")[:1500], flush=True)
        raise


def _base(positive, negative, w, h, seed, steps, cfg, batch, sampler, scheduler):
    """NoobAI-XL vpred 标准链：vpred 模型必须挂 ModelSamplingDiscrete，否则过曝"""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "ModelSamplingDiscrete",
              "inputs": {"model": ["1", 0], "sampling": "v_prediction", "zsnr": True}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": positive}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": negative}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                         "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": sampler,
                         "scheduler": scheduler, "denoise": 1.0}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
    }


def wf_t2i(positive, negative, w, h, seed, prefix, steps=26, cfg=5.5, batch=1,
           sampler="euler_ancestral", scheduler="normal"):
    wf = _base(positive, negative, w, h, seed, steps, cfg, batch, sampler, scheduler)
    wf["5"] = {"class_type": "EmptyLatentImage",
               "inputs": {"width": w, "height": h, "batch_size": batch}}
    wf["6"]["inputs"]["latent_image"] = ["5", 0]
    wf["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    return wf


def wf_i2i(image, positive, negative, denoise, seed, prefix, steps=26, cfg=5.5,
           sampler="euler_ancestral", scheduler="normal"):
    wf = _base(positive, negative, 0, 0, seed, steps, cfg, 1, sampler, scheduler)
    wf["5"] = {"class_type": "LoadImage", "inputs": {"image": image, "upload": "image"}}
    wf["10"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}}
    wf["6"]["inputs"]["latent_image"] = ["10", 0]
    wf["6"]["inputs"]["denoise"] = denoise
    wf["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    return wf


def wf_cn(image, positive, negative, strength, end, seed, prefix, steps=30, cfg=6.0,
          sampler="euler_ancestral", scheduler="normal", w=1024, h=1536):
    """线稿 → 上色。union promax 的 type 必须填组名字符串"""
    wf = _base(positive, negative, w, h, seed, steps, cfg, 1, sampler, scheduler)
    wf["5"] = {"class_type": "LoadImage", "inputs": {"image": image, "upload": "image"}}
    wf["9"] = {"class_type": "ControlNetLoader", "inputs": {"control_net_name": CNET}}
    wf["11"] = {"class_type": "SetUnionControlNetType",
                "inputs": {"control_net": ["9", 0], "type": "canny/lineart/anime_lineart/mlsd"}}
    wf["12"] = {"class_type": "ControlNetApplyAdvanced",
                "inputs": {"positive": ["3", 0], "negative": ["4", 0], "control_net": ["11", 0],
                           "image": ["5", 0], "strength": strength,
                           "start_percent": 0.0, "end_percent": end}}
    wf["13"] = {"class_type": "EmptyLatentImage",
                "inputs": {"width": w, "height": h, "batch_size": 1}}
    wf["6"]["inputs"].update({"positive": ["12", 0], "negative": ["12", 1], "latent_image": ["13", 0]})
    wf["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    return wf


def run(jobs, tag=""):
    """jobs: [(name, wf, seed)] → 返回 {name: [相对路径,...]}"""
    sub = []
    for name, wf, seed in jobs:
        r = api("/prompt", {"prompt": wf, "client_id": "a18"})
        sub.append((name, r["prompt_id"], seed, time.time()))
        print("queued: %-28s seed=%s" % (name, seed), flush=True)
    print("%s%d 个任务入队，等待中...\n" % (tag, len(sub)), flush=True)
    done, fail = {}, {}
    while len(done) + len(fail) < len(sub):
        time.sleep(5)
        for name, pid, seed, t0 in sub:
            if name in done or name in fail:
                continue
            h = api("/history/" + pid)
            if pid not in h:
                continue
            st = h[pid]["status"]
            if st.get("status_str") == "error":
                msg = ""
                for m in st.get("messages", []):
                    if m[0] == "execution_error":
                        msg = "%s | %s" % (m[1].get("node_type"), m[1].get("exception_message"))
                fail[name] = msg
                print("[FAIL] %s: %s" % (name, msg), flush=True)
            elif st.get("completed"):
                outs = []
                for _, o in h[pid].get("outputs", {}).items():
                    for im in o.get("images", []):
                        outs.append(os.path.join(im.get("subfolder", ""), im["filename"]))
                done[name] = outs
                print("[OK]   %-28s %ds  %s" % (name, int(time.time() - t0), outs), flush=True)
    print("\n成功 %d / 失败 %d" % (len(done), len(fail)), flush=True)
    for n, m in fail.items():
        print("  FAIL", n, m)
    return done, fail


def view(relpath, dst):
    """从 ComfyUI output 取回图片"""
    q = urllib.parse.urlencode({"filename": os.path.basename(relpath),
                                "subfolder": os.path.dirname(relpath).replace("\\", "/"),
                                "type": "output"})
    with _op.open(BASE + "/view?" + q, timeout=120) as r:
        data = r.read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(data)
    return dst


def upload(path, name=None):
    """上传到 ComfyUI input/，返回文件名"""
    import mimetypes, uuid
    name = name or os.path.basename(path)
    bnd = "----a18" + uuid.uuid4().hex
    body = b""
    body += ("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
             "Content-Type: image/png\r\n\r\n" % (bnd, name)).encode()
    body += open(path, "rb").read()
    body += ("\r\n--%s\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--%s--\r\n"
             % (bnd, bnd)).encode()
    req = urllib.request.Request(BASE + "/upload/image", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + bnd})
    with _op.open(req, timeout=180) as r:
        j = json.load(r)
    return j.get("name", name)


def free():
    """清空队列"""
    try:
        api("/queue", {"clear": True})
    except Exception:
        pass
