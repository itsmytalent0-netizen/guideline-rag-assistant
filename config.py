from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    google_drive_folder_id: str
    google_service_account_json: str
    embedding_model: str
    vector_db_dir: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @classmethod
    def from_environment(cls) -> "AppConfig":
        load_dotenv()

        def get_secret(name: str, default: str = "") -> str:
            value = os.getenv(name)
            if value:
                return value.strip()
            try:
                import streamlit as st

                if name in st.secrets:
                    return str(st.secrets[name]).strip()
            except Exception:
                pass
            return default

        return cls(
            google_drive_folder_id=get_secret("GOOGLE_DRIVE_FOLDER_ID"),
            google_service_account_json=get_secret("GOOGLE_SERVICE_ACCOUNT_JSON"),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
            ).strip(),
            vector_db_dir=get_secret("VECTOR_DB_DIR", ".rag/chroma"),
            llm_provider=get_secret("LLM_PROVIDER", "openai_compatible"),
            llm_base_url=get_secret("LLM_BASE_URL"),
            llm_api_key=get_secret("LLM_API_KEY"),
            llm_model=get_secret("LLM_MODEL"),
        )

    @property
    def llm_is_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)
