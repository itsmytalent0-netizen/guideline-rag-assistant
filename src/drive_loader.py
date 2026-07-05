from __future__ import annotations

import io
import json

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import AppConfig


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _drive_service(config: AppConfig):
    service_account_info = json.loads(config.google_service_account_json)
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=SCOPES,
    )
    return build("drive", "v3", credentials=credentials)


def load_csvs_from_drive(config: AppConfig) -> list[tuple[str, pd.DataFrame]]:
    service = _drive_service(config)
    query = (
        f"'{config.google_drive_folder_id}' in parents "
        "and mimeType='text/csv' and trashed=false"
    )
    response = service.files().list(
        q=query,
        fields="files(id,name,modifiedTime)",
        pageSize=1000,
    ).execute()

    csvs: list[tuple[str, pd.DataFrame]] = []
    for file in response.get("files", []):
        request = service.files().get_media(fileId=file["id"])
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)
        try:
            df = pd.read_csv(buffer)
        except UnicodeDecodeError:
            buffer.seek(0)
            df = pd.read_csv(buffer, encoding="latin-1")
        csvs.append((file["name"], df))
    return csvs
