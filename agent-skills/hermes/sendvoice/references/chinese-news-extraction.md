# 中文新闻头条提取（curl + grep 模式）

## 适用场景

在无 Chrome 浏览器的环境中（如 cron job 沙箱），需要通过终端获取当天中文新闻头条（新浪、凤凰网等），然后推送至家庭音箱。

**不依赖 browser 工具**，仅使用 `curl` + `grep` 即可提取纯文本标题。

## 工作流

1. **`curl` 获取页面 HTML**
2. **`grep -oP` 提取 `<a>` 标签中的中文文本**（比 HTML 转文本更轻量、更抗反爬）

## 核心命令

### 从新浪新闻提取标题

```bash
curl -s -L --connect-timeout 10 --max-time 15 'https://news.sina.com.cn/' \
  | grep -oP '<a[^>]*>([^<]{10,60})</a>' \
  | grep -oP '>[^<]+<' \
  | tr -d '<>' \
  | head -50
```

结果示例：
```
美国：艾奥瓦州列车脱轨
中国女排3比2泰国女排
中国工商界表示强烈不满和坚决反对
英学者喊话欧洲：中美会谈，你得争取加入
特朗普回应"对伊朗动武权力被限制"
近五年来最强季度增长，香港怎么做到的？
```

### 从凤凰网提取标题

```bash
curl -s -L --connect-timeout 10 --max-time 15 'https://www.ifeng.com/' \
  | grep -oP '<h[23][^>]*><a[^>]*title="[^"]{10,60}"' \
  | grep -oP 'title="[^"]+' \
  | sed 's/title="//' \
  | head -30
```

### 从新浪提取特定关键词相关新闻

```bash
curl -s -L --connect-timeout 10 --max-time 15 'https://news.sina.com.cn/' \
  | grep -oP '.{0,100}(关税|贸易|制裁|加征|关税).{0,100}' \
  | head -15
```

### 获取 Sina 头条大号加粗标题

```bash
curl -s -L --connect-timeout 10 --max-time 15 'https://news.sina.com.cn/' \
  | grep -oP 'class="linkNewsTopBold"[^>]*>[^<]+'
```

## 新闻过滤优先级（针对跨境贸易家庭）

筛选"最重要的一条"新闻时，按以下优先级判断：

| 优先级 | 新闻类别 | 示例 |
|---|---|---|
| 1 | 中美贸易政策 / 关税 / 制裁 | "中国工商界表示强烈不满和坚决反对" |
| 2 | 宏观经济 / 地缘政治 | "中美会谈"、"欧盟"、"香港经济" |
| 3 | 重大突发事件 | 自然灾害、战争、政策突变 |
| 4 | 与行业直接相关（LED / 电子 / 跨境电商） | 油价、汇率、航运 |

## 20字以内纯中文压缩

将精选标题压缩到 **20 个汉字以内**，并确保**无英文、无数字、无符号**：

| 原标题（长度） | 压缩后（长度） |
|---|---|
| 中国工商界表示强烈不满和坚决反对（18字） | 中国强烈反对美国对华贸易限制（14字） |
| 近五年来最强季度增长，香港怎么做到的？（20字） | 香港经济近五年最强增长（11字） |
| 商务部：反对美以"强迫劳动"为由对华贸易限制（21字） | 商务部反对美国对华贸易限制（13字） |

## 已知抗性

| 网站 | 反爬措施 | 绕过方案 |
|---|---|---|
| news.163.com | 返回 403 Forbidden | 跳过，使用 Sina 或 Ifeng 替代 |
| Xinhua (news.cn) | 返回空 HTML | 跳过，使用 Sina 或 Ifeng 替代 |
| Sina / Ifeng | 无显著反爬（文字版） | 直接使用 curl |

## 与 sendvoice 集成

获取并压缩新闻后，直接推送到音箱：

```bash
/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '中国强烈反对美国对华贸易限制' 0
```

## 完整工作流示例（execute_code 中调用 terminal）

```python
from hermes_tools import terminal

# 1. 获取新闻标题
result = terminal("""
curl -s -L --connect-timeout 10 --max-time 15 'https://news.sina.com.cn/' \
  | grep -oP '<a[^>]*>([^<]{10,60})</a>' \
  | grep -oP '>[^<]+<' \
  | tr -d '<>' \
  | head -20
""", timeout=20)
headlines = result["output"].strip().split('\n')

# 2. 过滤、选择、压缩...

# 3. 推送
terminal("/opt/hermes/.venv/bin/python3 /opt/data/skills/sendvoice/__init__.py '压缩后的新闻标题' 0")
```
