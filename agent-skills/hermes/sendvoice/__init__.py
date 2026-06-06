import requests
import logging
import sys
import os

# ================= 配置区 =================
API_URL = os.getenv("SENDVOICE_API_URL", "https://your-server/api/send")
SENDVOICE_TARGET = os.getenv("SENDVOICE_TARGET", "speaker")


def _get_bearer_token():
    """动态获取 token，优先环境变量，回退到 /proc/<pid>/environ（自动查找 hermes gateway 进程）。"""
    token = os.environ.get("SENDVOICE_BEARER_TOKEN", "")
    if token:
        return token
    # 回退：遍历常见 PID，再通过 ps aux 定位 hermes gateway 进程
    for pid in ["1"]:
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = f.read().decode("utf-8", errors="replace")
            for line in env.split("\x00"):
                if line.startswith("SENDVOICE_BEARER_TOKEN="):
                    return line.split("=", 1)[1]
        except Exception:
            pass
    # ps aux 回退：查找 hermes gateway 进程
    try:
        import subprocess
        ps_out = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        ).stdout
        for line in ps_out.splitlines():
            if "hermes gateway" in line.lower() or "/hermes " in line:
                pid = line.split()[1]
                with open(f"/proc/{pid}/environ", "rb") as f:
                    env = f.read().decode("utf-8", errors="replace")
                for env_line in env.split("\x00"):
                    if env_line.startswith("SENDVOICE_BEARER_TOKEN="):
                        return env_line.split("=", 1)[1]
    except Exception:
        pass
    return ""


def send_voice_api(title, content, play_now=0):
    """纯 API 发送，不依赖任何框架对象。"""
    bearer_token = _get_bearer_token()
    if not bearer_token:
        raise RuntimeError("SENDVOICE_BEARER_TOKEN 未设置，请检查环境变量")
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }
    payload = {
            "targets": [SENDVOICE_TARGET],
            "event": {
                "title": title,
                "content": content,
                "play_now": play_now
             }
    }
    res = requests.post(API_URL, json=payload, headers=headers, timeout=5)
    res.raise_for_status()
    return res


def detect_urgency(text):
    """检测文本是否包含紧急语气。"""
    urgent_keywords = ["紧急", "立即", "马上", "现在", "快点", "即刻"]
    return any(word in text for word in urgent_keywords) or "!" in text or "！" in text


def generate_title(content, use_llm=False):
    """
    生成摘要标题。
    use_llm=True 时尝试调用 LLM（需要框架环境），否则使用截断降级。
    """
    if use_llm:
        try:
            summary_prompt = (
                f"请将以下内容概括为一句通顺的中文短句作为标题（15字以内），"
                f"要求保留核心人物和事件，不要标点符号：{content}"
            )
            # 兼容 OpenClaw/Hermes 框架注入的 assistant 对象
            import __main__
            assistant = getattr(__main__, "assistant", None)
            if assistant is None:
                raise RuntimeError("assistant not available")
            title = (
                assistant.ask_llm(summary_prompt)
                .strip()
                .replace("。", "")
                .replace("“", "")
                .replace("”", "")
            )
            if len(title) > 20:
                title = title[:17] + "..."
            return title
        except Exception:
            pass
    # 降级：直接截断
    return content[:15] + "..." if len(content) > 15 else content


def send_voice(text, auto_urgency=True, play_now=None, use_llm=False):
    """
    独立可复用的语音推送接口，不依赖框架对象。

    Args:
        text: 播报内容
        auto_urgency: 是否自动检测紧急关键词（默认 True）
        play_now: 强制指定 play_now（0/1），None 则自动判断
        use_llm: 是否尝试使用 LLM 生成标题（默认 False，独立运行时建议关闭）

    Returns:
        dict: {"success": True/False, "title": ..., "play_now": ..., "message": ...}
    """
    content = text.strip()
    if not content:
        return {
            "success": False,
            "message": "❌ 未检测到播报内容",
            "title": "",
            "play_now": 0,
        }

    # 优先级判定
    if play_now is None:
        play_now = 1 if (auto_urgency and detect_urgency(text)) else 0

    # 生成标题
    title = generate_title(content, use_llm=use_llm)

    # 发送
    try:
        send_voice_api(title, content, play_now)
        status = "🔊 立即播放" if play_now == 1 else "📥 已入队(等待按键)"
        return {
            "success": True,
            "title": title,
            "play_now": play_now,
            "message": f"✅ {status}\n【摘要】{title}",
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Network Exception: {e}")
        return {
            "success": False,
            "title": title,
            "play_now": play_now,
            "message": f"⚠️ 无法连接到推送网关：{e}",
        }


def handle_send_voice(assistant, text, session):
    """
    框架内置 handler（兼容 OpenClaw/Hermes）。
    保留原有接口供框架调用，内部复用独立函数。
    """
    # 1. 提取原始内容
    content = None
    if session and hasattr(session, "slots"):
        content = session.slots.get("content")
    if not content:
        if text.startswith("/send_voice"):
            content = text.replace("/send_voice!", "").replace("/send_voice", "").strip()
        else:
            content = text.strip()

    if not content:
        assistant.say("❌ 未检测到播报内容")
        return

    # 2. 使用独立接口发送（启用 LLM）
    result = send_voice(content, use_llm=True)
    assistant.say(result["message"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python __init__.py '播报内容' [play_now]")
        sys.exit(1)

    text = sys.argv[1]
    play_now = int(sys.argv[2]) if len(sys.argv) > 2 else None

    result = send_voice(text, play_now=play_now, auto_urgency=(play_now is None))
    print(result["message"])
    sys.exit(0 if result["success"] else 1)
