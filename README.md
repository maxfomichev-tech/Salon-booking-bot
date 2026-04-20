# Telegram бот салона красоты "Аарон"

Бот:

- консультирует клиентов (через бесплатные модели Groq)
- предлагает услуги и цены из прайс-листа
- записывает клиента в Google Calendar

## 1) Что понадобится

- Windows + **Python 3.12 или 3.13** (важно: под Python 3.14 часть зависимостей ставится из исходников и часто требует компилятор)
- Telegram Bot Token (у @BotFather)
- Groq API key (из Groq Console)
- Google Calendar, куда будем писать записи

## 2) Быстрый старт

1. Установить зависимости:

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Если у вас установлен Python 3.14 и установка “зависает” на сборке пакетов (например `pydantic-core`), поставьте Python 3.13 и создайте окружение так:

```bash
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

1. Создать `.env` из примера:

```bash
copy .env.example .env
```

1. Подготовить Google Calendar (вариант с service account)

- В Google Cloud Console создайте **Service Account** и скачайте ключ JSON.
- Укажите креды одним из способов:
  - `GOOGLE_SERVICE_ACCOUNT_JSON` — путь к JSON файлу
  - `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` — содержимое JSON (удобно для Render)
- В Google Calendar (в вебе) откройте настройки календаря → **Доступ** → **Поделиться** и добавьте email service account (вида `xxx@yyy.iam.gserviceaccount.com`) с правом **Вносить изменения**.
- В `.env` укажите `GOOGLE_CALENDAR_ID`:
  - обычно это email календаря, либо ID вида `...@group.calendar.google.com`.

1. Запуск:

```bash
python -m src.bot
```

## Деплой на Render

Рекомендация: запускать в **webhook режиме**.

1. Загрузите проект в GitHub.
2. В Render создайте **New → Web Service** из репозитория.
3. Укажите переменные окружения (секретами):
  - `TELEGRAM_BOT_TOKEN`
  - `GROQ_API_KEY`
  - `GOOGLE_CALENDAR_ID`
  - `GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT` (JSON строкой в секрете) **или** `GOOGLE_SERVICE_ACCOUNT_JSON` (путь к secret file)
4. В Render внешний URL автоматически попадает в `RENDER_EXTERNAL_URL`, бот сам соберёт `WEBHOOK_URL = <ваш_render_url>/webhook`.

Проверка здоровья: `GET /health` (возвращает `ok`).

## 3) Прайс-лист услуг

- Файл `services_pricelist.csv` открывается в Excel и служит примером (можно заменить).
- Если нужен именно `.xlsx`, запустите:

```bash
python scripts/make_xlsx.py
```

## 4) Как работает запись

Бот собирает:

- имя
- телефон
- услугу
- дату и время

После подтверждения создаёт событие в Google Calendar.

## 5) Переменные окружения

Смотрите `.env.example`.