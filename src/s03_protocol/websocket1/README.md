> issue: #6 · 案例: websocket1 · 来源: https://websocket1.scrape.center

## 案例描述（逐字引自 scrape.center）

> WebSocket 单人聊天室，适合做 WebSocket 抓包分析。

---

## 一、结论速览

| 项 | 实测结果 |
|---|---|
| 端点 | `wss://websocket1.scrape.center/websocket` |
| 握手 | `HTTP/1.1 101 Switching Protocols` |
| 扩展 | `permessage-deflate; server_max_window_bits=12; client_max_window_bits=12` |
| 子协议 | 无（`subprotocol: null`） |
| 应用层协议 | 发 `{"sender","content"}` → 收 `{"sender","answer"}`，纯 JSON |
| 服务端行为 | echo + 追加一个 `!`，固定延迟约 **1.07 s** |
| 会话帧数 | 10 帧（8 TEXT + 2 CLOSE），**0 帧被截断** |
| 关闭 | 双向 `CLOSE 1000 (OK) bye`，`clean_close: true` |

---

## 二、脚本与产物

```
websocket1/
├── chat_session.py         # 握手 → 收发 → 主动关闭，全程记帧
├── data/
│   └── chat_transcript.json    # 4 轮对话（发了什么/收到什么/RTT）
└── evidence/
    ├── session-frames.json     # 握手头 + 逐帧记录 + 关闭信息（结构化）
    └── session-frames.log      # websockets 库的原始日志（逐字保留）
```

复跑：

```bash
python chat_session.py                       # 默认发 4 条
python chat_session.py --messages 你好 再见   # 自定义消息
```

---

## 三、握手：一次「伪装成 HTTP 的升级请求」

WebSocket 握手就是一个带特殊头的 HTTP/1.1 GET，服务端答 `101` 之后同一条 TCP
连接就不再说 HTTP 了。原始日志（`evidence/session-frames.log`）逐字保留：

```
> GET /websocket HTTP/1.1
> Host: websocket1.scrape.center
> Upgrade: websocket
> Connection: Upgrade
> Sec-WebSocket-Key: 0cgfYsfOO+jNH7XFYibccA==
> Sec-WebSocket-Version: 13
> Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits
> User-Agent: Python/3.14 websockets/17.0.1
< HTTP/1.1 101 Switching Protocols
< Date: Sun, 23 Aug 2026 10:19:04 GMT
< Connection: upgrade
< Upgrade: websocket
< Sec-WebSocket-Accept: s85ZiXChCUX1YLSu0UR3NTRvEZA=
< Sec-WebSocket-Extensions: permessage-deflate; server_max_window_bits=12; client_max_window_bits=12
< Strict-Transport-Security: max-age=15724800; includeSubDomains
```

几个要点：

- `Sec-WebSocket-Key` 是客户端随机生成的 16 字节 base64；服务端把它拼上固定 GUID
  `258EAFA5-E914-47DA-95CA-C5AB0DC85B11` 做 SHA-1 再 base64，得到 `Sec-WebSocket-Accept`。
  这不是安全机制，只是证明对面**确实懂 WebSocket 协议**、不是个傻缓存。
  本次握手已本地复算验证通过：

  ```python
  base64.b64encode(hashlib.sha1((key + GUID).encode()).digest())
  # key='0cgfYsfOO+jNH7XFYibccA==' -> 's85ZiXChCUX1YLSu0UR3NTRvEZA='  与服务端返回一致
  ```
- 服务端把 `client_max_window_bits` 砍到 12（客户端没指定具体值），
  即 LZ77 滑动窗口 4 KB —— 省内存，压缩率略降。
- **注意与 spa16 的对比**：WebSocket 走的是 HTTP/1.1 Upgrade。
  HTTP/2 上的 WebSocket 是另一套机制（RFC 8441 的 `:protocol` 扩展 CONNECT），
  本站用的是经典 h1.1 路线。

---

## 四、应用层协议怎么摸出来的

握手成功只代表管道通了，**发什么内容得自己找**。端点与 JSON 结构来自页面 JS
（`js/chunk-e3bb7ce4.bdd85238.js`）：客户端每条消息发

```json
{"sender": "<uuid4>", "content": "<文本>"}
```

服务端回

```json
{"sender": "<原样回显的 uuid4>", "answer": "<文本>!"}
```

`sender` 是前端生成的 uuid4，用来在「单人聊天室」里区分自己和别人的气泡。
服务端逻辑就是 echo 后面加个 `!`——四条消息全部验证：

| 发送 | 收到 | RTT |
|---|---|---|
| `hello` | `hello!` | 1067.4 ms |
| `你好，我是来做 WebSocket 抓包分析的` | `你好，我是来做 WebSocket 抓包分析的!` | 1073.0 ms |
| `What is the weather like?` | `What is the weather like?!` | 1069.5 ms |
| `bye` | `bye!` | 1069.4 ms |

四条 RTT 都在 1067–1073 ms，方差不到 6 ms —— 这是**服务端故意 sleep 1 秒**模拟「机器人思考」，
不是网络延迟（网络往返只占其中几十毫秒，见握手耗时）。

---

## 五、帧记录是怎么拿到的

`websockets` 库在 DEBUG 级别会把每一帧打成 `> TEXT '...' [70 bytes]` 这样的行。
脚本挂了一个 `logging.Handler` 把这些行截下来，解析成结构化帧记录。

**一个坑**：库默认把 payload 截断到 75 字符（`MAX_LOG_SIZE`），截断过的记录算不上
「完整帧记录」。这个上限读环境变量、且在 import 时求值，所以必须**在 `import websockets` 之前**设：

```python
os.environ.setdefault("WEBSOCKETS_MAX_LOG_SIZE", "4096")
import websockets
```

产物里 `frames_truncated: 0` 就是「确实没截断」的自证字段。

10 帧完整记录（方向 / opcode / payload / 字节数 / 时间戳）：

```
client->server TEXT  70B  {"sender": "...", "content": "hello"}
server->client TEXT  70B  {"sender": "...", "answer": "hello!"}
client->server TEXT 112B  {"sender": "...", "content": "你好，我是来做 WebSocket 抓包分析的"}
server->client TEXT 112B  {"sender": "...", "answer": "你好，我是来做 WebSocket 抓包分析的!"}
client->server TEXT  90B  {"sender": "...", "content": "What is the weather like?"}
server->client TEXT  90B  {"sender": "...", "answer": "What is the weather like?!"}
client->server TEXT  68B  {"sender": "...", "content": "bye"}
server->client TEXT  68B  {"sender": "...", "answer": "bye!"}
client->server CLOSE  5B  1000 (OK) bye
server->client CLOSE  5B  1000 (OK) bye
```

没有 PING/PONG —— 会话只有 8.85 秒，没触到 `websockets` 的心跳间隔
（`ping_interval` 默认 20 秒，已查库签名确认）。

---

## 六、正确关闭连接

「关闭」不是把 socket 一扔。WebSocket 的关闭握手是**双向**的：

1. 客户端发 `CLOSE` 帧，带 code=1000（正常关闭）和 reason；
2. 客户端进入 `CLOSING`，**继续读**，等对端的 CLOSE 回帧；
3. 收到对端 CLOSE 后才关 TCP。

原始日志清楚记下这个序列：

```
> CLOSE 1000 (OK) bye [5 bytes]
= connection is CLOSING
< CLOSE 1000 (OK) bye [5 bytes]
> EOF
= connection is CLOSED
x closing TCP connection
```

`close_code=1000` + `clean_close=true` 是「正常关闭」的判据。
如果直接断 TCP，对端只会看到 `1006 abnormal closure`——那是异常，不是关闭。

CLOSE 帧的 payload 是 5 字节：2 字节大端 code（1000）+ 3 字节 UTF-8 reason（`bye`）。

---

## 七、抓取纪律

- 每条消息间隔 1 s（`--gap`），默认只发 4 条，不把人家聊天室当压测靶子。
- 收消息带 15 s 超时，不无限挂着占连接。
- 每次运行都主动做完关闭握手，不留半开连接。
