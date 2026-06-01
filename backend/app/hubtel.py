"""Hubtel SMS client.

Hubtel is a Ghanaian comms provider. We use it for OTP delivery — instant,
no template approval required (unlike Meta WhatsApp). Get credentials at
https://unity.hubtel.com → API Keys.

Required env vars:
- HUBTEL_CLIENT_ID
- HUBTEL_CLIENT_SECRET
- HUBTEL_SENDER_ID  (≤11 chars, must be approved in your Hubtel dashboard)

If any are unset, send_sms is a no-op and logs a warning — the rest of the
auth flow still works (OTP is generated and stored), it just isn't delivered.
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from flask import Flask

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://sms.hubtel.com/v1/messages/send"


class HubtelClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        sender_id: str,
        base: str = DEFAULT_BASE,
        timeout: float = 10.0,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.sender_id = sender_id
        self.base = base
        self.timeout = timeout

    @classmethod
    def from_app(cls, app: Flask) -> "HubtelClient":
        return cls(
            client_id=app.config.get("HUBTEL_CLIENT_ID", ""),
            client_secret=app.config.get("HUBTEL_CLIENT_SECRET", ""),
            sender_id=app.config.get("HUBTEL_SENDER_ID", ""),
            base=app.config.get("HUBTEL_SMS_URL", DEFAULT_BASE),
        )

    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.sender_id)

    def send_sms(self, to: str, content: str) -> dict[str, Any] | None:
        """Send a single SMS. Returns Hubtel's JSON response, or None if the
        client is not configured.

        Raises requests.HTTPError on a non-2xx response from Hubtel — caller
        decides whether to swallow it (auth.py does, so OTP issuance survives
        carrier outages).
        """
        if not self.configured():
            log.warning(
                "Hubtel not configured (CLIENT_ID/SECRET/SENDER_ID); dropping SMS to %s",
                to,
            )
            return None

        # Hubtel accepts E.164 with or without leading '+'. Normalize to '+'
        # form so numbers like '233244111222' get routed correctly.
        normalized = to if to.startswith("+") else f"+{to}"

        resp = requests.post(
            self.base,
            auth=(self.client_id, self.client_secret),
            json={
                "From": self.sender_id,
                "To": normalized,
                "Content": content,
                "RegisteredDelivery": True,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()
