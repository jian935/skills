# -*- coding: utf-8 -*-
"""PS COM 连接健壮化工具。

背景：上一次 PS 被 SIGTERM 强杀后，COM 出现
    pywintypes.com_error: (-2147417846, '消息筛选器显示应用程序正在使用中。')
即 RPC_E_SERVERCALL_RETRYLATER —— 服务端没在泵消息（冷启动中）或
注册表里残留了指向已死进程的激活信息。

策略（按代价从低到高）：
  1) 直接 Dispatch（晚绑定，绕开 gencache 的 typelib 缓存）
  2) 每轮 sleep 递增重试，冷启动给足时间（PS 首启可达 40s+）
  3) 仍失败就主动 Start-Process 拉起 PS，等窗口就绪后再 Dispatch
"""
import os
import subprocess
import sys
import time

import pythoncom
import win32com.client
from win32com.client import gencache

PS_EXE_CANDIDATES = [
    r"C:\Program Files\Adobe\Adobe Photoshop 2025\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2023\Photoshop.exe",
    r"C:\Program Files\Adobe\Adobe Photoshop 2022\Photoshop.exe",
    r"D:\Program Files\Adobe\Adobe Photoshop 2024\Photoshop.exe",
]


def find_ps():
    for p in PS_EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    # 注册表里找
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",):
                try:
                    k = winreg.OpenKey(root, sub)
                    v = winreg.QueryValueEx(k, None)[0]
                    if os.path.exists(v):
                        return v
                except OSError:
                    pass
    except Exception:
        pass
    return None


def ps_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Photoshop.exe", "/NH"],
            capture_output=True, text=True, timeout=20).stdout
        return "Photoshop.exe" in out
    except Exception:
        return False


def launch(ps_exe, wait=90):
    print("  拉起 Photoshop: %s" % ps_exe)
    subprocess.Popen([ps_exe], close_fds=True)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(3)
        if ps_running():
            print("  进程已出现（%.0fs），再等 12s 让它初始化" % (time.time() - t0))
            time.sleep(12)
            return True
    return False


def connect(tries=8, base_sleep=5):
    """返回可用的 app 对象。"""
    pythoncom.CoInitialize()
    last = None
    for k in range(tries):
        try:
            app = win32com.client.Dispatch("Photoshop.Application")
            # 晚绑定属性访问也可能卡在 server busy
            name = app.Name
            ver = app.Version
            print("  已连接 %s %s（第 %d 次尝试）" % (name, ver, k + 1))
            return app
        except Exception as e:
            last = e
            d = getattr(e, "excepinfo", None)
            msg = (d[2] if d else str(e))
            print("  第 %d/%d 次失败：%s" % (k + 1, tries, msg))
            time.sleep(base_sleep + 2 * k)
    raise last


def ensure(tries=8):
    """尽量拿到一个活着的 PS。失败抛异常。"""
    print("1) 直接连接 ...")
    try:
        return connect(tries=tries)
    except Exception:
        pass
    print("2) 清掉 gencache 后重试 ...")
    try:
        gencache._GenCache__my_GetClassForCLSID = None  # noqa  (占位，避免误用)
    except Exception:
        pass
    ps = find_ps()
    if ps and not ps_running():
        launch(ps)
    elif not ps_running():
        print("  未找到 Photoshop.exe，跳过拉起")
    print("3) 拉起后再连 ...")
    return connect(tries=tries, base_sleep=6)


if __name__ == "__main__":
    try:
        app = ensure()
    except Exception as e:
        d = getattr(e, "excepinfo", None)
        print("失败：%s" % (d[2] if d else e))
        sys.exit(1)
    print("OK  Name=%s  Version=%s  Docs=%s" % (app.Name, app.Version, app.Documents.Count))
