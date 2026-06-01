"""Agora Chat callback receiver.

When you enable "Chat Pre/Post Callbacks" in the Agora Console, Agora POSTs
the event to your configured URL. We accept the post-send (`chat`) variant
and dispatch:

  - msg.to == "bot" (1:1): invoke ChatbotEngine.handle → reply via REST.
  - chat_type == "groupchat" + @bot mention: same.
  - everything else: persist to Store only (so /api/groups/.../messages stays
    a usable history fallback) and exit.

Auth: Agora's docs describe a `signature` header that's MD5 of
`callback_id + AGORA_CHAT_WEBHOOK_SECRET + timestamp`. We accept either:
  - `Signature` header MD5(secret + raw_body) — the modern variant
  - Empty `AGORA_CHAT_WEBHOOK_SECRET` env: signature check is skipped (dev-only).

Configure the secret in Console → Chat → Callback Settings.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

from flask import Blueprint, current_app, jsonify, request

from .chatbot import ChatbotEngine
from .store import Message, Store, User
from .whatsapp import is_bot_mentioned, strip_mention

log = logging.getLogger(__name__)

bp = Blueprint("agora_webhook", __name__)


def _signature_ok(secret: str, raw_body: bytes, supplied: str | None) -> bool:
    """Verify Agora's `signature` header.

    Empty secret = dev mode, signature check is skipped. We try both MD5
    (Agora's documented hash) and HMAC-SHA256 (newer variants) — whichever
    matches, the request is authenticated.
    """
    if not secret:
        log.warning("AGORA_CHAT_WEBHOOK_SECRET unset; skipping signature check")
        return True
    if not supplied:
        return False
    expected_md5 = hashlib.md5(secret.encode() + raw_body).hexdigest()
    if hmac.compare_digest(expected_md5, supplied.lower().strip()):
        return True
    expected_hmac = hmac.new(
        secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_hmac, supplied.lower().strip())


def _extract_text(payload: dict) -> str:
    """Pull the first text body out of an Agora Chat message payload."""
    body = payload.get("payload") or {}
    bodies = body.get("bodies") if isinstance(body, dict) else None
    if not isinstance(bodies, list):
        return ""
    for item in bodies:
        if isinstance(item, dict) and item.get("type") == "txt":
            msg = item.get("msg")
            if isinstance(msg, str):
                return msg
    return ""


@bp.post("/agora")
def inbound():
    """Receive an Agora Chat post-send callback.
    ---
    tags: [webhooks]
    """
    raw = request.get_data(cache=True)
    secret = os.environ.get("AGORA_CHAT_WEBHOOK_SECRET", "").strip()
    if not _signature_ok(secret, raw, request.headers.get("Signature")):
        return jsonify(error="invalid signature"), 403

    try:
        envelope = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return jsonify(error="malformed JSON"), 400
    if not isinstance(envelope, dict):
        return jsonify(error="envelope must be a JSON object"), 400

    sender = (envelope.get("from") or "").strip()
    target = (envelope.get("to") or "").strip()  # 1:1 recipient or group id
    chat_type = (envelope.get("chat_type") or "").strip().lower()
    text = _extract_text(envelope)

    if not sender or not text:
        return jsonify(received=0), 200

    # Ignore messages the bot itself sent — otherwise we'd loop forever.
    if sender == "bot":
        return jsonify(received=0, skipped="self"), 200

    store: Store = current_app.extensions["store"]
    engine: ChatbotEngine = current_app.extensions["chatbot_engine"]
    chat_rest = current_app.extensions.get("agora_chat_rest")
    mention = current_app.config.get("BOT_MENTION_NAME", "@bot")

    # Persist every message for history + WhatsApp bridge consistency.
    user = store.upsert_user(User(user_id=sender))
    session_key = target if chat_type == "groupchat" else sender
    store.append_message(Message(
        session_key=session_key,
        user_id=sender,
        direction="in",
        text=text,
        sender_id=sender,
        sender_name=user.name,
    ))

    should_reply = False
    bot_input = text
    if chat_type == "chat" and target == "bot":
        should_reply = True
    elif chat_type == "groupchat" and is_bot_mentioned(text, mention):
        should_reply = True
        bot_input = strip_mention(text, mention)

    if not should_reply:
        return jsonify(received=1, replied=False), 200

    reply_text = engine.handle(
        user_id=sender,
        text=bot_input,
        group_id=target if chat_type == "groupchat" else None,
    )
    if not reply_text:
        return jsonify(received=1, replied=False), 200

    store.append_message(Message(
        session_key=session_key,
        user_id=sender,
        direction="out",
        text=reply_text,
        sender_id="bot",
        sender_name="Bot",
    ))

    posted = False
    if chat_rest is not None:
        try:
            if chat_type == "groupchat":
                posted = chat_rest.send_to_group(
                    from_user="bot", group_id=target, text=reply_text,
                )
            else:
                posted = chat_rest.send_text(
                    from_user="bot", to_user=sender, text=reply_text,
                )
        except Exception as exc:
            log.warning("Agora Chat bot reply failed: %s", exc)
            posted = False

    return jsonify(received=1, replied=True, posted=posted), 200
