"""FastAPI app: login, chats, global settings, bot process control."""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

from decouple import config
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from dashboard import process_control
from helpers import normalize_telegram_chat_id
from logger import log as dash_log, release_dashboard_file_handlers
from saherbot_db.bootstrap import bump_chats_revision, init_db
from saherbot_db.database import get_session_factory
from saherbot_db.models import AutoReply, Bot, Chat, ChatBannedWord, Event, GlobalSettings

import backup_zip_util
from config_store import DEFAULT_ALLOWED_CONTENT_TYPES
from list_seed import seed_auto_replies_from_list_folder

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

# عناوين عربية لأنواع الأحداث في الواجهة (المفتاح = القيمة المخزّنة في DB)
_EVENT_TYPE_LABEL_AR: dict[str, str] = {
    "list_reply": "قائمة الردود",
    "delete_length": "حذف — تجاوز طول الرسالة",
    "delete_bad_type": "حذف — نوع رسالة غير مسموح",
    "delete_forbidden_share": "حذف — رابط أو جوال أو منشن",
    "delete_moderation": "حذف — إشراف عام",
    "delete_banned_word": "حذف — كلمة ممنوعة",
    "kick_banned_word_strikes": "طرد — تكرار مخالفات الكلمات الممنوعة",
    "ban_strikes": "حظر — تكرار مخالفات الإشراف",
}


def event_type_label_ar(event_type: str | None) -> str:
    """تسمية عربية لنوع الحدث في الداشبورد؛ إن لم تُعرَف تُعاد القيمة الأصلية."""
    t = (event_type or "").strip()
    if not t:
        return "—"
    return _EVENT_TYPE_LABEL_AR.get(t, t)


app = FastAPI(title="SaherBot Dashboard", docs_url=None, redoc_url=None)
_secret = str(config("DASHBOARD_SECRET", default="")).strip() or str(config("DASHBOARD_PASSWORD", default="change-me"))
app.add_middleware(SessionMiddleware, secret_key=_secret[:64].ljust(16, "x"), same_site="lax", https_only=False)
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.globals["event_type_label_ar"] = event_type_label_ar
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def _on_startup() -> None:
    try:
        init_db()
        dash_log("Dashboard: DB initialized", "info")
    except RuntimeError as e:
        import logging

        logging.getLogger("uvicorn.error").warning("SaherBot DB init: %s", e)
    _dash_data = Path(__file__).resolve().parent.parent / "data"
    _dash_data.mkdir(parents=True, exist_ok=True)
    try:
        (_dash_data / "dashboard.pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


@app.on_event("shutdown")
def _on_shutdown_dash_pid() -> None:
    _p = Path(__file__).resolve().parent.parent / "data" / "dashboard.pid"
    try:
        if _p.is_file() and _p.read_text(encoding="utf-8").strip() == str(os.getpid()):
            _p.unlink(missing_ok=True)
    except OSError:
        pass


def _pw_ok(password: str) -> bool:
    expected = str(config("DASHBOARD_PASSWORD", default="")).strip()
    if not expected:
        return False
    return password == expected


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def _flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def _pop_flash(request: Request) -> str | None:
    return request.session.pop("flash", None)


def _optional_chat_id_query_param(raw: str | None) -> tuple[int | None, str]:
    """Parse ``chat_id`` from a GET filter: blank means no filter; returns (id_or_none, field_value_for_form)."""
    s = (raw or "").strip()
    if not s:
        return None, ""
    try:
        cid = normalize_telegram_chat_id(int(s))
        return cid, str(cid)
    except ValueError:
        return None, s


def _wants_json(request: Request) -> bool:
    return "application/json" in (request.headers.get("accept") or "").lower()


def _parse_chat_form(
    chat_id: str,
    bot_id: str | None,
    title: str | None,
    moderation_enabled: str | None,
    msg_max_length: str | None,
    msg_length_unlimited: str | None,
    echo_enabled: str | None,
    moderation_apply_to_admins: str | None = None,
    moderation_block_phones: str | None = None,
    moderation_block_mentions: str | None = None,
    moderation_block_links: str | None = None,
) -> tuple[str | None, dict | None]:
    """Shared validation for creating/updating chats (same rules as ``/chats/new``)."""
    try:
        cid = normalize_telegram_chat_id(int(str(chat_id).strip()))
    except ValueError:
        return "معرف المحادثة غير صالح.", None
    mod = moderation_enabled in ("1", "on", "true", "yes")
    try:
        bid_raw = (bot_id or "").strip()
        bid = int(bid_raw) if bid_raw else None
    except ValueError:
        return "معرّف البوت غير صالح.", None
    if mod and bid is None:
        return "عند تفعيل المراقبة يجب اختيار البوت المسؤول عن هذه المحادثة.", None
    try:
        msg_limit = int(str(msg_max_length or "").strip()) if str(msg_max_length or "").strip() else None
    except ValueError:
        return "حد طول الرسالة يجب أن يكون رقماً أو فارغاً.", None
    def _on(v: str | None) -> bool:
        return v in ("1", "on", "true", "yes")

    return None, {
        "cid": cid,
        "bid": bid,
        "title": (title or "").strip() or None,
        "mod": mod,
        "msg_limit": msg_limit,
        "unlimited": msg_length_unlimited in ("1", "on", "true", "yes"),
        "echo": echo_enabled in ("1", "on", "true", "yes"),
        "apply_admins": moderation_apply_to_admins in ("1", "on", "true", "yes"),
        "block_phones": _on(moderation_block_phones),
        "block_mentions": _on(moderation_block_mentions),
        "block_links": _on(moderation_block_links),
    }


_CT_FORM_ORDER = (
    "audio",
    "photo",
    "voice",
    "video",
    "text",
    "document",
    "sticker",
    "location",
    "contact",
)


def _collect_allowed_content_types_values(*vals: str | None) -> list[str]:
    """قيم حقول ``allow_ct_*`` بنفس ترتيب ``_CT_FORM_ORDER``."""
    def _on(v: str | None) -> bool:
        return v in ("1", "on", "true", "yes")

    return [ct for ct, v in zip(_CT_FORM_ORDER, vals) if _on(v)]


def _json_bot_control(
    request: Request, ok: bool, msg: str, action: str
) -> JSONResponse:
    process_control.prune_stale_bot_pid()
    pid = process_control.read_bot_pid()
    st = process_control.bot_status()
    dash_log(f"Dashboard: bot {action} ok={ok} status={st} msg={msg[:200]}", "info")
    payload: dict[str, Any] = {
        "ok": ok,
        "message": msg,
        "action": action,
        "status": st,
        "pid": pid,
    }
    if not ok:
        payload["detail"] = msg
    return JSONResponse(payload)


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("dash_ok"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"flash": _pop_flash(request), "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, password: Annotated[str, Form()]):
    if _pw_ok(password):
        request.session["dash_ok"] = True
        dash_log("Dashboard: login success", "info")
        return RedirectResponse("/", status_code=303)
    dash_log("Dashboard: login failed (wrong password)", "info")
    return templates.TemplateResponse(
        request,
        "login.html",
        {"flash": None, "error": "كلمة المرور غير صحيحة."},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    dash_log("Dashboard: logout", "info")
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def _db() -> Session:
    SessionLocal = get_session_factory()
    return SessionLocal()


_LOG_TAIL_LINES = 200


def _tail_file_lines(path: Path, max_lines: int, chunk_size: int = 65536) -> list[str]:
    """Read last ``max_lines`` complete or partial lines from a file (UTF-8, ignore errors)."""
    blocks: list[bytes] = []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        newline_count = 0
        while pos > 0 and newline_count < max_lines + 1:
            step = min(chunk_size, pos)
            pos -= step
            f.seek(pos)
            blocks.insert(0, f.read(step))
            newline_count = b"".join(blocks).count(b"\n")
    text = b"".join(blocks).decode("utf-8", errors="ignore")
    lines = text.splitlines()
    return lines[-max_lines:] if len(lines) > max_lines else lines


def _safe_tail_log_file(filename: str, max_lines: int) -> list[str]:
    """Tail lines from ``logs/<filename>`` only; rejects path traversal."""
    name = (filename or "").strip()
    if not name or "/" in name or "\\" in name or ".." in name:
        return []
    logs_dir = (_PROJECT_ROOT / "logs").resolve()
    path = (logs_dir / name).resolve()
    try:
        path.relative_to(logs_dir)
    except ValueError:
        return []
    if not path.is_file():
        return []
    return _tail_file_lines(path, max_lines)


_LOG_DATE_FILENAME = re.compile(r"^\d{2}-\d{2}-\d{4}\.log$")


def _resolved_logs_dir() -> Path:
    d = (_PROJECT_ROOT / "logs").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_allowed_dashboard_log_file(path: Path, logs_dir: Path) -> bool:
    """True only for regular ``*.log`` files directly under ``logs/`` (no subdirs, no traversal)."""
    try:
        path = path.resolve()
        path.relative_to(logs_dir)
    except (ValueError, OSError):
        return False
    if not path.is_file():
        return False
    name = path.name
    if ".." in name or "/" in name or "\\" in name:
        return False
    if path.parent != logs_dir:
        return False
    if not name.endswith(".log"):
        return False
    if name == "bot-spawn.log" or _LOG_DATE_FILENAME.match(name):
        return True
    return name.endswith(".log")


def _clear_dashboard_logs() -> int:
    """Remove ``*.log`` files directly in ``logs/``; recreate empty ``bot-spawn.log``. Returns files removed."""
    try:
        release_dashboard_file_handlers()
    except Exception:
        pass
    logs_dir = _resolved_logs_dir()
    removed = 0
    for raw in logs_dir.iterdir():
        try:
            p = raw.resolve()
        except OSError:
            continue
        if not _is_allowed_dashboard_log_file(p, logs_dir):
            continue
        cleared = False
        try:
            p.unlink()
            cleared = True
        except OSError:
            try:
                p.write_text("", encoding="utf-8")
                cleared = True
            except OSError:
                pass
        if cleared:
            removed += 1
    try:
        (logs_dir / "bot-spawn.log").write_text("", encoding="utf-8")
    except OSError:
        pass
    return removed


def _events_log_sections(max_lines: int = _LOG_TAIL_LINES) -> list[dict[str, Any]]:
    """Tails for the events page: today's log (same name as ``logger.py``) and ``bot-spawn.log``."""
    today_name = datetime.now().strftime("%d-%m-%Y") + ".log"
    return [
        {
            "id": "today",
            "filename": today_name,
            "lines": _safe_tail_log_file(today_name, max_lines),
        },
        {
            "id": "bot_spawn",
            "filename": "bot-spawn.log",
            "lines": _safe_tail_log_file("bot-spawn.log", max_lines),
        },
    ]


def _dashboard_home_context() -> dict:
    """Stats + global settings for the main dashboard page (``/``)."""
    process_control.prune_stale_bot_pid()
    bot_st = process_control.bot_status()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with _db() as session:
        gs = session.get(GlobalSettings, 1)
        n_chats = int(session.scalar(select(func.count()).select_from(Chat)) or 0)
        n_chats_mod = int(
            session.scalar(select(func.count()).select_from(Chat).where(Chat.moderation_enabled.is_(True))) or 0
        )
        n_replies = int(session.scalar(select(func.count()).select_from(AutoReply)) or 0)
        n_events = int(session.scalar(select(func.count()).select_from(Event)) or 0)
        n_events_24h = int(session.scalar(select(func.count()).select_from(Event).where(Event.ts >= since)) or 0)
        n_bots = int(session.scalar(select(func.count()).select_from(Bot)) or 0)
        recent = list(session.scalars(select(Event).order_by(Event.id.desc()).limit(12)).all())
    return {
        "bot_status": bot_st,
        "bot_pid": process_control.read_bot_pid(),
        "global_settings": gs,
        "n_chats": n_chats,
        "n_chats_mod": n_chats_mod,
        "n_replies": n_replies,
        "n_events": n_events,
        "n_events_24h": n_events_24h,
        "n_bots": n_bots,
        "recent_events": recent,
    }


def _backup_files() -> list[Path]:
    backup_dir = _PROJECT_ROOT / "data" / "backups"
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)


def _selected_backup(name: str) -> Path | None:
    candidate = Path(name or "").name
    if not candidate:
        return None
    path = _PROJECT_ROOT / "data" / "backups" / candidate
    try:
        path.relative_to(_PROJECT_ROOT / "data" / "backups")
    except ValueError:
        return None
    if not path.is_file() or path.suffix.lower() != ".zip":
        return None
    return path


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    flash = _pop_flash(request)
    ctx = _dashboard_home_context()
    ctx["flash"] = flash
    return templates.TemplateResponse(request, "stats.html", ctx)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_legacy_redirect(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    return RedirectResponse("/", status_code=303)


@app.get("/api/bot-status")
async def api_bot_status(request: Request):
    if not request.session.get("dash_ok"):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    process_control.prune_stale_bot_pid()
    pid = process_control.read_bot_pid()
    return JSONResponse(
        {
            "status": process_control.bot_status(),
            "pid": pid,
            "last_message": process_control.bot_status_last_message(),
        }
    )


@app.post("/settings/global")
async def save_global_settings(
    request: Request,
    bot_description: Annotated[str | None, Form()] = None,
    bot_short_description: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        gs = session.get(GlobalSettings, 1)
        if gs is None:
            session.add(
                GlobalSettings(
                    id=1,
                    primary_chat_id=0,
                    bot_token=None,
                    notify_on_startup=False,
                    chats_config_revision=0,
                    default_msg_max_length=300,
                    default_msg_length_unlimited=False,
                    default_echo_enabled=False,
                    bot_description=(bot_description or "").strip() or None,
                    bot_short_description=(bot_short_description or "").strip() or None,
                )
            )
        else:
            gs.bot_description = (bot_description or "").strip() or None
            gs.bot_short_description = (bot_short_description or "").strip() or None
        session.commit()
    dash_log("Dashboard: global settings saved", "info")
    _flash(request, "تم حفظ أوصاف البوت (تُطبَّق عند إعادة تشغيل جميع عمليات البوت).")
    return RedirectResponse("/", status_code=303)


@app.get("/bots", response_class=HTMLResponse)
async def bots_list(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        bots = list(session.scalars(select(Bot).order_by(Bot.id)).all())
        chat_counts: dict[int, int] = {}
        for bid, cnt in session.execute(
            select(Chat.bot_id, func.count(Chat.chat_id)).where(Chat.bot_id.isnot(None)).group_by(Chat.bot_id)
        ).all():
            if bid is not None:
                chat_counts[int(bid)] = int(cnt)
    return templates.TemplateResponse(request, "bots.html", {"bots": bots, "chat_counts": chat_counts, "flash": _pop_flash(request)})


@app.get("/bots/new", response_class=HTMLResponse)
async def bots_new_get(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    return templates.TemplateResponse(request, "bot_form.html", {"bot": None, "error": None})


@app.post("/bots/new", response_class=HTMLResponse)
async def bots_new_post(
    request: Request,
    name: Annotated[str | None, Form()] = None,
    bot_token: Annotated[str, Form()] = "",
    primary_chat_id: Annotated[str | None, Form()] = None,
    notify_on_startup: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    tok = (bot_token or "").strip()
    if not tok:
        return templates.TemplateResponse(
            request, "bot_form.html", {"bot": None, "error": "التوكن مطلوب."}, status_code=400
        )
    try:
        pid_raw = int(str(primary_chat_id or "0").strip() or "0")
        pid = 0 if pid_raw == 0 else normalize_telegram_chat_id(pid_raw)
    except ValueError:
        return templates.TemplateResponse(
            request, "bot_form.html", {"bot": None, "error": "معرف المحادثة الأساسية يجب أن يكون رقماً."}, status_code=400
        )
    notify = notify_on_startup in ("1", "on", "true", "yes")
    with _db() as session:
        session.add(
            Bot(
                name=(name or "").strip() or None,
                bot_token=tok,
                notify_on_startup=notify,
                primary_chat_id=pid,
            )
        )
        session.commit()
    dash_log("Dashboard: bot created", "info")
    _flash(request, "تمت إضافة البوت.")
    return RedirectResponse("/bots", status_code=303)


@app.get("/bots/{bot_id}/edit", response_class=HTMLResponse)
async def bots_edit_get(request: Request, bot_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        row = session.get(Bot, bot_id)
        chats = list(session.scalars(select(Chat).where(Chat.bot_id == bot_id).order_by(Chat.chat_id)).all())
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "bot_form.html", {"bot": row, "linked_chats": chats, "error": None})


@app.post("/bots/{bot_id}/edit", response_class=HTMLResponse)
async def bots_edit_post(
    request: Request,
    bot_id: int,
    name: Annotated[str | None, Form()] = None,
    bot_token: Annotated[str | None, Form()] = None,
    primary_chat_id: Annotated[str | None, Form()] = None,
    notify_on_startup: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    try:
        pid_raw = int(str(primary_chat_id or "0").strip() or "0")
        pid = 0 if pid_raw == 0 else normalize_telegram_chat_id(pid_raw)
    except ValueError:
        _flash(request, "معرف المحادثة الأساسية يجب أن يكون رقماً.")
        return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)
    notify = notify_on_startup in ("1", "on", "true", "yes")
    new_tok = (bot_token or "").strip()
    with _db() as session:
        row = session.get(Bot, bot_id)
        if row is None:
            raise HTTPException(status_code=404)
        row.name = (name or "").strip() or None
        row.primary_chat_id = pid
        row.notify_on_startup = notify
        if new_tok:
            row.bot_token = new_tok
        session.commit()
    dash_log(f"Dashboard: bot {bot_id} updated", "info")
    _flash(request, "تم الحفظ. أعد تشغيل عمليات البوت لتطبيق التوكن الجديد إن وُجد.")
    return RedirectResponse("/bots", status_code=303)


@app.post("/bots/{bot_id}/chats/new")
async def bots_chat_new_post(
    request: Request,
    bot_id: int,
    chat_id: Annotated[str, Form()],
    title: Annotated[str | None, Form()] = None,
    moderation_enabled: Annotated[str | None, Form()] = None,
    moderation_apply_to_admins: Annotated[str | None, Form()] = None,
    moderation_block_phones: Annotated[str | None, Form()] = None,
    moderation_block_mentions: Annotated[str | None, Form()] = None,
    moderation_block_links: Annotated[str | None, Form()] = None,
    msg_max_length: Annotated[str | None, Form()] = None,
    msg_length_unlimited: Annotated[str | None, Form()] = None,
    echo_enabled: Annotated[str | None, Form()] = None,
    allow_ct_audio: Annotated[str | None, Form()] = None,
    allow_ct_photo: Annotated[str | None, Form()] = None,
    allow_ct_voice: Annotated[str | None, Form()] = None,
    allow_ct_video: Annotated[str | None, Form()] = None,
    allow_ct_text: Annotated[str | None, Form()] = None,
    allow_ct_document: Annotated[str | None, Form()] = None,
    allow_ct_sticker: Annotated[str | None, Form()] = None,
    allow_ct_location: Annotated[str | None, Form()] = None,
    allow_ct_contact: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    err, fields = _parse_chat_form(
        chat_id,
        str(bot_id),
        title,
        moderation_enabled,
        msg_max_length,
        msg_length_unlimited,
        echo_enabled,
        moderation_apply_to_admins,
        moderation_block_phones,
        moderation_block_mentions,
        moderation_block_links,
    )
    if err:
        _flash(request, err)
        return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)
    allowed_ct = _collect_allowed_content_types_values(
        allow_ct_audio,
        allow_ct_photo,
        allow_ct_voice,
        allow_ct_video,
        allow_ct_text,
        allow_ct_document,
        allow_ct_sticker,
        allow_ct_location,
        allow_ct_contact,
    )
    if not allowed_ct:
        _flash(request, "اختر نوعاً واحداً على الأقل من أنواع الرسائل المسموحة.")
        return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)
    cid = int(fields["cid"])
    bid = int(fields["bid"]) if fields["bid"] is not None else None
    with _db() as session:
        if session.get(Bot, bot_id) is None:
            raise HTTPException(status_code=404)
        if bid != bot_id:
            _flash(request, "معرّف البوت غير متطابق.")
            return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)
        if session.get(Chat, cid) is not None:
            _flash(request, "هذا المعرف موجود مسبقاً.")
            return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)
        session.add(
            Chat(
                chat_id=cid,
                bot_id=bid,
                title=fields["title"],
                moderation_enabled=fields["mod"],
                moderation_apply_to_admins=fields["apply_admins"],
                moderation_block_phones=fields["block_phones"],
                moderation_block_mentions=fields["block_mentions"],
                moderation_block_links=fields["block_links"],
                allowed_content_types=allowed_ct,
                msg_max_length=fields["msg_limit"],
                msg_length_unlimited=fields["unlimited"],
                echo_enabled=fields["echo"],
            )
        )
        n_seed = seed_auto_replies_from_list_folder(session, cid)
        bump_chats_revision(session)
        session.commit()
    dash_log(
        f"Dashboard: chat {cid} created from bot {bot_id} (seeded {n_seed} replies from list/)",
        "info",
    )
    _flash(request, "تمت إضافة المحادثة وربطها بهذا البوت.")
    return RedirectResponse(f"/bots/{bot_id}/edit", status_code=303)


@app.post("/bots/{bot_id}/delete")
async def bots_delete(request: Request, bot_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        row = session.get(Bot, bot_id)
        if row is None:
            raise HTTPException(status_code=404)
        for c in session.scalars(select(Chat).where(Chat.bot_id == bot_id)).all():
            c.bot_id = None
        session.delete(row)
        bump_chats_revision(session)
        session.commit()
    dash_log(f"Dashboard: bot {bot_id} deleted", "info")
    _flash(request, "تم حذف البوت وفك ربط المحادثات.")
    return RedirectResponse("/bots", status_code=303)


@app.get("/chats", response_class=HTMLResponse)
async def chats_list(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        rows = list(session.scalars(select(Chat).order_by(Chat.chat_id)).all())
        bots_by_id = {b.id: b for b in session.scalars(select(Bot).order_by(Bot.id)).all()}
    return templates.TemplateResponse(
        request,
        "chats.html",
        {"chats": rows, "bots_by_id": bots_by_id, "flash": _pop_flash(request)},
    )


@app.get("/chats/new", response_class=HTMLResponse)
async def chats_new_get(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        bots = list(session.scalars(select(Bot).order_by(Bot.id)).all())
    return templates.TemplateResponse(request, "chat_form.html", {"chat": None, "error": None, "bots": bots, "default_allowed_content_types": list(DEFAULT_ALLOWED_CONTENT_TYPES)})


@app.post("/chats/new")
async def chats_new_post(
    request: Request,
    chat_id: Annotated[str, Form()],
    bot_id: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    moderation_enabled: Annotated[str | None, Form()] = None,
    moderation_apply_to_admins: Annotated[str | None, Form()] = None,
    moderation_block_phones: Annotated[str | None, Form()] = None,
    moderation_block_mentions: Annotated[str | None, Form()] = None,
    moderation_block_links: Annotated[str | None, Form()] = None,
    msg_max_length: Annotated[str | None, Form()] = None,
    msg_length_unlimited: Annotated[str | None, Form()] = None,
    echo_enabled: Annotated[str | None, Form()] = None,
    allow_ct_audio: Annotated[str | None, Form()] = None,
    allow_ct_photo: Annotated[str | None, Form()] = None,
    allow_ct_voice: Annotated[str | None, Form()] = None,
    allow_ct_video: Annotated[str | None, Form()] = None,
    allow_ct_text: Annotated[str | None, Form()] = None,
    allow_ct_document: Annotated[str | None, Form()] = None,
    allow_ct_sticker: Annotated[str | None, Form()] = None,
    allow_ct_location: Annotated[str | None, Form()] = None,
    allow_ct_contact: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    err, fields = _parse_chat_form(
        chat_id,
        bot_id,
        title,
        moderation_enabled,
        msg_max_length,
        msg_length_unlimited,
        echo_enabled,
        moderation_apply_to_admins,
        moderation_block_phones,
        moderation_block_mentions,
        moderation_block_links,
    )
    if err:
        if "معرف المحادثة" in err:
            with _db() as session:
                bots = list(session.scalars(select(Bot).order_by(Bot.id)).all())
            return templates.TemplateResponse(
                request,
                "chat_form.html",
                {"chat": None, "error": err, "bots": bots, "default_allowed_content_types": list(DEFAULT_ALLOWED_CONTENT_TYPES)},
                status_code=400,
            )
        _flash(request, err)
        return RedirectResponse("/chats/new", status_code=303)
    allowed_ct = _collect_allowed_content_types_values(
        allow_ct_audio,
        allow_ct_photo,
        allow_ct_voice,
        allow_ct_video,
        allow_ct_text,
        allow_ct_document,
        allow_ct_sticker,
        allow_ct_location,
        allow_ct_contact,
    )
    if not allowed_ct:
        _flash(request, "اختر نوعاً واحداً على الأقل من أنواع الرسائل المسموحة.")
        return RedirectResponse("/chats/new", status_code=303)
    cid = int(fields["cid"])
    bid = fields["bid"]
    with _db() as session:
        if session.get(Chat, cid) is not None:
            _flash(request, "هذا المعرف موجود مسبقاً.")
            return RedirectResponse("/chats", status_code=303)
        if bid is not None and session.get(Bot, bid) is None:
            _flash(request, "البوت المختار غير موجود.")
            return RedirectResponse("/chats/new", status_code=303)
        session.add(
            Chat(
                chat_id=cid,
                bot_id=bid,
                title=fields["title"],
                moderation_enabled=fields["mod"],
                moderation_apply_to_admins=fields["apply_admins"],
                moderation_block_phones=fields["block_phones"],
                moderation_block_mentions=fields["block_mentions"],
                moderation_block_links=fields["block_links"],
                allowed_content_types=allowed_ct,
                msg_max_length=fields["msg_limit"],
                msg_length_unlimited=fields["unlimited"],
                echo_enabled=fields["echo"],
            )
        )
        n_seed = seed_auto_replies_from_list_folder(session, cid)
        bump_chats_revision(session)
        session.commit()
    dash_log(f"Dashboard: chat {cid} created (seeded {n_seed} replies from list/)", "info")
    _flash(request, "تمت إضافة المحادثة.")
    return RedirectResponse("/chats", status_code=303)


@app.get("/chats/{chat_id}/edit", response_class=HTMLResponse)
async def chats_edit_get(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        row = session.get(Chat, chat_id)
        bots = list(session.scalars(select(Bot).order_by(Bot.id)).all())
    if row is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "chat_form.html",
        {
            "chat": row,
            "error": None,
            "bots": bots,
            "default_allowed_content_types": list(DEFAULT_ALLOWED_CONTENT_TYPES),
        },
    )


@app.post("/chats/{chat_id}/edit")
async def chats_edit_post(
    request: Request,
    chat_id: int,
    new_chat_id: Annotated[str | None, Form()] = None,
    bot_id: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    moderation_enabled: Annotated[str | None, Form()] = None,
    moderation_apply_to_admins: Annotated[str | None, Form()] = None,
    moderation_block_phones: Annotated[str | None, Form()] = None,
    moderation_block_mentions: Annotated[str | None, Form()] = None,
    moderation_block_links: Annotated[str | None, Form()] = None,
    msg_max_length: Annotated[str | None, Form()] = None,
    msg_length_unlimited: Annotated[str | None, Form()] = None,
    echo_enabled: Annotated[str | None, Form()] = None,
    allow_ct_audio: Annotated[str | None, Form()] = None,
    allow_ct_photo: Annotated[str | None, Form()] = None,
    allow_ct_voice: Annotated[str | None, Form()] = None,
    allow_ct_video: Annotated[str | None, Form()] = None,
    allow_ct_text: Annotated[str | None, Form()] = None,
    allow_ct_document: Annotated[str | None, Form()] = None,
    allow_ct_sticker: Annotated[str | None, Form()] = None,
    allow_ct_location: Annotated[str | None, Form()] = None,
    allow_ct_contact: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    path_id = int(chat_id)
    new_raw = (new_chat_id or "").strip()
    try:
        desired_id = normalize_telegram_chat_id(int(new_raw)) if new_raw else path_id
    except ValueError:
        _flash(request, "معرف المحادثة الجديد غير صالح.")
        return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
    mod = moderation_enabled in ("1", "on", "true", "yes")
    try:
        bid_raw = (bot_id or "").strip()
        bid = int(bid_raw) if bid_raw else None
    except ValueError:
        _flash(request, "معرّف البوت غير صالح.")
        return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
    if mod and bid is None:
        _flash(request, "عند تفعيل المراقبة يجب اختيار البوت.")
        return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
    try:
        msg_limit = int(str(msg_max_length or "").strip()) if str(msg_max_length or "").strip() else None
    except ValueError:
        _flash(request, "حد طول الرسالة يجب أن يكون رقماً أو فارغاً.")
        return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
    apply_admins = moderation_apply_to_admins in ("1", "on", "true", "yes")
    block_phones = moderation_block_phones in ("1", "on", "true", "yes")
    block_mentions = moderation_block_mentions in ("1", "on", "true", "yes")
    block_links = moderation_block_links in ("1", "on", "true", "yes")
    allowed_ct = _collect_allowed_content_types_values(
        allow_ct_audio,
        allow_ct_photo,
        allow_ct_voice,
        allow_ct_video,
        allow_ct_text,
        allow_ct_document,
        allow_ct_sticker,
        allow_ct_location,
        allow_ct_contact,
    )
    if not allowed_ct:
        _flash(request, "اختر نوعاً واحداً على الأقل من أنواع الرسائل المسموحة.")
        return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
    id_changed = False
    with _db() as session:
        row = session.get(Chat, path_id)
        if row is None:
            raise HTTPException(status_code=404)
        if bid is not None and session.get(Bot, bid) is None:
            _flash(request, "البوت المختار غير موجود.")
            return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
        if desired_id != path_id:
            err = _reassign_chat_primary_key(session, row, desired_id)
            if err:
                _flash(request, err)
                return RedirectResponse(f"/chats/{path_id}/edit", status_code=303)
            row = session.get(Chat, desired_id)
            if row is None:
                raise HTTPException(status_code=500)
            id_changed = True
        row.moderation_enabled = mod
        row.bot_id = bid
        row.title = (title or "").strip() or None
        row.msg_max_length = msg_limit
        row.msg_length_unlimited = msg_length_unlimited in ("1", "on", "true", "yes")
        row.echo_enabled = echo_enabled in ("1", "on", "true", "yes")
        row.moderation_apply_to_admins = apply_admins
        row.moderation_block_phones = block_phones
        row.moderation_block_mentions = block_mentions
        row.moderation_block_links = block_links
        row.allowed_content_types = allowed_ct
        bump_chats_revision(session)
        session.commit()
    final_id = int(desired_id) if id_changed else path_id
    dash_log(
        f"Dashboard: chat updated id={final_id} (id_changed={id_changed})",
        "info",
    )
    _flash(request, "تم الحفظ.")
    if id_changed:
        return RedirectResponse(f"/chats/{final_id}/edit", status_code=303)
    return RedirectResponse("/chats", status_code=303)


@app.post("/chats/{chat_id}/delete")
async def chats_delete(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        row = session.get(Chat, chat_id)
        if row is not None:
            session.execute(delete(AutoReply).where(AutoReply.chat_id == chat_id))
            session.execute(delete(ChatBannedWord).where(ChatBannedWord.chat_id == chat_id))
            session.delete(row)
            bump_chats_revision(session)
            session.commit()
    dash_log(f"Dashboard: chat {chat_id} deleted (and its auto-replies)", "info")
    _flash(request, "تم الحذف.")
    return RedirectResponse("/chats", status_code=303)


def _reassign_chat_primary_key(session: Session, old_row: Chat, new_id: int) -> str | None:
    """Replace ``chats.chat_id`` with ``new_id`` and repoint children. Returns Arabic error or None."""
    old_id = int(old_row.chat_id)
    new_id = int(new_id)
    if new_id == old_id:
        return None
    if session.get(Chat, new_id) is not None:
        return "معرف المحادثة الجديد مستخدم مسبقاً."
    session.add(
        Chat(
            chat_id=new_id,
            bot_id=old_row.bot_id,
            title=old_row.title,
            moderation_enabled=old_row.moderation_enabled,
            moderation_apply_to_admins=bool(getattr(old_row, "moderation_apply_to_admins", False)),
            moderation_block_phones=bool(getattr(old_row, "moderation_block_phones", True)),
            moderation_block_mentions=bool(getattr(old_row, "moderation_block_mentions", True)),
            moderation_block_links=bool(getattr(old_row, "moderation_block_links", True)),
            allowed_content_types=getattr(old_row, "allowed_content_types", None),
            msg_max_length=old_row.msg_max_length,
            msg_length_unlimited=old_row.msg_length_unlimited,
            echo_enabled=old_row.echo_enabled,
            moderation_rules=old_row.moderation_rules,
        )
    )
    session.flush()
    session.execute(update(AutoReply).where(AutoReply.chat_id == old_id).values(chat_id=new_id))
    session.execute(update(ChatBannedWord).where(ChatBannedWord.chat_id == old_id).values(chat_id=new_id))
    session.execute(update(Event).where(Event.chat_id == old_id).values(chat_id=new_id))
    session.delete(old_row)
    session.flush()
    return None


def _chat_or_404(session: Session, chat_id: int) -> Chat:
    row = session.get(Chat, chat_id)
    if row is None:
        raise HTTPException(status_code=404)
    return row


@app.get("/chats/{chat_id}/replies", response_class=HTMLResponse)
async def chat_replies_list(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        chat = _chat_or_404(session, chat_id)
        rows = list(
            session.scalars(
                select(AutoReply).where(AutoReply.chat_id == chat_id).order_by(AutoReply.sort_order, AutoReply.id)
            ).all()
        )
        others = list(
            session.scalars(select(Chat).where(Chat.chat_id != chat_id).order_by(Chat.chat_id)).all()
        )
    return templates.TemplateResponse(
        request,
        "chat_replies.html",
        {"chat": chat, "rows": rows, "other_chats": others, "flash": _pop_flash(request)},
    )


@app.get("/chats/{chat_id}/replies/new", response_class=HTMLResponse)
async def chat_replies_new_get(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        chat = _chat_or_404(session, chat_id)
    return templates.TemplateResponse(
        request,
        "chat_reply_form.html",
        {"chat": chat, "chat_id": chat_id, "reply": None, "error": None},
    )


@app.post("/chats/{chat_id}/replies/new")
async def chat_replies_new_post(
    request: Request,
    chat_id: int,
    trigger: Annotated[str, Form()],
    response_type: Annotated[str, Form()],
    response_text: Annotated[str | None, Form()] = None,
    photo_path: Annotated[str | None, Form()] = None,
    enabled: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    rt = (response_type or "text").strip().lower()
    if rt not in ("text", "photo"):
        rt = "text"
    en = enabled in ("1", "on", "true", "yes")
    trig = (trigger or "").strip()
    if not trig:
        with _db() as session:
            chat = _chat_or_404(session, chat_id)
        return templates.TemplateResponse(
            request,
            "chat_reply_form.html",
            {"chat": chat, "chat_id": chat_id, "reply": None, "error": "المحفّز فارغ."},
            status_code=400,
        )
    with _db() as session:
        chat = _chat_or_404(session, chat_id)
        existing = list(
            session.scalars(
                select(AutoReply).where(AutoReply.chat_id == chat_id).where(AutoReply.enabled.is_(True))
            ).all()
        )
        if any((row.trigger or "").strip().lower() == trig.lower() for row in existing):
            return templates.TemplateResponse(
                request,
                "chat_reply_form.html",
                {
                    "chat": chat,
                    "chat_id": chat_id,
                    "reply": None,
                    "error": "يوجد محفّز مفعّل بنفس الاسم في هذه المحادثة.",
                },
                status_code=400,
            )
        session.add(
            AutoReply(
                chat_id=chat_id,
                trigger=trig,
                response_type=rt,
                response_text=(response_text or "").strip() or None,
                photo_path=(photo_path or "").strip() or None,
                enabled=en,
                sort_order=0,
            )
        )
        session.commit()
    dash_log(f"Dashboard: auto-reply created chat_id={chat_id} trigger={trig!r}", "info")
    _flash(request, "تمت الإضافة.")
    return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)


@app.get("/chats/{chat_id}/replies/{reply_id}/edit", response_class=HTMLResponse)
async def chat_replies_edit_get(request: Request, chat_id: int, reply_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        chat = _chat_or_404(session, chat_id)
        row = session.get(AutoReply, reply_id)
        if row is None or int(row.chat_id) != int(chat_id):
            raise HTTPException(status_code=404)
        reply_row = row
    return templates.TemplateResponse(
        request,
        "chat_reply_form.html",
        {"chat": chat, "chat_id": chat_id, "reply": reply_row, "error": None},
    )


@app.post("/chats/{chat_id}/replies/{reply_id}/edit")
async def chat_replies_edit_post(
    request: Request,
    chat_id: int,
    reply_id: int,
    trigger: Annotated[str, Form()],
    response_type: Annotated[str, Form()],
    response_text: Annotated[str | None, Form()] = None,
    photo_path: Annotated[str | None, Form()] = None,
    enabled: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    rt = (response_type or "text").strip().lower()
    if rt not in ("text", "photo"):
        rt = "text"
    en = enabled in ("1", "on", "true", "yes")
    trig = (trigger or "").strip()
    if not trig:
        _flash(request, "المحفّز فارغ.")
        return RedirectResponse(f"/chats/{chat_id}/replies/{reply_id}/edit", status_code=303)
    with _db() as session:
        chat = _chat_or_404(session, chat_id)
        row = session.get(AutoReply, reply_id)
        if row is None or int(row.chat_id) != int(chat_id):
            raise HTTPException(status_code=404)
        others = list(
            session.scalars(
                select(AutoReply).where(AutoReply.chat_id == chat_id, AutoReply.id != reply_id).where(
                    AutoReply.enabled.is_(True)
                )
            ).all()
        )
        if any((r.trigger or "").strip().lower() == trig.lower() for r in others):
            return templates.TemplateResponse(
                request,
                "chat_reply_form.html",
                {
                    "chat": chat,
                    "chat_id": chat_id,
                    "reply": row,
                    "error": "يوجد محفّز مفعّل بنفس الاسم.",
                },
                status_code=400,
            )
        row.trigger = trig
        row.response_type = rt
        row.response_text = (response_text or "").strip() or None
        row.photo_path = (photo_path or "").strip() or None
        row.enabled = en
        session.commit()
    dash_log(f"Dashboard: auto-reply {reply_id} updated chat_id={chat_id}", "info")
    _flash(request, "تم الحفظ.")
    return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)


@app.post("/chats/{chat_id}/replies/{reply_id}/delete")
async def chat_replies_delete(request: Request, chat_id: int, reply_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        row = session.get(AutoReply, reply_id)
        if row is not None and int(row.chat_id) == int(chat_id):
            session.delete(row)
            session.commit()
            dash_log(f"Dashboard: auto-reply {reply_id} deleted chat_id={chat_id}", "info")
    _flash(request, "تم الحذف.")
    return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)


@app.get("/chats/{chat_id}/banned-words", response_class=HTMLResponse)
async def chat_banned_words_list(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        chat = session.get(Chat, chat_id)
        if chat is None:
            return templates.TemplateResponse(
                request,
                "chat_missing.html",
                {"chat_id": chat_id, "flash": _pop_flash(request)},
                status_code=404,
            )
        rows = list(
            session.scalars(
                select(ChatBannedWord).where(ChatBannedWord.chat_id == chat_id).order_by(ChatBannedWord.id)
            ).all()
        )
    return templates.TemplateResponse(
        request,
        "chat_banned_words.html",
        {"chat": chat, "rows": rows, "flash": _pop_flash(request)},
    )


@app.post("/chats/{chat_id}/banned-words")
async def chat_banned_words_add(request: Request, chat_id: int, word: Annotated[str, Form()]):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    w = (word or "").strip().lower()
    if not w:
        _flash(request, "الكلمة فارغة.")
        return RedirectResponse(f"/chats/{chat_id}/banned-words", status_code=303)
    if len(w) > 512:
        _flash(request, "الكلمة طويلة جداً (الحد 512).")
        return RedirectResponse(f"/chats/{chat_id}/banned-words", status_code=303)
    with _db() as session:
        if session.get(Chat, chat_id) is None:
            _flash(request, "المحادثة غير مسجّلة. أضفها من قائمة المحادثات أولاً.")
            return RedirectResponse("/chats", status_code=303)
        try:
            session.add(ChatBannedWord(chat_id=chat_id, word=w))
            bump_chats_revision(session)
            session.commit()
        except IntegrityError:
            session.rollback()
            _flash(request, "هذه الكلمة موجودة مسبقاً لهذه المحادثة.")
            return RedirectResponse(f"/chats/{chat_id}/banned-words", status_code=303)
    dash_log(f"Dashboard: banned word added chat_id={chat_id} word={w!r}", "info")
    _flash(request, "تمت الإضافة.")
    return RedirectResponse(f"/chats/{chat_id}/banned-words", status_code=303)


@app.post("/chats/{chat_id}/banned-words/{bw_id}/delete")
async def chat_banned_words_delete(request: Request, chat_id: int, bw_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    deleted = False
    with _db() as session:
        row = session.get(ChatBannedWord, bw_id)
        if row is not None and int(row.chat_id) == int(chat_id):
            w = row.word
            session.delete(row)
            bump_chats_revision(session)
            session.commit()
            dash_log(f"Dashboard: banned word deleted id={bw_id} chat_id={chat_id} word={w!r}", "info")
            deleted = True
    _flash(request, "تم الحذف." if deleted else "لم يُعثر على السجل.")
    return RedirectResponse(f"/chats/{chat_id}/banned-words", status_code=303)


@app.post("/chats/{chat_id}/replies/copy")
async def chat_replies_copy(
    request: Request,
    chat_id: int,
    source_chat_id: Annotated[str, Form()],
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    try:
        src = normalize_telegram_chat_id(int(str(source_chat_id).strip()))
    except ValueError:
        _flash(request, "معرف المحادثة المصدر غير صالح.")
        return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)
    if src == chat_id:
        _flash(request, "اختر محادثة مصدر مختلفة.")
        return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)
    n = 0
    with _db() as session:
        _chat_or_404(session, chat_id)
        if session.get(Chat, src) is None:
            _flash(request, "المحادثة المصدر غير موجودة.")
            return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)
        for r in session.scalars(select(AutoReply).where(AutoReply.chat_id == src).order_by(AutoReply.id)).all():
            session.add(
                AutoReply(
                    chat_id=chat_id,
                    trigger=r.trigger,
                    response_type=r.response_type,
                    response_text=r.response_text,
                    photo_path=r.photo_path,
                    enabled=r.enabled,
                    sort_order=r.sort_order,
                )
            )
            n += 1
        bump_chats_revision(session)
        session.commit()
    dash_log(f"Dashboard: copied {n} auto-replies from chat {src} to {chat_id}", "info")
    _flash(request, f"تم نسخ {n} رد(ود) من المحادثة {src}.")
    return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)


@app.post("/chats/{chat_id}/replies/import-list")
async def chat_replies_import_list(request: Request, chat_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    n = 0
    with _db() as session:
        _chat_or_404(session, chat_id)
        n = seed_auto_replies_from_list_folder(session, chat_id)
        bump_chats_revision(session)
        session.commit()
    dash_log(f"Dashboard: import-list added {n} auto-replies for chat {chat_id}", "info")
    _flash(
        request,
        f"تم استيراد {n} رد(ود) من مجلد list/ (المحفّزات الموجودة مسبقاً لم تُكرّر)." if n else "لا توجد ملفات جديدة في list/ أو كل المحفّزات موجودة مسبقاً.",
    )
    return RedirectResponse(f"/chats/{chat_id}/replies", status_code=303)


@app.post("/bot/start")
async def bot_start(request: Request):
    if not request.session.get("dash_ok"):
        if _wants_json(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _redirect_login()
    ok, msg = process_control.start_bot()
    if _wants_json(request):
        return _json_bot_control(request, ok, msg, "start")
    dash_log(f"Dashboard: bot start (HTML) ok={ok}", "info")
    _flash(request, msg)
    return RedirectResponse("/", status_code=303)


@app.post("/bot/stop")
async def bot_stop(request: Request):
    if not request.session.get("dash_ok"):
        if _wants_json(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _redirect_login()
    ok, msg = process_control.stop_bot()
    if _wants_json(request):
        return _json_bot_control(request, ok, msg, "stop")
    dash_log(f"Dashboard: bot stop (HTML) ok={ok}", "info")
    _flash(request, msg)
    return RedirectResponse("/", status_code=303)


@app.post("/bot/restart")
async def bot_restart(request: Request):
    if not request.session.get("dash_ok"):
        if _wants_json(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return _redirect_login()
    ok, msg = process_control.restart_bot()
    if _wants_json(request):
        return _json_bot_control(request, ok, msg, "restart")
    dash_log(f"Dashboard: bot restart (HTML) ok={ok}", "info")
    _flash(request, msg)
    return RedirectResponse("/", status_code=303)


@app.get("/backup", response_class=HTMLResponse)
async def backup_page(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    return templates.TemplateResponse(
        request,
        "backup.html",
        {"flash": _pop_flash(request), "backups": _backup_files(), "bot_status": process_control.bot_status()},
    )


@app.post("/backup/create")
async def backup_create(
    request: Request,
    include_env: Annotated[str | None, Form()] = None,
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    inc = include_env in ("1", "on", "true", "yes")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    zip_path = _PROJECT_ROOT / "data" / "backups" / f"manual-{stamp}.zip"
    ok, msg = backup_zip_util.create_backup_zip(
        _PROJECT_ROOT,
        zip_path,
        include_env=inc,
        manifest_kind="dashboard_manual",
    )
    if ok:
        _flash(request, "تم إنشاء النسخة: " + msg)
    else:
        _flash(request, "فشل النسخ: " + msg)
    dash_log(f"Dashboard: backup create ok={ok} include_env={inc}", "info")
    return RedirectResponse("/backup", status_code=303)


@app.post("/backup/restore")
async def backup_restore(
    request: Request,
    backup_file: Annotated[str, Form()],
    CONFIRM: Annotated[str, Form()],
):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    if process_control.bot_status() == "running":
        _flash(request, "أوقف البوت أولاً من اللوحة قبل الاستعادة.")
        return RedirectResponse("/backup", status_code=303)
    zip_path = _selected_backup(backup_file)
    if zip_path is None:
        _flash(request, "ملف النسخة غير صالح.")
        return RedirectResponse("/backup", status_code=303)
    if CONFIRM != f"RESTORE {zip_path.name}":
        _flash(request, "اكتب RESTORE متبوعة باسم ملف النسخة المحدد للتأكيد.")
        return RedirectResponse("/backup", status_code=303)
    ok, msg = backup_zip_util.restore_from_zip(_PROJECT_ROOT, zip_path)
    if ok:
        _flash(request, "تمت الاستعادة: " + msg + " أعد تشغيل البوت بعد المراجعة.")
    else:
        _flash(request, "فشلت الاستعادة: " + msg)
    dash_log(f"Dashboard: backup restore ok={ok} file={zip_path.name}", "info")
    return RedirectResponse("/backup", status_code=303)


@app.get("/events", response_class=HTMLResponse)
async def events_list(request: Request, event_type: str | None = None, chat_id: str | None = None):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    dash_log("Dashboard: events page viewed", "info")
    etype = (event_type or "").strip()
    filter_chat_id, chat_id_field_value = _optional_chat_id_query_param(chat_id)
    raw_chat = (chat_id or "").strip()
    if raw_chat and filter_chat_id is None:
        _flash(request, "معرف المحادثة غير صالح.")
    log_sections = _events_log_sections()
    with _db() as session:
        stmt = select(Event)
        if etype:
            stmt = stmt.where(Event.event_type == etype)
        if filter_chat_id is not None:
            stmt = stmt.where(Event.chat_id == filter_chat_id)
        rows = list(session.scalars(stmt.order_by(Event.id.desc()).limit(100)).all())
        event_types = list(session.scalars(select(Event.event_type).distinct().order_by(Event.event_type)).all())
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "rows": rows,
            "event_types": event_types,
            "selected_type": etype,
            "selected_chat_id": filter_chat_id,
            "chat_id_field_value": chat_id_field_value,
            "log_sections": log_sections,
            "log_tail_max": _LOG_TAIL_LINES,
            "flash": _pop_flash(request),
        },
    )


@app.post("/events/clear-logs")
async def events_clear_logs(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    n = _clear_dashboard_logs()
    dash_log(f"Dashboard: cleared {n} log file(s) under logs/ (recreated empty bot-spawn.log)", "info")
    _flash(request, "تم تفريغ ملفات السجل في المجلد logs/ بما فيها سجل اليوم.")
    return RedirectResponse("/events?cleared=logs", status_code=303)


@app.post("/events/clear-events")
async def events_clear_events(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    with _db() as session:
        session.execute(delete(Event))
        session.commit()
    dash_log("Dashboard: cleared all rows from events table", "info")
    _flash(request, "تم تفريغ جدول الأحداث.")
    return RedirectResponse("/events?cleared=events", status_code=303)


@app.get("/replies", response_class=HTMLResponse)
async def replies_legacy_redirect(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    _flash(request, "الردود التلقائية تُدار من صفحة كل محادثة ← «ردود تلقائية» بجانب تعديل المحادثة.")
    return RedirectResponse("/chats", status_code=303)


@app.get("/replies/new", response_class=HTMLResponse)
async def replies_new_legacy_redirect(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    _flash(request, "اختر محادثة من القائمة ثم افتح «ردود تلقائية» لتلك المحادثة.")
    return RedirectResponse("/chats", status_code=303)


@app.post("/replies/new")
async def replies_new_legacy_post(request: Request):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    _flash(request, "لم يعد مسار /replies/new مدعوماً. استخدم /chats/{معرف}/replies")
    return RedirectResponse("/chats", status_code=303)


@app.post("/replies/{reply_id}/delete")
async def replies_delete_legacy(request: Request, reply_id: int):
    if not request.session.get("dash_ok"):
        return _redirect_login()
    _flash(request, "احذف الرد من صفحة ردود المحادثة المعنية.")
    return RedirectResponse("/chats", status_code=303)
