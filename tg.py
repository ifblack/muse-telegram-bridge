#!/usr/bin/env python3
"""Telegram Bot API 收发 CLI（Muse × Telegram 平替方案）。


认证走 Secure Vault 里的 custom.telegram，经 authd surrogate 注入，
token 以 hsurr: 形式存在于发出的请求中，绝不打印、不落盘。

用法：
  tg.py getme                                  # 验凭证，返回 bot 身份
  tg.py poll --state <state.json>              # 拉新消息（JSON），推进 offset
  tg.py send <chat_id> <text>                  # 发消息，超 4000 字自动分段
  tg.py send-quote <chat_id> <label> <text>    # 发引用框消息（HTML），用于区分身份

  send-quote 示例：把 side chat 里用户说的话同步到 Telegram 时，
  用 label="💬 你在 Muse 里说" 包成引用框，和机器人自己的回复视觉区分。

只用标准库。
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import (  # noqa: E402
    dynamic_credential_entry,
    ensure_allowed_url,
    read_json_response,
    DynamicCredentialError,
)

CRED = "custom.telegram"
HOSTS = ["api.telegram.org"]
SEND_LIMIT = 4000

_surrogate_cache: str | None = None


def _surrogate() -> str:
    """取 authd 的 surrogate。注意：绝不能对它做 URL 编码——
    scaffold 的 url_with_surrogate_path_segment 会把冒号 encode 成 %3A，
    导致 Sentinel 无法识别替换，Telegram 会回 404。这里手动拼接。"""
    global _surrogate_cache
    if _surrogate_cache:
        return _surrogate_cache
    entry = dynamic_credential_entry(CRED)
    placement = entry.get("placement")
    if not (isinstance(placement, dict) and "url_path_segment" in placement):
        raise DynamicCredentialError(
            f"credential is not url_path_segment: {placement!r}")
    surr = str(entry["surrogate"]).strip()
    if not surr.startswith("hsurr:"):
        raise DynamicCredentialError("authd returned a non-surrogate value")
    _surrogate_cache = surr
    return surr


def api_url(method: str) -> str:
    url = f"https://api.telegram.org/bot{_surrogate()}/{method}"
    ensure_allowed_url(url, HOSTS)
    return url


def call(method: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        api_url(method), data=data, headers=headers,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = read_json_response(resp)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        raise SystemExit(f"Telegram API 错误 {e.code}: {body[:300]}")
    except OSError as e:
        raise SystemExit(f"网络错误: {e}")
    if not result.get("ok"):
        raise SystemExit(f"Telegram 返回失败: {json.dumps(result)[:300]}")
    return result


def cmd_getme() -> None:
    r = call("getMe")
    bot = r.get("result", {})
    print(json.dumps(
        {"ok": True, "id": bot.get("id"), "username": bot.get("username"),
         "name": bot.get("first_name")},
        ensure_ascii=False))


def cmd_poll(state_path: str) -> None:
    state: dict = {}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    offset = int(state.get("offset") or 0)
    r = call("getUpdates", {"offset": offset, "timeout": 0,
                            "allowed_updates": ["message"]})
    updates = r.get("result", [])
    msgs = []
    max_id = offset
    for u in updates:
        uid = int(u.get("update_id") or 0)
        max_id = max(max_id, uid)
        m = u.get("message") or {}
        text = m.get("text")
        if not text:
            continue
        chat = m.get("chat") or {}
        frm = m.get("from") or {}
        msgs.append({
            "update_id": uid,
            "chat_id": chat.get("id"),
            "chat_type": chat.get("type"),
            "from_name": frm.get("first_name") or frm.get("username") or "",
            "text": text,
            "date": m.get("date"),
        })
    if updates:
        state["offset"] = max_id + 1
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, state_path)
    print(json.dumps({"ok": True, "messages": msgs}, ensure_ascii=False))


def cmd_send(chat_id: str, text: str, parse_mode: str | None = None) -> None:
    try:
        cid = int(chat_id)
    except ValueError:
        raise SystemExit(f"chat_id 非法: {chat_id}")
    parts = [text[i:i + SEND_LIMIT] for i in range(0, len(text), SEND_LIMIT)] or [""]
    for p in parts:
        payload: dict = {"chat_id": cid, "text": p}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        call("sendMessage", payload)
    print(json.dumps({"ok": True, "parts": len(parts)}, ensure_ascii=False))


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cmd_send_quote(chat_id: str, label: str, text: str) -> None:
    """把 text 包进引用框发出，用于区分"用户在别处说的话"和机器人自己的回复。"""
    html = f"<b>{_html_escape(label)}</b>\n<blockquote>{_html_escape(text)}</blockquote>"
    cmd_send(chat_id, html, parse_mode="HTML")


def main(argv: list[str]) -> None:
    if len(argv) < 2:
        raise SystemExit("用法: tg.py getme | poll --state <f> | send <chat_id> <text>")
    cmd = argv[1]
    if cmd == "getme":
        cmd_getme()
    elif cmd == "poll":
        if len(argv) != 4 or argv[2] != "--state":
            raise SystemExit("用法: tg.py poll --state <state.json>")
        cmd_poll(argv[3])
    elif cmd == "send":
        if len(argv) != 4:
            raise SystemExit("用法: tg.py send <chat_id> <text>")
        cmd_send(argv[2], argv[3])
    elif cmd == "send-quote":
        if len(argv) != 5:
            raise SystemExit("用法: tg.py send-quote <chat_id> <label> <text>")
        cmd_send_quote(argv[2], argv[3], argv[4])
    else:
        raise SystemExit(f"未知命令: {cmd}")


if __name__ == "__main__":
    main(sys.argv)
