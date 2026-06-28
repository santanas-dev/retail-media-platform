# Manual E2E Demo Scenario Closure — Шаг 45.4.4

**Дата:** 2026-06-28
**Commit:** (pending)
**Статус:** Завершён

## Результат

**Manual E2E: ❌ FAIL (readiness gap)**
**Тип сценария:** Вариант Б — Prepared-data demo

## Что сделано

### 1. Storage bug fix
- **Баг:** `_detect_mime_type` передавал только 2048 байт в Pillow `verify()`, что ломало загрузку PNG >2KB
- **Фикс:** `storage.py:120` — `file_content[:2048]` → `file_content`
- Файлы: `backend/app/domains/media/storage.py`

### 2. Order status constraint fix
- **Баг:** `_ensure_technical_order` использовал `status="active"`, не входящий в CHECK constraint `ck_orders_status`
- **Фикс:** `service.py:639` — `"active"` → `"draft"`
- Файлы: `backend/app/domains/campaigns/service.py`

### 3. Missing DB migration
- **Проблема:** Таблицы `schedules` и `schedule_slots` были в моделях, но отсутствовали в БД
- **Фикс:** Создана миграция `033_schedules_and_slots`
- Файлы: `backend/alembic/versions/033_schedules_and_slots.py`

### 4. Upload fix — креативы успешно загружены
- Созданы 2 реальных PNG 768×1024: «Акция Скидка 30%» и «Новинка свежие продукты»
- Загружены через API (`POST /api/creatives/upload`)
- Одобрены через API (`PUT /api/creatives/{id}` → `status=approved`)

### 5. Campaign creation — частично
- Кампания `demo_promo_jan` создана через API (`POST /api/campaigns/by-code`)
- 2 креатива привязаны на уровне БД (таблица `campaign_creatives`)
- **Проблема:** Портал не отображает привязанные креативы (столбец «КРЕАТИВЫ» — всегда «Креатив не выбран»)

## Readiness Gap — подробно

### Campaign submit не работает
`POST /api/campaigns/by-code/{code}/submit` требует:
1. ✅ Creative bindings — есть в БД
2. ✅ Creatives approved — да
3. ❌ Schedule — создаётся, но:
   - `GET /api/schedules` → 500 (ошибка сериализации)
   - `GET /api/schedules/{code}` → 500
4. ❌ Schedule slots — эндпоинт `/api/schedules/{code}/items` не протестирован

### Причины 500 на schedules
- Таблицы созданы миграцией 033, но schedule service имеет баги сериализации
- `_schedule_to_dict` возвращает `datetime` объекты вместо строк
- ScheduleResponse схема ожидает строки

### Multi-creative campaign
- ✅ Модель `campaign_creatives` поддерживает N:N связь
- ✅ API принимает `creative_codes: []` при создании
- ❌ Портал не показывает привязанные креативы
- ❌ Портал не даёт UI для управления креативами кампании

### Placements/Schedule UI
- ❌ Портал не даёт UI для создания placements
- ❌ Портал не даёт UI для создания schedule slots
- ❌ Расписание всегда показывает «0 расписаний»

## Что работает для демо

| Шаг | API | Портал |
|-----|-----|--------|
| Загрузить креатив | ✅ | ✅ (через форму, но file input глючный) |
| Одобрить креатив | ✅ | ✅ (через moderation page) |
| Создать кампанию | ✅ | ❌ (только через API) |
| Привязать креативы | ✅ (при создании) | ❌ |
| Создать расписание | ❌ (500) | ❌ |
| Отправить на согласование | ❌ (нужно расписание) | ❌ |
| Публикации | ✅ (seed data) | ✅ |
| Отчёты | ✅ (seed data) | ✅ |

## Оставшиеся product gaps (P1)

1. **Schedule API broken** — нужен фикс сериализации и тесты
2. **Submit flow** — не работает без schedule + slots
3. **Campaign creatives UI** — портал не показывает привязанные креативы
4. **Schedule/placement UI** — полностью отсутствует
5. **«Креатив не выбран»** — показывает даже когда креативы привязаны

## Рекомендация для бизнес-показа

**Использовать Вариант Б:** Показывать готовые seed-данные:
- Список креативов (22 шт., включая 2 новых)
- Список кампаний (21 шт.)
- Список публикаций (74 пакета)
- Отчёты (CSV export)
- Честно сказать: «Создание кампании с нуля — в разработке, показываем на готовых данных»

## Regression

| Слой | Результат |
|------|-----------|
| Backend | **807** passed, 0 failed |
| Portal | **777** passed, 32 skipped, 0 failed |

## Безопасность

- ✅ JS/CDN/localStorage: 0
- ✅ Secrets/leaks: 0
- ✅ RBAC/RLS/audit: не ослаблены
- ✅ Физическая КСО: не трогали
- ✅ Scanner E2E: не запускали
- ✅ Production AV: не включён
