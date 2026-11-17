---
name: pseudo-impasto-layered-illustration
description: 生成"伪厚涂/半厚涂"插画并交付**分层 PSD**（19 图层：6 组 + 13 层），走草稿→线稿→上色→分图层→细化五步。当需求出现「伪厚涂/半厚涂/Pseudo Impasto」「保留线稿边缘的厚涂」「二分/阴影层/高光层/整体调色层」「关掉某一层画面要变」「全开等于成品」「约二十个图层」「按这个参考 PSD 的分层结构做」时使用。
---

# 伪厚涂插画 · 分层 PSD 管线

一次成型的五步流程，产出 `主体_主题_分层.psd`（6 组 + 13 层 = 19 图层），
**13 层全开时逐像素等于成品图**，且每层关掉都真的会改变画面。

## 0. 图层结构（已验证，直接照抄）

面板自上而下：
```
[组] ①线稿        线稿-轮廓粗线 / 线稿-中间线 / 线稿-细节细线   ← 默认隐藏（工作层）
[组] ②整体调色    整体-暖调柔光 SOFT_LIGHT 22% / 整体-提亮 SCREEN 14%
[组] ③细化        人物-边缘光 SCREEN 40% / 人物-高光 SCREEN 46%
[组] ④二分        人物-阴影 MULTIPLY 50%
[组] ⑤分区上色    人物-完整色 NORMAL 100%
[组] ⑥背景        背景-柔光罩 SOFT_LIGHT 20% / 背景-光斑 SCREEN 52%
                  / 背景-虚化（默认隐藏）/ 背景-原色
```
组编号 ①线稿在**最顶**、⑥背景在**最底**（编号从下往上数）。
暖橙统一用 `(255,178,102)`，提亮用 `(255,238,208)`，高光 `(255,232,186)`，
边缘光 `(255,236,196)`，暖棕阴影 `(86,56,40)`。

## 1. 出图引擎怎么选

- **云端出图**（ImageGen）质量显著高于本地，伪厚涂的柔和体积光、干净线稿边缘、细腻过渡都对得上；
  本地 NoobAI 容易出"海报式金色光柱"（大光比、过饱和）。
- 建议先本地出草稿定构图，云端出定稿。用户需先被告知积分消耗。
- 云端出图**光线/氛围**靠这几句就能压住爆白：
  `soft warm golden hour light, gentle side light, subtle rim light, volumetric haze, delicate bokeh`
  负面补 `huge sun, giant sun, blown out highlights, overexposed, silhouette, oversaturated, neon colors`

## 2. ⚠️ 硬坑（全部踩过，别再试）

### 2.1 云端出图工具必须「一次一张」
同一消息里并行发多个出图请求，若完成时间落在**同一秒**，返回的文件名相同 →
**后写覆盖前写，图直接丢**（给每个调用单独 `output_dir` 也拦不住）。
→ **一条消息只发一个出图调用**，拿到 localPath 立刻重命名，再发下一张。

### 2.2 「色 → 线稿」：生成式正解（2026-09-29 定稿，一次成功）

**✅ 正解 = 内置 Canny 做结构引导 + NoobAI txt2img 全重画（denoise 1.0）**，脚本 `20-gothic-couple/gen_lineart_cn.py`：
1. LoadImage 彩稿 → ComfyUI **内置 `Canny` 节点**（阈值是 **0..1 浮点**，用 0.24/0.55）→ 天然就是黑底白线
2. union promax `SetUnionControlNetType` type 填组合串 `"canny/lineart/anime_lineart/mlsd"`（不是单个 "lineart"）
3. ControlNetApplyAdvanced strength 0.7 / end_percent 0.85 → NoobAI vpred（832x1216 / 26步 / cfg 5.5 / euler_ancestral / denoise **1.0 全重画**）
4. 正面词：`monochrome, greyscale, lineart, white background, coloring book page, clean line art, no shading, no screentone, black lines, thick black outline` + 主体描述（人物/服饰/玫瑰背景）
5. 负面词：基线 + `color, colored, shading, screentone, halftone, crosshatch, gradient, grey background, blue lines, pale lines, sketch, rough draft, unfinished`（**别压 color 压太死**，见下）
6. 出来常是**淡蓝铅笔稿**（NoobAI 习惯）→ 取 **R 通道**自适应拉伸（p1~p99.5）即纯黑线白底，保抗锯齿
- 构图由 ControlNet 锁定（贴近原彩稿），线条由模型画 → 蕾丝会重排成**可读的封闭结构**，正是 coloring-book 效果；花体英文水印这类元素也会被画出来
- 局部小错（手指等）→ 换种子重出，比调参有效
- 之前判它"40 选 2 不稳定"是**手搓控制图 + 手调阈值**的锅；内置 Canny + 上述参数 2026-09-29 首发即合格，三个种子全可用

纯像素抽取（Canny/骨架/平滑矢量）只能当**PSD 内对齐用的结构层**，上限就是碎线，
永远到不了手绘线稿质量——用户参考图（豆包/ coloring-book 风）本身就是生成的。

**判据补充（2026-10-01 立绘实战）**：**浅色平涂立绘直接走生成式，别试像素抽取。**
白丝上的白线、粉发里的浅粉线这类"低对比线"灰度差≈0，Canny 任何阈值都抓不到
（实测墨量 1.2%、最大连通段 20%、脸和四肢大段缺失，调 4 组参数全部无解）。
深背景/高对比图（21 哥特）像素抽取才够用。通用版脚本 `22-立绘-伪厚涂/gen_lineart2.py`
（拷贝彩稿进 ComfyUI input → 生成 → R 通道拉伸 → 白底黑线+透明层+草稿层，一条命令）。
注意：生成式线稿的墨量指标在"纯线条稿"（无填黑区域）上会只有 2% 左右，属正常，
以肉眼完整性为准；深色服饰会被模型填黑（coloring-book 惯例），墨量 6%+。

**判据补充 2（2026-10-02 头像批）**：**高对比赛璐璐稿会生成"灰调铅笔素描"**。
墨绿银雾（纯黑短发 + 纯白脸）首轮线稿出来是石墨/铅笔质感：大面积灰调子、
线宽粗细分三级、边缘毛糙——因为 Canny 在这类硬边大色块上给出的是"填充面边界"，
NoobAI 把它理解成块面而非线条。
**解药（`gen_lineart2.py` 的 `simplify()`）**：先扁平化再做 Canny——
`cv2.pyrMeanShiftFiltering(im, 14, 32, maxLevel=3)` + `cv2.bilateralFilter(im, 9, 70, 9)`
把色块压成纯平面，边界退化成单像素台阶；产出后再加一道**去调子斜坡**
`ink = np.clip((ink - 0.30) / (0.68 - 0.30), 0, 1)` 砍掉淡灰底噪。
Canny 阈值回到 0.24/0.55、cn_strength 0.7。改完即得"白底黑线、粗细一致"。
（反向坑：浅色/低对比图别做 simplify，色块本来就不分明，压完线会断。）

**判据补充 4（2026-10-04，27-米画师样品批 gen_lineart3.py 定稿）：用户要「参考级连续闭合线」（填色书质感）时，NoobAI 全重画不行。**
全重画输出的线又细又淡又碎（1~2px、灰 150~230），阈值化边缘抖动→点→闭运算连成棋盘，后处理救不回来。
**正解 = LineartAnime（informative-drawings anime）直接从彩稿抽线**，连续性天然达标：
1. `controlnet_aux` 装进 ComfyUI 内嵌 python：`pip install controlnet-aux --no-deps`
   （cv2.pyd 被运行中的 ComfyUI 锁定，绝不能带 --deps；缺的纯 py 包 lazy-loader/imageio/scikit-image/timm 单独 --no-deps 补）。
2. 模型 netG.pth（217MB）经 hf-mirror 下载，`HF_HOME` 指到 E 盘。**坑：Windows 上 HF 建的快照是 0 字节断链**，
   报 EOFError unpickle 时把 blobs/<sha256> 复制成 snapshots/<rev>/netG.pth 真文件即可。
3. **库输出是黑底白线**（内部做过一次 255-），取回后要再反相回白底黑线。
4. 后处理定稿流程（在 detect_resolution=1536 原生分辨率处理，别在 1024 上动刀）：
   反相后**先 Gauss σ1.2 轻度平滑**（发梢/衣纹的锯齿碎笔连成顺滑长线，消掉「虚线感」）→
   反锐化 `g - 0.8*(g-Gauss(g,2))` 压深 → `cv2.erode(g,3x3)` 增粗 → 阈值 0.25 一网打尽 →
   close 3x3×2 桥接 → AREA 降采样回成图尺寸 → blur0.7×1.45 回羽化（线芯满墨、边缘 AA）。
   **中值滤波 / 密度剔除 / 开运算剔块全部会切碎发丝，禁用**；密集区（睫毛/辫子）黏连成浓黑可接受（参考图眼睛同浓）。
5. 墨量 18% 左右属正常（含密集发丝）。草稿层若已验收，脚本不要重写草稿 PNG。
6. **重组装验收铁律（27 批教训）**：build 完必须 ①核对 PSD 落盘 mtime（COM 组装可能静默失败，
   输出正常但没保存）；②**回读 PSD 图层原始像素与源 PNG 比对**——只验「全开=成品」验不到单层
   （成图置顶全不透明会遮住一切）。比像素时注意 PSD 图层按内容 bbox 裁切存储，须按
   `lay.offset` 贴回全画布再切源 PNG 对应区域，否则误报 MISMATCH。

**判据补充 3（2026-10-02 方形头像批，25-头像工作区 gen_lineart2.py v8）**：
- **结构描述（CLI 第 4 参）禁带颜色词**。"black dress / orange eyes / pink dress"
  会让模型输出彩色图或填黑块；只写形状（"frilled maid headdress / puffy short sleeves dress"）。
- **极淡线稿的提墨**：清透头像上模型常输出亮度 235~250 的淡线，
  R 通道拉伸 + 旧斜坡 0.38/0.72 会把眼睛一起杀掉（墨量仅 2.5%）。
  改：① 提墨用**亮度通道**（0.299R+0.587G+0.114B，对不听 monochrome 的淡彩输出稳）；
  ② 斜坡放宽 `np.clip((ink-0.15)/(0.50-0.15),0,1)**0.8`；
  ③ Canny 降到 0.14/0.40、cn_strength 0.92、monochrome/greyscale 加权 1.35/1.25。
- **两个失败特征对照**：输出是"彩色图"→ 描述词带色 / monochrome 权重不够；
  输出"结构对但线极淡"→ 别重跑模型，直接放宽离线提墨参数。
- 墨量健康区间（纯线稿）：4%~7%；低于 3% 先看是不是眼睛被杀掉了。

**判据补充 4（2026-10-04 头像二创批）：模型给深色帽子/蝴蝶结填"中灰调子"怎么办。**
深色服饰区域 NoobAI 有时不填黑、填成 flat 中灰（帽穹/蝴蝶结整片中灰，0.3~0.4 灰带 3%+），
单靠收紧斜坡（0.10/0.42 + gamma 0.55）只能压一部分。
**正解 = dual-threshold + 边界抗锯齿**：`solid = ink>=0.30` 全归黑、`<0.30` 归白，
只在 solid 的形态学边界带（`solid - erode(solid,3x3)`，2px）内用 `clip((ink-0.30)/0.25)` 做过渡。
灰调子全部变实黑（coloring-book 填黑惯例，符合参考里深色帽子），浅灰噪底同时清干净，
墨量从 11.4%（gamma 硬提）回落到健康的 5.8%，边缘仍是抗锯齿的。
另：若彩稿角色本来就是银白发，NEG 里的 `silver hair/white hair/platinum blonde` 防"洗白"词必须删掉，否则正负打架。

**判据补充 5（2026-10-04 米画师样品批）：模型把深色马甲/斗篷整块填"实黑"怎么办。**
这次不是中灰调子而是纯实黑大块（7%~11% 面积），调提示词
（`(outline drawing only:1.35) (pure white fills:1.25)` + NEG 加 `(solid black:1.4)`）只能减轻、消不掉。
**正解 = 后处理「填充→轮廓环」**：`filled = open(ink>0.5, 17x17椭圆)` 抓出填充块，
`ink = ink*(1-dilate(filled,3)) + gradient(filled,3x3)*0.95` ——
块内清白、只留 ~2px 轮廓环，填充变回线，墨量从 12% 回落到 1.8%~5.7%。
粗细一致性不受影响（真线都细于 17px 核，开运算抓不到）。

**PSD 图层顺序（2026-10-02 定稿，2026-10-13 修订「成图」规则）**：按**作画顺序自下而上**堆叠
草稿→线稿→固有色→阴影→二分→细化→背景→成图（面板自上而下 = 成图在最顶）。
不透明固有色若压在阴影/细化上面，全开就只剩平涂色块——用户确认要用作画堆叠。

> ⛔ **铁律：顶层「成图」绝不能是一张不透明整图**（2026-10-13 用户明令）。
> 用户原话：「成图这个图层，应该是下面的图层一个个演化来的，其他图层不管是隐藏了还是显示都不会在这个成图的图层上显示，这样并不符合个人手绘的流程」
> 正确做法 = **下层演化 + 顶层半透明补差修正**：
> ```python
> mid = compose(white, sbu)                 # 下层逐级叠加出的画面
> res = target - mid
> a   = np.clip(np.abs(res).max(axis=2) / 0.10, 0, 1)   # 残差≥0.10 处完全接管
> C   = np.clip(mid + res / np.maximum(a, 1e-4)[..., None], 0, 1)
> save_rgba(C, a, "成图-修正.png")           # NORMAL / 不透明度 100%
> ```
> 验收：平均 alpha ≈ 0.3、约 1/3 像素近乎全透明（说明下层在主导画面）；
> 纯下层演化差 3~4%，含修正层 ≤0.2%（逐像素=成图）。关掉任何下层画面必须真的变。
> 逐层验收脚本藏「成图-修正」+「背景-原色」再逐层开关，否则误报"无效"。

历史失败记录（别再走）：
1. **NoobAI img2img 重画成线稿** —— denoise 0.60 保色出平涂；0.84 线条碎裂；0.93 崩黑块。
2. ~~手搓 ControlNet 线稿管线~~（已被上面正解取代）

### 2.3 分层不能用「往上叠效果」
叠加会让画面越来越亮、越来越糊。必须**从成品图反演**（见 4）。

### 2.4 OpenCV 在 Windows 上不支持非 ASCII 路径
`cv2.imwrite("中文名.png")` 会静默失败或写出乱码文件名 → **一律用 PIL 读写**，
cv2 只处理 numpy 数组。

**（2026-10-02 补充）`cv2.imread` 同样会栽**：路径含中文时**返回 `None` 而不抛异常**，
下一行 `normalize` 就炸成 `error: (-215:Assertion failed) !ssize.empty()`——
报错指向 normalize，真因却在读图。必须走字节流：
`cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)`。
写回同理 `cv2.imencode(".png", arr)[1].tofile(p)`。

### 2.5 PS COM
连接走晚绑定 + 探活放进重试循环（见 `photoshop-com-automation` 技能第十三章）。
组装相关：
- `DocumentFill.TRANSPARENT` 会留下一个空图层「图层 1」，要删；
  但这版 PS 的 `Layer` **没有 `delete` 方法**（且 `delete` 是 JS 保留字）→ 用
  `ActionReference(charIDToTypeID("Lyr "), id)` + `executeAction(charIDToTypeID("Dlt "), …)`
- `move(set, INSIDE)` 恒落在**组顶** → 层必须**逆序**移入
- 组重排：逆序 `move(doc, ElementPlacement.PLACEATBEGINNING)` 得到目标自上而下顺序
- 隐藏只能按名字找，`layers[0]` 是**最上面**那层
- **PS 一直报「应用程序正在使用中」(-2147417846)**：说明有模态对话框或上次脚本卡住，
  重试多少次都不会好。用户 2026-09-29 授权 → **直接自己重启 PS**（`assets/restart_ps.py`：
  `taskkill /F /IM Photoshop.exe` → 拉起 → 轮询 COM 直到 `DoJavaScript("1+1")` 成功，约 5s 就绪）。
  PS 安装路径可在注册表 `HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe` 里查。
  另外 `build_psd.py` 务必加 `--no-open`：同时开 6 个大文档会直接把 PS 拖死。

### 2.6 ⚠️ 空桶色块层会让 PS 置入**静默失败**（2026-10-01 新坑）
两极配色的图（如"深裙+亮发肤"）中间亮度桶一个簇都落不进去 → 模板把 alpha 全 0 的
PNG 也写盘了。PS `Plc` 动作置入全透明 PNG **不报错、不建层**，`activeLayer` 还是上一层
→ 上一层被反复改名/move，最终组内层数与预期不符（症状：build 日志层数对、dump 里层少）。
**修复**：`color_blocks` 返回前剔除 mask<1000px 的空桶（不写文件），build_psd 靠 glob
自然跳过。组装后必须核对 dump 树里 ⑥上色 的层数与目录文件数一致。

### 2.7 ⚠️ layers_20 系模板的**双重衰减** bug（21-gothic-trio 及更早全部中招）
模板里效果层 `a = soften(m)*coef`（alpha 预乘系数），build_psd 的 OPACITY 又设 coef×100
→ PSD 实际强度 = coef²：阴影-轻 0.16（设计 0.40）、整体-暖调 0.022（设计 0.15，几乎不可见）。
反演 inv 按单层 alpha 算颜色，所以"成稿"自洽但比原图平，"过程显著"被压扁。
**修复（22 工程 layers_22.py 为准）**：alpha **满值落盘**（不预乘），inv 反演用
`a_raw*coef`，强度只由 PSD 层不透明度承担 → 全开≈原图（验收 0.7~1.3%）且每层强度到位。
render_final/make_preview 的 compose 里保持 `a*coef` 与 PSD 一致。再复制旧模板时务必带这个修复。

### 2.8 皮肤判定：高亮平涂立绘的肤色极淡 + 金色装饰干扰
- 高亮平涂图的肤色 R-B 只有 0.02~0.06（接近纯白），旧阈值 0.025 直接漏检；
  金色装饰 R-B 高达 0.7 会被误当皮肤。
- **新条件**（layers_22 验证）：`(R-B>0.012) & (G-B>0.004) & (V>0.55) & (sat<0.35)`，
  sat 上限排金色（0.7）保红发肤色（0.3）；裸露皮肤少而碎时（小脸/脖子/单臂）
  连通域二档放宽（area 260→120，have_skin 2000→800）。
- 粉发靠 `G-B>0.004` 排除（粉发 G<B）；仍失败就接受并入亮白桶（小面积皮肤不影响主流程）。

## 2.9 浅色立绘 txt2img 经验（银白科技 3 次返工换来）
- **浅色/白色系服装必须给深色锚点**（`deep indigo trousers`、`dark burgundy and gold`），
  否则整套浅色词（silver-white/pale/white/pastel）会让模型漂成单色草图：
  实测 荧光青色块 → 青灰网点 → 蓝色线稿 三连崩。锚点色绑到具体衣物上
  （"mint-green jacket, deep indigo trousers" 比 "mint and indigo outfit" 稳）。
- `glowing`、`cyan streamers` 这类词会把整张图染成荧光单色，负面压不住，正面别写。
- `amber eyes` + `earth-toned` 会把肤色拉成亮黄 → 正面加 `fair skin, natural skin tone`，
  负面加 `yellow skin, orange skin`。
- **白底立绘的 NEG 必须去掉 `bright background`**（它会把白底压暗），
  换成 `dark background, colored background, gradient background, complex background`。

## 2.10 繁密背景场景插画（2026-10-01 生日插画批，23-立绘-生日插画）

**这一批和"白底立绘"是两套完全不同的取向，别把那批的参数直接搬过来。**

### 出图：情绪词 + glowing/translucent = 暗蓝发光幽灵
人物带 `sorrowful / melancholic / pity / fragile / forlorn` + `glowing particles /
translucent / transparent watercolor / dim cool-warm light` 时，NoobAI 必崩成
**暗蓝/青绿单色发光幽灵**（三条全中，背景花海全丢）。
反向把暖色词堆满又会崩成**奶油白一片、人物白到看不见**。
正解：**给背景一个中调暖色锚点**（比人物深）——`muted olive and warm tan background` /
`warm dark brown hazy backdrop` / `deep mauve and dusty teal background`，
NEG 同时压 `dark blue, navy blue, cyan lighting, glowing, ghost, transparent body` +
`white background, washed out, low contrast, faded colors`。两步锁死才有对比。
另外 `bloom / glare / light rays` 进 NEG，能消掉头后那类黄色光晕伪影。

### 分层：背景层必须"去人物"，且羽化带要留原图
白底立绘批 `背景-原色 = 整张原图` 没问题（反正背景是白的）；场景插画这么干，
**关掉⑥上色组还能看见人物**，过程阶梯演示不出来。
做法（`23-立绘-生日插画/layers_23.py`）：
1. `背景-原色 = np.where(cov >= 0.995, 补出来的背景, 原图)`。
   **`cov < 0.995` 的羽化带必须留原图像素**——解析反演的基准 t 就是"原图+色块"，
   基准不一致，"全开=成品"立刻破功。
2. 补背景**别用 `cv2.inpaint(TELEA)`**：掩膜占 35%~42% 时会留下旋涡状涂抹
   （紫灰祭礼的紫色漩涡、桃银神谕的深青团块），①背景那格很难看。
   改**行向线性插值**（`inpaint_bg()`：逐行在左右已知像素间 `np.interp`，
   全遮行退回上一行，再只在填充区内做 σ7 轻模糊）——这类图背景本就是横向色带，
   插出来就是连续色带。20 行代码，1 秒跑完。

### 分层：两个"判定退化"的坑
- **皮肤判定**：暖光场景图里奶白长袍的 R-B 同样过阈 → 整件袍子被吞进`底色-皮肤`
  （紫灰祭礼 297k px），色块只剩 2~3 个。纯色阈在这类图上无解。
  改 **`face_skin()`：人物包围盒上部 22% 中央区找最大暖色团当脸 → 取该团颜色中位
  → 只保留「色差<0.13 + 与脸连通 + 距脸<0.16 人物高」的像素**，
  皮肤严格落在头颈（13k~22k px）。
- **亮度分桶**：绝对阈值（0.72/0.58/0.45…）在整体偏亮的图上会把 80% 像素塞进
  「亮白」单桶（桃银神谕 390k px 一桶）。改**按簇亮度排名分桶**：
  kmeans 中心按亮度降序 → 依次命名 亮白→极暗（K=9）。
  好处：每张图都拿到 6~8 个可辨色块，且排序天然等于 PSD 内自下而上的 极暗→亮白。
  注：`medianBlur(31)×2` 会抹掉细簇，色块数最终由画面本身决定（15~20 层属正常）。

## 2.11 特写 / 头像规格（1024×1280，2026-10-02 头像批）

**层数基准（别为凑"20 层"返工）**：交付目录里已验收的 PSD 实测内容层为
**21 / 18 / 15**（烟绿祭司 / 红发波西米亚 / 银白科技），本批 20 / 19 / 17。
层数由原图色块数量决定，浮动是正常的；用户说"约 20 个"指的是**结构**（7 组：
线稿/草稿/高光/阴影/调色/上色/背景），不是精确计数。**硬凑档位只会造出无效层，
`verify_psd.py` 会直接报"无效!"**。

从立绘（1024×1536）切到头像（1024×1280）只需：画布尺寸常量 + `build_psd.py` 的
`OUT_DIR`，**其余参数要动的是"脸部锚定"**——头像里人物占比大、脸的位置更靠上：

```python
# layers_23.py  color_blocks 内
if (P > 0).mean() > 0.50:          # 特写/头像（人物占画面过半）
    f0, f1, g0, g1 = 0.06, 0.42, 0.25, 0.75
else:                               # 立绘/半身
    f0, f1, g0, g1 = 0.00, 0.22, 0.20, 0.80
```

另外两条本批踩到的：
- **皮肤层抓到头发**：粉发/银发的 `R-B` 与肤色同量级，会整片被吞。除 2.8 的
  `G-B>0.004` 外，再加宽松的暖色判据 `(R-B>0.012) & (R-G>-0.03) & (V>0.50) & (sat<0.45)`
  并**限制在脸部锚定区内**，皮肤就老实落在 y 26%~51% 的脸部，不再跑到头顶。
- **`make_preview23.py` 的标题文案是硬编码的**（"立绘_%s"），换批次记得改成"头像_%s"，
  否则预览图标题张冠李戴。

**出图参数（本批定稿）**：1024×1280，euler_ancestral，26~30 步，cfg 5.5~7。
墨绿这类"深发 + 白脸"的高对比配色，容易被模型画成**枯树林 / 面罩阴影 / 平涂硬边**——
正面改写成"干净银灰渐变"，NEG 加 `dark shading on face, mask, heavy eyeshadow`，
换种子（281 号）即解。橘棕暖光背景过橙 → 事后 `post_tune.py` 降饱和，不必重出。

## 2.12 清透风（高明度低饱和）：用户说"颜色太脏"时怎么改（2026-10-02）

**先量化，别凭感觉。** 用户给参考图说"要这种清透的"时，先量参考图的统计量
（脚本见 `25-头像-伪厚涂/参考/analyze_ref.py` + `compare_palette.py`）：

```
主体区（避开四角）统计： 饱和度S中位 / 明度V中位 / 浓色占比（S>0.35 的像素比例）
参考图实测：            S 0.116~0.129 | V 0.737~0.749 | 浓色占比 19.7%
被否掉的"脏"版实测：      S 0.115~0.348 | V 0.37~0.99   | 浓色占比 40~50%  ← 浓色铺满全画面
```

**结论：清透 ≠ 把颜色调淡，而是「浓色从满铺退成点缀」。**
配方 = 大面积低饱和高明度 + 小面积高饱和点缀 + 大面积留白。
目标：浓色占比压到 20% 以下，S 中位 ≈ 0.10~0.13。

（反例：墨绿银雾的 S 中位只有 0.115 看着"不艳"，但浓色占比 47.5% ——
深绿整片铺满，仍然重。**只看 S 中位会被骗，必须看浓色占比。**）

### 提示词：删掉"厚涂油感"三件套，补上低饱和
```
删：pseudo-impasto / painterly brushwork / atmospheric / heavy shading
加：low saturation / pale muted colors / soft pastel tones / soft delicate shading /
    flat clean colors / lots of white negative space / mostly white background with faint color wash
NEG 加：muddy colors, dirty colors, grimy, murky, heavy shading, thick paint, overpainting,
        over-rendered, excessive details, cluttered, oily skin, shiny skin,
        deep shadows, harsh shadows, dark tones
```
"参考图的视觉语法"也值得照搬：白蕾丝帽 + 缎带蝴蝶结 + 白蕾丝暗纹 + 稀疏半透明小蝴蝶。

### ⚠️ 发色会被"洗成银白"的四个陷阱（本批实测全部踩中）
1. **`ash` 开头 = 灰烬色**：`ash blue grey hair` 出的是银白发，不是灰蓝发。
2. **`grey hair` 放进 NEG 是自杀**：参考图的头发本来就该是灰调，压掉它 →
   灰调头发整片变白（藕荷张实测）。NEG 里只留 `silver hair / white hair / platinum blonde`。
3. **无色相的通用词会洗掉色相**：`light colored hair`、`bright soft hair color`
   这类写进 TAIL（三条共用）会让三张的头发全变银白。
4. **`pale X grey` 叠太多也发白**：`pale` × 2~3 次 + `high key lighting:1.35` + 大面积留白，
   合起来就是"白"。
→ **正解：发色只能用具体色名**（`light periwinkle blue` / `light mint green` /
`soft lavender` / `light mauve`），且 `high key lighting` 别超过 1.2。
`violet`/`purple`/`pink` 裸词一给就出高饱和 → 对应 NEG 补 `vivid purple hair, vivid pink hair`。

### 层强度必须同步减弱（否则分层这一步就把清透稿重新压脏）
| 层 | 厚涂版 | 清透版 |
|---|---|---|
| 阴影-轻 / 重 / 细节 | 0.40 / 0.75 / 0.22 | **0.28 / 0.50 / 0.15** |
| 高光-整体 / 强 / 细节 | 0.75 / 0.95 / 0.50 | **0.48 / 0.60 / 0.32** |
| 整体-暖调 / 冷调 | 0.15 / 0.12 | **0.10 / 0.09** |

改这四个数必须**四处同步**：`layers_23.py` COEF / `build_psd.py` OPACITY /
`make_preview23.py` EFFECTS / `render_final.py` compose。
清透稿的还原误差会升到 1.6~2.9%（色差小、色块量化误差大），**这是正常的**。

### 线稿：清透稿是个两难，别在这上面耗太久
清透稿的头发浅（≈#C8C8D0）与白底（#FFF）只差 ~55 级灰度 → **Canny 抓不到发型轮廓** →
生成式线稿会按模型的"长发蕾丝少女"先验自行发挥（bob 短发被画成披肩长发）。
试过的六种方案，结论是**结构准的必然碎线、线条干净的必然改发型**：

| 方案 | 结构 | 线条 |
|---|---|---|
| 生成式 CN 0.7 / 0.88 | ✗ 发型被改写 | **✓ 连续、粗细一致** |
| + 剪影轮廓叠加进引导图 | ✗ 仍被改写 | ✓ |
| + 浅色区对比拉伸 [170,255]→[0,255] | ✗ 仍被改写 | ✓ |
| Canny 像素抽取（lineart_canny） | ✓ 完全贴合 | ✗ 蕾丝/发丝全成碎线 |
| 暗度阈值 + 骨架化等宽 | ✓ 贴合 | ✗ 断续、放宽阈值后成网 |

**建议直接取生成式**（用户的线稿标准是"连续平滑无短线、粗细一致"，线条质量权重更高），
并在 `postprocess` 把去调子斜坡收紧到 `(ink-0.38)/(0.72-0.38)` 以清掉灰调子。
如果想根治，得改用 lineart 类型的 ControlNet（而非 canny）+ 低 denoise img2img，
成本高，除非用户明确要求线稿必须与原图一致。

### 2.13 全场景批 + 「线稿上部分渲染」过程感（2026-10-04 秋日站台续 26 批定稿）

用户要求：七组顺序（草稿→线稿→固有色平涂→二分→阴影→细化→成图）不变，但上色层必须
**在线稿上部分渲染、逐步推进**，不能一次性满铺（参考他给的"上色预览"半成品图）。
工程脚本见 `assets/layers_template.py`，要点：

1. **全场景无遮罩分桶**：kmeans K=8 直接对全画面（pyrMeanShift 9/26 + medianBlur31×2），
   按簇亮度排名命名，无人物遮罩/皮肤层。
2. **部分渲染的实现（别用纯 erode/min_area 自适应——08 实测 erode 会涨到 18px 把色块磨糊）**：
   种子 = 局部对比度 |L−blur(L,9)| 的 p74 以上区域（细节丰富的主体），
   `F = blur(distanceTransform(~seed), 25)`，平涂掩膜 = 桶 ∩ {F ≤ quantile(F, 0.52)}
   再 largest_components(≥2200) + erode 9/dilate 5 轻收边。覆盖率稳定 42~50%，
   且天然"从主体向外画"，比人工阈值好看得多。
3. **「补全-平涂」层**（放细化组底）：颜色 = 全画面桶色合成，alpha = 1−平涂覆盖。
   细化阶段把剩余白纸补齐，过程阶梯 ③平涂(半铺)→⑥细化(补全+高光) 才完整。
4. 效果层（二分/阴影/高光）蒙版一律 ∩ 已平涂区（画家不在白纸上单提阴影）；
   整体-暖调/冷调是全幅 SOFT_LIGHT（放补全之上）。
5. 因有「补全」层，效果层颜色反解的基准 t 用**平涂阶段底**即可，不必精确；
   顶层放半透明「成图-修正」补差层（勿用不透明整图，见 2.2 铁律），全开=成品成立（verify mean ≤0.2%）。
6. 每层强度沿用清透版：二分 0.50 / 轻 0.28 / 细节 0.15 / 高光 0.48、0.60 / 暖冷 0.10、0.09。
7. 交付后若对成品做二次修正（去水印残影等），**必须把新成品拷回成图源（target）后
   重跑 `layers_*.py` + `build_psd*`**——补差修正层是由 target 反算的，只换成品不重算会在顶层留下旧残差。

## 3. 三个派生素材

### 3.1 线稿三层（**v2 定稿版**，替换旧的墨线抽取）

> ⚠️ **旧的「中值滤波基线做差」抽墨线不要再用了。**
> 它抽出的线宽中位只有 **1px**、alpha 中位 0.3~0.5（灰线），
> 用户原话：「这些线稿根本不明显，达不到要求」。
> 保持下面这套 Canny 管线，不要再退回去。

```python
# 1) 轻滤波（保细节，不要下重手：bilateral 半径别超过 sc=34、median 只用 3）
f = bilateral(rgb, 9, 34, 9) ×2 → medianBlur(3) → 灰度
# 2) 双阈值 Canny：主体区细、背景区粗（背景枝叶不喧宾夺主）
ec = Canny(灰度, 32, 88)      # 主体：五官/衣褶/背包带
eb = Canny(灰度, 72, 170)     # 背景：只留树、墙、栏杆这类大结构
m  = where(charmask>0.5, ec, eb)
# 3) 接断口 → 骨架 → 剪碎段 → 拉直
m = close(m, 椭圆 5×5)
sk = skeletonize(m)                  # Zhang-Suen，numpy 向量化
sk = prune_skeleton(sk, minlen=30)   # 按**骨架连通域长度**剪枝（剪肥掩膜会误删细节）
sk = straighten(sk)                  # 加粗 3px → 模糊 1.1 → 阈值 0.5 → 再骨架化
sk = prune_skeleton(sk, minlen=30)
# 4) **统一线宽**（用户定稿语义：粗细一致，不分粗细级）
hi = sk & (mag_s >= P65);  md = sk & (mag_s >= P35) & ~hi;  lo = 其余
#   mag_s = 梯度沿骨架 31px 邻域最大值传播（档位沿空间连续，一条线不宽窄突变）
P1 = dilate(hi, r)              # 主轮廓  —— 全部 2r+1 px
P2 = dilate(hi|md, r)           # 加细节  —— 全部 2r+1 px
P3 = dilate(hi|md|lo, r)        # 完整线  —— 全部 2r+1 px，单开 = 完整线稿
#   r=1 → 实测线宽中位 2.0px，与参考手绘线稿（green_lineart 中位 2.0）一致
```

**平滑版渲染（2026-09-29 定稿，优先用这个）**：`assets/smooth_line.py` 的 `split3_smooth(sk, mag, W, H)`。
上面的 dilate 版放大看是像素锯齿（用户：「像这种平滑度的线稿你还是没办法做吗」），
平滑版链路：**骨架→8 邻接图走路径→approxPolyDP(1.4) 去抖→滑动平均×2→Chaikin 角切割×3
→4x 超采样 cv2.polylines(LINE_AA)+圆头端点→INTER_AREA 缩回**。
- 线宽 WIDTH=2.5（实测中位 2.0px，与参考/旧版一致）；输出已是抗锯齿 alpha，**不要再过 aa()**
- 三层语义不变（按 tier 游程切分路径，短游程(<6px)并入前段，段间共享 1px 保证连续）
- 闭合环（无锚点的度2像素链）单独走路径，closed=True 传给 polylines
- 平滑强度三档横评（q2 大正脸）：mavg=2/eps=1.4 最优；mavg=3/eps=1.8 开始丢细节
- 纯 numpy/cv2，不需要 scipy/skan

**踩过的坑（会直接毁掉输出）**
- **对 1px 骨架直接 `GaussianBlur(0.8)` 再阈值 0.42 → 斜向单像素线中心值只有 ~0.40，
  整条被删掉，线稿碎成虚线。** 必须走「加粗 → 模糊 → 阈值 → **再骨架化**」。
- 滤波太狠（bilateral sc≥50 + median 5）+ 剪枝太狠（open 2px / minpx 200）→
  骨架只剩 5k px（正常应 40k+），画面几乎空白。
- 只用 DoG 不用 Canny：DoG 在柔和边缘给出**宽带响应**，骨架化后被切成小段，
  最大连通段只占 18%，观感是"虚线"。Canny 的迟滞连接天生给连通边链，最大段能到 50~80%。

**参数体检口径**（每次改完都先跑一遍再往 PSD 里塞）
| 指标 | 合格区间 |
|---|---|
| 墨线覆盖率（alpha>0.45） | 4% ~ 16% |
| 三层线宽 p25/中位/p90 | 三层相同，中位 ≈ 2.0px（与参考图一致） |
| 最大连通段占比 | ≥ 45% |
| 三层关系 | **递进包含 P1⊂P2⊂P3**（单开任一层都完整可读） |
| 白底图 alpha 中位 | ≥ 0.9（旧版只有 0.3~0.5，就是"不明显"的根因） |

**PSD 里的不透明度必须是 100%**：旧版给 0.84/0.66/0.46 是配"细灰线"的，
换成纯黑统一线宽后必须满不透明。线稿层默认隐藏（是工作层），
但 `make_preview.compose()` 必须**显式排除 ①线稿 组**，否则「全开（=成品）」
那一行会被线稿盖住、和成品对不上（旧版 `HIDDEN()` 恒返回空集合，等于没排除）。

### 3.2 人物遮罩
~~本地无 rembg~~（2026-09-29 已装：`pip install rembg onnxruntime`，模型 isnet-anime.onnx 168MB
在 `~/.u2net/`，GitHub 被代理挡时走 `https://gh-proxy.com/https://github.com/...` 镜像下载）。
**云端 matting 有个坑**：深色服装 + 深蓝复杂背景的动漫图会失效（人物区虚高到 90%+，掩膜几乎全白）。
判据：alpha>0.4 占比 >80% 即可疑 → 换 `rembg new_session('isnet-anime')` 本地抠，效果好得多。
云端 matting 仍适用于纯色/浅色背景。拿到 alpha 后：`>0.45` 二值化 → 最大连通域 + 质心校验
→ floodFill 补洞 → 闭运算 9×9 → 高斯羽化 2.2。

**繁密服饰图（蕾丝/花纹遍布）的两个特殊处理**：
- 分层语义：解剖命名（头发/服饰）不可靠——mean-shift 会把皮肤也压成蓝灰。
  改「皮肤优先（R-B>0.025 & V>0.55 暖色种子+脸部位置）+ 色调四分（白银/灰蓝/深蓝/墨色，按簇亮度分桶）」。
- 线稿密度：正常参数线稿会密成蛛网。定稿：bilateral×2(σ40) + Gaussian σ2.0 预模糊融掉
  蕾丝纹理 → Canny 主体 55/125 背景 85/185 → 骨架 prune 60 → 只取 P2（强+中档）。
  实测墨量 5.35%（正常图 8~14%），密度与可读性平衡。

### 3.3 阴影 / 高光 / 边缘光（从亮度派生）
```python
base = cv2.blur(L, 71)                       # 局部受光基准
rel  = clip((base - L)/max(base,0.14), 0, 1)
absd = clip((0.56 - L)/0.56, 0, 1)
sh = clip(max(rel*1.9 - 0.04, absd*0.70), 0, 1) |> blur7 |> ×M
hl = clip((L-0.58)/0.42, 0, 1)**1.25 * clip(0.45+0.75*clip((L-blur(L,41))/0.09,0,1), 0, 1.2) |> blur3.4 |> ×M
rim = (M - erode(M, 23×23)) |> blur3.2 × clip((blur(bgL,18)-0.38)/0.34, 0, 1) × M
```
**然后做分位数归一**（`rescale_mask`：主体内 p97 → 0.94 等）。
不归一的话蒙版 mean 只有 0.03，关掉这层根本看不出变化。

## 4. 核心：解析反演（让"全开 == 成品"）

PS 混色公式（`e` = 图层 alpha × 不透明度，`b` = 底色，`C` = 图层色）：
| 模式 | 正向 | 反解 b |
|---|---|---|
| MULTIPLY | `t = b(1-e) + b·C·e` | `b = t/(1-e+C·e)` |
| SCREEN | `t = b(1-eC) + eC` | `b = (t-eC)/(1-eC)` |
| SOFT_LIGHT | `t = b(1-e) + SL(b,C)·e` | 对 b 单调 → 二分 26 次 |
| NORMAL | `t = b(1-e) + L·e` | `L = (t - b·(1-M))/M` |

**做法**：从成品 `T` 出发，按面板**自顶向下**逐层求逆，
最后得到 `背景-原色` 需要的等效结果；再把人物区域用 inpaint 抹平（被上层盖住，看不见）。

两个关键推论：
1. **反演对任意 alpha 都成立** → 蒙版可以随便加强/归一，还原精度不受影响，
   只会让"基础色层"离成品更远、效果层更有存在感。
2. 组必须设 **PASS_THROUGH**，子层的混色模式才能穿透到组下方图层。

顺序（自顶向下）：整体-暖调柔光 → 整体-提亮 → 人物-边缘光 → 人物-高光 → 人物-阴影
→ （人物-完整色 vs 背景）→ 背景-柔光罩 → 背景-光斑 → 背景-原色。

## 5. 验收（必做）

```python
# a) 回读 PSD：psd_tools 能正常读 PS 写的 PSD，直接比合成图
psd = PSDImage.open(psd_path)
d = |np.asarray(psd.composite()) - np.asarray(成品)|  # mean 应 < 2%
cnt = 非组图层数                                      # 应等于预期层数

# b) 逐层影响：关掉每层算 mean Δ，全部必须 > 0
```
实测可达 **mean 0.3%~1.8%**。若明显偏大，检查是否漏了 PASS_THROUGH 或某层 opacity 不一致。

## 6. 脚本（assets/）

| 文件 | 作用 |
|---|---|
| `lineart_canny.py` | **线稿三层生成器（自包含）**：双阈值 Canny + 骨架 + 统一线宽（2px，递进完整） |
| `smooth_line.py` | **平滑线稿渲染（定稿）**：骨架→矢量路径→Chaikin 平滑→超采样 AA，`split3_smooth()` 与 split3 同参 |
| `comfy.py` | ComfyUI API 客户端（NoobAI vpred / Z-Image / 线稿 img2img / ControlNet 上色） |
| `layers_template.py` | **核心**：蒙版派生、解析反演、13 层落盘、自检 |
| `build_psd_template.py` | PS COM 组装分层 PSD（组结构、混色、隐藏、空层删除） |
| `make_preview_template.py` | 分层预览图 + 关层对比图 |
| `dewatermark.py` | 去云端出图右下角半透明水印（inpaint 打底 + 镜像补丁羽化融合） |

用时把 `*_template.py` 复制进工程改 `themes.json` 与路径即可；
线稿直接 `python lineart_canny.py 成品.png 图层/t1 --charmask 图层/t1/_alpha.png --white 线稿/t1_线稿_白底.png`。

## 7. 交付

成品放 `OUT_DIR`（默认 `./out`，可用同名环境变量覆盖），命名 `<主体>_<编号><主题>_分层.psd`，
配套同前缀的 `_成品.jpg` / `_分层预览.png` / `_关层对比.png` / `_线稿_白底.png`，
备选稿放 `<主体>_备选\`。中间图层写 `WORK_DIR/layers/`，不要落在系统盘临时目录。

**判据补充 6（2026-10-07 四季头像批 gen_lineart30.py）：珠光排线风的两个新坑。**
1. **LineartAnime@1536 会在密集排线风上糊块+丢虹膜**：刘海/卷发的排线黏成黑块（墨量 24%+），
   亮色大虹膜（绿/琥珀/冰蓝）被整只丢掉（informative-drawings 先验）。**detect_resolution 提到 2048**
   输出立即干净（raw 墨量 9%），后处理改为轻平滑 σ0.8 + 温和反锐化 0.6，不再 erode。
2. **自动虹膜检测不可靠**：虹膜常与刘海暗带连通成一片（sat 仅 0.11、V 阈难卡）。
   正解 = **脸部中央带整带 Canny 补细节**：人物 bbox y 24%~46%、x 30%~70%，
   `Canny(50,130) × 暗掩膜(L<0.62, dilate 9×9)` 后与 LA 线取 max——虹膜/睫毛/唇线补回，
   与 LA 已有线重叠无害，带边在刘海里的轻微加密可接受。
3. **psd_tools 读取 PS 置入层的坑**：`layer.composite()` 对这批层返回全白空图（alpha=0），
   **必须用 `layer.topil()`**（按 offset 贴回全画布再比）。
4. **单层像素校验必须「alpha + 预乘 RGB」**：源 PNG 是全画布色值+alpha 掩膜，
   PS 置入后按内容 bbox 裁切、透明区 RGB 被清白——直接比 RGB 全误报。

**判据补充 7（2026-10-07 去水印幽灵肢体事故）：**
去水印用「镜像补丁」前，**必须先检查镜像源区内容**：右下角有手/肢体/物体时，
从左侧取源镜像会把这些元素复制成「幽灵肢体」（09盛夏案例：左手指尖被镜像到右下角叠在篮子上）。
源区需满足：与目标区内容同构（纯背景/连续纹理），且用皮肤掩膜量化检查污染占比 <3%。
修复此类角落的稳妥套路（fix_corner09_v2.py）：同行纹理复制（带行对齐）+ 背景按行线性外推（锚定边界行均值）
+ 高斯纸纹颗粒 + 边缘暗描线（小幅波动模拟手绘）+ 需保留物体的**几何掩膜**（连通域/颜色掩膜会被
多次迭代烤进画面的雾带骗过，几何实测轮廓才稳）。绘制顺序：纹理→背景→晕影→物体回贴→描线。
另：miora_edit_image 整图重绘不适合此类局部修复——改动范围失控（会删掉真实内容、恢复水印）。

**交付口径（2026-10-07 用户定稿）：** 插画分层任务只交付「成品 PSD + 成果预览图」，
线稿白底、演变过程图、关层对比图一律不再放交付目录。

**判据补充 8（2026-10-07 竖版/缩略图批）：**
1. **竖版图（高>宽）2048 检测会爆内存**（2048×3072 中间数组 ~13GB）。正解 = 方形白底填充到
   max 边再检测、输出裁回原区，每轴分辨率不缩水。
2. **全身构图脸位偏高**（脸中心 ~人物 bbox y18-25%），默认细节带(24-46%)够不着眼睛。
   带整片上移放宽会带进大量发丝 Canny 噪声（脸糊成草图）。正解 = **手动虹膜模式**
   `iris=cx,cy,rx,ry;...`：眼框网格放大实测坐标，跳过 Canny，直接画椭圆环+瞳孔+高光缺口。
   蓝色优势掩膜自动定位不可行——银蓝/浅蓝发丝的 B-R 与虹膜同量级。
3. 用户要求「线稿不能太厚」：末段增益 1.25、core 阈 0.32（默认 1.55/0.28 偏厚重）。
4. 微信缩略图（256px 级）先 Lanczos 4x + 反锐化(σ1.2, 0.35) 再进管线，线稿检测 2048 仍可。
