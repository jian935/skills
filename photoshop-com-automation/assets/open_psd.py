# -*- coding: utf-8 -*-
"""启动 Photoshop 并打开 10 个分层 PSD，然后回读图层树做复核。"""
import os
import sys
import json
import time

import pythoncom
import win32com.client
from win32com.client import gencache

HERE = os.path.abspath(os.path.dirname(__file__))
PSD_DIR = os.path.join(HERE, "psd")

DOCS_JS = (
    'var out = [];\n'
    'for (var d = 0; d < app.documents.length; d++){\n'
    '  var doc = app.documents[d];\n'
    '  var names = [];\n'
    '  var sub = 0, sets = 0;\n'
    '  for (var i = 0; i < doc.layers.length; i++){\n'
    '    var l = doc.layers[i];\n'
    '    if (l.typename === "LayerSet"){ names.push("[" + l.name + "](" + l.layers.length + ")"); sets++; sub += l.layers.length; }\n'
    '    else { names.push(l.name); }\n'
    '  }\n'
    '  out.push(doc.name + "  ||  顶层" + doc.layers.length + " 组" + sets + " 含子层" + (sub + doc.layers.length - sets) + "  ||  " + names.join(" / "));\n'
    '}\n'
    'out.join("\\n");'
)


def call(app, js, tries=3):
    last = None
    for k in range(tries):
        try:
            return app.DoJavaScript(js)
        except Exception as e:
            last = e
            print("   重试 %d/%d：%s" % (k + 1, tries, e))
            time.sleep(8)
    raise last


def main():
    slugs = sorted(f[:-4] for f in os.listdir(PSD_DIR) if f.endswith(".psd"))
    if not slugs:
        print("psd 目录为空：%s" % PSD_DIR)
        return

    pythoncom.CoInitialize()
    print("连接 / 启动 Photoshop ...")
    t0 = time.time()
    try:
        app = gencache.EnsureDispatch("Photoshop.Application")
    except Exception:
        app = win32com.client.Dispatch("Photoshop.Application")
    print("已连接 %s %s（耗时 %.1fs，冷启动较慢）" % (app.Name, app.Version, time.time() - t0))

    paths = [os.path.join(PSD_DIR, s + ".psd").replace("\\", "/") for s in slugs]
    js = ('var ps = %s;\n' % json.dumps(paths)
          + 'for (var i = 0; i < ps.length; i++){ app.open(new File(ps[i])); }\n'
          + 'app.activeDocument = app.documents[0];\n'
          + 'app.bringToFront();\n'
          + 'app.documents.length;')
    n = call(app, js)
    print("已打开 %s 个文档\n" % n)

    print("=== 回读图层树 ===")
    print(call(app, DOCS_JS))


if __name__ == "__main__":
    main()
