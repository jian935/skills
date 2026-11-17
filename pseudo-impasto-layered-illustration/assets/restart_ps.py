# -*- coding: utf-8 -*-
"""重启 Photoshop：进程不在就拉起来，然后轮询 COM 直到能 DoJavaScript。

背景：PS 前台有模态对话框 / 上一次脚本卡住时，COM 会一直抛
(-2147417846, '消息筛选器显示应用程序正在使用中')。
用户 2026-09-29 授权：遇到这种情况**直接自己重启 PS**，不用问。
"""
import os, subprocess, sys, time

PS_EXE = r"D:\ps2025   8.18\Adobe Photoshop 2025\Photoshop.exe"


def running():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Photoshop.exe"],
                       capture_output=True, text=True, errors="replace")
    return "Photoshop.exe" in (r.stdout or "")


def com_ok():
    try:
        import pythoncom, win32com.client
        pythoncom.CoInitialize()
        app = win32com.client.Dispatch("Photoshop.Application")
        app.DoJavaScript("1+1")
        return True
    except Exception:
        return False


def main(timeout=360, kill=False):
    if kill and running():
        subprocess.run(["taskkill", "/F", "/IM", "Photoshop.exe"], capture_output=True)
        for _ in range(30):
            if not running():
                break
            time.sleep(1)
        print("旧进程已结束")

    if not running():
        if not os.path.exists(PS_EXE):
            print("找不到 PS:", PS_EXE)
            return 2
        subprocess.Popen([PS_EXE], shell=False)
        print("已启动 PS…")

    t0 = time.time()
    while time.time() - t0 < timeout:
        if com_ok():
            print("PS 就绪，用时 %.0fs" % (time.time() - t0))
            return 0
        time.sleep(5)
    print("超时 %ds：PS 仍未就绪" % timeout)
    return 1


if __name__ == "__main__":
    sys.exit(main(kill="--kill" in sys.argv))
