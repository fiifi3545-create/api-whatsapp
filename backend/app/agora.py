"""Agora server-side helpers.

We mint tokens for RTC (voice/video), RTM (signalling), and Chat from the App
Certificate, so the certificate never leaves the backend. The mobile SDKs
call `/api/agora/*-token` to fetch a short-lived token scoped to the JWT user.

For Agora Chat we also expose a thin REST client used by the bot integration:
when an Agora-Chat-routed message comes in, the chatbot reply is posted back
into the channel as the `bot` user.

Configuration: AGORA_APP_ID + AGORA_APP_CERTIFICATE (required for any token
generation), plus AGORA_CHAT_APP_KEY + AGORA_CHAT_REST_HOST + optional
AGORA_CHAT_APP_TOKEN for the Chat REST integration. When credentials are
missing, all methods raise AgoraNotConfigured — callers handle this and the
endpoint returns 503.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import jwt
import requests
from agora_token_builder import RtcTokenBuilder, RtmTokenBuilder

log = logging.getLogger(__name__)

# agora_token_builder.AccessToken role constants (avoid importing the private module).
RTC_ROLE_PUBLISHER = 1
RTC_ROLE_SUBSCRIBER = 2
RTM_ROLE_USER = 1

DEFAULT_RTC_TTL = 3600          # 1 h — calls usually fit
DEFAULT_RTM_TTL = 24 * 3600     # 24 h
DEFAULT_CHAT_TTL = 24 * 3600    # 24 h — mobile re-mints on next launch

# Agora Chat usernames must match this. Phone-number user IDs (e.g. 233244...)
# pass naturally; we still lowercase + sanitize anything unexpected.
_CHAT_USERNAME_OK = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


class AgoraNotConfigured(RuntimeError):
    """Raised when an Agora helper is called but the env is not configured."""


def _sanitize_chat_username(user_id: str) -> str:
    """Agora Chat allows [A-Za-z0-9_-] up to 64 chars. Map disallowed chars to '_'."""
    cleaned = "".join(c if c in _CHAT_USERNAME_OK else "_" for c in user_id)
    return cleaned[:64] or "user"


@dataclass
class AgoraConfig:
    app_id: str
    app_certificate: str
    chat_app_key: str
    chat_rest_host: str
    chat_app_token: str

    @classmethod
    def from_env(cls) -> "AgoraConfig":
        # Agora Chat's app key has the literal shape "<org>#<app>" but some
        # hosting UIs (Render, at least) silently strip `#` from env var
        # values. Allow the org and app halves to be supplied separately;
        # prefer those when both are set, fall back to the combined value
        # for local dev.
        org = os.environ.get("AGORA_CHAT_ORG_NAME", "").strip()
        app = os.environ.get("AGORA_CHAT_APP_NAME", "").strip()
        if org and app:
            chat_app_key = f"{org}#{app}"
        else:
            chat_app_key = os.environ.get("AGORA_CHAT_APP_KEY", "").strip()
        return cls(
            app_id=os.environ.get("AGORA_APP_ID", "").strip(),
            app_certificate=os.environ.get("AGORA_APP_CERTIFICATE", "").strip(),
            chat_app_key=chat_app_key,
            chat_rest_host=os.environ.get("AGORA_CHAT_REST_HOST", "").strip(),
            chat_app_token=os.environ.get("AGORA_CHAT_APP_TOKEN", "").strip(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_certificate)

    @property
    def chat_is_configured(self) -> bool:
        return bool(
            self.is_configured
            and self.chat_app_key
            and self.chat_rest_host
        )


class AgoraClient:
    """Token minter. Stateless; safe to share across requests."""

    def __init__(self, config: AgoraConfig | None = None):
        self.config = config or AgoraConfig.from_env()

    def _ensure_configured(self) -> None:
        if not self.config.is_configured:
            raise AgoraNotConfigured(
                "Agora is not configured (AGORA_APP_ID / AGORA_APP_CERTIFICATE)"
            )

    # ----- RTC (voice/video) -----------------------------------------
    def rtc_token(
        self,
        channel: str,
        uid: int = 0,                # 0 = let Agora assign; mobile must echo back
        role: int = RTC_ROLE_PUBLISHER,
        ttl: int = DEFAULT_RTC_TTL,
    ) -> dict:
        """Mint an RTC token. Mobile passes (channel, uid, token, app_id) to RtcEngine.joinChannel."""
        self._ensure_configured()
        if not channel:
            raise ValueError("channel is required")
        expires_at = int(time.time()) + ttl
        token = RtcTokenBuilder.buildTokenWithUid(
            self.config.app_id,
            self.config.app_certificate,
            channel,
            uid,
            role,
            expires_at,
        )
        return {
            "token": token,
            "app_id": self.config.app_id,
            "channel": channel,
            "uid": uid,
            "role": role,
            "expires_at": expires_at,
        }

    # ----- RTM (signalling) ------------------------------------------
    def rtm_token(self, user_id: str, ttl: int = DEFAULT_RTM_TTL) -> dict:
        """Mint an RTM token for presence/typing/custom signalling."""
        self._ensure_configured()
        if not user_id:
            raise ValueError("user_id is required")
        expires_at = int(time.time()) + ttl
        token = RtmTokenBuilder.buildToken(
            self.config.app_id,
            self.config.app_certificate,
            user_id,
            RTM_ROLE_USER,
            expires_at,
        )
        return {
            "token": token,
            "app_id": self.config.app_id,
            "user_id": user_id,
            "expires_at": expires_at,
        }

    # ----- Chat (messaging) ------------------------------------------
    def chat_user_token(self, user_id: str, ttl: int = DEFAULT_CHAT_TTL) -> dict:
        """Mint a JWT user-token for the Agora Chat SDK.

        Per Agora's "Authentication" spec for Chat, the token is HS256 over
        the App Certificate with claims:
          iss = AppID
          exp = expiry (epoch seconds)
          iat = issued-at
          chatUserName = the Agora-Chat username to bind to
        """
        self._ensure_configured()
        if not user_id:
            raise ValueError("user_id is required")
        username = _sanitize_chat_username(user_id)
        now = int(time.time())
        expires_at = now + ttl
        payload = {
            "iss": self.config.app_id,
            "iat": now,
            "exp": expires_at,
            "chatUserName": username,
        }
        token = jwt.encode(payload, self.config.app_certificate, algorithm="HS256")
        return {
            "token": token,
            "app_key": self.config.chat_app_key,
            "rest_host": self.config.chat_rest_host,
            "user_id": username,
            "expires_at": expires_at,
        }


class AgoraChatRestClient:
    """Thin REST wrapper for Agora Chat admin actions (register user, post as bot).

    Auth uses the app-scoped token from `AGORA_CHAT_APP_TOKEN` (the dev token
    from the console, or a token minted from client_credentials). Production
    should rotate this via the Chat /token endpoint periodically; for now we
    just trust the env var.
    """

    def __init__(self, config: AgoraConfig | None = None, timeout: float = 15.0):
        self.config = config or AgoraConfig.from_env()
        self.timeout = timeout

    def _ensure(self) -> tuple[str, str]:
        if not self.config.chat_is_configured:
            raise AgoraNotConfigured("Agora Chat REST not configured")
        if not self.config.chat_app_token:
            raise AgoraNotConfigured("AGORA_CHAT_APP_TOKEN missing")
        org, app = self.config.chat_app_key.split("#", 1)
        return org, app

    def _base(self) -> str:
        org, app = self._ensure()
        return f"https://{self.config.chat_rest_host}/{org}/{app}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.config.chat_app_token}",
            "Content-Type": "application/json",
        }

    def ensure_user(self, username: str) -> bool:
        """Idempotent register. Returns True if newly created, False if already existed."""
        username = _sanitize_chat_username(username)
        url = f"{self._base()}/users"
        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                json=[{"username": username}],  # bulk-shape per Agora docs
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat register call failed for %s: %s", username, exc)
            return False
        if resp.status_code in (200, 201):
            log.info("Agora Chat register %s: created", username)
            return True
        if resp.status_code == 400 and "duplicate" in resp.text.lower():
            log.info("Agora Chat register %s: already exists", username)
            return False
        log.warning("Agora Chat register %s unexpected response %s: %s",
                    username, resp.status_code, resp.text[:200])
        return False

    def send_text(self, *, from_user: str, to_user: str, text: str) -> bool:
        """Post a 1:1 text message as `from_user`. Used by the bot to reply."""
        url = f"{self._base()}/messages/users"
        body = {
            "from": _sanitize_chat_username(from_user),
            "to": [_sanitize_chat_username(to_user)],
            "type": "txt",
            "body": {"msg": text},
        }
        try:
            resp = requests.post(
                url, headers=self._headers(), json=body, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat send_text failed: %s", exc)
            return False
        if resp.ok:
            return True
        log.warning("Agora Chat send_text %s: %s", resp.status_code, resp.text[:200])
        return False

    def send_to_group(self, *, from_user: str, group_id: str, text: str) -> bool:
        url = f"{self._base()}/messages/chatgroups"
        body = {
            "from": _sanitize_chat_username(from_user),
            "to": [group_id],
            "type": "txt",
            "body": {"msg": text},
        }
        try:
            resp = requests.post(
                url, headers=self._headers(), json=body, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat send_to_group failed: %s", exc)
            return False
        return resp.ok

    # ----- group lifecycle ----------------------------------------
    def create_chat_group(
        self,
        *,
        name: str,
        owner: str,
        members: list[str] | None = None,
        public: bool = False,
        approval: bool = False,
        maxusers: int = 200,
    ) -> str | None:
        """Create an Agora Chat group and return its groupid.

        We mirror our backend `Group` to an Agora Chat group so the mobile
        client can subscribe to chat events for that group via the SDK.
        Returns None on failure; caller decides whether to abort or proceed.
        """
        url = f"{self._base()}/chatgroups"
        body = {
            "groupname": name,
            "owner": _sanitize_chat_username(owner),
            "members": [_sanitize_chat_username(m) for m in (members or [])],
            "public": public,
            "approval": approval,
            "maxusers": maxusers,
        }
        try:
            resp = requests.post(
                url, headers=self._headers(), json=body, timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat create_chat_group failed: %s", exc)
            return None
        if not resp.ok:
            log.warning("Agora Chat create_chat_group %s: %s",
                        resp.status_code, resp.text[:200])
            return None
        try:
            data = resp.json().get("data") or {}
        except ValueError:
            return None
        return (data.get("groupid") or "").strip() or None

    def add_member(self, *, chat_group_id: str, username: str) -> bool:
        username = _sanitize_chat_username(username)
        url = f"{self._base()}/chatgroups/{chat_group_id}/users/{username}"
        try:
            resp = requests.post(
                url, headers=self._headers(), timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat add_member failed: %s", exc)
            return False
        if resp.ok:
            return True
        if resp.status_code == 400 and "duplicate" in resp.text.lower():
            return True  # already a member; idempotent
        log.warning("Agora Chat add_member %s: %s",
                    resp.status_code, resp.text[:200])
        return False

    def remove_member(self, *, chat_group_id: str, username: str) -> bool:
        username = _sanitize_chat_username(username)
        url = f"{self._base()}/chatgroups/{chat_group_id}/users/{username}"
        try:
            resp = requests.delete(
                url, headers=self._headers(), timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat remove_member failed: %s", exc)
            return False
        return resp.ok or resp.status_code == 404  # 404 = already gone

    def delete_chat_group(self, chat_group_id: str) -> bool:
        url = f"{self._base()}/chatgroups/{chat_group_id}"
        try:
            resp = requests.delete(
                url, headers=self._headers(), timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.warning("Agora Chat delete_chat_group failed: %s", exc)
            return False
        return resp.ok or resp.status_code == 404


def make_agora_client_from_env() -> AgoraClient:
    return AgoraClient(AgoraConfig.from_env())


def make_chat_rest_client_from_env() -> AgoraChatRestClient:
    return AgoraChatRestClient(AgoraConfig.from_env())
