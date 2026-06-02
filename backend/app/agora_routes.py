"""REST endpoints for the mobile Agora SDKs to fetch short-lived tokens.

All endpoints require a valid bearer JWT. Tokens are minted for the JWT
subject, so a user can only request tokens that bind to their own identity.

When Agora is not configured (no APP_ID / APP_CERTIFICATE), every endpoint
returns 503 — useful in dev when these keys aren't set.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, g, jsonify, request

from .agora import (
    AgoraClient,
    AgoraNotConfigured,
    RTC_ROLE_PUBLISHER,
    RTC_ROLE_SUBSCRIBER,
)
from .auth import require_auth

log = logging.getLogger(__name__)
bp = Blueprint("agora", __name__)


def _client() -> AgoraClient:
    return current_app.extensions["agora"]


@bp.post("/rtc-token")
@require_auth(enforce_user_id_param=None)
def rtc_token():
    """Mint an RTC token for joining a voice/video channel.
    ---
    tags: [agora]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [channel]
          properties:
            channel: {type: string, example: "group-abc123"}
            uid: {type: integer, default: 0, description: "0 = let Agora assign"}
            role: {type: string, enum: [publisher, subscriber], default: publisher}
            ttl_seconds: {type: integer, default: 3600}
    responses:
      200: {description: Token issued}
      400: {description: Bad request}
      503: {description: Agora not configured on the server}
    """
    body = request.get_json(silent=True) or {}
    channel = (body.get("channel") or "").strip()
    if not channel:
        return jsonify(error="channel is required"), 400

    try:
        uid_raw = body.get("uid", 0)
        uid = int(uid_raw) if uid_raw is not None else 0
    except (TypeError, ValueError):
        return jsonify(error="uid must be an integer"), 400

    role_str = (body.get("role") or "publisher").strip().lower()
    role = RTC_ROLE_PUBLISHER if role_str == "publisher" else RTC_ROLE_SUBSCRIBER

    try:
        ttl = int(body.get("ttl_seconds") or 3600)
    except (TypeError, ValueError):
        ttl = 3600
    ttl = max(60, min(ttl, 24 * 3600))

    try:
        result = _client().rtc_token(channel=channel, uid=uid, role=role, ttl=ttl)
    except AgoraNotConfigured as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(result)


@bp.post("/rtm-token")
@require_auth(enforce_user_id_param=None)
def rtm_token():
    """Mint an RTM (signalling) token for the authenticated user.
    ---
    tags: [agora]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            ttl_seconds: {type: integer, default: 86400}
    responses:
      200: {description: Token issued}
      503: {description: Agora not configured}
    """
    body = request.get_json(silent=True) or {}
    try:
        ttl = int(body.get("ttl_seconds") or 86400)
    except (TypeError, ValueError):
        ttl = 86400
    ttl = max(60, min(ttl, 7 * 24 * 3600))

    user_id = g.auth_user_id
    try:
        result = _client().rtm_token(user_id=user_id, ttl=ttl)
    except AgoraNotConfigured as exc:
        return jsonify(error=str(exc)), 503
    return jsonify(result)


@bp.post("/chat-token")
@require_auth(enforce_user_id_param=None)
def chat_token():
    """Mint an Agora Chat user-token for the authenticated user.
    ---
    tags: [agora]
    security: [{Bearer: []}]
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            ttl_seconds: {type: integer, default: 86400}
    responses:
      200:
        description: Token + app_key + rest_host the mobile SDK needs to init.
      503: {description: Agora not configured}
    """
    body = request.get_json(silent=True) or {}
    try:
        ttl = int(body.get("ttl_seconds") or 86400)
    except (TypeError, ValueError):
        ttl = 86400
    ttl = max(60, min(ttl, 7 * 24 * 3600))

    user_id = g.auth_user_id
    try:
        result = _client().chat_user_token(user_id=user_id, ttl=ttl)
    except AgoraNotConfigured as exc:
        return jsonify(error=str(exc)), 503

    chat_rest = current_app.extensions.get("agora_chat_rest")
    register_status: dict | None = None
    token_source = "local_jwt"
    if chat_rest is not None:
        cfg = chat_rest.config
        if not (cfg.chat_is_configured and cfg.chat_app_token):
            register_status = {
                "ok": False,
                "reason": "chat_rest_not_configured",
                "chat_is_configured": cfg.chat_is_configured,
                "has_app_token": bool(cfg.chat_app_token),
            }
            log.warning("chat-token: %s", register_status)
        else:
            try:
                ok = chat_rest.ensure_user(user_id)
                register_status = {"ok": True, "newly_created": ok}
                log.info("chat-token: ensure_user(%s) newly_created=%s", user_id, ok)
            except Exception as exc:
                register_status = {"ok": False, "reason": "exception", "error": str(exc)}
                log.warning("ensure_user(%s) raised: %s", user_id, exc)

            # Local JWT minting fails with code 202 when AGORA_APP_ID and the
            # Chat AppKey are from different Agora projects. Prefer a REST-
            # minted token so Agora signs it themselves.
            rest_token = chat_rest.mint_user_token(user_id, ttl=ttl)
            if rest_token:
                result = {**result, "token": rest_token}
                token_source = "rest_minted"
                log.info("chat-token: REST-minted token for %s", user_id)
            else:
                log.warning("chat-token: REST mint failed for %s, returning local JWT", user_id)

    if register_status is not None:
        result = {**result, "_register_status": register_status, "_token_source": token_source}
    return jsonify(result)
