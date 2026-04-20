from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build


@dataclass(frozen=True)
class Booking:
    service_name: str
    client_name: str
    phone: str
    start: datetime
    duration_minutes: int
    timezone: str
    salon_name: str

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)


class GoogleCalendarClient:
    def __init__(
        self,
        calendar_id: str,
        *,
        service_account_json_path: str | None = None,
        service_account_json_content: str | None = None,
    ) -> None:
        if service_account_json_content:
            info = json.loads(service_account_json_content)
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
        elif service_account_json_path:
            creds = service_account.Credentials.from_service_account_file(
                service_account_json_path,
                scopes=["https://www.googleapis.com/auth/calendar"],
            )
        else:
            raise ValueError("Provide service_account_json_content or service_account_json_path")

        self._service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        self._calendar_id = calendar_id

    def is_time_available(self, start: datetime, end: datetime) -> bool:
        """Проверяет, свободно ли время в календаре."""
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": self._calendar_id}],
        }
        result = self._service.freebusy().query(body=body).execute()
        busy_times = result["calendars"][self._calendar_id]["busy"]
        return len(busy_times) == 0

    def create_booking_event(self, booking: Booking) -> str:
        summary = f"{booking.salon_name}: {booking.service_name}"
        description = f"Клиент: {booking.client_name}\nТелефон: {booking.phone}\nУслуга: {booking.service_name}"
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": booking.start.isoformat(), "timeZone": booking.timezone},
            "end": {"dateTime": booking.end.isoformat(), "timeZone": booking.timezone},
        }
        event = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return event.get("htmlLink") or ""