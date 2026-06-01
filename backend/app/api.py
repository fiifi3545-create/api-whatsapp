"""REST API for the Flutter companion app.

All endpoints under `/api/*` require a Bearer JWT issued by
`POST /api/auth/verify-otp`, except `/api/auth/*` and `/api/config`.
Routes with a `<user_id>` path parameter additionally enforce that the JWT
subject matches the path's user_id.
"""
from __future__ import annotations

import logging

import requests
from flask import Blueprint, Response, current_app, g, jsonify, request

from .auth import require_auth
from .chatbot import ChatbotEngine
from .groups import GroupService
from .push import FcmPusher
from .store import Device, Group, Message, Store, User
from .whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

bp = Blueprint("api", __name__)


def _store() -> Store:
    return current_app.extensions["store"]


def _groups() -> GroupService:
    chat_rest = current_app.extensions.get("agora_chat_rest")
    # Only mirror to Agora Chat when REST is actually usable. Saves a noisy
    # log on every group action in dev when AGORA_CHAT_APP_TOKEN is empty.
    mirror = chat_rest if (
        chat_rest is not None
        and chat_rest.config.chat_is_configured
        and chat_rest.config.chat_app_token
    ) else None
    return GroupService(_store(), chat_mirror=mirror)


def _engine() -> ChatbotEngine:
    # Shared singleton (created in create_app) so REST + WS + webhook all see
    # the same in-process conversation-history cache.
    return current_app.extensions["chatbot_engine"]


def _user_json(user: User) -> dict:
    return {
        "user_id": user.user_id,
        "name": user.name,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _group_json(group: Group) -> dict:
    return {
        "group_id": group.group_id,
        "name": group.name,
        "creator_id": group.creator_id,
        "join_code": group.join_code,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "members": sorted(group.members),
        "whatsapp_group_id": group.whatsapp_group_id,
        "agora_chat_group_id": group.agora_chat_group_id,
    }


def _message_json(msg: Message) -> dict:
    return {
        "session_key": msg.session_key,
        "user_id": msg.user_id,
        "direction": msg.direction,
        "text": msg.text,
        "media_url": msg.media_url,
        "media_type": msg.media_type,
        "caption": msg.caption,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
    }


# Public config -------------------------------------------------------
@bp.get("/config")
def get_config():
    """Public client configuration.
    ---
    tags: [config]
    responses:
      200:
        description: Static config the mobile app needs at boot.
        schema:
          type: object
          properties:
            whatsapp_bot_number:
              type: string
              example: "233244111222"
            otp_dev_mode:
              type: boolean
              description: When true the OTP is echoed in the request-otp response.
    """
    return jsonify(
        whatsapp_bot_number=current_app.config.get("WHATSAPP_BOT_NUMBER", ""),
        otp_dev_mode=bool(current_app.config.get("OTP_ECHO_IN_RESPONSE", False)),
    )


# Users ---------------------------------------------------------------
@bp.get("/users/<user_id>")
@require_auth()
def get_user(user_id: str):
    """Fetch a user profile.
    ---
    tags: [users]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
    responses:
      200: {description: User profile}
      404: {description: User not found}
    """
    user = _store().get_user(user_id)
    if not user:
        return jsonify(error="user not found"), 404
    return jsonify(_user_json(user))


@bp.patch("/users/<user_id>")
@require_auth()
def patch_user(user_id: str):
    """Upsert the display name on a user profile.
    ---
    tags: [users]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name: {type: string, example: "Ama K."}
    responses:
      200: {description: Updated profile}
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    user = _store().upsert_user(User(user_id=user_id, name=name))
    return jsonify(_user_json(user))


@bp.get("/users/<user_id>/groups")
@require_auth()
def list_user_groups(user_id: str):
    """List the study groups a user belongs to.
    ---
    tags: [users, groups]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
    responses:
      200: {description: Array of groups}
    """
    groups = _store().list_groups_for_user(user_id)
    return jsonify(groups=[_group_json(g) for g in groups])


@bp.post("/users/<user_id>/chat")
@require_auth()
def post_user_chat(user_id: str):
    """In-app chat with the bot — alternative entry point to the WhatsApp webhook.

    Persists the inbound message, runs the same ChatbotEngine, persists the
    reply, and returns both. Intended for the Flutter chat screen as a fallback
    demo path when the WhatsApp Business API isn't wired up.
    ---
    tags: [users]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [text]
          properties:
            text: {type: string, example: "when is the library open"}
    responses:
      200:
        description: Inbound + outbound messages, oldest-first.
        schema:
          type: object
          properties:
            messages:
              type: array
              items:
                type: object
      422: {description: Missing or empty text}
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify(error="text is required"), 422

    store = _store()
    store.upsert_user(User(user_id=user_id))
    inbound = store.append_message(Message(
        session_key=user_id,
        user_id=user_id,
        direction="in",
        text=text,
    ))

    reply_text = _engine().handle(user_id=user_id, text=text)
    outbound = None
    if reply_text:
        outbound = store.append_message(Message(
            session_key=user_id,
            user_id=user_id,
            direction="out",
            text=reply_text,
        ))

    messages = [_message_json(inbound)]
    if outbound:
        messages.append(_message_json(outbound))
    return jsonify(messages=messages)


@bp.get("/users/<user_id>/messages")
@require_auth()
def list_user_messages(user_id: str):
    """1:1 conversation history for a user, oldest-first.
    ---
    tags: [users]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
      - in: query
        name: limit
        type: integer
        default: 20
    """
    limit = _safe_limit(request.args.get("limit"))
    msgs = _store().recent_messages(session_key=user_id, limit=limit)
    return jsonify(messages=[_message_json(m) for m in msgs])


# Devices -------------------------------------------------------------
@bp.post("/users/<user_id>/devices")
@require_auth()
def register_device(user_id: str):
    """Register an FCM device token (idempotent).
    ---
    tags: [devices]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [fcm_token, platform]
          properties:
            fcm_token: {type: string}
            platform:
              type: string
              enum: [android, ios, web]
    responses:
      201: {description: Device registered}
      422: {description: Invalid body}
    """
    body = request.get_json(silent=True) or {}
    token = (body.get("fcm_token") or "").strip()
    platform = (body.get("platform") or "android").strip().lower()
    if not token:
        return jsonify(error="fcm_token is required"), 422
    if platform not in {"android", "ios", "web"}:
        return jsonify(error="platform must be android|ios|web"), 422
    device = _store().register_device(
        Device(user_id=user_id, fcm_token=token, platform=platform)
    )
    return jsonify(
        user_id=device.user_id,
        fcm_token=device.fcm_token,
        platform=device.platform,
    ), 201


@bp.delete("/users/<user_id>/devices/<path:fcm_token>")
@require_auth()
def unregister_device(user_id: str, fcm_token: str):
    """Unregister a device (e.g. on sign-out).
    ---
    tags: [devices]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: user_id
        required: true
        type: string
      - in: path
        name: fcm_token
        required: true
        type: string
    responses:
      204: {description: Deleted}
      404: {description: Not found}
    """
    ok = _store().delete_device(user_id=user_id, fcm_token=fcm_token)
    if not ok:
        return jsonify(error="device not found"), 404
    return "", 204


# Groups --------------------------------------------------------------
@bp.post("/groups")
@require_auth(enforce_user_id_param=None)
def create_group():
    """Create a new study group. Caller becomes the creator and first member.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [name, creator_id]
          properties:
            name: {type: string, example: "AI 401 Study Group"}
            creator_id:
              type: string
              description: Must equal the JWT subject.
    responses:
      201: {description: Group created (includes join_code)}
      403: {description: creator_id ≠ JWT subject}
    """
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    creator_id = (body.get("creator_id") or "").strip()
    whatsapp_group_id = (body.get("whatsapp_group_id") or "").strip()
    if not name or not creator_id:
        return jsonify(error="name and creator_id are required"), 422
    if creator_id != g.auth_user_id:
        return jsonify(error="creator_id must match the authenticated user"), 403
    group = _groups().create(
        name=name,
        creator_id=creator_id,
        whatsapp_group_id=whatsapp_group_id,
    )
    return jsonify(_group_json(group)), 201


@bp.get("/groups/<group_id>")
@require_auth(enforce_user_id_param=None)
def get_group(group_id: str):
    """Fetch group details (member IDs only — use /members for hydrated names).
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: group_id
        required: true
        type: string
    responses:
      200: {description: Group}
      404: {description: Not found}
    """
    group = _store().get_group(group_id)
    if not group:
        return jsonify(error="group not found"), 404
    return jsonify(_group_json(group))


@bp.get("/groups/<group_id>/members")
@require_auth(enforce_user_id_param=None)
def list_group_members(group_id: str):
    """Hydrated member list (user_id + display name). Members-only.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: group_id
        required: true
        type: string
    responses:
      200:
        description: List of hydrated members
        schema:
          type: object
          properties:
            members:
              type: array
              items:
                type: object
                properties:
                  user_id: {type: string}
                  name: {type: string}
                  is_creator: {type: boolean}
      403: {description: Not a member}
      404: {description: Group not found}
    """
    group = _store().get_group(group_id)
    if not group:
        return jsonify(error="group not found"), 404
    if g.auth_user_id not in group.members:
        return jsonify(error="not a member of this group"), 403
    members = []
    for uid in sorted(group.members):
        user = _store().get_user(uid)
        members.append({
            "user_id": uid,
            "name": (user.name if user else "") or "",
            "is_creator": uid == group.creator_id,
        })
    return jsonify(members=members)


@bp.delete("/groups/<group_id>")
@require_auth(enforce_user_id_param=None)
def delete_group(group_id: str):
    """Delete a group. Creator-only.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: group_id
        required: true
        type: string
    responses:
      204: {description: Deleted}
      403: {description: Caller is not the creator}
      404: {description: Not found}
    """
    group = _store().get_group(group_id)
    if not group:
        return jsonify(error="group not found"), 404
    if group.creator_id != g.auth_user_id:
        return jsonify(error="only the creator may delete this group"), 403

    _store().delete_group(group_id)
    return "", 204


@bp.post("/groups/join")
@require_auth(enforce_user_id_param=None)
def join_group():
    """Join a group by its code.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [code]
          properties:
            code: {type: string, example: "AB12CD"}
            user_id:
              type: string
              description: Optional. Defaults to JWT subject; must match if sent.
    responses:
      200: {description: Joined; returns the group}
      403: {description: user_id ≠ JWT subject}
      404: {description: Invalid join code}
    """
    body = request.get_json(silent=True) or {}
    code = (body.get("code") or "").strip()
    user_id = (body.get("user_id") or "").strip() or g.auth_user_id
    if not code or not user_id:
        return jsonify(error="code is required"), 422
    if user_id != g.auth_user_id:
        return jsonify(error="user_id must match the authenticated user"), 403

    group = _groups().join(code=code, user_id=user_id)
    if not group:
        return jsonify(error="invalid join code"), 404
    return jsonify(_group_json(group))


@bp.get("/groups/<group_id>/messages")
@require_auth(enforce_user_id_param=None)
def list_group_messages(group_id: str):
    """Group conversation history, oldest-first. Members-only.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: group_id
        required: true
        type: string
      - in: query
        name: limit
        type: integer
        default: 20
    responses:
      200: {description: Messages array}
      403: {description: Not a member}
      404: {description: Group not found}
    """
    group = _store().get_group(group_id)
    if not group:
        return jsonify(error="group not found"), 404
    if g.auth_user_id not in group.members:
        return jsonify(error="not a member of this group"), 403
    limit = _safe_limit(request.args.get("limit"))
    msgs = _store().recent_messages(session_key=group_id, limit=limit)
    return jsonify(messages=[_message_json(m) for m in msgs])


# Calls ----------------------------------------------------------------
@bp.post("/calls/notify")
@require_auth(enforce_user_id_param=None)
def notify_call_start():
    """Ring the other members of a group. Sent when the caller opens the
    Agora RTC call screen — every other group member gets an FCM data
    message they can render as an incoming-call banner.
    ---
    tags: [groups]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [group_id]
          properties:
            group_id: {type: string}
    responses:
      200:
        description: Fan-out succeeded.
        schema:
          type: object
          properties:
            notified: {type: integer, description: "Number of members the push was sent to (caller excluded)."}
      403: {description: Caller is not a member of the group}
      404: {description: Group not found}
      422: {description: Missing group_id}
    """
    body = request.get_json(silent=True) or {}
    group_id = (body.get("group_id") or "").strip()
    if not group_id:
        return jsonify(error="group_id is required"), 422

    store = _store()
    group = store.get_group(group_id)
    if not group:
        return jsonify(error="group not found"), 404
    if g.auth_user_id not in group.members:
        return jsonify(error="not a member of this group"), 403

    caller_user = store.get_user(g.auth_user_id)
    caller_name = (caller_user.name if caller_user else "") or g.auth_user_id

    pusher: FcmPusher = current_app.extensions["pusher"]
    notified = 0
    for member_id in group.members:
        if member_id == g.auth_user_id:
            continue
        pusher.push(
            user_id=member_id,
            title=f"📞 {group.name}",
            body=f"{caller_name} is calling…",
            data={
                # All FCM data values must be strings.
                "type": "call_invitation",
                "group_id": group_id,
                "group_name": group.name,
                "initiator_id": g.auth_user_id,
                "initiator_name": caller_name,
            },
        )
        notified += 1
    return jsonify(notified=notified)


# Media proxy -----------------------------------------------------------
@bp.get("/media/<media_id>")
@require_auth(enforce_user_id_param=None)
def get_media(media_id: str):
    """Proxy a WhatsApp media id to its binary bytes.

    Required because Graph API signed URLs need the WABA access token as a
    bearer header — the mobile client cannot fetch them directly. Streams the
    bytes back with the Graph API's reported mime_type.
    ---
    tags: [media]
    security: [{Bearer: []}]
    parameters:
      - in: path
        name: media_id
        required: true
        type: string
    responses:
      200: {description: Media bytes (Content-Type set from Graph API)}
      404: {description: Media id unknown to WhatsApp}
      502: {description: Graph API error}
      503: {description: WhatsApp access token not configured on the backend}
    """
    client = WhatsAppClient.from_app(current_app)
    try:
        result = client.fetch_media(media_id)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 502
        if status == 404:
            return jsonify(error="media not found"), 404
        log.warning("Graph API error fetching media %s: %s", media_id, exc)
        return jsonify(error="graph api error", status=status), 502
    except requests.RequestException as exc:
        log.warning("Network error fetching media %s: %s", media_id, exc)
        return jsonify(error="upstream unreachable"), 502

    if result is None:
        return jsonify(error="whatsapp access token not configured"), 503

    mime_type, content = result
    return Response(
        content,
        mimetype=mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _safe_limit(raw: str | None) -> int:
    try:
        value = int(raw) if raw is not None else 20
    except (TypeError, ValueError):
        value = 20
    return max(1, min(value, 100))
