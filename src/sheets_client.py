from __future__ import annotations

import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import Optional


class SheetsClient:
    def __init__(self, spreadsheet_id: str, credentials_json: str) -> None:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            json.loads(credentials_json), scopes=scopes
        )
        self._client = gspread.authorize(creds)
        self._sheet = self._client.open_by_key(spreadsheet_id).sheet1

    def add_or_update(
        self,
        client_id: str,
        name: str,
        phone: str,
        service_name: str,
    ) -> None:
        """Добавляет нового клиента или обновляет существующего."""
        now = datetime.now().isoformat()

        # gspread exception names differ between versions; resolve dynamically.
        cell_not_found_exc = getattr(getattr(gspread, "exceptions", object()), "CellNotFound", None)

        # Ищем клиента по ID
        try:
            cell = self._sheet.find(client_id)
            if cell is None:
                raise LookupError(f"Client id not found: {client_id}")
            row = cell.row
            
            # Обновляем существующего
            self._sheet.update_cell(row, 5, now)  # last_contact
            self._sheet.update_cell(row, 6, now)  # last_service_date
            self._sheet.update_cell(row, 7, service_name)  # last_service_name
            current_visits = int(self._sheet.cell(row, 8).value or 0)
            self._sheet.update_cell(row, 8, current_visits + 1)  # total_visits
        except Exception as e:
            if isinstance(e, LookupError) or (
                cell_not_found_exc is not None and isinstance(e, cell_not_found_exc)
            ):
                # Новый клиент
                self._sheet.append_row([
                    client_id,
                    name,
                    phone,
                    now,  # first_contact
                    now,  # last_contact
                    now,  # last_service_date
                    service_name,
                    1,    # total_visits
                ])
                return
            raise

    def get_client(self, client_id: str) -> Optional[dict]:
        cell_not_found_exc = getattr(getattr(gspread, "exceptions", object()), "CellNotFound", None)
        try:
            cell = self._sheet.find(client_id)
            if cell is None:
                raise LookupError(f"Client id not found: {client_id}")
            row = cell.row
            values = self._sheet.row_values(row)
            return {
                "client_id": values[0],
                "name": values[1],
                "phone": values[2],
                "first_contact": values[3],
                "last_contact": values[4],
                "last_service_date": values[5],
                "last_service_name": values[6],
                "total_visits": values[7],
            }
        except Exception as e:
            if isinstance(e, LookupError) or (
                cell_not_found_exc is not None and isinstance(e, cell_not_found_exc)
            ):
                return None
            raise