---
name: sendvoice
description: "语音播报网关 - 通过 WebSocket API 推送语音通知到树莓派 TTS 设备"
version: 2.2.0
author: Laona
license: MIT
category: custom
metadata:
  hermes:
    tags: [voice, tts, notification, home]
prerequisites:
  commands: []
  env:
    - SENDVOICE_BEARER_TOKEN  # 必填：API Token
    - SENDVOICE_API_URL       # 可选：默认 https://your-server/api/send
    - SENDVOICE_TARGET        # 可选：目标设备名，默认 speaker
---

# SendVoice

语音播报网关。所有 API 调用**必须通过 `__init__.py` 执行**，不得绕过此文件直接构造 HTTP 请求。

## ⚠️ 规则一：全中文推送

树莓派 TTS 设备**不支持中英文混读**，英文会被逐字母拼读。**所有推送内容必须是纯中文**，包含英文的原始数据须先翻译再调用。

```python
# ❌ 错误
send_voice("今天深圳天气：Partly cloudy +27°C")

# ✅ 正确
send_voice("今天深圳天气：多云，二十七度，西北风四级")
```

| 原始内容 | 翻译为 |
|---|---|
| Partly cloudy / Sunny / Rainy | 多云 / 晴 / 有雨 |
| 27°C | 二十七度 |
| 62% | 百分之六十二 |
| NW 14km/h | 西北风四级 |

## ⚠️ 规则二：只能通过 `__init__.py` 发送请求

所有语音推送**必须调用 `__init__.py` 中的函数或通过命令行执行此文件**。禁止在外部代码中自行构造 HTTP 请求。

## 配置

```bash
export SENDVOICE_BEARER_TOKEN="你的 API Token"
export SENDVOICE_API_URL="https://your-server/api/send"  # 可选
export SENDVOICE_TARGET="speaker"                         # 可选
```

## 使用方式

### 框架模式（Hermes / OpenClaw 自动触发）

框架自动拦截以下意图，调用 `handle_send_voice()`：

- "给家里发一条语音通知"
- "通知家里 / 发语音 / 紧急通知家里"

### 命令行 / cron 任务（推荐）

**必须使用 `terminal()` 工具执行**，不得用 `execute_code()`。`terminal()` 通过宿主 shell 运行，天然继承 `SENDVOICE_BEARER_TOKEN` 等环境变量。

```bash
/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '纯中文内容' 0
# 第二个参数：0 = 入队等待按键，1 = 立即播放
```

**为什么不用 `execute_code()`：** 其沙箱不继承宿主环境变量，`SENDVOICE_BEARER_TOKEN` 无法读取，会直接报错。

### cron 任务创建示例

```bash
cronjob action=create \
  skills=["sendvoice"] \
  schedule="2026-06-01T07:00:00+08:00" \
  model={provider:"deepseek", model:"deepseek-v4-flash"} \
  prompt="请使用 terminal 工具执行语音推送：\n/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '纯中文提醒内容' 0"
```

> **重要**：创建 cron 任务时必须固定 `model`，否则切换模型后任务会报 `HTTP 404`。

### 验证推送是否成功

```bash
/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '测试播报'
```

或立即运行一次已创建的任务：

```bash
cronjob action=run job_id="<job_id>"
```

## 优先级判定

| 触发条件 | play_now | 设备行为 |
|---|---|---|
| 含"紧急/立即/马上/现在/快点/即刻"或感叹号 | 1 | 立即播放 |
| 普通文本 | 0 | 静默入队，等待按键触发 |
| 手动指定 play_now=0/1 | 0/1 | 按指定执行 |

## 文件结构

```
sendvoice/
├── SKILL.md          # 本文档
├── __init__.py       # 主代码（所有 API 调用的唯一入口）
└── references/
    ├── chinese-news-extraction.md    # curl+grep 提取中文新闻头条
    ├── cron-env-injection.md         # Docker 环境变量注入说明
    └── cron-job-troubleshooting.md   # 定时任务故障排查
```

## 注意事项

- `SENDVOICE_BEARER_TOKEN` 为必填，未设置时抛出明确错误
- `use_llm=True` 需框架环境注入 `assistant` 对象，独立运行时保持 `False`
- 所有请求有 5 秒超时
- **推送内容必须全中文，禁止中英混排**
