# 绘画生产管线 · 4 个 Agent Skill

把「一句话或一张参考图」变成**可交付的分层 PSD**，全过程在本机跑完：出图 → 抠图 → 线稿 → 分层 → Photoshop 组装。

这四个 skill 原本是我自己画插画时沉淀下来的操作手册，现在按可复用的形式整理发布：每个目录里是一份 `SKILL.md`（给 Agent 读的流程与判据）加若干可直接执行的 Python 脚本。

## 四个 skill

| # | Skill | 解决什么 | 关键产物 |
|---|---|---|---|
| 01 | `pseudo-impasto-layered-illustration` | 伪厚涂 / 半厚涂插画，一次成型出分层 PSD | 19 图层 PSD（6 组 + 13 层），13 层全开逐像素等于成品 |
| 02 | `anime-lineart-psd-pipeline` | 二次元成图转可上色 20 层 PSD | 白底 2.5px 黑线稿 + 20 层 PSD |
| 03 | `photoshop-com-automation` | 用 Python 驱动 Photoshop 的通用底座 | COM 连接、置入图层、设混合模式、批量导出 |
| 04 | `comfyui-anime-pipeline` | 本地 ComfyUI 的操作手册 | API 调用范式、ControlNet 上色、模型下载、显存配置 |

后两个是底座（Windows + Photoshop、本地 ComfyUI），前两个是建立在底座上的成品线。四者可以单独用，也可以串成一条链。

## 安装

这些 skill 面向任何支持 `SKILL.md` 约定的 Agent（WorkBuddy、Claude Code、自建 agent 均可）：

```bash
git clone https://github.com/jian935/skills.git
cp -r skills/pseudo-impasto-layered-illustration ~/.workbuddy/skills/
```

四个目录彼此独立，按需只取其一即可；`anime-lineart-psd-pipeline` 与 `pseudo-impasto-layered-illustration` 会用到的依赖见 `docs/illustration-requirements.txt`。

Claude Code 用户放到 `~/.claude/skills/`；其他框架把它当普通「流程文档 + 脚本目录」直接读也行，`SKILL.md` 里没有私有语法。

## 环境

| 依赖 | 版本 | 说明 |
|---|---|---|
| 操作系统 | Windows 10/11 | 只有 Photoshop COM 部分需要；纯线稿/分层逻辑本身跨平台 |
| Photoshop | 2022–2025 | 需注册 COM（脚本里逐个探测常见安装路径） |
| Python | 3.11+ | `pip install -r docs/illustration-requirements.txt` |
| ComfyUI | 可选 | 用于出图与 LineartAnime 线稿；装在任意目录，用 `COMFY_ROOT` 指定 |

```bash
pip install -r docs/illustration-requirements.txt
set COMFY_ROOT=D:\ComfyUI        # ComfyUI 安装根目录（含 ComfyUI/ 与 python_embeded/）
set OUT_DIR=D:\art\deliver       # 成品目录，默认 ./out
set SERIES=分层插画              # PSD 文件名前缀，默认「分层插画」
```

`COMFY_ROOT` 只在 `comfy.py` 里用到；`OUT_DIR` 影响 `build_psd*.py`；`SERIES` 只影响文件名。

## 一条完整链路

```
参考图 / 提示词
   │  ① 出图        pseudo-impasto · comfy.py（ComfyUI 或云端出图）
   ▼
成图 PNG
   │  ② 抠图        anime-lineart · matting_local.py（rembg + isnet-anime）
   ▼
alpha.png
   │  ③ 线稿        lineart_canny.py / make_lineart_v2.py（Canny + Chaikin 平滑）
   ▼
白底线稿 + 图层切片
   │  ④ 分层        layers_20.py（8 档明度 + 皮肤 + 高光3 + 阴影3 + 冷暖2）
   ▼
图层/ 目录
   │  ⑤ 组装        build_psd.py（Photoshop COM 置入、设混合模式与不透明度）
   ▼
OUT_DIR/<系列>_<编号><主题>_分层.psd
```

最小可跑示例（第 ②→⑤ 步，已有成图）：

```bash
cd anime-lineart-psd-pipeline/scripts
python matting_local.py ../成品/t1.png 图层/t1/_alpha.png
python layers_20.py ../成品/t1.png 图层/t1/_alpha.png t1
python build_psd.py t1 "分层插画_01秋日放学路_分层"
```

伪厚涂那条线把第 ④ 步换成 `assets/layers_template.py` + `assets/themes_example.json` 的配置方式，再跑 `build_psd_template.py`。

## 为什么是「分层」而不是一张图

关掉某一层画面要真的变，全开要等于成品——这是判断分层是否合格的标准，也是这套脚本存在的理由。以伪厚涂为例，面板结构是：

```
①线稿        轮廓粗线 / 中间线 / 细节细线              ← 默认隐藏（工作层）
②整体调色    暖调柔光 SOFT_LIGHT 22% / 提亮 SCREEN 14%
③细化        边缘光 SCREEN 40% / 高光 SCREEN 46%
④二分        阴影 MULTIPLY 50%
⑤分区上色    完整色 NORMAL 100%
⑥背景        柔光罩 SOFT_LIGHT 20% / 光斑 SCREEN 52% / 虚化 / 原色
```

配色不靠肉眼调：暖橙 `(255,178,102)`、提亮 `(255,238,208)`、高光 `(255,232,186)`、边缘光 `(255,236,196)`、暖棕阴影 `(86,56,40)`，全部写死在脚本里，换主题只改 `themes.json`。

## 已经踩平的坑（SKILL.md 里有完整记录）

这些是这套东西真正的价值，不是「怎么调用 API」那种能在文档里查到的东西：

- **云端出图并行会丢图**：同一秒完成的多个请求返回同名文件，后写覆盖前写。必须一次一张，`output_dir` 分开也拦不住。
- **vpred 模型不挂 `ModelSamplingDiscrete` 会过曝**（NoobAI-XL vpred）。
- **`LineartAnime@1536` 在密集排线图上会糊块并丢虹膜**：`detect_resolution` 提到 2048，再用 Canny 在眼框内补回虹膜。
- **PS COM 抛「消息筛选器显示应用程序正在使用中」**：前台有模态对话框或上次脚本卡死，重试无用，只能 `taskkill` 后重启并轮询 `DoJavaScript("1+1")`。
- **同时打开 6 个大文档会把 PS 拖死**：`build_psd.py --no-open` 批量生成、最后统一打开。
- **PS 暂存文件侵蚀系统盘**：批量保存大 PSD 时 `%LOCALAPPDATA%\Temp\Photoshop Temp*` 会涨到数 GB，去首选项把暂存盘改到数据盘。
- **RMBG 节点 `invert_output` 语义反直觉**：默认保留背景抠掉主体，必须先小图验证方向。
- **LatentSync 1.6 在 8GB 显存上跑不动**（unet 5GB fp32），下限约 12GB；Q 版脸也检测不到，只能走程序化口型。

## 可验证的口径

- 伪厚涂：19 图层；13 层全开与成品图逐像素一致（`numpy` 比对最大通道差 0）。
- 线稿：纯白底、2.5px 黑线、连续无短线（Canny 后接矢量 Chaikin 平滑，不是位图膨胀）。
- 20 层 PSD：底色按 8 档明度自动聚类（极暗/墨色/深蓝/暗蓝/深灰/中灰/浅灰/亮银），加皮肤层与高光/阴影各 3 层。
- ComfyUI 出图：8GB 显存下 512×896 可跑，10 秒素材建议降到 448×768；121 帧/512×896 约 195s。

## 已知限制

- Photoshop 相关脚本只在 Windows 上验证过，macOS 的 COM 等价物（AppleScript）未实现。
- 分层质量依赖线稿与抠图的干净程度，抠图失败会让整条链退化。
- 模型权重不随仓库分发（NoobAI-XL、controlnet-union、RMBG、LayerDiffuse 需自行下载，SKILL.md 里写了国内镜像方式）。
- 显存、PS 版本、字体渲染都会影响结果，跨机器复现需要重新校准那几个数值。

## 目录

```
skills/
├── pseudo-impasto-layered-illustration/
│   ├── SKILL.md                       流程、图层结构、硬坑
│   └── assets/                        comfy.py / layers_template.py / build_psd_template.py …
├── anime-lineart-psd-pipeline/
│   ├── SKILL.md
│   ├── references/workflow_notes.md    工程笔记
│   └── scripts/                        matting_local / lineart / layers_20 / build_psd …
├── photoshop-com-automation/
│   ├── SKILL.md                        COM + ExtendScript 全量用法
│   └── assets/                         ps_conn.py / open_psd.py
├── comfyui-anime-pipeline/
│   └── SKILL.md                        环境、API、模型、显存配置
└── docs/
    ├── illustration-pipeline.md        本文件
    └── illustration-requirements.txt   这四条的 Python 依赖
```

## License

同仓库约定，这四个 skill 以 **MIT** 授权使用；第三方模型与节点归各自权利方所有。第三方模型、ComfyUI 自定义节点、Photoshop 归各自权利方所有，不在此授权范围内。

---

### English

Four agent skills for a local illustration pipeline: `pseudo-impasto-layered-illustration` (text → 19-layer PSD), `anime-lineart-psd-pipeline` (finished art → 20-layer PSD with a clean 2.5px lineart), `photoshop-com-automation` (drive Photoshop from Python via COM), and `comfyui-anime-pipeline` (local ComfyUI operations, ControlNet, VRAM tuning). Each folder is a `SKILL.md` plus runnable scripts. Windows + Photoshop required for the PSD assembly; ComfyUI optional. See `SKILL.md` for the pitfalls — that's the part worth reading.
