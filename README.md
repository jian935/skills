# Skills

`jian935` 的 skill 合集 —— 每个 skill 一个子目录，各自带独立的 `SKILL.md`。

## 索引

| Skill | 目录 | 说明 | 状态 |
|---|---|---|---|
| 伪厚涂分层插画 | [`pseudo-impasto-layered-illustration`](./pseudo-impasto-layered-illustration/) | 提示词或参考图 → 19 图层 PSD（6 组 + 13 层），13 层全开逐像素等于成品 | 可用 |
| 动漫成图转 PSD | [`anime-lineart-psd-pipeline`](./anime-lineart-psd-pipeline/) | 二次元成图 → 白底 2.5px 线稿 + 20 层可上色 PSD（抠图 / 分层 / COM 组装） | 可用 |
| Photoshop 自动化 | [`photoshop-com-automation`](./photoshop-com-automation/) | pywin32 + COM/ExtendScript 驱动 PS：新建、图层、选区填色、文字、批处理、导出 | 可用 |
| ComfyUI 绘画管线 | [`comfyui-anime-pipeline`](./comfyui-anime-pipeline/) | 本地 ComfyUI 的 API 调用、模型下载、ControlNet 上色、显存配置与已知坑 | 可用 |

上面四个构成一条「出图 → 抠图 → 线稿 → 分层 → PSD」的完整链路，串法与依赖见
[docs/illustration-pipeline.md](./docs/illustration-pipeline.md)。

单独发布的 skill（不在本仓库内）：

- [complaint-to-eval](https://github.com/jian935/complaint-to-eval) —— 把用户抱怨/issue/评价转成待评审的回归测试候选
- [release-contract](https://github.com/jian935/release-contract) —— 每个版本可审计的发布契约
- [ai-claim-audit](https://github.com/jian935/ai-claim-audit) —— 审计 AI 产品效果宣称里的数字

## 目录结构

```
.
├─ README.md              # 本文件：索引与约定
├─ _template/             # 新 skill 的骨架，复制后改
│  └─ SKILL.md
└─ <skill-name>/
   ├─ SKILL.md            # 必需：frontmatter + 使用说明
   ├─ README.md           # 可选：面向人类的简介
   ├─ scripts/            # 可选：可执行脚本
   ├─ examples/           # 可选：示例输入/输出
   └─ evals/              # 可选：评测用例
```

## 新增一个 skill

1. 复制 `_template/` 为 `<skill-name>/`（小写、连字符分隔，和 frontmatter 的 `name` 一致）
2. 填 `SKILL.md` 的 frontmatter：
   - `name`：与目录名一致
   - `description`：写清**什么时候该用**，包含真实触发语（中英文都写），并明确**不做什么**
3. 正文至少包含：Purpose / When to use / When not to use / Inputs / Output / Workflow / Failure modes
4. 更新本 README 的索引表
5. 提交推送

## 约定

- 一个目录一个 skill，不共用脚本
- `description` 决定会不会被自动触发，**宁可写长、写具体**，把不适用场景也写进去
- skill 只描述流程与判断，不内置大段与具体模型绑定的提示词
- 不提交密钥、个人信息、内部数据；示例数据一律脱敏

## 许可

除非子目录另有说明，均以 MIT 许可发布。
