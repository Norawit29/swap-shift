"""FastAPI entry: /webhook, /healthz, /cron/expire, /cron/drift, /cron/go-live"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request

from .change.models import utcnow
from .change.service import ChangeService, Incoming, Reply, expire_all
from .commands import HEAD_ONLY_CMDS, ensure_front_tab, go_live, parse_command, roster_link, run_admin
from .db import init_db, session
from .line import templates as T
from .line.client import LineClient
from .line.postback import parse_free_text, parse_postback
from .line.signature import verify_signature
from .llm.client import LLM
from .settings import get_settings
from .sheets.client import Ward, ward_for_group
from .sheets.control import active_months, read_control
from .sheets.drift import detect_drift
from .thai_date import Month, fmt_day

log = logging.getLogger("agent")
app = FastAPI(title="line-swap-agent")
CONFIDENCE_MIN = 0.6


@app.on_event("startup")
async def _startup() -> None:
    s = get_settings()
    logging.basicConfig(level=s.log_level, format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":%(message)r}')
    init_db()
    if s.internal_cron:
        asyncio.create_task(_internal_cron())


async def _internal_cron() -> None:
    """In-process scheduler: expire every 10 min, drift every 30 min, go-live daily 00:05 local time."""
    import zoneinfo

    tz = zoneinfo.ZoneInfo(get_settings().tz)
    last_go_live: date | None = None
    tick = 0
    log.info("internal cron started")
    while True:
        await asyncio.sleep(600)
        tick += 1
        try:
            await asyncio.to_thread(cron_expire, get_settings().cron_token or None)
            if tick % 3 == 0:
                await asyncio.to_thread(cron_drift, get_settings().cron_token or None)
            now = datetime.now(tz)
            if now.hour == 0 and now.minute >= 5 and last_go_live != now.date():
                await asyncio.to_thread(cron_go_live, get_settings().cron_token or None)
                last_go_live = now.date()
        except Exception:
            log.exception("internal cron tick failed")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# ───────────────────────── webhook ─────────────────────────

@app.post("/webhook")
async def webhook(request: Request, bg: BackgroundTasks) -> dict:
    body = await request.body()
    s = get_settings()
    if not verify_signature(s.line_channel_secret, body, request.headers.get("X-Line-Signature")):
        raise HTTPException(400, "bad signature")
    payload = json.loads(body)
    for ev in payload.get("events", []):
        src = ev.get("source", {})
        # setup aid: every event's ids at INFO so groupId / head-nurse userId can be copied from the log
        log.info("event type=%s source=%s groupId=%s userId=%s", ev.get("type"), src.get("type"),
                 src.get("groupId"), src.get("userId"))
        if src.get("type") != "group" or src.get("groupId") not in s.allowed_groups:
            continue  # ignore 1:1 and unknown groups entirely
        bg.add_task(handle_event, ev)
    return {"ok": True}


def handle_event(ev: dict, line: LineClient | None = None, llm: LLM | None = None, today: date | None = None) -> None:
    """Runs in background. All exceptions logged; never raise into LINE."""
    line = line or LineClient()
    llm = llm or LLM()
    try:
        _handle(ev, line, llm, today)
    except Exception:
        log.exception("event handling failed")


def _handle(ev: dict, line: LineClient, llm: LLM, today: date | None) -> None:
    s = get_settings()
    group_id = ev["source"]["groupId"]
    user_id = ev["source"].get("userId", "")
    token = ev.get("replyToken")
    ward = ward_for_group(group_id)
    if ward is None:
        log.warning("no sheet for group %s", group_id)
        return
    etype = ev.get("type")
    is_head = user_id in s.head_nurse_ids

    with session() as db:
        svc = ChangeService(ward, llm, db)

        if etype == "postback":
            action, cid = parse_postback(ev.get("postback", {}).get("data", ""))
            if action == "confirm" and cid:
                _send(line, token, group_id, svc.confirm(cid, user_id))
            elif action == "cancel" and cid:
                _send(line, token, group_id, svc.cancel(user_id, cid))
            return

        if etype != "message" or ev.get("message", {}).get("type") != "text":
            return
        text = ev["message"]["text"].strip()

        # 1) exact-match commands (before LLM)
        cmd = parse_command(text)
        log.info("route: cmd=%s head=%s", cmd.name if cmd else None, is_head)
        if cmd:
            if cmd.name in HEAD_ONLY_CMDS:
                if not is_head:
                    _send(line, token, group_id, Reply("คำสั่งนี้ใช้ได้เฉพาะหัวหน้าเวร"))
                    return
                name = line.display_name(group_id, user_id)
                _send(line, token, group_id, Reply(run_admin(cmd, ward, name, today)))
            elif cmd.name == "ตาราง":
                _send(line, token, group_id, Reply(roster_link(ward, cmd.arg, today)))
            elif cmd.name == "สถานะ":
                _send(line, token, group_id, svc.status(user_id))
            elif cmd.name == "ยกเลิก":
                _send(line, token, group_id, svc.cancel(user_id))
            return

        # 2) free-text confirm/cancel for an open request (no LLM needed)
        pending = svc.open_request(user_id)
        action, cid = parse_free_text(text)
        if pending is not None and pending.state == "PENDING_CONFIRM" and action:
            r = svc.confirm(cid or pending.id, user_id) if action == "confirm" else svc.cancel(user_id, cid or pending.id)
            _send(line, token, group_id, r)
            return

        # 3) clarification answer: merge with prior within window
        if pending is not None and pending.state == "PENDING_CLARIFICATION":
            age_min = (utcnow() - pending.updated_at).total_seconds() / 60 if pending.updated_at else 0
            if age_min <= s.clarify_window_min:
                msg = Incoming(group_id, user_id, pending.reporter_display_name, text, today)
                r = svc.handle_swap_report(msg, pending) if pending.kind == "swap" else svc.handle_edit(msg, pending)
                _send(line, token, group_id, r)
                return

        if action and pending is None and len(text) <= 12:
            log.info("route: confirm-word with no pending → silent")
            return  # "ยืนยัน"/"ok ค่ะ" with nothing open — no LLM call, stay silent

        # 4) classify
        c = llm.classify(text)
        log.info("classify: intent=%s conf=%.2f", c.intent, c.confidence)
        if c.confidence < CONFIDENCE_MIN or c.intent in ("other", "command"):
            return  # silent; nothing stored
        if c.intent == "confirm_reply":
            if pending is None:
                return
            r = svc.confirm(pending.id, user_id) if action != "cancel" else svc.cancel(user_id, pending.id)
            _send(line, token, group_id, r)
            return
        if c.intent == "roster_query":
            _send(line, token, group_id, svc.answer_query(Incoming(group_id, user_id, "", text, today)))
            return
        if c.intent == "roster_edit" and not is_head:
            _send(line, token, group_id, Reply(T.HEAD_ONLY))
            return
        name = line.display_name(group_id, user_id)
        msg = Incoming(group_id, user_id, name, text, today)
        r = svc.handle_swap_report(msg) if c.intent == "swap_report" else svc.handle_edit(msg)
        _send(line, token, group_id, r)


def _send(line: LineClient, token: str | None, group_id: str, r: Reply) -> None:
    log.info("reply: %s%s", r.text.splitlines()[0][:60], " [quick_reply]" if r.quick_reply_id else "")
    line.send(token, group_id, [r.text, *r.extra], r.quick_reply_id)


# ───────────────────────── cron ─────────────────────────

def _check_cron(token: str | None) -> None:
    s = get_settings()
    if s.cron_token and token != s.cron_token:
        raise HTTPException(401)


def _wards() -> list[tuple[str, Ward]]:
    return [(g, Ward(sid)) for g, sid in get_settings().sheet_ids.items()]


@app.post("/cron/expire")
def cron_expire(token: str | None = Query(None)) -> dict:
    _check_cron(token)
    line = LineClient()
    with session() as db:
        expired = expire_all(db)
        by_group: dict[str, list[str]] = {}
        for cr in expired:
            by_group.setdefault(cr.group_id, []).append(T.EXPIRED.format(cid=cr.id))
    for g, texts in by_group.items():  # batch one push per group
        line.push(g, ["\n".join(texts)])
    return {"expired": len(expired)}


@app.post("/cron/drift")
def cron_drift(token: str | None = Query(None)) -> dict:
    _check_cron(token)
    line = LineClient()
    found = 0
    for g, ward in _wards():
        ctl = read_control(ward)
        items: list[str] = []
        for key in active_months(ctl):
            if ctl.get(f"status:{key}") not in ("published", "live"):
                continue
            m = Month.from_key(key)
            try:
                for sid, d, exp, act in detect_drift(ward, m):
                    items.append(f"{sid} วันที่ {fmt_day(m, d)} ({exp or '-'} → {act or '-'})")
            except KeyError as e:
                log.warning("drift skip %s: %s", key, e)
        try:
            ensure_front_tab(ward, ctl)  # self-heal tab order (current month must stay leftmost)
        except Exception:  # noqa: BLE001
            log.warning("ensure_front_tab failed for %s", g)
        if items:
            found += len(items)
            log.warning("drift in %s: %s", g, items)
            line.push(g, [T.drift_alert(items[:30])])
    return {"drift": found}


@app.post("/cron/go-live")
def cron_go_live(token: str | None = Query(None)) -> dict:
    _check_cron(token)
    out = {}
    for g, ward in _wards():
        out[g] = go_live(ward, date.today())
    return out
