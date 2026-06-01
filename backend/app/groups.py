from __future__ import annotations

import logging
from typing import Protocol

from .store import Group, Store, new_group_id, new_join_code

log = logging.getLogger(__name__)


class ChatGroupMirror(Protocol):
    """The subset of AgoraChatRestClient that GroupService needs.

    Lets tests pass in a stub without standing up the full client.
    """

    def create_chat_group(self, *, name: str, owner: str,
                          members: list[str] | None = None) -> str | None: ...
    def add_member(self, *, chat_group_id: str, username: str) -> bool: ...
    def remove_member(self, *, chat_group_id: str, username: str) -> bool: ...
    def delete_chat_group(self, chat_group_id: str) -> bool: ...


class GroupService:
    """Thin service over a Store. Owns group lifecycle and membership rules.

    If a `chat_mirror` is supplied, every lifecycle event is also reflected
    into Agora Chat (create/join/delete). Mirroring is best-effort — REST
    failures are logged but don't abort the in-store change. This means a
    group can exist locally without an Agora-side mirror (the WS fallback
    path still serves it) until the next backfill.
    """

    def __init__(self, store: Store, chat_mirror: ChatGroupMirror | None = None):
        self._store = store
        self._chat = chat_mirror

    def create(
        self,
        name: str,
        creator_id: str,
        whatsapp_group_id: str = "",
    ) -> Group:
        agora_chat_group_id = ""
        if self._chat is not None:
            try:
                agora_chat_group_id = self._chat.create_chat_group(
                    name=name,
                    owner=creator_id,
                    members=[creator_id],
                ) or ""
            except Exception as exc:
                log.warning("Agora Chat mirror create failed for %s: %s", name, exc)

        group = Group(
            group_id=new_group_id(),
            name=name,
            creator_id=creator_id,
            join_code=new_join_code(),
            members={creator_id},
            whatsapp_group_id=whatsapp_group_id,
            agora_chat_group_id=agora_chat_group_id,
        )
        return self._store.create_group(group)

    def join(self, code: str, user_id: str) -> Group | None:
        group = self._store.get_group_by_code(code)
        if not group:
            return None
        updated = self._store.add_member(group.group_id, user_id)
        if updated and self._chat is not None and updated.agora_chat_group_id:
            try:
                self._chat.add_member(
                    chat_group_id=updated.agora_chat_group_id,
                    username=user_id,
                )
            except Exception as exc:
                log.warning("Agora Chat mirror add_member failed for %s: %s",
                            updated.group_id, exc)
        return updated

    def get(self, group_id: str) -> Group | None:
        return self._store.get_group(group_id)

    def delete(self, group_id: str, requester_id: str) -> bool:
        group = self._store.get_group(group_id)
        if not group or group.creator_id != requester_id:
            return False
        if self._chat is not None and group.agora_chat_group_id:
            try:
                self._chat.delete_chat_group(group.agora_chat_group_id)
            except Exception as exc:
                log.warning("Agora Chat mirror delete failed for %s: %s",
                            group.group_id, exc)
        return self._store.delete_group(group_id)
