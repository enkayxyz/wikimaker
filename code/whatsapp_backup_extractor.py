from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
DEFAULT_OUTPUT_ROOT = Path.home() / "extracts" / "whatsapp"
DEFAULT_BACKUP_SEARCH_ROOT = Path.home() / "Library" / "Application Support" / "MobileSync" / "Backup"
DEFAULT_STATE_FILENAME = "whatsapp_extractor_state.json"
DEFAULT_LOG_FILENAME = "extract_log.md"
DEFAULT_SUMMARY_FILENAME = "summary.md"
DEFAULT_RUNS_DIRNAME = "runs"
DEFAULT_CHAT_DIRNAME = "chats"


class ExtractionError(RuntimeError):
    pass


@dataclass
class SourceInfo:
    db_path: Path
    manifest_path: Path | None
    backup_root: Path | None
    manifest_match: dict[str, Any] | None = None


@dataclass
class MessageBundle:
    row: dict[str, Any]
    media_items: list[dict[str, Any]]
    data_items: list[dict[str, Any]]
    info_items: list[dict[str, Any]]


@dataclass
class ChatResult:
    chat_pk: int
    file_path: Path
    title: str
    total_messages: int
    new_messages: int
    changed_messages: int
    unchanged_messages: int
    removed_messages: int
    metadata_changed: bool
    last_message_iso: str | None


@dataclass
class RunResult:
    run_id: str
    mode: str
    source: SourceInfo
    output_root: Path
    state_root: Path
    run_dir: Path
    summary_path: Path
    chat_results: list[ChatResult]
    db_sha256: str


@dataclass
class AuxiliaryData:
    manifest_path: Path | None
    messaging_infra_path: Path | None
    extchat_path: Path | None
    backedup_storage_path: Path | None
    smb_path: Path | None
    profile_push_name_by_jid: dict[str, str]
    profile_picture_by_jid: dict[str, dict[str, Any]]
    contact_metadata_by_jid: dict[str, list[dict[str, Any]]]
    group_metadata_by_chat_jid: dict[str, dict[str, Any]]
    group_members_by_chat_pk: dict[int, list[dict[str, Any]]]
    group_member_changes_by_group_jid: dict[str, list[dict[str, Any]]]
    receipt_device_by_message_key: dict[tuple[str, str], list[dict[str, Any]]]
    parent_assoc_by_message_key: dict[tuple[str, str], list[dict[str, Any]]]
    thread_messages_by_message_key: dict[tuple[str, str], list[dict[str, Any]]]
    orphan_messages_by_chat_jid: dict[str, list[dict[str, Any]]]
    extended_media_by_message_key: dict[tuple[str, str], list[dict[str, Any]]]
    chat_push_config_by_jid: dict[str, list[dict[str, Any]]]
    black_list_by_jid: dict[str, list[dict[str, Any]]]
    customer_data_by_chat_jid: dict[str, list[dict[str, Any]]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Human-readable WhatsApp backup extractor")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--db", type=Path, help="Path to ChatStorage.sqlite (or compatible WhatsApp SQLite DB)")
    source.add_argument("--backup-root", type=Path, help="Root of an iPhone backup folder")
    parser.add_argument("--manifest", type=Path, help="Path to Manifest.db inside an iPhone backup")
    parser.add_argument(
        "--relative-path",
        default="ChatStorage.sqlite",
        help="Relative path to search in Manifest.db (defaults to ChatStorage.sqlite)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Where the human-readable corpus and run logs are written",
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Where incremental state is stored (defaults to <output-root>/state)",
    )
    parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help="Full = write everything into chat files; incremental = append only new/changed rows",
    )
    parser.add_argument("--batch-size", type=int, default=1000, help="SQLite fetch batch size")
    parser.add_argument("--include-tables", action="append", default=None, help="Compatibility filter; ignored by chat view")
    parser.add_argument("--exclude-tables", action="append", default=None, help="Compatibility filter; ignored by chat view")
    parser.add_argument("--quiet", action=argparse.BooleanOptionalAction, default=False, help="Reduce progress output")
    return parser.parse_args(argv)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"__type__": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return {"__type__": "bytes", "base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, memoryview):
        return {"__type__": "bytes", "base64": base64.b64encode(value.tobytes()).decode("ascii")}
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return {"__type__": type(value).__name__, "iso": value.isoformat()}
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return str(value)


def to_json(value: Any) -> str:
    return json.dumps(json_safe(value), indent=2, ensure_ascii=False, sort_keys=True)


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True)


def apple_timestamp_to_iso(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            dt_value = APPLE_EPOCH + dt.timedelta(seconds=float(value))
            return dt_value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None
    return None


def unix_timestamp_to_iso(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return None
    return None


def slugify(value: str) -> str:
    chars: list[str] = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            chars.append(ch)
        else:
            chars.append("_")
    slug = "".join(chars).strip("._")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "chat"


def open_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def find_latest_backup_root(search_root: Path = DEFAULT_BACKUP_SEARCH_ROOT) -> Path:
    search_root = search_root.expanduser().resolve()
    if not search_root.exists():
        raise ExtractionError(f"Backup search root not found: {search_root}")

    candidates: list[tuple[float, Path]] = []
    for manifest in search_root.rglob("Manifest.db"):
        root = manifest.parent
        try:
            score = max(manifest.stat().st_mtime, root.stat().st_mtime)
        except OSError:
            score = manifest.stat().st_mtime
        candidates.append((score, root))

    if not candidates:
        raise ExtractionError(f"No iPhone backup manifests found under: {search_root}")
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def discover_db_from_manifest(manifest_path: Path, relative_path: str) -> tuple[Path, dict[str, Any]]:
    con = sqlite3.connect(str(manifest_path))
    con.row_factory = sqlite3.Row
    cur = con.execute(
        "SELECT fileID, relativePath FROM Files WHERE relativePath LIKE ? ORDER BY relativePath",
        (f"%{relative_path}%",),
    )
    matches = [dict(row) for row in cur.fetchall()]
    con.close()
    if not matches:
        raise ExtractionError(f"No entries matched {relative_path!r} in {manifest_path}")
    preferred = None
    for match in matches:
        rel = match.get("relativePath") or ""
        if rel.endswith("ChatStorage.sqlite") and not rel.endswith(".enc"):
            preferred = match
            break
    if preferred is None:
        preferred = matches[0]
    file_id = preferred["fileID"]
    db_path = manifest_path.parent / file_id[:2] / file_id
    if not db_path.exists():
        raise ExtractionError(f"Resolved WhatsApp DB not found on disk: {db_path}")
    return db_path, preferred


def resolve_source(args: argparse.Namespace) -> SourceInfo:
    if args.db:
        return SourceInfo(db_path=args.db.expanduser().resolve(), manifest_path=None, backup_root=None, manifest_match=None)

    manifest_path = args.manifest.expanduser().resolve() if args.manifest else None
    backup_root = args.backup_root.expanduser().resolve() if args.backup_root else None

    if manifest_path is None:
        if backup_root is None:
            backup_root = find_latest_backup_root()
        else:
            if not (backup_root / "Manifest.db").exists():
                backup_root = find_latest_backup_root(backup_root)
        manifest_path = backup_root / "Manifest.db"

    if not manifest_path.exists():
        raise ExtractionError(f"Manifest not found: {manifest_path}")

    db_path, match = discover_db_from_manifest(manifest_path, args.relative_path)
    return SourceInfo(db_path=db_path, manifest_path=manifest_path, backup_root=backup_root, manifest_match=match)


def discover_related_db_path(manifest_path: Path, relative_path: str) -> Path | None:
    con = sqlite3.connect(str(manifest_path))
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT fileID, relativePath FROM Files WHERE relativePath = ? OR relativePath LIKE ? ORDER BY CASE WHEN relativePath = ? THEN 0 ELSE 1 END, relativePath LIMIT 1",
            (relative_path, f"%{relative_path}", relative_path),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    file_id = row["fileID"]
    candidate = manifest_path.parent / file_id[:2] / file_id
    return candidate if candidate.exists() else None


def load_auxiliary_data(source: SourceInfo) -> AuxiliaryData:
    if not source.manifest_path:
        return AuxiliaryData(
            manifest_path=None,
            messaging_infra_path=None,
            extchat_path=None,
            backedup_storage_path=None,
            smb_path=None,
            profile_push_name_by_jid={},
            profile_picture_by_jid={},
            contact_metadata_by_jid={},
            group_metadata_by_chat_jid={},
            group_members_by_chat_pk={},
            group_member_changes_by_group_jid={},
            receipt_device_by_message_key={},
            parent_assoc_by_message_key={},
            thread_messages_by_message_key={},
            orphan_messages_by_chat_jid={},
            extended_media_by_message_key={},
            chat_push_config_by_jid={},
            black_list_by_jid={},
            customer_data_by_chat_jid={},
        )

    manifest = source.manifest_path
    messaging_infra_path = discover_related_db_path(manifest, "MessagingInfraDB_v2/MessagingInfraDatabase.sqlite")
    extchat_path = discover_related_db_path(manifest, "ExtChatDB/ExtChatDatabase.sqlite")
    backedup_storage_path = discover_related_db_path(manifest, "BackedUpStorageDB/BackedUpStorageDatabase.sqlite")
    smb_path = discover_related_db_path(manifest, "smbDB/SMB.sqlite")

    profile_push_name_by_jid: dict[str, str] = {}
    profile_picture_by_jid: dict[str, dict[str, Any]] = {}
    receipt_device_by_message_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    parent_assoc_by_message_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    thread_messages_by_message_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    orphan_messages_by_chat_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    extended_media_by_message_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    contact_metadata_by_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    group_metadata_by_chat_jid: dict[str, dict[str, Any]] = {}
    group_members_by_chat_pk: dict[int, list[dict[str, Any]]] = defaultdict(list)
    group_member_changes_by_group_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    chat_push_config_by_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    black_list_by_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    customer_data_by_chat_jid: dict[str, list[dict[str, Any]]] = defaultdict(list)

    con = open_db(source.db_path)
    try:
        for row in fetch_all(con, "SELECT * FROM ZWAPROFILEPUSHNAME ORDER BY ZJID"):
            jid = safe_text(row.get("ZJID"))
            push_name = safe_text(row.get("ZPUSHNAME"))
            if jid and push_name:
                profile_push_name_by_jid[jid] = push_name
        for row in fetch_all(con, "SELECT * FROM ZWAPROFILEPICTUREITEM ORDER BY ZJID, ZREQUESTDATE"):
            jid = safe_text(row.get("ZJID"))
            if jid:
                profile_picture_by_jid[jid] = row
        for row in fetch_all(con, "SELECT * FROM ZWAGROUPMEMBER ORDER BY ZCHATSESSION, ZISADMIN DESC, ZCONTACTNAME, ZMEMBERJID"):
            chat_pk = row.get("ZCHATSESSION")
            if chat_pk is not None:
                group_members_by_chat_pk[int(chat_pk)].append(row)
        for row in fetch_all(con, "SELECT * FROM ZWAGROUPMEMBERSCHANGE ORDER BY ZGROUPJID, ZCHANGEDATE"):
            jid = safe_text(row.get("ZGROUPJID"))
            if jid:
                group_member_changes_by_group_jid[jid].append(row)
    finally:
        con.close()

    if messaging_infra_path and messaging_infra_path.exists():
        con = open_db(messaging_infra_path)
        try:
            for row in fetch_all(con, "SELECT * FROM receipt_device ORDER BY chat_jid, stanza_id, device_id, _id"):
                key = (safe_text(row.get("chat_jid")), safe_text(row.get("stanza_id")))
                receipt_device_by_message_key[key].append(row)
        finally:
            con.close()

    if extchat_path and extchat_path.exists():
        con = open_db(extchat_path)
        try:
            for row in fetch_all(con, "SELECT * FROM message_parent_association ORDER BY chat_jid, stanza_id, parent_stanza_id"):
                key = (safe_text(row.get("chat_jid")), safe_text(row.get("stanza_id")))
                parent_assoc_by_message_key[key].append(row)
            for row in fetch_all(con, "SELECT * FROM thread_messages ORDER BY chat_jid, stanza_id, sort, id"):
                key = (safe_text(row.get("chat_jid")), safe_text(row.get("stanza_id")))
                thread_messages_by_message_key[key].append(row)
            for row in fetch_all(con, "SELECT * FROM orphan_message_store ORDER BY parent_remote_chat_jid, parent_stanza_id"):
                orphan_messages_by_chat_jid[safe_text(row.get("parent_remote_chat_jid"))].append(row)
            for row in fetch_all(con, "SELECT * FROM extended_media_item ORDER BY file_hash, row_id"):
                key = (safe_text(row.get("file_hash")), safe_text(row.get("direct_path")))
                extended_media_by_message_key[key].append(row)
            for row in fetch_all(con, "SELECT * FROM contact_metadata ORDER BY contact_lid, contact_pn, contact_username"):
                for jid in {safe_text(row.get("contact_lid")), safe_text(row.get("contact_pn")), safe_text(row.get("contact_username"))}:
                    if jid:
                        contact_metadata_by_jid[jid].append(row)
            for row in fetch_all(con, "SELECT * FROM group_metadata ORDER BY group_jid"):
                jid = safe_text(row.get("group_jid"))
                if jid:
                    group_metadata_by_chat_jid[jid] = row
        finally:
            con.close()

    if backedup_storage_path and backedup_storage_path.exists():
        con = open_db(backedup_storage_path)
        try:
            for row in fetch_all(con, "SELECT * FROM profile_push_name ORDER BY jid"):
                jid = safe_text(row.get("jid"))
                push_name = safe_text(row.get("push_name"))
                if jid and push_name:
                    profile_push_name_by_jid[jid] = push_name
            for row in fetch_all(con, "SELECT * FROM chat_push_config ORDER BY jid"):
                jid = safe_text(row.get("jid"))
                if jid:
                    chat_push_config_by_jid[jid].append(row)
            for row in fetch_all(con, "SELECT * FROM black_list_item ORDER BY jid"):
                jid = safe_text(row.get("jid"))
                if jid:
                    black_list_by_jid[jid].append(row)
        finally:
            con.close()

    if smb_path and smb_path.exists():
        con = open_db(smb_path)
        try:
            for row in fetch_all(con, "SELECT * FROM customer_data ORDER BY chat_jid"):
                jid = safe_text(row.get("chat_jid"))
                if jid:
                    customer_data_by_chat_jid[jid].append(row)
        finally:
            con.close()

    if source.manifest_match:
        pass

    return AuxiliaryData(
        manifest_path=manifest,
        messaging_infra_path=messaging_infra_path,
        extchat_path=extchat_path,
        backedup_storage_path=backedup_storage_path,
        smb_path=smb_path,
        profile_push_name_by_jid=profile_push_name_by_jid,
        profile_picture_by_jid=profile_picture_by_jid,
        contact_metadata_by_jid=contact_metadata_by_jid,
        group_metadata_by_chat_jid=group_metadata_by_chat_jid,
        group_members_by_chat_pk=dict(group_members_by_chat_pk),
        group_member_changes_by_group_jid=dict(group_member_changes_by_group_jid),
        receipt_device_by_message_key=dict(receipt_device_by_message_key),
        parent_assoc_by_message_key=dict(parent_assoc_by_message_key),
        thread_messages_by_message_key=dict(thread_messages_by_message_key),
        orphan_messages_by_chat_jid=dict(orphan_messages_by_chat_jid),
        extended_media_by_message_key=dict(extended_media_by_message_key),
        chat_push_config_by_jid=chat_push_config_by_jid,
        black_list_by_jid=black_list_by_jid,
        customer_data_by_chat_jid=customer_data_by_chat_jid,
    )


def load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {"version": 1, "runs": [], "chat_state": {}}
    return json.loads(state_path.read_text(encoding="utf-8"))


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def fetch_all(con: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(query, params).fetchall()]


def pick_first(values: list[Any]) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def chat_display_name(session: dict[str, Any], group: dict[str, Any] | None) -> str:
    return str(
        pick_first(
            [
                session.get("ZPARTNERNAME"),
                session.get("ZCONTACTIDENTIFIER"),
                session.get("ZCONTACTJID"),
                group.get("ZSUBJECTOWNERJID") if group else None,
                group.get("ZOWNERJID") if group else None,
                f"Chat {session.get('Z_PK')}",
            ]
        )
    )


def render_chat_header(session: dict[str, Any], group: dict[str, Any] | None, source: SourceInfo, created_at: str) -> str:
    payload = {"session": session, "group": group}
    lines = [
        f"# Chat: {chat_display_name(session, group)}",
        "",
        f"- chat_pk: {session.get('Z_PK')}",
        f"- chat_file_version: 1",
        f"- source_db: {source.db_path}",
    ]
    if source.manifest_path:
        lines.append(f"- manifest: {source.manifest_path}")
    if source.backup_root:
        lines.append(f"- backup_root: {source.backup_root}")
    lines.extend([
        f"- first_extracted_at: {created_at}",
        "",
        "## Chat snapshot",
        "",
        "```json",
        to_json(payload),
        "```",
        "",
    ])
    return "\n".join(lines)


def render_related_items(title: str, items: list[dict[str, Any]], important_fields: list[str]) -> str:
    if not items:
        return f"- {title}: none"
    lines = [f"- {title}:"]
    for item in items:
        parts = []
        for field in important_fields:
            if field in item and item[field] not in (None, ""):
                value = item[field]
                if field.upper().endswith("DATE") or field.upper().endswith("TIMESTAMP"):
                    iso = apple_timestamp_to_iso(value)
                    if iso:
                        parts.append(f"{field}={value} ({iso})")
                    else:
                        parts.append(f"{field}={value}")
                else:
                    parts.append(f"{field}={safe_text(value)}")
        if not parts:
            parts.append(f"Z_PK={item.get('Z_PK')}")
        lines.append(f"  - {'; '.join(parts)}")
    return "\n".join(lines)


def message_row_id(message: dict[str, Any]) -> str:
    return f"message_{message['Z_PK']}"


def message_hash(bundle: MessageBundle) -> str:
    payload = {
        "message": json_safe(bundle.row),
        "media_items": json_safe(bundle.media_items),
        "data_items": json_safe(bundle.data_items),
        "info_items": json_safe(bundle.info_items),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def message_heading(message: dict[str, Any], chat_title: str) -> str:
    raw_date = message.get("ZMESSAGEDATE")
    iso_date = apple_timestamp_to_iso(raw_date)
    dt_text = iso_date or "unknown-time"
    direction = "outgoing" if message.get("ZISFROMME") else "incoming"
    sender = pick_first([message.get("ZPUSHNAME"), message.get("ZFROMJID"), message.get("ZTOJID"), chat_title, f"message {message.get('Z_PK')}"])
    return f"### {dt_text} | {direction} | {sender} | {message_row_id(message)}"


def render_text_view(text_value: Any) -> list[str]:
    if text_value in (None, ""):
        return ["- text: [empty]"]
    text = safe_text(text_value)
    try:
        parsed = json.loads(text)
    except Exception:
        return [f"- text: {text}"]
    return [
        "- text (interpreted as JSON):",
        "",
        "```json",
        json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True),
        "```",
        "",
        f"- text_raw: {text}",
    ]


def jid_display_name(jid: str, session: dict[str, Any] | None, group: dict[str, Any] | None, aux: AuxiliaryData | None, message: dict[str, Any] | None = None) -> str:
    jid = safe_text(jid)
    if not jid:
        return ""
    candidates: list[Any] = [jid]
    if aux:
        candidates.append(aux.profile_push_name_by_jid.get(jid))
        for row in aux.contact_metadata_by_jid.get(jid, []):
            candidates.extend([
                row.get("contact_push_name"),
                row.get("contact_username"),
                row.get("contact_pn"),
            ])
        for row in aux.customer_data_by_chat_jid.get(jid, []):
            candidates.extend([row.get("email"), row.get("address")])
    if session:
        candidates.extend([
            session.get("ZPARTNERNAME") if jid in {safe_text(session.get("ZCONTACTJID")), safe_text(session.get("ZCONTACTIDENTIFIER"))} else None,
            session.get("ZCONTACTIDENTIFIER"),
            session.get("ZCONTACTJID"),
        ])
    if group:
        candidates.extend([group.get("ZCREATORJID"), group.get("ZOWNERJID"), group.get("ZSOURCEJID"), group.get("ZSUBJECTOWNERJID")])
    if message:
        candidates.extend([message.get("ZPUSHNAME"), message.get("ZFROMJID"), message.get("ZTOJID")])
    label = pick_first([c for c in candidates if c not in (None, "")])
    return safe_text(label)


def render_chat_context_sections(
    session: dict[str, Any],
    group: dict[str, Any] | None,
    messages: list[dict[str, Any]],
    aux: AuxiliaryData,
    chat_pk: int,
) -> list[str]:
    chat_jid = safe_text(session.get("ZCONTACTJID"))
    participants: dict[str, dict[str, Any]] = {}
    for jid in [chat_jid, safe_text(session.get("ZCONTACTIDENTIFIER"))]:
        if jid:
            participants[jid] = {"jid": jid, "label": jid_display_name(jid, session, group, aux)}
    for message in messages:
        for jid in [safe_text(message.get("ZFROMJID")), safe_text(message.get("ZTOJID")), safe_text(message.get("ZPUSHNAME"))]:
            if jid and jid not in participants:
                participants[jid] = {"jid": jid, "label": jid_display_name(jid, session, group, aux, message)}
    if group:
        for jid in [safe_text(group.get("ZCREATORJID")), safe_text(group.get("ZOWNERJID")), safe_text(group.get("ZSOURCEJID")), safe_text(group.get("ZSUBJECTOWNERJID"))]:
            if jid and jid not in participants:
                participants[jid] = {"jid": jid, "label": jid_display_name(jid, session, group, aux)}
    participant_lines = []
    for jid, item in sorted(participants.items(), key=lambda kv: kv[1]["label"]):
        extras = []
        if aux.profile_push_name_by_jid.get(jid):
            extras.append(f"push_name={aux.profile_push_name_by_jid[jid]}")
        if aux.contact_metadata_by_jid.get(jid):
            first_meta = aux.contact_metadata_by_jid[jid][0]
            extras.append(f"contact_meta={safe_text({k: first_meta.get(k) for k in ['contact_lid','contact_pn','contact_username','contact_push_name']})}")
        if aux.profile_picture_by_jid.get(jid):
            pic = aux.profile_picture_by_jid[jid]
            extras.append(f"profile_picture={safe_text(pic.get('ZPATH'))}#{safe_text(pic.get('ZPICTUREID'))}")
        if aux.chat_push_config_by_jid.get(jid):
            extras.append(f"push_config_rows={len(aux.chat_push_config_by_jid[jid])}")
        if aux.black_list_by_jid.get(jid):
            extras.append("blacklisted=true")
        if aux.customer_data_by_chat_jid.get(jid):
            extras.append(f"customer_data_rows={len(aux.customer_data_by_chat_jid[jid])}")
        participant_lines.append(f"  - {item['label']} | jid={jid}{(' | ' + '; '.join(extras)) if extras else ''}")

    message_jids = [safe_text(message.get("ZFROMJID")) for message in messages] + [safe_text(message.get("ZTOJID")) for message in messages]
    linked_receipts = 0
    for message in messages:
        key = (chat_jid, safe_text(message.get("ZSTANZAID")))
        if aux.receipt_device_by_message_key.get(key):
            linked_receipts += 1
    conversation_link_count = sum(1 for message in messages if aux.parent_assoc_by_message_key.get((chat_jid, safe_text(message.get("ZSTANZAID")))))
    thread_link_count = sum(1 for message in messages if aux.thread_messages_by_message_key.get((chat_jid, safe_text(message.get("ZSTANZAID")))))

    participant_block = participant_lines if participant_lines else ["- none detected"]

    lines = [
        "## Chat context",
        "",
        f"- chat_jid: {chat_jid}",
        f"- chat_label: {jid_display_name(chat_jid, session, group, aux)}",
        f"- partner_name: {safe_text(session.get('ZPARTNERNAME'))}",
        f"- session_type: {safe_text(session.get('ZSESSIONTYPE'))}",
        f"- archived: {safe_text(session.get('ZARCHIVED'))}",
        f"- hidden: {safe_text(session.get('ZHIDDEN'))}",
        f"- removed: {safe_text(session.get('ZREMOVED'))}",
        f"- unread_count: {safe_text(session.get('ZUNREADCOUNT'))}",
        f"- last_message_date: {safe_text(session.get('ZLASTMESSAGEDATE'))} ({apple_timestamp_to_iso(session.get('ZLASTMESSAGEDATE')) or 'n/a'})",
        f"- last_message_text: {safe_text(session.get('ZLASTMESSAGETEXT'))}",
        f"- messages_in_chat: {len(messages)}",
        f"- messages_with_receipt_devices: {linked_receipts}",
        f"- messages_with_parent_links: {conversation_link_count}",
        f"- messages_with_thread_links: {thread_link_count}",
        "",
        "### Participants",
        "",
        *participant_block,
        "",
    ]

    if group:
        group_body = [
            f"- group_jid: {chat_jid}",
            f"- group_state: {safe_text(group.get('ZSTATE'))}",
            f"- creation_date: {safe_text(group.get('ZCREATIONDATE'))} ({unix_timestamp_to_iso(group.get('ZCREATIONDATE')) or apple_timestamp_to_iso(group.get('ZCREATIONDATE')) or 'n/a'})",
            f"- subject_timestamp: {safe_text(group.get('ZSUBJECTTIMESTAMP'))} ({unix_timestamp_to_iso(group.get('ZSUBJECTTIMESTAMP')) or apple_timestamp_to_iso(group.get('ZSUBJECTTIMESTAMP')) or 'n/a'})",
            f"- creator_jid: {safe_text(group.get('ZCREATORJID'))}",
            f"- owner_jid: {safe_text(group.get('ZOWNERJID'))}",
            f"- source_jid: {safe_text(group.get('ZSOURCEJID'))}",
            f"- subject_owner_jid: {safe_text(group.get('ZSUBJECTOWNERJID'))}",
            f"- picture_path: {safe_text(group.get('ZPICTUREPATH'))}",
            f"- picture_id: {safe_text(group.get('ZPICTUREID'))}",
            f"- member_count: {len(aux.group_members_by_chat_pk.get(chat_pk, []))}",
        ]
        if aux.group_members_by_chat_pk.get(chat_pk):
            group_body.append("- group_members:")
            for member in aux.group_members_by_chat_pk[chat_pk]:
                group_body.append(
                    f"  - jid={safe_text(member.get('ZMEMBERJID'))}; name={safe_text(member.get('ZCONTACTNAME'))}; first_name={safe_text(member.get('ZFIRSTNAME'))}; active={safe_text(member.get('ZISACTIVE'))}; admin={safe_text(member.get('ZISADMIN'))}; sender_keys_sent={safe_text(member.get('ZSENDERKEYSENT'))}"
                )
        if aux.group_member_changes_by_group_jid.get(chat_jid):
            group_body.append(f"- member_changes: {len(aux.group_member_changes_by_group_jid[chat_jid])}")
        if aux.group_metadata_by_chat_jid.get(chat_jid):
            group_body.append(f"- ext_group_metadata: {safe_text(aux.group_metadata_by_chat_jid[chat_jid])}")
        lines.extend(render_details_block("Group metadata", group_body))

    if aux.orphan_messages_by_chat_jid.get(chat_jid):
        orphan_body = [f"- orphan_message_count: {len(aux.orphan_messages_by_chat_jid[chat_jid])}"]
        for item in aux.orphan_messages_by_chat_jid[chat_jid][:20]:
            orphan_body.append(f"  - parent_stanza_id={safe_text(item.get('parent_stanza_id'))}; reason={safe_text(item.get('added_reason'))}; added={safe_text(item.get('added_timestamp'))} ({unix_timestamp_to_iso(item.get('added_timestamp')) or 'n/a'})")
        lines.extend(render_details_block("Orphan / imported conversation fragments", orphan_body))

    return lines


def _format_message_meta_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return safe_text(value)
    return safe_text(value)


def _message_parent_summary(message: dict[str, Any], aux: AuxiliaryData, chat_jid: str) -> list[str]:
    stanza_id = safe_text(message.get("ZSTANZAID"))
    bits: list[str] = []
    parent_message_pk = message.get("ZPARENTMESSAGE")
    if parent_message_pk not in (None, ""):
        bits.append(f"parent_message_pk={parent_message_pk}")
    key = (chat_jid, stanza_id)
    parent_links = aux.parent_assoc_by_message_key.get(key, [])
    if parent_links:
        parent_ids = [safe_text(row.get("parent_stanza_id")) for row in parent_links if safe_text(row.get("parent_stanza_id"))]
        if parent_ids:
            bits.append(f"reply_to={', '.join(parent_ids)}")
    thread_links = aux.thread_messages_by_message_key.get(key, [])
    if thread_links:
        bits.append(f"thread_links={len(thread_links)}")
    return bits


def _render_device_receipts(message: dict[str, Any], aux: AuxiliaryData, chat_jid: str) -> list[str]:
    stanza_id = safe_text(message.get("ZSTANZAID"))
    rows = aux.receipt_device_by_message_key.get((chat_jid, stanza_id), [])
    if not rows:
        return ["- delivery_read_devices: none"]
    lines = [f"- delivery_read_devices: {len(rows)}"]
    for idx, row in enumerate(rows, start=1):
        bits = [
            f"device_id={safe_text(row.get('device_id'))}",
            f"user_jid={safe_text(row.get('user_jid'))}",
            f"send={unix_timestamp_to_iso(row.get('send_timestamp')) or safe_text(row.get('send_timestamp'))}",
            f"delivered={unix_timestamp_to_iso(row.get('delivered_timestamp')) or safe_text(row.get('delivered_timestamp'))}",
            f"read={unix_timestamp_to_iso(row.get('read_timestamp')) or safe_text(row.get('read_timestamp'))}",
            f"played={unix_timestamp_to_iso(row.get('played_timestamp')) or safe_text(row.get('played_timestamp'))}",
            f"device_version={safe_text(row.get('device_version'))}",
        ]
        lines.append(f"  - device_{idx}: {'; '.join(bits)}")
    return lines


def _render_message_parent_and_thread(message: dict[str, Any], aux: AuxiliaryData, chat_jid: str) -> list[str]:
    bits = _message_parent_summary(message, aux, chat_jid)
    if not bits:
        return ["- conversation_links: none"]
    return ["- conversation_links:", *[f"  - {bit}" for bit in bits]]


def _render_message_aux_sections(message: dict[str, Any], aux: AuxiliaryData, chat_jid: str) -> list[str]:
    key = (chat_jid, safe_text(message.get("ZSTANZAID")))
    lines: list[str] = []
    if aux.receipt_device_by_message_key.get(key):
        lines.extend(_render_device_receipts(message, aux, chat_jid))
    else:
        lines.append("- delivery_read_devices: none")
    lines.extend(_render_message_parent_and_thread(message, aux, chat_jid))
    return lines


def render_message_section(
    chat_pk: int,
    chat_title: str,
    message: dict[str, Any],
    bundle: MessageBundle,
    row_hash: str,
    run_id: str,
    mode: str,
    aux: AuxiliaryData,
    chat_jid: str,
) -> str:
    message_date_raw = message.get("ZMESSAGEDATE")
    sent_date_raw = message.get("ZSENTDATE")
    message_date_iso = apple_timestamp_to_iso(message_date_raw)
    sent_date_iso = apple_timestamp_to_iso(sent_date_raw)
    lines = [message_heading(message, chat_title), ""]
    lines.extend([
        f"- chat_pk: {chat_pk}",
        f"- chat_jid: {chat_jid}",
        f"- chat_label: {chat_title}",
        f"- run_id: {run_id}",
        f"- mode: {mode}",
        f"- row_id: {message_row_id(message)}",
        f"- row_hash: {row_hash}",
        f"- message_pk: {message.get('Z_PK')}",
        f"- message_type: {safe_text(message.get('ZMESSAGETYPE'))}",
        f"- is_from_me: {safe_text(message.get('ZISFROMME'))}",
        f"- message_status: {safe_text(message.get('ZMESSAGESTATUS'))}",
        f"- message_error_status: {safe_text(message.get('ZMESSAGEERRORSTATUS'))}",
        f"- message_flags: {safe_text(message.get('ZFLAGS'))}",
        f"- spotlight_status: {safe_text(message.get('ZSPOTLIGHTSTATUS'))}",
        f"- starred: {safe_text(message.get('ZSTARRED'))}",
        f"- group_event_type: {safe_text(message.get('ZGROUPEVENTTYPE'))}",
        f"- message_date_raw: {safe_text(message_date_raw)}",
        f"- message_date_iso: {safe_text(message_date_iso)}",
        f"- sent_date_raw: {safe_text(sent_date_raw)}",
        f"- sent_date_iso: {safe_text(sent_date_iso)}",
        f"- from_jid: {safe_text(message.get('ZFROMJID'))}",
        f"- to_jid: {safe_text(message.get('ZTOJID'))}",
        f"- push_name: {safe_text(message.get('ZPUSHNAME'))}",
        f"- stanza_id: {safe_text(message.get('ZSTANZAID'))}",
        f"- media_section_id: {safe_text(message.get('ZMEDIASECTIONID'))}",
    ])
    lines.extend(render_text_view(message.get('ZTEXT')))
    lines.append(render_related_items("attachments", bundle.media_items, ["Z_PK", "ZFILESIZE", "ZMEDIALOCALPATH", "ZMEDIAURL", "ZTITLE", "ZLATITUDE", "ZLONGITUDE", "ZMEDIAURLDATE", "ZAUTHORNAME", "ZCOLLECTIONNAME", "ZVCARDNAME"]))
    lines.append(render_related_items("message_data", bundle.data_items, ["Z_PK", "ZINDEX", "ZTYPE", "ZTITLE", "ZSUMMARY", "ZMATCHEDTEXT", "ZCONTENT1", "ZCONTENT2", "ZDATE", "ZSENDERJID", "ZCHATJID"]))
    lines.append(render_related_items("message_info", bundle.info_items, ["Z_PK", "ZMESSAGE"]))
    lines.extend(_render_message_aux_sections(message, aux, chat_jid))
    lines.extend([
        "",
        *render_details_block(
            "Raw message bundle",
            [
                "```json",
                to_json({"message": message, "media_items": bundle.media_items, "data_items": bundle.data_items, "info_items": bundle.info_items}),
                "```",
            ],
        ),
    ])
    return "\n".join(lines)


def _read_varint_bytes(data: bytes, idx: int) -> tuple[int, int]:
    shift = 0
    val = 0
    while idx < len(data):
        b = data[idx]
        idx += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, idx
        shift += 7
    raise IndexError


def decode_wire_message(data: bytes, *, depth: int = 0, max_depth: int = 3, max_fields: int = 200) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    idx = 0
    count = 0
    while idx < len(data) and count < max_fields:
        count += 1
        try:
            key, idx = _read_varint_bytes(data, idx)
        except IndexError:
            break
        field_num = key >> 3
        wire_type = key & 7
        entry: dict[str, Any] = {"field": field_num, "wire_type": wire_type}
        try:
            if wire_type == 0:
                value, idx = _read_varint_bytes(data, idx)
                entry["varint"] = value
                if 1_000_000_000 <= value < 2_000_000_000:
                    entry["unix_seconds"] = apple_timestamp_to_iso(value)
                elif 1_000_000_000_000 <= value < 2_000_000_000_000:
                    entry["unix_milliseconds"] = dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
            elif wire_type == 1:
                raw = data[idx:idx + 8]
                if len(raw) < 8:
                    break
                idx += 8
                value = int.from_bytes(raw, "little")
                entry["fixed64"] = value
                entry["fixed64_hex"] = raw.hex()
                if 1_000_000_000_000 <= value < 2_000_000_000_000:
                    entry["unix_milliseconds"] = dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
            elif wire_type == 2:
                length, idx = _read_varint_bytes(data, idx)
                raw = data[idx:idx + length]
                idx += len(raw)
                entry["bytes_hex"] = raw.hex()
                if raw:
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = ""
                    if text:
                        entry["text"] = text
                    if depth < max_depth:
                        nested = decode_wire_message(raw, depth=depth + 1, max_depth=max_depth, max_fields=max_fields)
                        if nested:
                            entry["nested"] = nested
            elif wire_type == 5:
                raw = data[idx:idx + 4]
                if len(raw) < 4:
                    break
                idx += 4
                entry["fixed32"] = int.from_bytes(raw, "little")
                entry["fixed32_hex"] = raw.hex()
            else:
                entry["raw_remaining_hex"] = data[idx:].hex()
                break
        except IndexError:
            break
        fields.append(entry)
    return fields


def render_receipt_info(info_items: list[dict[str, Any]]) -> list[str]:
    receipt_rows = [item for item in info_items if item.get("ZRECEIPTINFO")]
    if not receipt_rows:
        return ["- receipt_info: none"]

    lines = ["- receipt_info:"]
    for item in receipt_rows:
        blob = item.get("ZRECEIPTINFO")
        if not isinstance(blob, (bytes, bytearray, memoryview)):
            lines.append(f"  - Z_PK={item.get('Z_PK')}; ZMESSAGE={item.get('ZMESSAGE')}; receipt_blob=[unavailable]")
            continue
        decoded = decode_wire_message(bytes(blob))
        top_level_time = None
        top_level_iso = None
        top_level_status = None
        recipients: list[dict[str, Any]] = []
        ip_like = []
        for field in decoded:
            if field.get("field") == 3 and field.get("wire_type") == 0 and "varint" in field:
                top_level_time = field["varint"]
                top_level_iso = field.get("unix_seconds")
            elif field.get("field") == 4 and field.get("wire_type") == 0 and "varint" in field:
                top_level_status = field["varint"]
            elif field.get("field") in (7, 10) and field.get("wire_type") == 2:
                nested = field.get("nested") or []
                recipient_texts = []
                recipient_time = None
                recipient_time_iso = None
                recipient_status = None
                for n in nested:
                    if n.get("wire_type") == 2 and n.get("text"):
                        recipient_texts.append(n["text"])
                    if n.get("wire_type") == 0 and "varint" in n:
                        if 1_000_000_000_000 <= n["varint"] < 2_000_000_000_000:
                            recipient_time = n["varint"]
                            recipient_time_iso = n.get("unix_milliseconds")
                        elif recipient_status is None:
                            recipient_status = n["varint"]
                    if n.get("wire_type") in (1, 5):
                        if "fixed64" in n and 1_000_000_000_000 <= n["fixed64"] < 2_000_000_000_000:
                            recipient_time = n["fixed64"]
                            recipient_time_iso = n.get("unix_milliseconds")
                        if "fixed32" in n and recipient_status is None:
                            recipient_status = n["fixed32"]
                recipients.append({
                    "path_field": field.get("field"),
                    "texts": recipient_texts,
                    "observed_time_raw": recipient_time,
                    "observed_time_iso": recipient_time_iso,
                    "status_code": recipient_status,
                    "raw": field,
                })
                for txt in recipient_texts:
                    if re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", txt):
                        ip_like.append(txt)
            elif field.get("wire_type") == 2 and field.get("text"):
                txt = field["text"]
                if re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", txt):
                    ip_like.append(txt)

        lines.append(f"  - Z_PK={item.get('Z_PK')}; ZMESSAGE={item.get('ZMESSAGE')}")
        if top_level_time is not None:
            lines.append(f"    - receipt_record_time_raw: {top_level_time}")
            if top_level_iso:
                lines.append(f"    - receipt_record_time_iso: {top_level_iso}")
        if top_level_status is not None:
            lines.append(f"    - receipt_status_code: {top_level_status}")
        if recipients:
            lines.append(f"    - receipt_entries: {len(recipients)}")
            for idx, rec in enumerate(recipients, start=1):
                summary_bits = []
                if rec["texts"]:
                    summary_bits.append(f"texts={'; '.join(rec['texts'])}")
                if rec["observed_time_iso"]:
                    summary_bits.append(f"observed_time={rec['observed_time_iso']}")
                elif rec["observed_time_raw"] is not None:
                    summary_bits.append(f"observed_time_raw={rec['observed_time_raw']}")
                if rec["status_code"] is not None:
                    summary_bits.append(f"status_code={rec['status_code']}")
                lines.append(f"      - entry_{idx}: {', '.join(summary_bits) if summary_bits else 'raw_present'}")
                lines.append("        <details>")
                lines.append("        <summary>receipt entry raw</summary>")
                lines.append("")
                lines.append("        ```json")
                lines.append("        " + to_json(rec).replace("\n", "\n        "))
                lines.append("        ```")
                lines.append("")
                lines.append("        </details>")
        if ip_like:
            lines.append(f"    - ip_like_strings: {', '.join(sorted(set(ip_like)))}")
    return lines


def render_details_block(summary: str, body_lines: list[str]) -> list[str]:
    return [
        "<details>",
        f"<summary>{summary}</summary>",
        "",
        *body_lines,
        "",
        "</details>",
        "",
    ]


def render_message_section(
    chat_pk: int,
    chat_title: str,
    message: dict[str, Any],
    bundle: MessageBundle,
    row_hash: str,
    run_id: str,
    mode: str,
    aux: AuxiliaryData,
    chat_jid: str,
) -> str:
    message_date_raw = message.get("ZMESSAGEDATE")
    sent_date_raw = message.get("ZSENTDATE")
    message_date_iso = apple_timestamp_to_iso(message_date_raw)
    sent_date_iso = apple_timestamp_to_iso(sent_date_raw)
    lines = [message_heading(message, chat_title), ""]
    lines.extend([
        f"- chat_pk: {chat_pk}",
        f"- run_id: {run_id}",
        f"- mode: {mode}",
        f"- row_id: {message_row_id(message)}",
        f"- row_hash: {row_hash}",
        f"- message_pk: {message.get('Z_PK')}",
        f"- message_type: {safe_text(message.get('ZMESSAGETYPE'))}",
        f"- is_from_me: {safe_text(message.get('ZISFROMME'))}",
        f"- message_date_raw: {safe_text(message_date_raw)}",
        f"- message_date_iso: {safe_text(message_date_iso)}",
        f"- sent_date_raw: {safe_text(sent_date_raw)}",
        f"- sent_date_iso: {safe_text(sent_date_iso)}",
        f"- from_jid: {safe_text(message.get('ZFROMJID'))}",
        f"- to_jid: {safe_text(message.get('ZTOJID'))}",
        f"- push_name: {safe_text(message.get('ZPUSHNAME'))}",
        f"- stanza_id: {safe_text(message.get('ZSTANZAID'))}",
        f"- media_section_id: {safe_text(message.get('ZMEDIASECTIONID'))}",
    ])
    lines.extend(render_text_view(message.get('ZTEXT')))
    lines.append(render_related_items("media_items", bundle.media_items, ["Z_PK", "ZFILESIZE", "ZMEDIALOCALPATH", "ZMEDIAURL", "ZTITLE", "ZLATITUDE", "ZLONGITUDE", "ZMEDIAURLDATE"]))
    lines.append(render_related_items("data_items", bundle.data_items, ["Z_PK", "ZINDEX", "ZTYPE", "ZTITLE", "ZSUMMARY", "ZMATCHEDTEXT", "ZCONTENT1", "ZCONTENT2", "ZDATE", "ZSENDERJID", "ZCHATJID"]))
    lines.append(render_related_items("message_info", bundle.info_items, ["Z_PK", "ZMESSAGE"]))
    lines.extend(render_receipt_info(bundle.info_items))
    lines.extend([
        "",
        *render_details_block(
            "Raw message bundle",
            [
                "```json",
                to_json({"message": message, "media_items": bundle.media_items, "data_items": bundle.data_items, "info_items": bundle.info_items}),
                "```",
            ],
        ),
    ])
    return "\n".join(lines)


def render_chat_footer(total_messages: int, new_messages: int, changed_messages: int, unchanged_messages: int, removed_messages: int) -> str:
    return "\n".join([
        "## Run summary",
        "",
        f"- total_messages: {total_messages}",
        f"- new_messages: {new_messages}",
        f"- changed_messages: {changed_messages}",
        f"- unchanged_messages: {unchanged_messages}",
        f"- removed_messages: {removed_messages}",
        "",
    ])


def render_index(chat_results: list[ChatResult], source: SourceInfo, run_id: str, mode: str, output_root: Path) -> str:
    lines = [
        "# WhatsApp corpus index",
        "",
        f"- run_id: {run_id}",
        f"- mode: {mode}",
        f"- source_db: {source.db_path}",
        f"- output_root: {output_root}",
        "",
        "| Chat | File | Messages | New | Changed | Unchanged | Removed | Last message |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in sorted(chat_results, key=lambda x: (x.last_message_iso or "", x.title), reverse=True):
        rel = item.file_path.as_posix()
        lines.append(
            f"| {item.title} | `{rel}` | {item.total_messages} | {item.new_messages} | {item.changed_messages} | {item.unchanged_messages} | {item.removed_messages} | {item.last_message_iso or ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def append_log(log_path: Path, result: RunResult) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n---\n")
        f.write(f"- timestamp: {timestamp}\n")
        f.write(f"- run_id: {result.run_id}\n")
        f.write(f"- mode: {result.mode}\n")
        f.write(f"- source_db: {result.source.db_path}\n")
        f.write(f"- db_sha256: {result.db_sha256}\n")
        if result.source.manifest_path:
            f.write(f"- manifest: {result.source.manifest_path}\n")
        if result.source.backup_root:
            f.write(f"- backup_root: {result.source.backup_root}\n")
        for chat in result.chat_results:
            f.write(
                f"- chat: {chat.title} file={chat.file_path} total={chat.total_messages} new={chat.new_messages} changed={chat.changed_messages} unchanged={chat.unchanged_messages} removed={chat.removed_messages}\n"
            )
        f.write(f"- summary: {result.summary_path}\n")
        f.write(f"- run_dir: {result.run_dir}\n")


def extract_whatsapp_corpus(source: SourceInfo, output_root: Path, state_root: Path, mode: str, batch_size: int, quiet: bool = False) -> RunResult:
    del batch_size  # kept for CLI compatibility
    output_root = output_root.expanduser().resolve()
    state_root = state_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    db_sha = sha256_file(source.db_path)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{db_sha[:12]}"
    run_dir = output_root / DEFAULT_RUNS_DIRNAME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / DEFAULT_SUMMARY_FILENAME
    index_path = output_root / "index.md"
    chats_dir = output_root / DEFAULT_CHAT_DIRNAME
    chats_dir.mkdir(parents=True, exist_ok=True)

    state_path = state_root / DEFAULT_STATE_FILENAME
    state = load_state(state_path)
    prev_chat_state: dict[str, Any] = state.get("chat_state", {}) if mode == "incremental" else {}
    next_chat_state: dict[str, Any] = {}
    chat_results: list[ChatResult] = []

    aux = load_auxiliary_data(source)

    con = open_db(source.db_path)
    try:
        sessions = fetch_all(con, "SELECT * FROM ZWACHATSESSION ORDER BY Z_PK")
        groups = fetch_all(con, "SELECT * FROM ZWAGROUPINFO ORDER BY Z_PK")
        messages = fetch_all(con, "SELECT * FROM ZWAMESSAGE ORDER BY ZCHATSESSION, ZMESSAGEDATE, Z_PK")
        media_items = fetch_all(con, "SELECT * FROM ZWAMEDIAITEM ORDER BY ZMESSAGE, Z_PK")
        data_items = fetch_all(con, "SELECT * FROM ZWAMESSAGEDATAITEM ORDER BY ZMESSAGE, ZINDEX, Z_PK")
        info_items = fetch_all(con, "SELECT * FROM ZWAMESSAGEINFO ORDER BY ZMESSAGE, Z_PK")

        group_by_chat = {int(row["ZCHATSESSION"]): row for row in groups if row.get("ZCHATSESSION") is not None}
        media_by_message: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in media_items:
            if row.get("ZMESSAGE") is not None:
                media_by_message[int(row["ZMESSAGE"])].append(row)
        data_by_message: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in data_items:
            if row.get("ZMESSAGE") is not None:
                data_by_message[int(row["ZMESSAGE"])].append(row)
        info_by_message: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in info_items:
            if row.get("ZMESSAGE") is not None:
                info_by_message[int(row["ZMESSAGE"])].append(row)
        messages_by_chat: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in messages:
            if row.get("ZCHATSESSION") is not None:
                messages_by_chat[int(row["ZCHATSESSION"])].append(row)

        created_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        if not quiet:
            print(f"Loaded {len(sessions)} chats and {len(messages)} messages", flush=True)

        for session in sessions:
            chat_pk = int(session["Z_PK"])
            group = group_by_chat.get(chat_pk)
            title = chat_display_name(session, group)
            slug = slugify(f"{chat_pk}_{title}")
            chat_file = chats_dir / f"{slug}.md"
            chat_state_key = str(chat_pk)
            prev = prev_chat_state.get(chat_state_key, {"messages": {}, "metadata_hash": None})
            prev_messages: dict[str, str] = dict(prev.get("messages", {}))
            current_messages: dict[str, str] = {}

            bundles: list[tuple[dict[str, Any], MessageBundle, str]] = []
            metadata_hash = hashlib.sha256(
                json.dumps(json_safe({"session": session, "group": group}), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            metadata_changed = prev.get("metadata_hash") != metadata_hash
            for message in messages_by_chat.get(chat_pk, []):
                m_pk = int(message["Z_PK"])
                bundle = MessageBundle(
                    row=message,
                    media_items=media_by_message.get(m_pk, []),
                    data_items=data_by_message.get(m_pk, []),
                    info_items=info_by_message.get(m_pk, []),
                )
                row_hash = message_hash(bundle)
                current_messages[str(m_pk)] = row_hash
                bundles.append((message, bundle, row_hash))

            new_messages = 0
            changed_messages = 0
            unchanged_messages = 0
            removed_messages = len(set(prev_messages) - set(current_messages))
            file_exists_before = chat_file.exists()
            should_write_header = not file_exists_before
            file_needs_metadata_update = metadata_changed or should_write_header
            file_has_new_content = False

            with chat_file.open("a", encoding="utf-8") as f:
                if should_write_header:
                    f.write(render_chat_header(session, group, source, created_at))
                    f.write("\n")
                    f.write("\n\n".join(render_chat_context_sections(session, group, messages_by_chat.get(chat_pk, []), aux, chat_pk)))
                    f.write("\n\n## Messages\n\n")
                    file_has_new_content = True
                elif metadata_changed:
                    f.write("## Metadata update\n\n")
                    f.write("```json\n")
                    f.write(to_json({"session": session, "group": group}))
                    f.write("\n```\n\n")
                    file_has_new_content = True

                for message, bundle, row_hash in bundles:
                    m_pk = int(message["Z_PK"])
                    row_id = str(m_pk)
                    prev_hash = prev_messages.get(row_id)
                    should_write = mode == "full" or prev_hash != row_hash
                    if should_write:
                        if prev_hash is None:
                            new_messages += 1
                        else:
                            changed_messages += 1
                        f.write(render_message_section(chat_pk, title, message, bundle, row_hash, run_id, mode, aux, safe_text(session.get("ZCONTACTJID"))))
                        file_has_new_content = True
                    else:
                        unchanged_messages += 1

                if file_has_new_content:
                    f.write(render_chat_footer(len(bundles), new_messages, changed_messages, unchanged_messages, removed_messages))

            next_chat_state[chat_state_key] = {
                "title": title,
                "file_path": str(chat_file),
                "metadata_hash": metadata_hash,
                "messages": current_messages,
                "last_message_iso": apple_timestamp_to_iso(bundles[-1][0].get("ZMESSAGEDATE")) if bundles else None,
            }
            chat_results.append(
                ChatResult(
                    chat_pk=chat_pk,
                    file_path=chat_file,
                    title=title,
                    total_messages=len(bundles),
                    new_messages=new_messages,
                    changed_messages=changed_messages,
                    unchanged_messages=unchanged_messages,
                    removed_messages=removed_messages,
                    metadata_changed=metadata_changed,
                    last_message_iso=apple_timestamp_to_iso(bundles[-1][0].get("ZMESSAGEDATE")) if bundles else None,
                )
            )
            if not quiet:
                print(f"[{chat_pk}] {title}: total={len(bundles)} new={new_messages} changed={changed_messages} unchanged={unchanged_messages}", flush=True)

        state["version"] = 1
        state["chat_state"] = next_chat_state
        state.setdefault("runs", []).append({
            "run_id": run_id,
            "mode": mode,
            "db_sha256": db_sha,
            "summary_path": str(summary_path),
            "run_dir": str(run_dir),
            "created_at": created_at,
        })
        state["runs"] = state["runs"][-200:]
        save_state(state_path, state)

        result = RunResult(
            run_id=run_id,
            mode=mode,
            source=source,
            output_root=output_root,
            state_root=state_root,
            run_dir=run_dir,
            summary_path=summary_path,
            chat_results=chat_results,
            db_sha256=db_sha,
        )
        summary_path.write_text(render_summary(result), encoding="utf-8")
        append_log(output_root / DEFAULT_LOG_FILENAME, result)
        index_path.write_text(render_index(chat_results, source, run_id, mode, output_root), encoding="utf-8")
        return result
    finally:
        con.close()


def render_summary(result: RunResult) -> str:
    lines = [
        "# WhatsApp extract summary",
        "",
        f"Run ID: {result.run_id}",
        f"Mode: {result.mode}",
        f"Source DB: {result.source.db_path}",
        f"DB SHA256: {result.db_sha256}",
    ]
    if result.source.manifest_path:
        lines.append(f"Manifest: {result.source.manifest_path}")
    if result.source.backup_root:
        lines.append(f"Backup root: {result.source.backup_root}")
    lines.extend([
        f"Output root: {result.output_root}",
        f"State root: {result.state_root}",
        "",
        "## Chats",
        "",
        "| Chat | Messages | New | Changed | Unchanged | Removed | File |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for chat in sorted(result.chat_results, key=lambda x: (x.last_message_iso or "", x.title), reverse=True):
        lines.append(
            f"| {chat.title} | {chat.total_messages} | {chat.new_messages} | {chat.changed_messages} | {chat.unchanged_messages} | {chat.removed_messages} | `{chat.file_path}` |"
        )
    lines.extend(["", "## Output", "", f"- Summary file: {result.summary_path}", f"- Run directory: {result.run_dir}", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        source = resolve_source(args)
        state_root = args.state_root if args.state_root is not None else args.output_root / "state"
        result = extract_whatsapp_corpus(source, args.output_root, state_root, args.mode, args.batch_size, quiet=args.quiet)
    except ExtractionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"sqlite error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"os error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Extract complete: {result.run_dir}")
        print(f"Summary: {result.summary_path}")
        print(f"Index: {result.output_root / 'index.md'}")
        print(f"Chats: {result.output_root / DEFAULT_CHAT_DIRNAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
