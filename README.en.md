[中文](README.md) | English

# Muse × Telegram: A Tested Workaround to Get Muse on Telegram

> Meta's personal AI assistant **Muse** currently supports WhatsApp as its only third-party chat channel — official Telegram support is still on the way (see [Background](#background)). This repo documents a **DIY, battle-tested** workaround: bind one Telegram bot to one Muse, then talk to your Muse right inside Telegram.

Battle-tested on 2026-10-03 with `@ifcc8337M_bot`: send/receive loop, owner binding lock, and conversation memory all verified.

---

## What you get

- Talk to the bot on Telegram; your Muse answers on the other end (in your language, remembers your preferences, can search memory).
- One bot = one Muse: create more bots, get more Muses with independent memories.
- A same-named side chat is created in the Muse app; Telegram conversations are mirrored there — pin it as a side-chat log.

## How it works

```
you ←→ Telegram bot ←→ Bot API ←→ [scheduled poll, every 1 min] ←→ side chat (this bot's dedicated memory)
```

- Each bot = one Telegram bot + one side chat + one polling task.
- The polling task pulls `getUpdates` every minute; new messages get a Muse reply, sent back via `sendMessage`.
- Conversations are also appended to a local transcript file; the bot only replies to the locked owner (`allowed_chat_id`).

## Prerequisites

- A Muse account (Meta's personal AI assistant, muse.ai / Muse app).
- A Telegram account.
- Your Muse runtime must be able to reach `https://api.telegram.org`.

## Step by step

### 1. Create the bot

Find [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and follow the prompts (display name is free; the username must end in `bot`, e.g. `my_muse_bot`). Save the **token** it gives you.

> ⚠️ **Security warning**: never screenshot or forward the token into any chat — a screenshot IS a leak. If leaked, go back to @BotFather and send `/revoke` to kill the old token. (Don't ask how I know.)

### 2. Hand the token to Muse (via Secure Vault, never through chat)

Create a custom API credential in Muse:

- provider: `telegram` (stored as `custom.telegram`)
- auth: API key placed in the URL path (Telegram Bot API format: `https://api.telegram.org/bot<token>/METHOD`)
- allowed host: `api.telegram.org`

Then fill in the token on the secure form. From then on the token lives only in the vault — injected by the system at call time, never written to disk, never in chat logs.

### 3. Drop in the `tg.py` tool

[`tg.py`](./tg.py) in this repo (Python standard library only) is the send/receive CLI:

```bash
python3 tg.py getme                                  # verify credentials, returns bot identity
python3 tg.py poll --state state.json                # pull new messages (JSON), auto-advances offset
python3 tg.py send <chat_id> <text>                  # send a message, auto-splits over 4000 chars
python3 tg.py send-quote <chat_id> <label> <text>    # send a quoted message (see "Advanced")
```

It relies on the Muse runtime's `dynamic_credentials` helper for credential injection. Run `getme` first — if it returns your bot's username, you're good.

> 🐛 **Gotcha**: the scaffold-generated `url_with_surrogate_path_segment` URL-encodes the colon in the credential to `%3A`, which breaks injection and Telegram returns 404. `tg.py` builds the URL by hand (colon kept as-is) — don't "fix" it back.

### 4. Create a dedicated side chat

Create a side chat in Muse (e.g. `TG @my_muse_bot`) as this bot's dedicated memory. Note its chat id.

### 5. Create the polling task

Create a scheduled task (every 1 minute); the task body is in [`cron-example.en.md`](./cron-example.en.md). Key points:

- Pull new messages: `tg.py poll --state <state.json>`
- No new messages → end quietly. New messages:
  1. If `allowed_chat_id` isn't locked yet, write the first message's `chat_id` into state, then send a binding confirmation;
  2. Only reply to `allowed_chat_id`;
  3. Read the transcript for context, reply in the user's language, send via `tg.py send`;
  4. Append the exchange to the transcript.
- See [`state.example.json`](./state.example.json) for the state file format.

> Note: each worker run takes ~1 minute, so the 1-minute schedule merges — expect roughly one round every 2–3 minutes. That's normal; no messages are lost.

### 6. Send the first message to verify

Say "hi" to the bot on Telegram; you should get the binding confirmation within 1–3 minutes. From then on, just talk to it there.

---

## Advanced (optional)

### Quote blocks to tell speakers apart

Everything the bot sends appears as the bot. If you mirror things you said elsewhere (e.g. in the side chat) verbatim, readers can't tell who said what. `tg.py send-quote` wraps text in a quote block:

```bash
python3 tg.py send-quote <chat_id> "💬 You said in Muse" "<original text>"
```

Result: your words show as a labeled quote; the bot's own replies stay plain.

### Reverse sync (side chat → Telegram)

Add a second poller that pushes new side-chat messages to Telegram for two-way sync. Four hard rules (all paid for with real incidents, see below):

1. The ONLY allowed message source is reading the side chat. If it can't be read, skip the round — **never** fall back to the transcript.
2. Echo guard: never send text that already appears in the transcript.
3. Record the watermark (processed-up-to timestamp) verbatim — never invent one.
4. Skip the poller's own status reports and "no updates" noise.

We later turned it off ("the side chat should be a pure mirror of Telegram"); re-enable any time.

---

## Gotchas

| # | Pit | Lesson |
|---|-----|--------|
| 1 | Token ended up in a chat screenshot | Only fix is `/revoke`; tokens go through the secure form only |
| 2 | Official helper URL-encodes the credential colon to `%3A`, Telegram returns 404 | Build the URL by hand, keep the colon |
| 3 | Reverse poller couldn't read the side chat, fell back to the transcript, and re-sent the Telegram Q&A (user got duplicates) | Lock the source + echo guard + verbatim watermark (see "Advanced") |
| 4 | 1-minute schedule but each worker run takes 1+ minute | Rounds merge; ~2–3 min per round is normal |

## Limitations

- Minute-level latency, not realtime.
- Text first; voice, buttons, and other media later.
- The bot can only send as itself.
- Each bot has independent memory; bots don't share by default (add a shared room if you want that).

## Background

- Meta is preparing official Muse access for Telegram/Messenger/Signal (TestingCatalog, Sep 2026); hidden entry points already exist in the web UI. This repo is the workaround until that ships.
- Manus (acquired by Meta) already launched on Telegram (QR-code binding) — an official precedent.
- The community repo [awesome-muse-connectors](https://github.com/anil-matcha/awesome-meta-muse-agent) lists 150+ Muse connectors, including a Telegram draft — untested end-to-end and carrying gotcha #2 above.

## Files

| File | Description |
|------|-------------|
| `tg.py` | Send/receive CLI (battle-tested 2026-10-03) |
| `cron-example.md` / `cron-example.en.md` | Polling task config (Chinese / English) |
| `state.example.json` | State file example |
| `.gitignore` | Reminder: never commit real state/transcripts |

## License

MIT
