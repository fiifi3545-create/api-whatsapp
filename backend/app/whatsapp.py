
from __future__ import annotations

import logging
import re
from typing import Any

import requests
from flask import Flask

log = logging.getLogger(__name__)



def is_bot_mentioned(text: str, mention: str) -> bool:
    """Case-insensitive substring check for the bot's mention token."""
    if not text or not mention:
        return False
    return mention.lower() in text.lower()


def strip_mention(text: str, mention: str) -> str:
    """Remove every occurrence of the mention token (case-insensitive) and tidy whitespace."""
    if not text or not mention:
        return text or ""
    stripped = re.sub(re.escape(mention), "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stripped).strip()


def parse_incoming(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a WhatsApp Business webhook payload into a list of messages.

    The payload schema is nested: entry → changes → value → messages[].
    Surfaces text, image, and document messages. Other types are skipped.
    For messages sent inside a WhatsApp group, `context.group_id` is the
    group's wa_id; populate it so the webhook can route accordingly.
    """
    out: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                msg_type = msg.get("type")
                context = msg.get("context") or {}
                parsed = {
                    "from": msg.get("from", ""),
                    "wa_id": msg.get("id"),
                    "group_id": context.get("group_id"),
                    "text": "",
                    "media_id": None,
                    "media_type": None,
                    "caption": None,
                }
                if msg_type == "text":
                    parsed["text"] = msg.get("text", {}).get("body", "")
                elif msg_type == "image":
                    image = msg.get("image", {})
                    parsed["media_id"] = image.get("id")
                    parsed["media_type"] = "image"
                    parsed["caption"] = image.get("caption")
                    parsed["text"] = image.get("caption") or "[image]"
                elif msg_type == "document":
                    doc = msg.get("document", {})
                    parsed["media_id"] = doc.get("id")
                    parsed["media_type"] = "document"
                    parsed["caption"] = doc.get("caption") or doc.get("filename")
                    parsed["text"] = parsed["caption"] or "[document]"
                else:
                    continue
                out.append(parsed)
    return out


class WhatsAppClient:
    def __init__(self, base: str, phone_number_id: str, access_token: str):
        self.base = base.rstrip("/")
        self.phone_number_id = phone_number_id
        self.access_token = access_token

    @classmethod
    def from_app(cls, app: Flask) -> "WhatsAppClient":
        return cls(
            base=app.config["WHATSAPP_API_BASE"],
            phone_number_id=app.config["WHATSAPP_PHONE_NUMBER_ID"],
            access_token=app.config["WHATSAPP_ACCESS_TOKEN"],
        )

    def send_text(self, to: str, body: str) -> dict[str, Any] | None:
        if not self.phone_number_id or not self.access_token:
            log.warning("WhatsApp credentials not configured; dropping outbound message to %s", to)
            return None

        url = f"{self.base}/{self.phone_number_id}/messages"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": body},
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_media(self, media_id: str) -> tuple[str, bytes] | None:
        """Resolve a WhatsApp media id to (mime_type, bytes).

        Two Graph API calls:
          1. GET /{media_id}            → JSON {url, mime_type, ...}
          2. GET <url> (signed CDN url) → binary bytes
        Both require the WABA access token. Returns None when credentials
        are unset; raises requests.HTTPError on any 4xx/5xx response.
        """
        if not self.access_token:
            log.warning("WhatsApp access token unset; cannot fetch media %s", media_id)
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        meta = requests.get(f"{self.base}/{media_id}", headers=headers, timeout=10)
        meta.raise_for_status()
        payload = meta.json()
        url = payload.get("url")
        mime_type = payload.get("mime_type") or "application/octet-stream"
        if not url:
            log.warning("Graph API returned no signed url for media %s", media_id)
            return None

        binary = requests.get(url, headers=headers, timeout=30)
        binary.raise_for_status()
        return mime_type, binary.content

    def send_template(
        self,
        to: str,
        template_name: str,
        language: str = "en",
        body_params: list[str] | None = None,
        button_otp: str | None = None,
    ) -> dict[str, Any] | None:
        """Send an approved Meta template message.

        Required for unsolicited messages (e.g. OTP delivery) outside the
        24-hour customer-service window. The template must be created and
        approved in Meta Business Manager first. For Authentication templates
        with a one-tap autofill button, pass `button_otp` so the OTP is
        included as the button URL parameter.
        """
        if not self.phone_number_id or not self.access_token:
            log.warning(
                "WhatsApp credentials not configured; dropping template '%s' to %s",
                template_name, to,
            )
            return None

        components: list[dict[str, Any]] = []
        if body_params:
            components.append({
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in body_params],
            })
        if button_otp:
            components.append({
                "type": "button",
                "sub_type": "url",
                "index": "0",
                "parameters": [{"type": "text", "text": button_otp}],
            })

        url = f"{self.base}/{self.phone_number_id}/messages"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language},
                    "components": components,
                },
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
