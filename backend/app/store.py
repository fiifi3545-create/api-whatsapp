from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

log = logging.getLogger(__name__)


@dataclass
class User:
    user_id: str  # WhatsApp phone-number id (msisdn-style)
    name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Group:
    group_id: str
    name: str
    creator_id: str
    join_code: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    members: set[str] = field(default_factory=set)
    # Optional bridge target: the WhatsApp group_id that this in-app group
    # mirrors. When set, outbound in-app group messages are best-effort relayed
    # via WhatsAppClient.send_text. Empty string = no bridge.
    whatsapp_group_id: str = ""
    # Mirror of this group in Agora Chat. Populated when the group is first
    # created if Chat REST is configured; empty otherwise (the in-app chat
    # path still works via WS for groups that pre-date the migration).
    agora_chat_group_id: str = ""


@dataclass
class Message:
    session_key: str  # group_id for group convos, user_id for 1:1
    user_id: str
    direction: str  # "in" | "out"
    text: str
    media_url: str | None = None
    media_type: str | None = None  # "image" | "document"
    caption: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # For group chat: who sent the message. In 1:1 these stay empty and
    # callers infer the sender from direction. The bot uses sender_id="bot".
    sender_id: str = ""
    sender_name: str = ""


@dataclass
class Device:
    user_id: str
    fcm_token: str
    platform: str  # "android" | "ios" | "web"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def new_group_id() -> str:
    return secrets.token_hex(8)


def new_join_code() -> str:
    return secrets.token_urlsafe(6).upper()


class Store(Protocol):
    # users
    def get_user(self, user_id: str) -> User | None: ...
    def upsert_user(self, user: User) -> User: ...

    # groups
    def create_group(self, group: Group) -> Group: ...
    def get_group(self, group_id: str) -> Group | None: ...
    def get_group_by_code(self, code: str) -> Group | None: ...
    def add_member(self, group_id: str, user_id: str) -> Group | None: ...
    def delete_group(self, group_id: str) -> bool: ...
    def list_groups_for_user(self, user_id: str) -> list[Group]: ...

    # messages
    def append_message(self, message: Message) -> Message: ...
    def recent_messages(self, session_key: str, limit: int = 20) -> list[Message]: ...

    # devices (FCM push targets)
    def register_device(self, device: Device) -> Device: ...
    def list_devices(self, user_id: str) -> list[Device]: ...
    def delete_device(self, user_id: str, fcm_token: str) -> bool: ...


class InMemoryStore:
    """Dict-backed Store for dev and tests. Single-process only."""

    def __init__(self):
        self._users: dict[str, User] = {}
        self._groups: dict[str, Group] = {}
        self._codes: dict[str, str] = {}  # join_code -> group_id
        self._messages: dict[str, list[Message]] = {}
        self._devices: dict[str, dict[str, Device]] = {}  # user_id -> token -> Device

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def upsert_user(self, user: User) -> User:
        existing = self._users.get(user.user_id)
        if existing:
            if user.name and user.name != existing.name:
                existing.name = user.name
            return existing
        self._users[user.user_id] = user
        return user

    def create_group(self, group: Group) -> Group:
        self._groups[group.group_id] = group
        self._codes[group.join_code] = group.group_id
        return group

    def get_group(self, group_id: str) -> Group | None:
        return self._groups.get(group_id)

    def get_group_by_code(self, code: str) -> Group | None:
        gid = self._codes.get(code)
        return self._groups.get(gid) if gid else None

    def add_member(self, group_id: str, user_id: str) -> Group | None:
        group = self._groups.get(group_id)
        if not group:
            return None
        group.members.add(user_id)
        return group

    def delete_group(self, group_id: str) -> bool:
        group = self._groups.pop(group_id, None)
        if not group:
            return False
        self._codes.pop(group.join_code, None)
        return True

    def list_groups_for_user(self, user_id: str) -> list[Group]:
        return [g for g in self._groups.values() if user_id in g.members]

    def append_message(self, message: Message) -> Message:
        self._messages.setdefault(message.session_key, []).append(message)
        return message

    def recent_messages(self, session_key: str, limit: int = 20) -> list[Message]:
        msgs = self._messages.get(session_key, [])
        return msgs[-limit:]

    def register_device(self, device: Device) -> Device:
        self._devices.setdefault(device.user_id, {})[device.fcm_token] = device
        return device

    def list_devices(self, user_id: str) -> list[Device]:
        return list(self._devices.get(user_id, {}).values())

    def delete_device(self, user_id: str, fcm_token: str) -> bool:
        devices = self._devices.get(user_id)
        if not devices or fcm_token not in devices:
            return False
        devices.pop(fcm_token)
        return True


class FirestoreStore:
    """google-cloud-firestore-backed Store.

    Only instantiate via make_store_from_env(); the factory checks creds.
    """

    USERS = "users"
    GROUPS = "groups"
    MESSAGES = "messages"
    DEVICES = "devices"  # doc id = fcm_token; field user_id for query

    def __init__(self, project_id: str):
        from google.cloud import firestore  # imported lazily to keep dev boots fast

        self._fs = firestore
        self._db = firestore.Client(project=project_id)

    # users -----------------------------------------------------------
    def get_user(self, user_id: str) -> User | None:
        snap = self._db.collection(self.USERS).document(user_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return User(
            user_id=user_id,
            name=data.get("name", ""),
            created_at=data.get("created_at") or datetime.now(timezone.utc),
        )

    def upsert_user(self, user: User) -> User:
        ref = self._db.collection(self.USERS).document(user.user_id)
        snap = ref.get()
        if snap.exists:
            updates: dict = {}
            if user.name:
                updates["name"] = user.name
            if updates:
                ref.update(updates)
            existing = snap.to_dict() or {}
            return User(
                user_id=user.user_id,
                name=updates.get("name", existing.get("name", "")),
                created_at=existing.get("created_at") or user.created_at,
            )
        ref.set({"name": user.name, "created_at": user.created_at})
        return user

    # groups ----------------------------------------------------------
    def create_group(self, group: Group) -> Group:
        self._db.collection(self.GROUPS).document(group.group_id).set({
            "name": group.name,
            "creator_id": group.creator_id,
            "join_code": group.join_code,
            "created_at": group.created_at,
            "members": list(group.members),
            "whatsapp_group_id": group.whatsapp_group_id,
            "agora_chat_group_id": group.agora_chat_group_id,
        })
        return group

    def get_group(self, group_id: str) -> Group | None:
        snap = self._db.collection(self.GROUPS).document(group_id).get()
        if not snap.exists:
            return None
        return self._group_from_snap(group_id, snap.to_dict() or {})

    def get_group_by_code(self, code: str) -> Group | None:
        query = (
            self._db.collection(self.GROUPS)
            .where("join_code", "==", code)
            .limit(1)
            .get()
        )
        for snap in query:
            return self._group_from_snap(snap.id, snap.to_dict() or {})
        return None

    def add_member(self, group_id: str, user_id: str) -> Group | None:
        ref = self._db.collection(self.GROUPS).document(group_id)
        snap = ref.get()
        if not snap.exists:
            return None
        ref.update({"members": self._fs.ArrayUnion([user_id])})
        return self.get_group(group_id)

    def delete_group(self, group_id: str) -> bool:
        ref = self._db.collection(self.GROUPS).document(group_id)
        if not ref.get().exists:
            return False
        ref.delete()
        return True

    def list_groups_for_user(self, user_id: str) -> list[Group]:
        query = (
            self._db.collection(self.GROUPS)
            .where("members", "array_contains", user_id)
            .get()
        )
        return [self._group_from_snap(snap.id, snap.to_dict() or {}) for snap in query]

    # messages --------------------------------------------------------
    def append_message(self, message: Message) -> Message:
        self._db.collection(self.MESSAGES).add({
            "session_key": message.session_key,
            "user_id": message.user_id,
            "direction": message.direction,
            "text": message.text,
            "media_url": message.media_url,
            "media_type": message.media_type,
            "caption": message.caption,
            "created_at": message.created_at,
            "sender_id": message.sender_id,
            "sender_name": message.sender_name,
        })
        return message

    def recent_messages(self, session_key: str, limit: int = 20) -> list[Message]:
        query = (
            self._db.collection(self.MESSAGES)
            .where("session_key", "==", session_key)
            .order_by("created_at", direction=self._fs.Query.DESCENDING)
            .limit(limit)
            .get()
        )
        msgs = [
            Message(
                session_key=snap.get("session_key"),
                user_id=snap.get("user_id"),
                direction=snap.get("direction"),
                text=snap.get("text"),
                media_url=snap.get("media_url"),
                media_type=snap.get("media_type"),
                caption=snap.get("caption"),
                created_at=snap.get("created_at"),
                sender_id=snap.get("sender_id") or "",
                sender_name=snap.get("sender_name") or "",
            )
            for snap in query
        ]
        msgs.reverse()  # return oldest-first for prompt-context use
        return msgs

    # devices ---------------------------------------------------------
    def register_device(self, device: Device) -> Device:
        self._db.collection(self.DEVICES).document(device.fcm_token).set({
            "user_id": device.user_id,
            "platform": device.platform,
            "created_at": device.created_at,
        })
        return device

    def list_devices(self, user_id: str) -> list[Device]:
        query = (
            self._db.collection(self.DEVICES)
            .where("user_id", "==", user_id)
            .get()
        )
        return [
            Device(
                user_id=snap.get("user_id"),
                fcm_token=snap.id,
                platform=snap.get("platform"),
                created_at=snap.get("created_at") or datetime.now(timezone.utc),
            )
            for snap in query
        ]

    def delete_device(self, user_id: str, fcm_token: str) -> bool:
        ref = self._db.collection(self.DEVICES).document(fcm_token)
        snap = ref.get()
        if not snap.exists or (snap.to_dict() or {}).get("user_id") != user_id:
            return False
        ref.delete()
        return True

    @staticmethod
    def _group_from_snap(group_id: str, data: dict) -> Group:
        return Group(
            group_id=group_id,
            name=data.get("name", ""),
            creator_id=data.get("creator_id", ""),
            join_code=data.get("join_code", ""),
            created_at=data.get("created_at") or datetime.now(timezone.utc),
            members=set(data.get("members") or []),
            whatsapp_group_id=data.get("whatsapp_group_id") or "",
            agora_chat_group_id=data.get("agora_chat_group_id") or "",
        )


def make_store_from_env() -> Store:
    """Pick a store based on env. Defaults to InMemoryStore when GCP is absent."""
    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "").strip()
    has_creds = bool(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        or os.environ.get("FIRESTORE_EMULATOR_HOST", "").strip()
    )
    if project_id and has_creds:
        try:
            return FirestoreStore(project_id=project_id)
        except Exception as exc:
            log.warning("FirestoreStore init failed, falling back to InMemoryStore: %s", exc)
    return InMemoryStore()
