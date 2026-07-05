from __future__ import annotations

import io
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import AppConfig


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
GOOGLE_EXPORT_TYPES = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "text/csv",
        ".csv",
    ),
}
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "text/csv",
    "text/plain",
}


def _drive_service(config: AppConfig):
    service_account_info = json.loads(config.google_service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=credentials)


def load_files_from_drive(config: AppConfig) -> list[tuple[str, bytes, str]]:
    service = _drive_service(config)
    query = (
        f"'{config.google_drive_folder_id}' in parents "
        "and trashed=false"
    )
    response = service.files().list(
        q=query,
        fields="files(id,name,mimeType,modifiedTime)",
        pageSize=1000,
    ).execute()

    files: list[tuple[str, bytes, str]] = []
    for file in response.get("files", []):
        mime_type = file.get("mimeType", "")
        filename = file["name"]
        if mime_type in GOOGLE_EXPORT_TYPES:
            export_mime_type, extension = GOOGLE_EXPORT_TYPES[mime_type]
            request = service.files().export_media(
                fileId=file["id"],
                mimeType=export_mime_type,
            )
            if not filename.lower().endswith(extension):
                filename = f"{filename}{extension}"
            mime_type = export_mime_type
        elif mime_type in SUPPORTED_MIME_TYPES:
            request = service.files().get_media(fileId=file["id"])
        else:
            continue

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        files.append((filename, buffer.getvalue(), mime_type))
    return files
