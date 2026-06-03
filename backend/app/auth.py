from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Callable

import jwt
from flask import Blueprint, current_app, g, jsonify, request

from .hubtel import HubtelClient
from .whatsapp import WhatsAppClient

log = logging.getLogger(__name__)

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5


@dataclass
class OtpRecord:
    code: str
    expires_at: datetime
    attempts: int = 0


class OtpStore:
    """In-process OTP store. One record per phone number.

    Production should swap this for Redis or Firestore TTL — the in-process
    map will not survive worker restarts and won't be shared across processes.
    """

    def __init__(self):
        self._records: dict[str, OtpRecord] = {}

    def issue(self, phone: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._records[phone] = OtpRecord(
            code=code,
            expires_at=datetime.now(timezone.utc) + OTP_TTL,
        )
        return code

    def verify(self, phone: str, code: str) -> bool:
        record = self._records.get(phone)
        if not record:
            return False
        if datetime.now(timezone.utc) >= record.expires_at:
            self._records.pop(phone, None)
            return False
        record.attempts += 1
        if record.attempts > OTP_MAX_ATTEMPTS:
            self._records.pop(phone, None)
            return False
        if not secrets.compare_digest(record.code, code):
            return False
        self._records.pop(phone, None)
        return True


def issue_jwt(user_id: str, *, secret: str, ttl_days: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl_days)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, *, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header.split(" ", 1)[1].strip() or None


def require_auth(*, enforce_user_id_param: str | None = "user_id") -> Callable:
    """Decorator that validates the bearer JWT and (optionally) enforces that the
    JWT subject matches a path parameter.

    Usage:
        @require_auth()                                     # subject must match <user_id>
        @require_auth(enforce_user_id_param=None)           # any authenticated caller
        @require_auth(enforce_user_id_param="creator_id")   # match a different path key
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            token = _bearer_token()
            if not token:
                return jsonify(error="missing bearer token"), 401
            try:
                payload = decode_jwt(token, secret=current_app.config["JWT_SECRET"])
            except jwt.ExpiredSignatureError:
                return jsonify(error="token expired"), 401
            except jwt.InvalidTokenError:
                return jsonify(error="invalid token"), 401

            g.auth_user_id = payload.get("sub", "")
            if enforce_user_id_param:
                path_user = kwargs.get(enforce_user_id_param)
                if path_user and path_user != g.auth_user_id:
                    return jsonify(error="forbidden"), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


# Blueprint --------------------------------------------------------------
bp = Blueprint("auth", __name__)


def _otp_store() -> OtpStore:
    return current_app.extensions["otp_store"]


def _deliver_otp_whatsapp(phone: str, code: str) -> bool:
    """Send the OTP via an approved Meta Authentication template.

    Authentication templates put the code in both the body and a copy-code
    button, so we pass `code` to both. Returns True only if Meta accepted the
    send (credentials + template must be configured); any failure returns
    False so the caller can fall back / surface `delivered: false`.
    """
    try:
        client = WhatsAppClient.from_app(current_app)
        result = client.send_template(
            to=phone,
            template_name=current_app.config.get("WHATSAPP_OTP_TEMPLATE", "otp_code"),
            language=current_app.config.get("WHATSAPP_OTP_LANGUAGE", "en"),
            body_params=[code],
            button_otp=code,
        )
        return result is not None
    except Exception:
        log.warning("WhatsApp OTP send failed for %s", phone, exc_info=True)
        return False


def _deliver_otp_sms(phone: str, code: str) -> bool:
    """Send the OTP as a plain SMS via Hubtel. Best-effort (see request_otp)."""
    try:
        sms = HubtelClient.from_app(current_app)
        result = sms.send_sms(
            to=phone,
            content=f"Your verification code is {code}. It expires in 5 minutes.",
        )
        return result is not None
    except Exception:
        log.warning("Hubtel SMS send failed for %s", phone, exc_info=True)
        return False


def _deliver_otp(phone: str, code: str) -> bool:
    """Deliver the OTP over the channel(s) named by OTP_DELIVERY_CHANNEL.

    "whatsapp" → Meta template, "sms" → Hubtel, "both" → try each.
    Returns True if at least one channel accepted the message. Delivery is
    best-effort: failures never abort signup (the OTP is in the store and, in
    dev, echoed in the response / logged).
    """
    channel = current_app.config.get("OTP_DELIVERY_CHANNEL", "sms").strip().lower()
    delivered = False
    if channel in ("whatsapp", "both"):
        delivered = _deliver_otp_whatsapp(phone, code) or delivered
    if channel in ("sms", "both"):
        delivered = _deliver_otp_sms(phone, code) or delivered
    return delivered


@bp.post("/request-otp")
def request_otp():
    """Issue a one-time login code for a phone number.
    ---
    tags: [auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone_number]
          properties:
            phone_number: {type: string, example: "233244111222"}
    responses:
      202:
        description: OTP issued (in dev the code is echoed under `otp`).
        schema:
          type: object
          properties:
            sent: {type: boolean}
            phone_number: {type: string}
            ttl_seconds: {type: integer}
            otp: {type: string, description: "Dev-only echo."}
      422: {description: Missing phone_number}
    """
    body = request.get_json(silent=True) or {}
    phone = (body.get("phone_number") or "").strip()
    if not phone:
        return jsonify(error="phone_number is required"), 422

    code = _otp_store().issue(phone)
    # Logged at WARNING so it shows in default log output. Once OTP delivery
    # works in production, this should drop back to INFO.
    log.warning("OTP for %s: %s", phone, code)

    delivered = _deliver_otp(phone, code)

    response: dict = {
        "sent": delivered,
        "phone_number": phone,
        "ttl_seconds": int(OTP_TTL.total_seconds()),
    }
    if current_app.config.get("OTP_ECHO_IN_RESPONSE", False):
        response["otp"] = code  # dev convenience only
    return jsonify(response), 202


@bp.post("/verify-otp")
def verify_otp():
    """Trade a valid OTP for a JWT.
    ---
    tags: [auth]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [phone_number, code]
          properties:
            phone_number: {type: string, example: "233244111222"}
            code: {type: string, example: "123456"}
    responses:
      200:
        description: JWT issued.
        schema:
          type: object
          properties:
            token: {type: string}
            user_id: {type: string}
            expires_in_days: {type: integer}
      401: {description: Invalid or expired code}
    """
    body = request.get_json(silent=True) or {}
    phone = (body.get("phone_number") or "").strip()
    code = (body.get("code") or "").strip()
    if not phone or not code:
        return jsonify(error="phone_number and code are required"), 422

    if not _otp_store().verify(phone, code):
        return jsonify(error="invalid or expired code"), 401

    token = issue_jwt(
        user_id=phone,
        secret=current_app.config["JWT_SECRET"],
        ttl_days=current_app.config["JWT_TTL_DAYS"],
    )
    return jsonify(
        token=token,
        user_id=phone,
        expires_in_days=current_app.config["JWT_TTL_DAYS"],
    )
