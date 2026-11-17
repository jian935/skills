# Photoshop COM 自动化

```mermaid
flowchart LR
    A["Python 脚本"] -->|pywin32| B["COM<br/>Photoshop.Application"]
    B --> C["Photoshop.exe /Automation"]
    C -->|DoJavaScript| D["ExtendScript<br/>(JSX)"]
    D --> E["文档 / 图层 / 选区 / 文字 / 导出"]
    E --> F["PNG · JPG · 分层 PSD"]
```

这个 skill 没有画面产物，产出是一份**可直接照抄的接口手册 + 两个健壮化脚本**：
让脚本能稳定连上 Photoshop，并在 COM 被进程内沙箱拦截、PS 卡在模态框、`gencache` 早期失败这些情况下还能跑通。

## 一句话

用 Python（pywin32）通过 COM / ExtendScript 驱动 Windows 上的 Photoshop：
新建、打开、图层、选区填色、文字、批处理、导出 PNG/JPG/PSD。

## 适合谁

- 想让 AI 直接操作 Photoshop 做批量处理（换尺寸、加水印、导出多规格）；
- 要把程序生成的 PNG 图层组装成分组 PSD（本仓库另外两个 skill 就依赖它）；
- 已经写了 COM 脚本但一直被"应用程序正在使用中"、`Dispatch` 失败、图层顺序反了这些问题卡住。

不适合 macOS / Linux，也不覆盖 Photoshop 网页版。详见 [SKILL.md](./SKILL.md) 的「不适用」。

## 手册里被反复踩到的部分

| 章节 | 讲什么 |
|---|---|
| 一 | 先确认 COM 是否注册：查 `CurVer` → `CLSID` → `LocalServer32`，应指向 `Photoshop.exe /Automation` |
| 三 | 连接与基本操作，`Dispatch` 失败时退回 `win32com.client.Dispatch` |
| 四 | **别硬拼 COM 对象模型**，用 `DoJavaScript` 跑任意 JSX 更稳 |
| 五 | 常见任务速查：新建、填色、加文字、批量导出 |
| 八~十一 | 分层 PSD 全流程：组装、重开核对、"用户说没看见图层"时怎么查 |
| 十二 | 两个必踩坑：`set.layers[0]` 是**最上面**那层；OpenCV 在 Windows 上不支持非 ASCII 路径 |
| 十三 | `RPC_E_SERVERCALL_RETRYLATER`（"应用程序正在使用中"）的成因与正确写法 |
| 十四 | PS 把 C 盘吃爆：`Photoshop Temp` 暂存文件怎么排查 |

## 脚本清单

| 文件 | 作用 |
|---|---|
| `assets/ps_conn.py` | 健壮化连接：`gencache` 失败前置处理 + 重试，避开 `RPC_E_SERVERCALLRETRYLATER` |
| `assets/open_psd.py` | 批量打开 `psd/` 下的分层 PSD，回读图层树（组名 + 层数）做交付复核 |

## 起点

1. 先跑 [SKILL.md](./SKILL.md) 第一章那段注册表检查，确认 `LocalServer32` 指向 `Photoshop.exe /Automation`；
2. 再用 `assets/ps_conn.py` 的 `connect()` 拿 app 对象，别自己写 `EnsureDispatch`；
3. 复杂逻辑一律塞进 JSX 字符串用 `DoJavaScript` 执行，返回 `JSON.stringify` 的结果。

## 边界

- 仅 Windows COM，其他平台不覆盖；
- 依赖已安装的桌面版 Photoshop（实测 26.0），网页版与 Express 没有 COM 接口；
- 不做视频渲染。
