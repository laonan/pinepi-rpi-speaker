# Cron Job 故障排查

## 1. HTTP 404: Not found the model

**症状**：定时任务执行失败，`last_status` 为 `error`，错误信息包含 `HTTP 404`。

**根因**：任务的 `model` 和 `provider` 为 null，运行时读取 `config.yaml` 中的默认模型配置。切换模型后旧模型不可用（API 下架、Token 过期、base_url 变更等）。

**修复**：固定模型到任务上：

```
cronjob action=update job_id="<id>" model={provider:"deepseek", model:"deepseek-v4-flash"}
```

**验证**：`cronjob action=run job_id="<id>"`，然后 `cronjob action=list` 确认 `last_status` 为 `ok`。

## 2. HTTP 401/403: Unauthorized

**症状**：API 返回鉴权错误。

**根因**：API Key 过期、被吊销，或 provider 配置错误（如 base_url 不匹配）。

**排查**：
- 确认环境变量中存在对应 API Key（`echo $DEEPSEEK_API_KEY` 等）
- 确认 base_url 正确（DeepSeek: `https://api.deepseek.com`）
- 确认 API Key 余额充足

## 3. 任务没播报但 status=ok

**症状**：`last_status=ok` 但家里音箱没响。

**原因**：
- **最常见：`/proc/1/environ` 读取失败** → cronjob 里的 `execute_code` 代码尝试读取 PID 1 环境变量注入 token，但 PID 1 是 `tini`（root 运行），hermes 用户没权限读取，代码崩溃或静默失败，LLM 却在报告中"假装"成功
- `SENDVOICE_BEARER_TOKEN` 未正确注入 cron 执行环境
- 播报内容含英文，TTS 跳过
- play_now=0（静默入队）且无人按键触发

**修复（推荐）**：
把 cronjob prompt 里的推送方式从 `execute_code` 改为 `terminal()`：

```bash
# 新的推送命令（放在 cronjob prompt 中）
/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '要播报的纯中文内容' 0
```

`terminal()` 通过宿主 shell 执行，天然继承环境变量，完全绕过 `/proc` 读取问题。

**排查**：
- 如果仍用 `execute_code` 方案，见 `cron-env-injection.md` 修复环境变量注入
- 确认播报内容为纯中文
- 手动设置 `play_now=1` 测试
- 确认使用 `/opt/hermes/.venv/bin/python3`（系统 `python3` 可能缺 `requests`）

## 4. 任务在错误时间执行

**症状**：定时任务不在期望的北京时间运行。

**根因**：cron 表达式按 UTC 计算。

**对照表**：

| 北京时间 | UTC Cron 表达式 |
|---|---|
| 06:00 | 0 22 * * * |
| 07:00 | 0 23 * * * |
| 19:40 | 使用 ISO 时间戳：`2026-05-29T19:40:00+08:00` |
| 20:00 | 0 12 * * * |

**最佳实践**：固定时间的提醒（如 5月29日19:40）使用 ISO 时间戳 + `+08:00` 后缀，避免 UTC 换算错误。周期执行的固定用 UTC cron 表达式。

## 快速检查清单

- [ ] 任务是否固定了 model/provider？
- [ ] 环境变量 `SENDVOICE_BEARER_TOKEN` 是否存在？
- [ ] 播报内容是否全中文？
- [ ] 时间设置是否为正确的时区？
- [ ] 立即用 `action=run` 验证过吗？
