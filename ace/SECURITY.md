# ACE Security Notes

## Dedicated Telegram bot token

ACE V1 hardening uses a dedicated Telegram Bot API token for `@JACEthaACE_Bot` instead of OpenClaw's shared Telegram bot configuration.

Local secret file:

```text
ace/state/ace-telegram.env
```

Required permissions:

```bash
chmod 600 ace/state/ace-telegram.env
```

Expected keys:

```text
ACE_TELEGRAM_TRANSPORT=telegram_bot_api
ACE_TELEGRAM_BOT_TOKEN=<BotFather token>
ACE_TELEGRAM_CHAT_ID=<operator chat id>
```

The file is ignored by `ace/.gitignore` via `state/*.env` and must never be committed.

## Rotation procedure

If the token is exposed or suspected stale:

1. Open Telegram with `@BotFather`.
2. Run `/revoke`.
3. Select `@JACEthaACE_Bot`.
4. Copy the newly issued token directly into `ace/state/ace-telegram.env`.
5. Re-apply `chmod 600 ace/state/ace-telegram.env`.
6. Verify with `getMe` and a no-conflict `getUpdates` check.
7. Run the ACE test suite and `ace audit verify` before claiming transport ownership is still green.

Do not reuse OpenClaw's shared Telegram bot token for ACE Bot API polling. Shared-token `getUpdates` caused a prior ownership conflict and remains outside the accepted Gate 1 design.
