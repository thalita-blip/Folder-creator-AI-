import hmac
import mimetypes
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "tools"))

from auth import get_services  # noqa: E402
from drive_folders import (  # noqa: E402
    find_duplicate_candidates,
    get_or_create_folder,
    upload_file,
    upload_bytes,
)
from rfa_ingest import extract_text, ExtractionError  # noqa: E402
from scrape_grant_page import find_attachment_links, download_attachment, ScrapeBlockedError  # noqa: E402
from synthesize import synthesize  # noqa: E402
from sop_generator import generate_sop_docx  # noqa: E402
from tracker_generator import generate_tracker_xlsx  # noqa: E402

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "")
TMP_DIR = ROOT / ".tmp"
TMP_DIR.mkdir(exist_ok=True)

GRANTS_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_GRANTS_ROOT_FOLDER_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


@app.before_request
def require_login():
    if request.path == "/login" or request.path.startswith("/static"):
        return
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Incorrect password."
    return render_template("login.html", error=error)

_drive_service = None


def drive():
    global _drive_service
    if _drive_service is None:
        _drive_service = get_services()
    return _drive_service


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/check-duplicate", methods=["POST"])
def check_duplicate():
    body = request.get_json(force=True)
    grant_name = (body.get("grant_name") or "").strip()
    if not grant_name:
        return jsonify({"error": "Grant name is required."}), 400
    if not GRANTS_ROOT_FOLDER_ID:
        return jsonify({"error": "GOOGLE_DRIVE_GRANTS_ROOT_FOLDER_ID is not set in .env"}), 500

    try:
        matches = find_duplicate_candidates(drive(), GRANTS_ROOT_FOLDER_ID, grant_name)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Drive lookup failed: {e}"}), 500

    return jsonify({"matches": matches})


@app.route("/ingest", methods=["POST"])
def ingest():
    url = (request.form.get("url") or "").strip()
    pasted_text = (request.form.get("text") or "").strip()
    file = request.files.get("file")

    pdf_bytes = None
    docx_bytes = None
    if file and file.filename:
        raw = file.read()
        if file.filename.lower().endswith(".pdf"):
            pdf_bytes = raw
        elif file.filename.lower().endswith(".docx"):
            docx_bytes = raw
        else:
            return jsonify({"error": "Only .pdf or .docx uploads are supported."}), 400

    try:
        text = extract_text(pdf_bytes=pdf_bytes, docx_bytes=docx_bytes, url=url or None, pasted_text=pasted_text or None)
    except ExtractionError as e:
        return jsonify({"error": str(e)}), 400
    except ScrapeBlockedError as e:
        return jsonify({"error": f"{e} — try pasting the text instead."}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Could not extract RFA text: {e}"}), 400

    (TMP_DIR / "grant_raw.txt").write_text(text, encoding="utf-8")
    return jsonify({"text": text, "char_count": len(text)})


@app.route("/synthesize", methods=["POST"])
def do_synthesize():
    body = request.get_json(force=True)
    rfa_text = (body.get("text") or "").strip()
    if not rfa_text:
        return jsonify({"error": "No RFA text to synthesize."}), 400
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY is not set in .env"}), 500

    try:
        result = synthesize(rfa_text, api_key=GEMINI_API_KEY)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Synthesis failed: {e}"}), 500

    return jsonify(result)


@app.route("/create", methods=["POST"])
def create():
    body = request.get_json(force=True)
    grant_name = (body.get("grant_name") or "").strip()
    year = (body.get("year") or "").strip()
    sop_sections = body.get("sop_sections") or {}
    tracker_extras = body.get("tracker_extras") or {}
    website_url = (body.get("website_url") or "").strip()
    use_existing_grant_folder_id = body.get("use_existing_grant_folder_id")

    if not grant_name or not year:
        return jsonify({"error": "Grant name and year are required."}), 400
    if not GRANTS_ROOT_FOLDER_ID:
        return jsonify({"error": "GOOGLE_DRIVE_GRANTS_ROOT_FOLDER_ID is not set in .env"}), 500

    d = drive()
    scrape_log = []

    try:
        if use_existing_grant_folder_id:
            grant_folder_id = use_existing_grant_folder_id
        else:
            grant_folder_id, _ = get_or_create_folder(d, grant_name, GRANTS_ROOT_FOLDER_ID)

        year_folder_id, year_created = get_or_create_folder(d, year, grant_folder_id)
        if not year_created:
            scrape_log.append(f"Note: a folder for {year} already existed under {grant_name} — reused it.")

        docs_folder_id, _ = get_or_create_folder(d, "Important Documents", year_folder_id)

        if website_url:
            try:
                attachments = find_attachment_links(website_url)
                for a in attachments:
                    try:
                        content = download_attachment(a["url"])
                        mime_type, _ = mimetypes.guess_type(a["filename"])
                        upload_bytes(d, content, a["filename"], docs_folder_id, mime_type=mime_type or "application/octet-stream")
                        scrape_log.append(f"Uploaded: {a['filename']}")
                    except Exception as e:
                        scrape_log.append(f"Failed to download {a['filename']}: {e}")
            except Exception as e:
                scrape_log.append(f"Could not scrape {website_url}: {e}")

        sop_path = TMP_DIR / f"{grant_name} {year} - SOP.docx"
        generate_sop_docx(grant_name, year, sop_sections, sop_path)
        sop_file_id = upload_file(d, sop_path, year_folder_id, name="SOP.docx")

        tracker_path = TMP_DIR / f"{grant_name} {year} - Tracker.xlsx"
        generate_tracker_xlsx(grant_name, year, tracker_extras, tracker_path)
        tracker_file_id = upload_file(d, tracker_path, year_folder_id, name="Tracker.xlsx")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Drive creation failed: {e}"}), 500

    return jsonify({
        "grant_folder_url": f"https://drive.google.com/drive/folders/{grant_folder_id}",
        "year_folder_url": f"https://drive.google.com/drive/folders/{year_folder_id}",
        "sop_url": f"https://drive.google.com/file/d/{sop_file_id}/view",
        "tracker_url": f"https://drive.google.com/file/d/{tracker_file_id}/view",
        "scrape_log": scrape_log,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050)
