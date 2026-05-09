"""
Google Sheets integration service (API v4).

Features:
- Service account authentication
- Append row to configured sheet
- Retry logic with exponential backoff on transient API errors
"""

from __future__ import annotations

import asyncio
import json
import os
import logging
from typing import List, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class SheetsService:
    def __init__(self) -> None:
        self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self.sheet_name = os.getenv("GOOGLE_SHEETS_SHEET_NAME", "HotLeads")
        self._service = self._build_service()

    def _build_credentials(self) -> Credentials:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
        credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

        if credentials_json:
            info = json.loads(credentials_json)
            return Credentials.from_service_account_info(info, scopes=scopes)

        if credentials_path:
            return Credentials.from_service_account_file(credentials_path, scopes=scopes)

        raise RuntimeError(
            "Google Sheets service account credentials missing. "
            "Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON."
        )

    def _build_service(self):
        creds = self._build_credentials()
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    async def append_row(
        self,
        row_values: List[str],
        spreadsheet_id: Optional[str] = None,
        sheet_name: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        """
        Append a single row to a Google Sheet with retry on transient failures.
        """
        target_spreadsheet = spreadsheet_id or self.spreadsheet_id
        target_sheet = sheet_name or self.sheet_name

        if not target_spreadsheet:
            raise RuntimeError("GOOGLE_SHEETS_SPREADSHEET_ID is required.")

        body = {"values": [row_values]}
        range_name = f"{target_sheet}!A1"

        delay_seconds = 1.0
        for attempt in range(1, max_retries + 1):
            try:
                await asyncio.to_thread(
                    lambda: self._service.spreadsheets()
                    .values()
                    .append(
                        spreadsheetId=target_spreadsheet,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        insertDataOption="INSERT_ROWS",
                        body=body,
                    )
                    .execute()
                )
                return
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                retriable = status in {429, 500, 502, 503, 504}
                logger.exception(
                    "Google Sheets API error on append attempt %s/%s (status=%s, retriable=%s, spreadsheet=%s, sheet=%s)",
                    attempt,
                    max_retries,
                    status,
                    retriable,
                    target_spreadsheet,
                    target_sheet,
                )
                if attempt >= max_retries or not retriable:
                    raise
            except Exception:
                logger.exception(
                    "Unexpected Google Sheets append failure on attempt %s/%s (spreadsheet=%s, sheet=%s)",
                    attempt,
                    max_retries,
                    target_spreadsheet,
                    target_sheet,
                )
                if attempt >= max_retries:
                    raise

            await asyncio.sleep(delay_seconds)
            delay_seconds *= 2.0

