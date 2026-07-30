"""
Drive folder operations: fuzzy duplicate detection, nested folder creation,
and file upload. Used by app.py's /check-duplicate and /create routes.
"""
from __future__ import annotations

import io
import mimetypes
import re
from pathlib import Path

from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from rapidfuzz import fuzz

DUPLICATE_THRESHOLD = 85

_STOPWORDS = {"grant", "grants", "program", "the", "a", "an", "of", "for", "and"}


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, drop common grant-naming stopwords."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    words = [w for w in name.split() if w not in _STOPWORDS]
    return " ".join(words)


def list_subfolders(drive, parent_id: str) -> list[dict]:
    """Return [{id, name}] for all folders directly under parent_id."""
    folders = []
    page_token = None
    query = (
        f"'{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    while True:
        resp = (
            drive.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
        )
        folders.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return folders


def find_duplicate_candidates(drive, parent_id: str, candidate_name: str) -> list[dict]:
    """
    Fuzzy-match candidate_name against existing subfolders of parent_id.
    Returns matches >= DUPLICATE_THRESHOLD, sorted by score descending, as
    [{id, name, score}].
    """
    normalized_candidate = normalize_name(candidate_name)
    existing = list_subfolders(drive, parent_id)

    matches = []
    for folder in existing:
        score = fuzz.token_sort_ratio(normalized_candidate, normalize_name(folder["name"]))
        if score >= DUPLICATE_THRESHOLD:
            matches.append({"id": folder["id"], "name": folder["name"], "score": round(score, 1)})

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


def find_exact_or_close_subfolder(drive, parent_id: str, name: str, threshold: float = 95) -> dict | None:
    """Used for year-level existence checks — near-exact match only."""
    normalized = normalize_name(name)
    for folder in list_subfolders(drive, parent_id):
        if fuzz.token_sort_ratio(normalized, normalize_name(folder["name"])) >= threshold:
            return folder
    return None


def create_folder(drive, name: str, parent_id: str) -> str:
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = drive.files().create(body=meta, fields="id").execute()
    return folder["id"]


def get_or_create_folder(drive, name: str, parent_id: str, threshold: float = 95) -> tuple[str, bool]:
    """Returns (folder_id, created) — created=False if an existing near-exact match was reused."""
    existing = find_exact_or_close_subfolder(drive, parent_id, name, threshold=threshold)
    if existing:
        return existing["id"], False
    return create_folder(drive, name, parent_id), True


def upload_file(drive, local_path: Path, parent_id: str, name: str | None = None) -> str:
    """Upload a local file to a Drive folder. Returns the new file's id."""
    upload_name = name or local_path.name
    mime_type, _ = mimetypes.guess_type(str(local_path))
    media = MediaFileUpload(str(local_path), mimetype=mime_type or "application/octet-stream", resumable=True)
    meta = {"name": upload_name, "parents": [parent_id]}
    file = drive.files().create(body=meta, media_body=media, fields="id").execute()
    return file["id"]


def upload_bytes(drive, data: bytes, name: str, parent_id: str, mime_type: str) -> str:
    """Upload in-memory bytes (e.g. a downloaded attachment) to a Drive folder."""
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime_type, resumable=True)
    meta = {"name": name, "parents": [parent_id]}
    file = drive.files().create(body=meta, media_body=media, fields="id").execute()
    return file["id"]
