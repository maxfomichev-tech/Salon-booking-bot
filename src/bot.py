from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from src.calendar_client import Booking, GoogleCalendarClient
from src.config import load_config
from src.groq_chat import GroqConsultant
from src.services import load_services, format_services, Service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aaron-salon-bot")

class BookingFlow(StatesGroup):
    service = State()
    dt = State()
    name = State()
    phone = State()
    confirm = State()


def _parse_datetime_ru(text: str, tz: str) -> datetime | None:
    """
    Minimal parser: expects 'YYYY-MM-DD HH:MM' in local salon timezone.
    """
    text = text.strip()
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=ZoneInfo(tz))
    except ValueError:
        return None


@dataclass(frozen=True)
class AppState:
    cfg: object
    services: list[Service]
    consultant: GroqConsultant
    calendar: GoogleCalendarClient


def _match_service(services: list[Service], user_text: str) -> Service | None:
    t = (user_text or "").strip().lower()
    if not t:
        return None
    for s in services:
        if t in s.service.lower() or s.service.lower() in t:
            return s
    return None


async def cmd_start(message: Message, state: FSMContext, app: AppState) -> None:
    await state.clear()
    await message.answer(
        f"Здравствуйте! Это бот салона красоты <b>{app.cfg.salon_name}</b>.\n\n"
        "Я могу:\n"
        "- подсказать по услугам и ценам\n"
        "- записать вас в Google Calendar\n\n"
        "Команды:\n"
        "/price — прайс-лист\n"
        "/book — запись\n"
        "/help — помощь\n",
        parse_mode=ParseMode.HTML,
    )
    await message.answer(format_services(app.services, limit=12))


async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Напишите вопрос текстом или используйте /book для записи.")


async def cmd_price(message: Message, app: AppState) -> None:
    await message.answer(format_services(app.services, limit=30))


async def cmd_book(message: Message, state: FSMContext, app: AppState) -> None:
    await state.set_state(BookingFlow.service)
    await state.update_data(draft={})
    await message.answer(
        "Ок, давайте запишем вас. Напишите название услуги (как в прайсе). Например:\n"
        f"{app.services[0].service}"
    )


async def book_service(message: Message, state: FSMContext, app: AppState) -> None:
    svc = _match_service(app.services, message.text or "")
    if not svc:
        await message.answer("Не нашёл такую услугу. Напишите точнее, или /price чтобы посмотреть список.")
        return

    await state.update_data(service=svc.service, duration_minutes=svc.duration_minutes, price_rub=svc.price_rub)
    await state.set_state(BookingFlow.dt)
    await message.answer(
        "Отлично. Напишите дату и время в формате <code>YYYY-MM-DD HH:MM</code>.\n"
        f"Часовой пояс: {app.cfg.salon_timezone}\n"
        "Пример: 2026-04-25 15:30",
        parse_mode=ParseMode.HTML,
    )


async def book_dt(message: Message, state: FSMContext, app: AppState) -> None:
    dt = _parse_datetime_ru(message.text or "", app.cfg.salon_timezone)
    if not dt:
        await message.answer("Не понял дату/время. Формат должен быть <code>YYYY-MM-DD HH:MM</code>.", parse_mode=ParseMode.HTML)
        return

    # ПРОВЕРКА ЗАНЯТОСТИ
    data = await state.get_data()
    duration = int(data.get("duration_minutes", 60))
    end = dt + timedelta(minutes=duration)
    
    try:
        if not app.calendar.is_time_available(dt, end):
            await message.answer(
                f"⚠️ К сожалению, время {dt.strftime('%H:%M')} уже занято.\n"
                "Пожалуйста, выберите другое время в формате <code>YYYY-MM-DD HH:MM</code>:",
                parse_mode=ParseMode.HTML,
            )
            return  # Остаёмся в состоянии BookingFlow.dt, просим ввести снова
    except Exception as e:
        logger.error("Error checking availability: %s", e)
        # Если проверка сломалась — продолжаем запись, но логируем ошибку

    await state.update_data(start_iso=dt.isoformat())
    await state.set_state(BookingFlow.name)
    await message.answer("Как вас зовут?")


async def book_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Имя слишком короткое. Напишите ещё раз.")
        return
    await state.update_data(client_name=name)
    await state.set_state(BookingFlow.phone)
    await message.answer("Ваш телефон (например +7 999 123-45-67)?")


async def book_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer("Похоже на слишком короткий номер. Напишите телефон ещё раз.")
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingFlow.confirm)

    data = await state.get_data()
    await message.answer(
        "Проверьте запись:\n"
        f"- Услуга: {data['service']} ({data['duration_minutes']} мин, {data['price_rub']} ₽)\n"
        f"- Когда: {data['start_iso'][:16].replace('T', ' ')}\n"
        f"- Имя: {data['client_name']}\n"
        f"- Телефон: {data['phone']}\n\n"
        "Ответьте «да» чтобы подтвердить или «нет» чтобы отменить."
    )


async def book_confirm(message: Message, state: FSMContext, app: AppState) -> None:
    answer = (message.text or "").strip().lower()
    if answer not in {"да", "нет"}:
        await message.answer("Ответьте «да» или «нет».")
        return
    if answer == "нет":
        await state.clear()
        await message.answer("Ок, отменил. Если захотите — /book.")
        return

    data = await state.get_data()
    start = datetime.fromisoformat(data["start_iso"])
    booking = Booking(
        service_name=data["service"],
        client_name=data["client_name"],
        phone=data["phone"],
        start=start,
        duration_minutes=int(data["duration_minutes"]),
        timezone=app.cfg.salon_timezone,
        salon_name=app.cfg.salon_name,
    )
    link = app.calendar.create_booking_event(booking)
    await state.clear()
    await message.answer("Готово! Я создал событие в календаре.")
    if link:
        await message.answer(f"Ссылка: {link}")


async def consult(message: Message, state: FSMContext, app: AppState) -> None:
    if await state.get_state() is not None:
        return
    try:
        reply = app.consultant.reply(message.text or "")
    except Exception as e:
        logger.exception("Groq error")
        await message.answer(f"Ошибка консультации. Попробуйте ещё раз.\n\n{e}")
        return
    await message.answer(reply)


async def maybe_start_booking(message: Message, state: FSMContext, app: AppState) -> None:
    text = (message.text or "").strip().lower()
    
    booking_triggers = ["запиши", "записаться", "хочу записаться", "хочу на", "запись", "booking"]
    
    for trigger in booking_triggers:
        if trigger in text:
            await cmd_book(message, state, app)
            return
    
    await consult(message, state, app)


def main() -> None:
    cfg = load_config()
    services = load_services(cfg.services_csv)

    consultant = GroqConsultant(
        api_key=cfg.groq_api_key,
        model=cfg.groq_model,
        salon_name=cfg.salon_name,
        services_text=format_services(services, limit=60),
        address=cfg.address,
    )
    calendar = GoogleCalendarClient(
        calendar_id=cfg.google_calendar_id,
        service_account_json_path=str(cfg.google_service_account_json_path) if cfg.google_service_account_json_path else None,
        service_account_json_content=cfg.google_service_account_json_content,
    )
    app_state = AppState(cfg=cfg, services=services, consultant=consultant, calendar=calendar)

    async def _run() -> None:
        bot = Bot(token=cfg.telegram_bot_token)
        dp = Dispatcher(storage=MemoryStorage())

        async def _cmd_start(message: Message, state: FSMContext) -> None:
            await cmd_start(message, state, app_state)

        async def _cmd_price(message: Message) -> None:
            await cmd_price(message, app_state)

        async def _cmd_book(message: Message, state: FSMContext) -> None:
            await cmd_book(message, state, app_state)

        async def _book_service(message: Message, state: FSMContext) -> None:
            await book_service(message, state, app_state)

        async def _book_dt(message: Message, state: FSMContext) -> None:
            await book_dt(message, state, app_state)

        async def _book_confirm(message: Message, state: FSMContext) -> None:
            await book_confirm(message, state, app_state)

        async def _maybe_start_booking(message: Message, state: FSMContext) -> None:
            await maybe_start_booking(message, state, app_state)

        dp.message.register(_cmd_start, Command("start"))
        dp.message.register(cmd_help, Command("help"))
        dp.message.register(_cmd_price, Command("price"))
        dp.message.register(_cmd_book, Command("book"))

        dp.message.register(_book_service, BookingFlow.service, F.text)
        dp.message.register(_book_dt, BookingFlow.dt, F.text)
        dp.message.register(book_name, BookingFlow.name, F.text)
        dp.message.register(book_phone, BookingFlow.phone, F.text)
        dp.message.register(_book_confirm, BookingFlow.confirm, F.text)

        dp.message.register(_maybe_start_booking, F.text)

        webhook_url = (os.getenv("WEBHOOK_URL") or "").strip()
        render_external_url = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
        port = int(os.getenv("PORT", "10000"))

        if not webhook_url and render_external_url:
            webhook_url = f"{render_external_url.rstrip('/')}/webhook"

        if webhook_url:
            await bot.set_webhook(webhook_url)
            logger.info("Bot starting in webhook mode on port %s", port)

            app = web.Application()
            app.router.add_get("/health", lambda _: web.Response(text="ok"))
            SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/webhook")
            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=port)
            await site.start()

            await asyncio.Event().wait()
        else:
            logger.info("Bot starting in polling mode...")
            await dp.start_polling(bot)

    asyncio.run(_run())


if __name__ == "__main__":
    main()