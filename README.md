# Retail Media Platform

Мультиканальная платформа управления рекламой на цифровых носителях розничной сети.

## Статус

🏗️ Шаг 1: Архитектурный каркас. Инфраструктура, базовая модель данных.

## Каналы (в порядке реализации)

1. КСО (Sherman-J, Linux + Chromium kiosk)
2. Android TV / ТВ-приставки
3. Android Price Checker
4. ESL (электронные ценники)
5. LED shelf banners

## Быстрый старт

```bash
# 1. Инфраструктура
cd infra && docker compose up -d

# 2. Миграция
cd ../backend && cp ../.env.example .env && alembic upgrade head

# 3. Запуск
uvicorn app.main:app --reload

# 4. Проверка
curl http://localhost:8000/health
```

## Архитектура

См. [docs/architecture.md](docs/architecture.md)

## Лицензия

Внутренний проект компании.
