# -*- coding: utf-8 -*-
"""阶段 F · 用 Photoshop 把 13 个 PNG 组装成分层 PSD

面板结构（自上而下）：
  [组] ①线稿        线稿-轮廓粗线 / 线稿-中间线 / 线稿-细节细线   （默认隐藏）
  [组] ②整体调色    整体-暖调柔光 / 整体-提亮
  [组] ③细化        人物-边缘光 / 人物-高光
  [组] ④二分        人物-阴影
  [组] ⑤分区上色    人物-完整色
  [组] ⑥背景        背景-柔光罩 / 背景-光斑 / 背景-虚化（隐藏） / 背景-原色

6 组 + 13 层 = 19 个图层。混色模式/不透明度直接取自 layers.py，避免两处不一致。

⚠️ move(set, INSIDE) 恒落在组顶 → 层必须**逆序**移入；隐藏某层只能按名字找，不能按下标。
"""
import os, sys, json, time
import pythoncom

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import layers as LY            # 你的工程里：把 layers_template.py 复制成 layers.py 再改配色
except ImportError:
    import layers_template as LY   # 直接跑模板时回落

HERE = os.path.dirname(os.path.abspath(__file__))
LAY = os.path.join(HERE, "图层")
OUT_DIR = os.environ.get("OUT_DIR") or os.path.join(os.getcwd(), "out")
SERIES = os.environ.get("SERIES") or "分层插画"   # 文件名前缀，按你的系列改
W, H = LY.W, LY.H

PS_BLEND = {"NORMAL": "NORMAL", "SCREEN": "SCREEN", "MULTIPLY": "MULTIPLY", "SOFT_LIGHT": "SOFTLIGHT"}
GROUPS = [(g, [n for gg, n, _, _ in LY.LAYERS if gg == g]) for g in LY.GROUP_ORDER]
BLEND = {n: PS_BLEND[m] for _, n, m, _ in LY.LAYERS}
OPACITY = {n: int(round(o * 100)) for _, n, _, o in LY.LAYERS}
HIDE_GROUP = [g for g in LY.HIDDEN_BY_DEFAULT if g in LY.GROUP_ORDER]
HIDE_LAYER = [n for n in LY.HIDDEN_BY_DEFAULT if n not in LY.GROUP_ORDER]

JS_HEAD = r"""
app.displayDialogs = DialogModes.NO;
function placeFile(p, nm){
  var idPlc = charIDToTypeID("Plc ");
  var d = new ActionDescriptor();
  d.putPath(charIDToTypeID("null"), new File(p));
  d.putEnumerated(charIDToTypeID("FrPl"), charIDToTypeID("Plc "), charIDToTypeID("Plc "));
  executeAction(idPlc, d, DialogModes.NO);
  var l = app.activeDocument.activeLayer;
  if (l.typename !== "ArtLayer") throw new Error("置入未得到像素图层: " + nm);
  l.name = nm;
  l.rasterize(RasterizeType.ENTIRELAYER);
  l.move(app.activeDocument, ElementPlacement.PLACEATBEGINNING);
  return l;
}
function findSet(doc, nm){
  for (var i = 0; i < doc.layerSets.length; i++)
    if (doc.layerSets[i].name === nm) return doc.layerSets[i];
  return null;
}
function findLayer(ls, nm){
  for (var i = 0; i < ls.length; i++){
    if (ls[i].typename === "LayerSet"){ var r = findLayer(ls[i].layers, nm); if (r) return r; }
    else if (ls[i].name === nm) return ls[i];
  }
  return null;
}
function delLayer(l){
  var ref = new ActionReference();
  ref.putIdentifier(charIDToTypeID("Lyr "), l.id);
  var d = new ActionDescriptor();
  d.putReference(charIDToTypeID("null"), ref);
  executeAction(charIDToTypeID("Dlt "), d, DialogModes.NO);
}
function dump(ls, dep, out){
  for (var i = 0; i < ls.length; i++){
    var l = ls[i], pad = "";
    for (var k = 0; k < dep; k++) pad += "    ";
    if (l.typename === "LayerSet"){ out.push(pad + "[组] " + l.name + "   [" + (l.visible?"可见":"隐藏") + "]"); dump(l.layers, dep + 1, out); }
    else out.push(pad + "- " + l.name + "   [" + (l.visible?"可见":"隐藏") + "]  " + l.blendMode + "  " + l.opacity + "%");
  }
  return out;
}
"""


def P(*a):
    return os.path.join(*a).replace("\\", "/")


def js_one(slug, docname):
    L = [JS_HEAD]
    L.append('var DOCNAME = "%s";' % docname)
    L.append('for (var i = app.documents.length - 1; i >= 0; i--)'
             '{ if (app.documents[i].name === DOCNAME) app.documents[i].close(SaveOptions.DONOTSAVECHANGES); }')
    L.append('var doc = app.documents.add(%d, %d, 72, DOCNAME, NewDocumentMode.RGB, DocumentFill.TRANSPARENT);'
             % (W, H))
    # DocumentFill.TRANSPARENT 会留一个空图层「图层 1」，最后要删掉，否则层数会多 1
    L.append('if (doc.artLayers.length === 1) doc.artLayers[0].name = "__base__";')
    L.append('var GROUPS = %s;' % json.dumps([[g, m] for g, m in GROUPS], ensure_ascii=False))
    L.append('for (var i = 0; i < GROUPS.length; i++){ var s = doc.layerSets.add(); s.name = GROUPS[i][0]; }')
    L.append('for (var i = 0; i < GROUPS.length; i++){'
             '  var s = findSet(doc, GROUPS[i][0]);'
             '  var mem = GROUPS[i][1];'
             '  for (var j = mem.length - 1; j >= 0; j--){'
             '    var l = placeFile("%s/" + mem[j] + ".png", mem[j]);'
             '    l.move(s, ElementPlacement.INSIDE); } }' % P(LAY, slug))
    L.append('for (var i = GROUPS.length - 1; i >= 0; i--)'
             '{ findSet(doc, GROUPS[i][0]).move(doc, ElementPlacement.PLACEATBEGINNING); }')
    for nm, bm in BLEND.items():
        if bm != "NORMAL":
            L.append('var l = findLayer(doc.layers, "%s"); if (l) l.blendMode = BlendMode.%s;' % (nm, bm))
    for nm, op in OPACITY.items():
        if op != 100:
            L.append('var l = findLayer(doc.layers, "%s"); if (l) l.opacity = %d;' % (nm, op))
    for nm in HIDE_GROUP:
        L.append('var s = findSet(doc, "%s"); if (s) s.visible = false;' % nm)
    for nm in HIDE_LAYER:
        L.append('var l = findLayer(doc.layers, "%s"); if (l) l.visible = false;' % nm)
    # ⚠️ 这版 PS 的 Layer 没有 delete 方法（delete 又是 JS 保留字），
    # 只能用 ActionDescriptor 走 "Dlt " 动作删除
    L.append('var __b = findLayer(doc.layers, "__base__"); if (__b) delLayer(__b);')
    L.append('doc.saveAs(new File("%s"), new PhotoshopSaveOptions(), true, Extension.LOWERCASE);'
             % P(OUT_DIR, docname + ".psd"))
    L.append('var out = dump(doc.layers, 0, []);')
    L.append('doc.close(SaveOptions.DONOTSAVECHANGES);')
    L.append('out.join("\\n");')
    return "\n".join(L)


def call(app, js, tries=6):
    last = None
    for k in range(tries):
        try:
            return app.DoJavaScript(js)
        except Exception as e:
            last = e
            d = getattr(e, "excepinfo", None)
            print("   重试 %d/%d：%s" % (k + 1, tries, (d[2] if d else e)))
            time.sleep(8)
    raise last


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    themes = json.load(open(os.path.join(HERE, "themes.json"), encoding="utf-8"))
    if "--only" in sys.argv:
        o = sys.argv[sys.argv.index("--only") + 1]
        themes = [t for t in themes if t["key"] == o]
    themes = [t for t in themes
              if all(os.path.exists(os.path.join(LAY, t["key"], n + ".png"))
                     for _, n, _, _ in LY.LAYERS)]

    import ps_conn
    print("连接 Photoshop ...")
    t0 = time.time()
    app = ps_conn.ensure()
    print("已连接 %s %s（%.1fs）" % (app.Name, app.Version, time.time() - t0))

    for t in themes:
        docname = "%s_%02d%s_分层" % (SERIES, t["no"], t["name"])
        print("\n=== %s ===" % docname)
        tree = call(app, js_one(t["key"], docname))
        for line in str(tree).splitlines():
            print("   " + line)

    if "--no-open" in sys.argv:
        return 0
    paths = [P(OUT_DIR, "%s_%02d%s_分层.psd" % (SERIES, t["no"], t["name"])) for t in themes]
    js = ('var ps = %s;\n' % json.dumps(paths)
          + 'for (var i = 0; i < ps.length; i++){ app.open(new File(ps[i])); }\n'
          + 'app.activeDocument = app.documents[0];\napp.bringToFront();\napp.documents.length;')
    print("\n已打开 %s 个文档" % call(app, js))
    return 0


if __name__ == "__main__":
    pythoncom.CoInitialize()
    sys.exit(main())
