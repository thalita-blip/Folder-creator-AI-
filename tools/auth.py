"""
Usage: python tools/auth.py
Runs the browser OAuth consent flow and writes token.json.
"""
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]

ROOT = Path(__file__).parent.parent
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"


def get_services():
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    "credentials.json not found. Download it from Google Cloud Console "
                    "(APIs & Services -> Credentials -> OAuth 2.0 Client ID -> Desktop app)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    drive = build("drive", "v3", credentials=creds)
    return drive


if __name__ == "__main__":
    get_services()
    print("Authentication successful. token.json saved.")
