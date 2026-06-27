# Creative Moderation Queue & AV Production Readiness (44.4)

**Status:** ✅ Complete
**Date:** 2026-06-16

## Scope

Full manual moderation workflow for creatives: queue, statuses, maker-checker, rework, AV readiness, policy guards.

## Moderation Statuses

| Статус | Бизнес-формулировка | Описание |
|--------|---------------------|----------|
| `draft` | Черновик | Загружен, не отправлен на проверку |
| `pending_review` | Ожидает проверки | Отправлен, ждёт модератора |
| `in_review` | На проверке | Взят в работу |
| `manual_review` | Ручная проверка | Требуется ручная модерация |
| `approved` | Одобрен | Можно использовать в кампании |
| `rejected` | Отклонён | Не прошёл модерацию |
| `validation_failed` | Ошибка проверки | Не прошёл автоматическую валидацию |
| `archived` | Архив | Выведен из оборота |

## Moderation Actions

| Действие | Endpoint | Описание |
|----------|----------|----------|
| Отправить на проверку | `POST /creatives/{code}/submit-review` | draft/pending_review → in_review |
| Одобрить | `POST /creatives/{code}/approve` | in_review/pending_review → approved |
| Отклонить | `POST /creatives/{code}/reject` | in_review/pending_review → rejected |
| Вернуть на доработку | `POST /creatives/{code}/return-for-rework` | → draft + comment |
| Архивировать | `POST /creatives/{code}/archive` | → archived |

### Maker-Checker

Создатель креатива не может сам одобрить свой креатив — только другой сотрудник с правом `media.approve`. При попытке самосогласования: 400 + «Нельзя согласовать собственный креатив».

### Audit Trail

Каждое действие модерации пишется в audit:
- `creative.submit_review`
- `creative.approve` (включая `av_warning: true/false`)
- `creative.reject`
- `creative.return_for_rework`
- `creative.archive`

## Moderation Queue

`GET /api/creatives/moderation-queue` — возвращает все креативы в статусах `pending_review`, `in_review`, `manual_review` с метаданными, именем автора и флагом `can_use_in_campaign`.

Portal: `/creatives/moderation/queue`

## AV Production Readiness

`GET /api/admin/av-readiness` (требуется `admin.system`) — проверяет:
- Доступность ClamAV (через `create_av_scanner()`)
- Статус: `ready` / `not_configured` / `unavailable` / `error`
- `production_ready: true/false`
- Бизнес-сообщение на русском

### Сообщения в UI

| Статус | Сообщение |
|--------|-----------|
| `not_configured` | Проверка безопасности файлов ещё не настроена |
| `ready` | Проверка безопасности файлов работает |
| `unavailable` | Проверка безопасности файлов временно недоступна |
| `error` | Ошибка проверки безопасности |

Всегда присутствует: «Промышленный режим включать нельзя» (если `!production_ready`).

## Creative Detail Page

`/creatives/{creative_code}` — карточка креатива:
- Предпросмотр (изображение или 🎬/🖼️)
- Формат, размер, разрешение, длительность
- Статус модерации
- Статус проверки безопасности
- Профиль экрана: 768×1024
- Причина возврата (если есть)
- «Можно ли использовать в кампании» ✅/❌
- Кнопки действий (отправить, одобрить, отклонить, вернуть на доработку, архивировать)
- AV warning banner (пилотный режим)

## Policy Guards

| Режим | AV gate | Maker-checker | Manual approval |
|-------|---------|---------------|-----------------|
| `pilot_dev` | Warning + audit | ✅ | ✅ Разрешена |
| `production` | Block без clean | ✅ | ❌ Запрещена без clean |

## .mov Guard

- `.mov` НЕ входит в `ALLOWED_UPLOAD_MIME_TYPES` (только jpg, jpeg, png, gif, mp4, webm)
- `ALLOWED_CONTAINERS` (внутренний ffprobe) включает `mov` для mp4/mov family — это нормально для парсинга
- Пользователь НЕ может загрузить `.mov` файл

## Tests

| Слой | Файл | Тестов |
|------|------|--------|
| Backend | `test_creative_moderation_444.py` | 17 |
| Portal | обновлены существующие | 683/0 |

## Regression

| Слой | Passed | Failed |
|------|--------|--------|
| Backend | 767 | 0 |
| Portal | 683 | 0 |

## Production AV NOT enabled

- `av_policy_mode: pilot_dev`
- `require_av_clean_for_publication: false`
- Fake AV pass запрещён
- Production AV включается отдельным решением
