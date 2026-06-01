from flask import Blueprint, current_app, jsonify, request

from .agora import AgoraChatRestClient, AgoraNotConfigured
from .chatbot import ChatbotEngine
from .push import FcmPusher
from .security import verify_meta_signature
from .store import Message, Store, User
from .whatsapp import WhatsAppClient, is_bot_mentioned, parse_incoming, strip_mention

bp = Blueprint("webhooks", __name__)


def _engine() -> ChatbotEngine:
    return current_app.extensions["chatbot_engine"]


def _bridge_bot_reply_to_agora_chat(
    *,
    chat_rest: AgoraChatRestClient | None,
    store: Store,
    group_id: str | None,
    sender_id: str,
    reply_text: str,
) -> None:
    """Best-effort: republish a WhatsApp-triggered bot reply into Agora Chat.

    This is how in-app users see bot replies that were caused by a WhatsApp
    message. Inbound WhatsApp user messages themselves are NOT bridged into
    Agora Chat (would cause our own /webhooks/agora to fire and double-process
    them); they stay visible via /api/.../messages history instead.
    """
    if chat_rest is None:
        return
    if not (chat_rest.config.chat_is_configured and chat_rest.config.chat_app_token):
        return
    try:
        if group_id:
            group = store.get_group(group_id)
            if group and group.agora_chat_group_id:
                chat_rest.send_to_group(
                    from_user="bot",
                    group_id=group.agora_chat_group_id,
                    text=reply_text,
                )
        else:
            chat_rest.send_text(
                from_user="bot",
                to_user=sender_id,
                text=reply_text,
            )
    except (AgoraNotConfigured, Exception):
        # Bridging is best-effort. The bot reply already went out on WhatsApp;
        # in-app live mirroring is a nice-to-have, not the source of truth.
        current_app.logger.warning("Agora Chat bridge for bot reply failed",
                                   exc_info=True)


@bp.get("/whatsapp")
def verify():
    """Meta calls this once during webhook setup with a hub.challenge."""
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    expected = current_app.config["WHATSAPP_VERIFY_TOKEN"]
    if mode == "subscribe" and token and expected and token == expected:
        return challenge or "", 200
    return "forbidden", 403


@bp.post("/whatsapp")
def inbound():
    """Incoming message webhook from WhatsApp Business API."""
    raw = request.get_data(cache=True)
    if not verify_meta_signature(
        current_app.config["META_APP_SECRET"],
        raw,
        request.headers.get("X-Hub-Signature-256"),
    ):
        return jsonify(error="invalid signature"), 403

    payload = request.get_json(silent=True) or {}
    messages = parse_incoming(payload)

    store: Store = current_app.extensions["store"]
    pusher: FcmPusher = current_app.extensions["pusher"]
    engine = _engine()
    chat_rest: AgoraChatRestClient | None = current_app.extensions.get("agora_chat_rest")
    client = WhatsAppClient.from_app(current_app)
    mention = current_app.config.get("BOT_MENTION_NAME", "@bot")

    handled = 0
    for msg in messages:
        user_id = msg["from"]
        group_id = msg.get("group_id")
        session_key = group_id or user_id
        raw_text = msg["text"]

        sender = store.upsert_user(User(user_id=user_id))
        store.append_message(Message(
            session_key=session_key,
            user_id=user_id,
            direction="in",
            text=raw_text,
            media_url=msg.get("media_id"),
            media_type=msg.get("media_type"),
            caption=msg.get("caption"),
            sender_id=user_id,
            sender_name=sender.name,
        ))
        handled += 1

        # In a WhatsApp group, only respond when explicitly mentioned —
        # the bot must not chime in on every message.
        if group_id and not is_bot_mentioned(raw_text, mention):
            continue

        text_for_bot = strip_mention(raw_text, mention) if group_id else raw_text
        reply = engine.handle(
            user_id=user_id,
            text=text_for_bot,
            group_id=group_id,
        )
        if not reply:
            continue

        store.append_message(Message(
            session_key=session_key,
            user_id=user_id,
            direction="out",
            text=reply,
            sender_id="bot",
            sender_name="Bot",
        ))
        # Group replies are broadcast back into the group itself (one send,
        # every member sees it). 1:1 replies go to the sender.
        client.send_text(to=group_id or user_id, body=reply)

        # Mirror the bot reply into Agora Chat so in-app users see it live.
        _bridge_bot_reply_to_agora_chat(
            chat_rest=chat_rest,
            store=store,
            group_id=group_id,
            sender_id=user_id,
            reply_text=reply,
        )

        push_recipients: list[str]
        if group_id:
            group = store.get_group(group_id)
            push_recipients = list(group.members) if group else []
        else:
            push_recipients = [user_id]

        for recipient in push_recipients:
            pusher.push(
                user_id=recipient,
                title="Student Chatbot",
                body=reply[:120],
                data={
                    "session_key": session_key,
                    "kind": "reply",
                },
            )

    return jsonify(received=handled), 200
