from __future__ import annotations

import logging
import os
from typing import Any

from .store import Device, Store

log = logging.getLogger(__name__)


class FcmPusher:
    """Push notifications to FCM. Degrades to a logging no-op when creds absent.

    Activation requires both FCM_PROJECT_ID and GOOGLE_APPLICATION_CREDENTIALS.
    Init failure (missing firebase-admin, bad service account, etc.) also falls
    back to the no-op stub with a warning.
    """

    def __init__(self, store: Store, project_id: str | None = None):
        self._store = store
        self._project_id = project_id or os.environ.get("FCM_PROJECT_ID", "")
        self._messaging = None

        if self._project_id and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                import firebase_admin
                from firebase_admin import credentials, messaging

                if not firebase_admin._apps:
                    firebase_admin.initialize_app(
                        credentials.ApplicationDefault(),
                        {"projectId": self._project_id},
                    )
                self._messaging = messaging
            except Exception as exc:
                log.warning("FCM init failed, push will no-op: %s", exc)

    def push(
        self,
        user_id: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> int:
        """Send a push to every registered device for user_id.

        Returns the number of successful sends. 0 when there are no devices
        or when the client is in stub mode.
        """
        devices = self._store.list_devices(user_id)
        if not devices:
            return 0

        if self._messaging is None:
            log.info(
                "FCM stub: would push to %d device(s) for user=%s title=%r body=%r",
                len(devices), user_id, title, body,
            )
            return 0

        sent = 0
        for device in devices:
            try:
                self._send_one(device, title, body, data or {})
                sent += 1
            except Exception as exc:
                log.warning("FCM send failed for token=%s: %s", device.fcm_token[:8], exc)
        return sent

    def _send_one(
        self,
        device: Device,
        title: str,
        body: str,
        data: dict[str, str],
    ) -> Any:
        message = self._messaging.Message(
            notification=self._messaging.Notification(title=title, body=body),
            data=data,
            token=device.fcm_token,
        )
        return self._messaging.send(message)


def make_pusher_from_env(store: Store) -> FcmPusher:
    return FcmPusher(store=store)
