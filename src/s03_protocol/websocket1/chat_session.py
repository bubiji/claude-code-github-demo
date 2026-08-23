"""websocket1 —— WebSocket 单人聊天室的一次完整会话。

issue: #6 · 案例: websocket1 · 来源: https://websocket1.scrape.center

做三件事：
1. 完成 WebSocket 握手（HTTP/1.1 Upgrade），把请求/响应头原样记下来；
2. 收发若干条消息（应用层协议是 JSON：发 {"sender", "content"}，收 {"sender", "answer"}）；
3. 主动发 Close 帧（code=1000）并等待对端回 Close，确认连接是「正常关闭」而不是被掐断。

全过程的帧记录（方向 / opcode / payload / 时间戳）落盘到 evidence/。

用法：
    python chat_session.py                 # 默认发 4 条消息
    python chat_session.py --messages 你好 再见
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# websockets 打帧日志时会把 payload 截断成 "'{...}...尾巴'"（默认 MAX_LOG_SIZE=75），
# 截断过的帧记录算不上「完整帧记录」。这个上限读的是环境变量，且是在 import 时
# 求值的类属性，所以必须在 import websockets 之前设好。
os.environ.setdefault("WEBSOCKETS_MAX_LOG_SIZE", "4096")

import websockets  # noqa: E402 —— 必须在设完上面的环境变量之后再导入

WS_URL = "wss://websocket1.scrape.center/websocket"
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"

DEFAULT_MESSAGES = [
    "hello",
    "你好，我是来做 WebSocket 抓包分析的",
    "What is the weather like?",
    "bye",
]

# websockets 库在 DEBUG 级别会把每一帧打成 "> TEXT 'xxx' [5 bytes]" / "< PONG ''" 这样的行，
# 这里用一个 Handler 把它们截下来当作帧记录的原始素材。
FRAME_RE = re.compile(r"^([<>])\s+(TEXT|BINARY|CLOSE|PING|PONG)\s+(.*)$")
# 帧行尾部的 "[70 bytes]" 是 payload 的字节数，单独拆出来当一个字段。
SIZE_RE = re.compile(r"\s*\[(\d+) bytes\]$")


class FrameCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.frames: list[dict] = []
        self.raw_lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        self.raw_lines.append(f"{ts} {msg}")
        m = FRAME_RE.match(msg.strip())
        if not m:
            return
        arrow, opcode, payload = m.groups()
        payload = payload.strip()

        size_m = SIZE_RE.search(payload)
        payload_bytes = int(size_m.group(1)) if size_m else None
        body = SIZE_RE.sub("", payload).strip() if size_m else payload
        # TEXT/BINARY 的 payload 被库加了引号，剥掉好让 JSON 里是干净的原文；
        # CLOSE/PING/PONG 形如 "1000 (OK) bye"，原样保留。
        if len(body) >= 2 and body[0] == body[-1] == "'":
            body = body[1:-1]

        self.frames.append(
            {
                "ts": ts,
                "direction": "client->server" if arrow == ">" else "server->client",
                "opcode": opcode,
                "payload": body,
                "payload_bytes": payload_bytes,
                "truncated": body.endswith("...") and payload_bytes is not None
                and payload_bytes > len(body.encode()),
                "raw_log_line": payload,
            }
        )


def headers_to_list(headers) -> list[list[str]]:
    """把握手头转成 [[name, value], ...]，保留重复头与原始顺序。"""
    return [[k, v] for k, v in headers.raw_items()]


async def run(messages: list[str], recv_timeout: float, gap: float) -> dict:
    collector = FrameCollector()
    logger = logging.getLogger("websocket1.session")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(collector)
    logger.propagate = False

    sender = str(uuid.uuid4())
    t0 = time.perf_counter()
    transcript: list[dict] = []

    async with websockets.connect(WS_URL, logger=logger, open_timeout=20) as ws:
        handshake = {
            "request": {
                "path": ws.request.path,
                "headers": headers_to_list(ws.request.headers),
            },
            "response": {
                "status_code": ws.response.status_code,
                "reason": ws.response.reason_phrase,
                "headers": headers_to_list(ws.response.headers),
            },
            "subprotocol": ws.subprotocol,
            "extensions": [str(e) for e in ws.protocol.extensions],
            "local_address": list(ws.local_address),
            "remote_address": list(ws.remote_address),
        }
        print(f"[handshake] {ws.response.status_code} {ws.response.reason_phrase}")
        print(f"[handshake] Upgrade={ws.response.headers.get('Upgrade')} "
              f"Connection={ws.response.headers.get('Connection')} "
              f"Sec-WebSocket-Accept={ws.response.headers.get('Sec-WebSocket-Accept')}")
        print(f"[session] sender={sender}")

        for text in messages:
            payload = json.dumps({"sender": sender, "content": text}, ensure_ascii=False)
            sent_at = time.perf_counter()
            await ws.send(payload)
            print(f"  -> {text}")
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=recv_timeout)
            except asyncio.TimeoutError:
                print(f"  <- (超时 {recv_timeout}s，无回应)")
                transcript.append({"sent": text, "received": None, "rtt_ms": None})
                continue
            rtt_ms = round((time.perf_counter() - sent_at) * 1000, 1)
            try:
                answer = json.loads(raw).get("answer")
            except json.JSONDecodeError:
                answer = raw
            print(f"  <- {answer}   ({rtt_ms} ms)")
            transcript.append(
                {"sent": text, "received": answer, "raw": raw, "rtt_ms": rtt_ms}
            )
            await asyncio.sleep(gap)  # 礼貌间隔，别把人家聊天室当压测靶子

        # 主动关闭：发 Close(1000)，等对端 Close 回帧
        await ws.close(code=1000, reason="bye")

    close_info = {
        "close_code": ws.close_code,
        "close_reason": ws.close_reason,
        "clean_close": ws.close_code == 1000,
    }
    print(f"[close] code={ws.close_code} reason={ws.close_reason!r} clean={close_info['clean_close']}")

    return {
        "case": "websocket1",
        "issue": 6,
        "url": WS_URL,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "client": f"websockets/{websockets.__version__}",
        "frame_log_max_size": int(os.environ["WEBSOCKETS_MAX_LOG_SIZE"]),
        "frames_truncated": sum(1 for f in collector.frames if f["truncated"]),
        "sender_uuid": sender,
        "handshake": handshake,
        "app_protocol": {
            "send": {"sender": "<uuid4>", "content": "<text>"},
            "recv": {"sender": "<uuid4 回显>", "answer": "<text>"},
            "note": "端点与格式来自页面 JS：js/chunk-e3bb7ce4.bdd85238.js",
        },
        "transcript": transcript,
        "frames": collector.frames,
        "close": close_info,
        "duration_s": round(time.perf_counter() - t0, 2),
        "raw_log": collector.raw_lines,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="websocket1 一次完整会话 + 帧记录")
    p.add_argument("--messages", nargs="*", default=DEFAULT_MESSAGES)
    p.add_argument("--recv-timeout", type=float, default=15.0)
    p.add_argument("--gap", type=float, default=1.0, help="每条消息之间的间隔秒数")
    args = p.parse_args()

    result = asyncio.run(run(args.messages, args.recv_timeout, args.gap))

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_log = result.pop("raw_log")

    frames_path = EVIDENCE / "session-frames.json"
    frames_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    log_path = EVIDENCE / "session-frames.log"
    log_path.write_text("\n".join(raw_log) + "\n", encoding="utf-8")

    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data" / "chat_transcript.json").write_text(
        json.dumps(result["transcript"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n帧记录 -> {frames_path}")
    print(f"原始日志 -> {log_path}")
    print(f"对话记录 -> {HERE / 'data' / 'chat_transcript.json'}")


if __name__ == "__main__":
    main()
