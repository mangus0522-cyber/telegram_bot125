#!/usr/bin/env python3
"""
Telegram Slideshow Bot (EXPERIMENTAL)
========================================

Posts photos using Telegram's brand-new "Rich Messages" feature
(sendRichMessage + a slideshow block), added to the Bot API in mid-2026.
This is the format that shows ONE photo, full-screen, with NO thumbnail
strip -- you only see the next photo after swiping. Same idea as an
Instagram carousel.

This is different from album_bot.py (which uses the older, well-proven
sendMediaGroup and always shows thumbnails).

IMPORTANT -- read this first
-------------------------------
This feature is very new. If something doesn't work, it is likely because:
  - Telegram is still rolling this feature out and it isn't live for your
    account/chat yet, or
  - the exact data format has details not yet reflected in public docs.
If you hit errors, tell me the exact error text and we'll adjust.

Setup
-----
1. Talk to @BotFather -> /newbot -> copy the token.
2. export BOT_TOKEN="123456:ABC-your-token-here"
3. python3 slideshow_bot.py

Usage inside Telegram
-----------------------
  Send the bot photos, one by one (up to 10).
  /caption <text>   optional caption shown with the slideshow
  /target <@chat>   post somewhere else (bot must be admin there)
  /post             publish the slideshow
  /status           show what's queued
  /clear            empty the queue
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not TOKEN:
    sys.exit("BOT_TOKEN is not set. Run: export BOT_TOKEN='your-token'")

API = "https://api.telegram.org/bot{}/".format(TOKEN)
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slideshow_bot_state.json")
MAX_PHOTOS = 10
MIN_PHOTOS = 2


# --------------------------------------------------------------------------
# Telegram API plumbing
# --------------------------------------------------------------------------

def call(method, **params):
    http_timeout = params.get("timeout", 10) + 15
    body = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(
        API + method,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            payload = json.load(e)
        except Exception:
            print("HTTP error on {}: {}".format(method, e))
            return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print("network hiccup on {}: {}".format(method, e))
        return None

    if not payload.get("ok"):
        print("API error on {}: {}".format(method, payload.get("description")))
        return {"__error__": payload.get("description")}
    return payload["result"]


def say(chat_id, text):
    call("sendMessage", chat_id=chat_id, text=text)


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)


STATE = load_state()


def queue_for(chat_id):
    key = str(chat_id)
    if key not in STATE:
        STATE[key] = {"photos": [], "caption": None, "target": None}
    return STATE[key]


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

HELP = (
    "EXPERIMENTAL: full-screen slideshow, no thumbnails (Telegram's newest "
    "photo format).\n\n"
    "Send me photos (2-10), then /post.\n\n"
    "/caption <text> — caption for the slideshow\n"
    "/target @chat — post elsewhere (I must be admin there)\n"
    "/status — what's queued\n"
    "/clear — empty the queue\n"
    "/post — publish"
)


def add_photo(chat_id, message):
    q = queue_for(chat_id)
    if len(q["photos"]) >= MAX_PHOTOS:
        say(chat_id, "Queue is full at {} photos. /post or /clear.".format(MAX_PHOTOS))
        return

    file_id = message["photo"][-1]["file_id"]
    q["photos"].append(file_id)
    save_state(STATE)

    n = len(q["photos"])
    if n == MAX_PHOTOS:
        say(chat_id, "10/10 — queue full. Send /post to publish.")
    else:
        say(chat_id, "Photo {}/{} queued.".format(n, MAX_PHOTOS))


def build_rich_message(photos, caption):
    """Build the JSON structure for a slideshow rich message."""
    slide_blocks = [
        {
            "type": "photo",
            "photo": {"type": "photo", "media": file_id},
        }
        for file_id in photos
    ]

    slideshow_block = {
        "type": "slideshow",
        "blocks": slide_blocks,
    }
    if caption:
        slideshow_block["caption"] = {"text": caption}

    return {"blocks": [slideshow_block]}


def do_post(chat_id):
    q = queue_for(chat_id)
    photos = q["photos"]

    if len(photos) < MIN_PHOTOS:
        say(chat_id, "Need at least 2 photos. You have {}.".format(len(photos)))
        return

    destination = q["target"] or chat_id
    rich_message = build_rich_message(photos, q["caption"])

    result = call("sendRichMessage", chat_id=destination, rich_message=rich_message)

    if result is None or "__error__" in (result or {}):
        err = (result or {}).get("__error__", "unknown error")
        say(chat_id,
            "Couldn't post the slideshow. Telegram said: {}\n\n"
            "This is a very new feature — this error likely means it isn't "
            "fully available yet for this account/chat, or the exact format "
            "needs a small adjustment. Tell me this exact message and we'll "
            "fix it.".format(err))
        return

    q["photos"] = []
    q["caption"] = None
    save_state(STATE)
    say(chat_id, "Posted {} photos as a slideshow.".format(len(photos)))


def handle_command(chat_id, text):
    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    q = queue_for(chat_id)

    if cmd in ("/start", "/help"):
        say(chat_id, HELP)

    elif cmd == "/caption":
        q["caption"] = arg or None
        save_state(STATE)
        say(chat_id, "Caption set." if arg else "Caption cleared.")

    elif cmd == "/target":
        q["target"] = arg or None
        save_state(STATE)
        say(chat_id, "Target set to {}.".format(arg) if arg else "Target cleared.")

    elif cmd == "/status":
        say(chat_id, "Photos: {}/{}\nCaption: {}\nTarget: {}".format(
            len(q["photos"]), MAX_PHOTOS,
            q["caption"] or "(none)",
            q["target"] or "this chat",
        ))

    elif cmd == "/clear":
        q["photos"] = []
        q["caption"] = None
        save_state(STATE)
        say(chat_id, "Queue emptied.")

    elif cmd == "/post":
        do_post(chat_id)

    else:
        say(chat_id, "Unknown command. /help for the list.")


def handle_update(update):
    message = update.get("message") or update.get("channel_post")
    if not message:
        return
    chat_id = message["chat"]["id"]

    if "photo" in message:
        add_photo(chat_id, message)
    elif message.get("text", "").startswith("/"):
        handle_command(chat_id, message["text"])


# --------------------------------------------------------------------------
# Long-polling loop
# --------------------------------------------------------------------------

def main():
    me = call("getMe")
    if not me:
        sys.exit("Couldn't reach Telegram. Check the token and your connection.")
    print("Running as @{}. Ctrl-C to stop.".format(me["username"]))

    offset = None
    while True:
        try:
            updates = call("getUpdates", offset=offset, timeout=50,
                            allowed_updates=["message", "channel_post"])
        except KeyboardInterrupt:
            print("\nStopped.")
            return

        if updates is None:
            time.sleep(3)
            continue

        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle_update(update)
            except Exception as e:
                print("error handling update {}: {}".format(update["update_id"], e))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
