# Muse × Telegram：把 Muse 接到 Telegram 的平替方案

> Meta 的个人 AI 助手 **Muse** 目前只支持 WhatsApp 作为第三方聊天通道，
> Telegram 官方接入还在路上（见[背景](#背景)）。这个仓库记录了一套**自己动手、
> 真机验证通过**的平替方案：一个 Telegram 机器人绑定一个 Muse，在 Telegram 里
> 直接跟你的 Muse 说话、派活。

真机验证：2026-10-03，`@ifcc8337M_bot`，收发闭环、绑定锁定、对话记忆全部通过。

---

## 效果

- 在 Telegram 里跟机器人说话，背后是你的 Muse 在回（中文、记得你的偏好、能查记忆）。
- 一个机器人绑定一个 Muse：多建几个机器人，就有几个独立记忆的 Muse。
- 在 Muse App 里会自动生成一个同名 side chat，Telegram 的对话会镜像进去，可置顶当旁聊记录看。

## 原理

```
你 ←→ Telegram 机器人 ←→ Bot API ←→ [定时轮询，每 1 分钟] ←→ side chat（该 bot 的专属记忆）
```

- 每个 bot = 一个 Telegram 机器人 + 一个 side chat + 一个轮询任务。
- 轮询任务每分钟拉 `getUpdates`，有新消息就让 Muse 回复，再经 `sendMessage` 发回去。
- 对话记录同时落盘一份（`transcript/`），机器人只回复锁定的主人（`allowed_chat_id`）。

## 前置条件

- 一个 Muse 账号（Meta 的个人 AI 助手，muse.ai / Muse App）。
- 一个 Telegram 账号。
- 你的 Muse 运行环境能出访 `https://api.telegram.org`。

## 手把手步骤

### 1. 建机器人

在 Telegram 里找 [@BotFather](https://t.me/BotFather)，发 `/newbot`，
按提示起名字（显示名随意，用户名必须以 `bot` 结尾，如 `my_muse_bot`）。
记下它给你的 **token**。

> ⚠️ **安全警告**：token 千万别截图、别转发到任何聊天里——截图即泄露。
> 泄露后只能回 @BotFather 发 `/revoke` 作废旧 token 换新。（别问我怎么知道的。）

### 2. 把 token 交给 Muse（走 Secure Vault，不经过聊天）

在 Muse 里创建一个自定义 API 凭证：

- provider：`telegram`（会存成 `custom.telegram`）
- 认证方式：API key，放在 URL path 里（Telegram Bot API 的格式是
  `https://api.telegram.org/bot<token>/METHOD`）
- 允许的 host：`api.telegram.org`

然后在安全表单里填入 token。token 从此只活在保险库里，
调用时由系统注入，绝不落盘、不进聊天记录。

### 3. 放收发工具 `tg.py`

本仓库的 [`tg.py`](./tg.py)（只用 Python 标准库）是收发 CLI：

```bash
python3 tg.py getme                                  # 验凭证，返回 bot 身份
python3 tg.py poll --state state.json                # 拉新消息（JSON），自动推进 offset
python3 tg.py send <chat_id> <text>                  # 发消息，超长自动分段
python3 tg.py send-quote <chat_id> <label> <text>    # 发引用框消息（见"进阶"）
```

它依赖 Muse 运行时的 `dynamic_credentials` helper 做凭证注入。
先跑 `getme`，返回你的 bot 用户名即成功。

> 🐛 **踩坑**：官方 scaffold 生成的 `url_with_surrogate_path_segment`
> 会把凭证里的冒号编码成 `%3A`，导致注入失败、Telegram 回 404。
> `tg.py` 里是手动拼接 URL（冒号保持原样），不要改回去。

### 4. 建专属 side chat

在 Muse 里新建一个 side chat（比如叫 `TG @my_muse_bot`），
作为这个机器人的专属记忆空间。记下它的 chat id。

### 5. 建轮询任务

建一个每 1 分钟运行的定时任务，任务内容见 [`cron-example.md`](./cron-example.md)，
要点：

- 拉新消息：`tg.py poll --state <state.json>`
- 没有新消息就安静结束；有新消息则：
  1. 如果 `allowed_chat_id` 还没锁定，把第一条消息的 `chat_id` 写进去，
     先回一条绑定确认；
  2. 只回 `allowed_chat_id` 发来的消息；
  3. 读对话记录找上下文、回中文、经 `tg.py send` 发回；
  4. 把问答追加到对话记录。
- 状态文件示例见 [`state.example.json`](./state.example.json)。

> 说明：worker 每轮实际跑 1 分多钟，1 分钟的排期会被合并，
> 实际约 2–3 分钟一轮，属正常现象，不丢消息。

### 6. 发第一句话验证

在 Telegram 里给机器人发"你好"，1–3 分钟内应该收到绑定确认。
从此直接在 Telegram 里跟它说话就行。

---

## 进阶（可选）

### 用引用框区分身份

机器人发出去的消息都显示为它自己发的。如果把别处（比如 side chat）
同步过来的"你说的话"也原样发出，会分不清谁说的。
`tg.py send-quote` 把文字包进引用框：

```bash
python3 tg.py send-quote <chat_id> "💬 你在 Muse 里说" "<原文>"
```

效果：你的话显示为带标签的引用块，机器人自己的回复保持原样。

### 反向同步（side chat → Telegram）

再建一个轮询，把 side chat 里新产生的对话也推到 Telegram，即双向同步。
注意三条铁律（都是拿事故换来的，见下）：

1. 消息来源**只许**从 side chat 读；读不到就跳过本轮，**绝不**拿对话记录凑数。
2. 回声兜底：正文在记录里出现过的，绝不发第二遍。
3. 水位（已处理到的时间戳）原样记录，不许编造。
4. 跳过轮询器自己的工作汇报和"无更新"噪音。

我们后来因为"只想让 side chat 做 Telegram 的纯镜像"把它关掉了，需要时重开即可。

---

## 踩坑记录

| # | 坑 | 教训 |
|---|----|------|
| 1 | token 截图进了聊天记录 | 只能 `/revoke` 作废；token 只走安全表单 |
| 2 | 官方 helper 把凭证冒号编码成 `%3A`，Telegram 回 404 | 手动拼接 URL，冒号保持原样 |
| 3 | 反向轮询读不到 side chat，改读 transcript，把 TG 问答又回发了一遍（用户收到重复消息） | 来源锁定 + 回声兜底 + 水位原样（见"进阶"） |
| 4 | 轮询排期 1 分钟但 worker 跑 1 分多钟 | 会被合并，实际 2–3 分钟一轮，正常 |

## 局限

- 分钟级延迟，不是实时的。
- 先只做文字；语音、按钮等多媒体以后再说。
- 机器人只能以自己的身份发消息。
- 每个 bot 背后是独立记忆，bot 之间默认不互通（想互通可以再搭一个公共会议室）。

## 背景

- Meta 正在准备 Muse 的 Telegram/Messenger/Signal 官方接入（TestingCatalog 2026-09 报道），
  Web UI 里已有隐藏入口。本方案是官方上线前的平替。
- Meta 收购的 Manus 已上线 Telegram（扫码绑定），是官方先例。
- 社区仓库 [awesome-muse-connectors](https://github.com/anil-matcha/awesome-meta-muse-agent)
  收录了 150+ Muse 连接器（含一个 Telegram draft，但没经过真机测试，且有上表第 2 个 bug）。

## 文件

| 文件 | 说明 |
|------|------|
| `tg.py` | 收发 CLI（真机验证过，2026-10-03） |
| `cron-example.md` | 轮询任务配置示例 |
| `state.example.json` | 状态文件示例 |
| `.gitignore` | 提醒：真 state/transcript 不要提交 |

## License

MIT
