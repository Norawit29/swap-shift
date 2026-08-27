"""LINE Messaging API wrapper. Reply where possible (free); push only when needed."""
from __future__ import annotations

import logging
from functools import lru_cache

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PostbackAction,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)

from ..settings import get_settings
from .postback import cancel_data, confirm_data

log = logging.getLogger(__name__)


@lru_cache
def _api() -> MessagingApi:
    cfg = Configuration(access_token=get_settings().line_channel_access_token)
    return MessagingApi(ApiClient(cfg))


def _quick_reply(cid: str) -> QuickReply:
    return QuickReply(items=[
        QuickReplyItem(action=PostbackAction(label="ยืนยัน", data=confirm_data(cid), display_text="ยืนยัน")),
        QuickReplyItem(action=PostbackAction(label="ยกเลิก", data=cancel_data(cid), display_text="ยกเลิก")),
    ])


def _messages(texts: list[str], quick_reply_id: str | None) -> list[TextMessage]:
    msgs = [TextMessage(text=t[:5000]) for t in texts if t]
    if msgs and quick_reply_id:
        msgs[-1].quick_reply = _quick_reply(quick_reply_id)
    return msgs


class LineClient:
    def reply(self, reply_token: str, texts: list[str], quick_reply_id: str | None = None) -> bool:
        try:
            _api().reply_message(ReplyMessageRequest(reply_token=reply_token,
                                                     messages=_messages(texts, quick_reply_id)))
            return True
        except Exception as e:  # reply token expired/used → caller may fall back to push
            log.warning("reply failed: %s", e)
            return False

    def push(self, to: str, texts: list[str], quick_reply_id: str | None = None) -> None:
        _api().push_message(PushMessageRequest(to=to, messages=_messages(texts, quick_reply_id)))

    def send(self, reply_token: str | None, group_id: str, texts: list[str], quick_reply_id: str | None = None) -> None:
        if reply_token and self.reply(reply_token, texts, quick_reply_id):
            return
        self.push(group_id, texts, quick_reply_id)

    def display_name(self, group_id: str, user_id: str) -> str:
        try:
            return _api().get_group_member_profile(group_id, user_id).display_name or ""
        except Exception as e:
            log.info("profile lookup failed: %s", e)
            return ""
