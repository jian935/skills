# -*- coding: utf-8 -*-
"""哥特三人组 · 20 层 PSD 组装（动态读 8 档底色 + 皮肤 + 高光3/阴影3/冷暖调 + 线稿/草稿/背景）

面板结构（自上而下，7 组 ≈ 20 层）：
  [组] ①线稿   线稿-完整                        ★默认隐藏
  [组] ②草稿   草稿-淡描                        ★默认隐藏
  [组] ③高光   高光-强 / 高光-整体 / 高光-细节
  [组] ④阴影   阴影-重 / 阴影-轻 / 阴影-细节
  [组] ⑤调色   整体-暖调 / 整体-冷调
  [组] ⑥上色   底色-极暗→亮银 + 皮肤（动态读）
  [组] ⑦背景   背景-原色（PSD 最底层为白色）
"""
import os, sys, json, glob, time
import pythoncom

HERE = os.path.dirname(os.path.abspath(__file__))
LAY = os.path.join(HERE, "图层")
OUT_DIR = os.environ.get("OUT_DIR") or os.path.join(os.getcwd(), "out")
W, H = 1024, 1536

PS_BLEND = {"NORMAL": "NORMAL", "SCREEN": "SCREEN", "MULTIPLY": "MULTIPLY", "SOFT_LIGHT": "SOFTLIGHT"}
HIDE_GROUP = ["①线稿", "②草稿"]
BLEND = {"高光-强": "SCREEN", "高光-整体": "SCREEN", "高光-细节": "SCREEN",
         "阴影-重": "MULTIPLY", "阴影-轻": "MULTIPLY", "阴影-细节": "MULTIPLY",
         "整体-暖调": "SOFTLIGHT", "整体-冷调": "SOFTLIGHT"}
OPACITY = {"高光-强": 95, "高光-整体": 75, "高光-细节": 50,
           "阴影-重": 75, "阴影-轻": 40, "阴影-细节": 22,
           "整体-暖调": 15, "整体-冷调": 12}

FIXED_TOP = [("①线稿", ["线稿-完整"]), ("②草稿", ["草稿-淡描"]),
             ("③高光", ["高光-强", "高光-整体", "高光-细节"]),
             ("④阴影", ["阴影-重", "阴影-轻", "阴影-细节"]),
             ("⑤调色", ["整体-暖调", "整体-冷调"])]


def groups_for(key):
    g = list(FIXED_TOP)
    bases = [os.path.basename(p)[:-4] for p in sorted(glob.glob(os.path.join(LAY, key, "底色-*.png")))]
    # 明度从暗到亮 + 皮肤
    order = ["底色-极暗", "底色-墨色", "底色-深蓝", "底色-暗蓝", "底色-深灰",
             "底色-中灰", "底色-浅灰", "底色-亮银", "底色-皮肤"]
    bases = [b for b in order if b in bases] + [b for b in bases if b not in order]
    g.append(("⑥上色", bases))
    g.append(("⑦背景", ["背景-原色"]))
    return g


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


def js_one(slug, docname, groups):
    L = [JS_HEAD]
    L.append('var DOCNAME = "%s";' % docname)
    L.append('for (var i = app.documents.length - 1; i >= 0; i--)'
             '{ if (app.documents[i].name === DOCNAME) app.documents[i].close(SaveOptions.DONOTSAVECHANGES); }')
    L.append('var doc = app.documents.add(%d, %d, 72, DOCNAME, NewDocumentMode.RGB, DocumentFill.WHITE);'
             % (W, H))
    L.append('if (doc.artLayers.length === 1) doc.artLayers[0].name = "背景-白色";')
    L.append('var GROUPS = %s;' % json.dumps(groups, ensure_ascii=False))
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
        L.append('var l = findLayer(doc.layers, "%s"); if (l) l.blendMode = BlendMode.%s;' % (nm, bm))
    for nm, op in OPACITY.items():
        L.append('var l = findLayer(doc.layers, "%s"); if (l) l.opacity = %d;' % (nm, op))
    for nm in HIDE_GROUP:
        L.append('var s = findSet(doc, "%s"); if (s) s.visible = false;' % nm)
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
    if len(sys.argv) < 3:
        print("用法: python build_psd.py <out_key> <docname>")
        sys.exit(1)
    out_key, docname = sys.argv[1], sys.argv[2]

    import ps_conn
    print("连接 Photoshop ...")
    app = ps_conn.ensure()
    print("已连接 %s %s" % (app.Name, app.Version))

    groups = groups_for(out_key)
    n_layers = sum(len(m) for _, m in groups)
    print("\n=== %s ===（%d 层）" % (docname, n_layers))
    tree = call(app, js_one(out_key, docname, groups))
    for line in str(tree).splitlines():
        print("   " + line)
    return 0


if __name__ == "__main__":
    pythoncom.CoInitialize()
    sys.exit(main())
