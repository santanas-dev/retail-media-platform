# Deviation Register — 44.0

Осознанные отклонения от ТЗ v2.5, оформленные как ADR (Architecture Decision Records).

---

## DEV-001: Server-side HTML вместо React + TypeScript

**Пункт ТЗ:** 4.7 — React + TypeScript frontend для портала

**Статус:** ⚠️ DEVIATION (accepted for v1)

**Решение:** Портал реализован на server-side HTML/CSS/Jinja2 без JavaScript.

**Обоснование:**
- Security-first подход: отсутствие JS исключает XSS, CDN supply-chain атаки, localStorage token theft
- Простота аудита: любой аудитор может проверить HTML-вывод без динамического анализа
- Совместимость с КСО: Chromium на КСО не требует JS-фреймворков для мониторинга
- Нулевая зависимость от внешних CDN/библиотек

**Риски:**
- Ограниченная интерактивность (нет drag-and-drop, real-time обновлений)
- Меньше визуальных возможностей для отчётов (графики)
- Не соответствует современным ожиданиям SaaS-продуктов

**Mitigation:**
- Все операции доступны через server-side POST-формы
- Pipeline и workflow визуализированы через CSS
- Готовность к переходу на React в v2, если потребуется

**Target:** v1 KSO pilot и production. Пересмотр при переходе к v2 multichannel.

---

## DEV-002: 768×1024 portrait вместо Full HD

**Пункт ТЗ:** 2.1, 8.4 — КСО экраны Full HD (1920×1080), ad zone 1440×1080 слева

**Статус:** ⚠️ DEVIATION (physical environment constraint)

**Решение:** Test KSO имеет физический экран 768×1024 portrait.

**Обоснование:**
- Это физическое ограничение доступного тестового оборудования
- Код плеера поддерживает обе геометрии (конфигурируется)
- Creative QA проверяет 768×1024 для текущего этапа

**Риски:**
- Креативы, оптимизированные под 768×1024, могут некорректно выглядеть на 1920×1080
- Ad zone positioning отличается (1440×1080 left vs full portrait)

**Mitigation:**
- Player поддерживает display surface configuration
- При переходе на Full HD: обновить creative QA limits, перевалидировать креативы
- Задокументировать target profile в pilot runbook

**Target:** v1 KSO pilot (768×1024). v1 KSO production — target Full HD 1920×1080 с ad zone 1440×1080.

---

## DEV-003: Монолит FastAPI вместо микросервисов

**Пункт ТЗ:** 4.1 — Микросервисная архитектура

**Статус:** ⚠️ DEVIATION (accepted for v1)

**Обоснование:**
- 16 доменов разделены на уровне сервисов (service layer isolation)
- Общая кодовая база упрощает деплой и тестирование для пилота (≤100 КСО)
- При необходимости домены могут быть выделены в отдельные сервисы

**Риски:**
- Single point of failure
- Сложнее масштабировать независимо

**Mitigation:**
- Домены изолированы: сервисы не пересекаются напрямую
- Готовность к разделению при v2

**Target:** v1. Разделение на микросервисы — v2.

---

## DEV-004: Мультиканальность отложена

**Пункт ТЗ:** 17.1, 17.2 — Многоканальная платформа (KSO, Android TV, LED, ESL, Mobile)

**Статус:** 📅 DEFERRED

**Обоснование:**
- KSO — первый и приоритетный канал
- Channel/DeviceType модель заложена в БД для будущего расширения
- KSO adapter реализован как reference implementation

**Target:** v2 multichannel.

---

## DEV-005: AD/SSO/MFA не реализованы

**Пункт ТЗ:** 5.6 — Корпоративная аутентификация

**Статус:** 📅 DEFERRED

**Обоснование:**
- Для v1 KSO pilot достаточно локальной аутентификации
- 8 ролей RBAC + 47 permissions покрывают все сценарии
- Локальный логин: bcrypt-хэши, httpOnly cookies

**Target:** v1 KSO production (для enterprise-клиентов).

---

## DEV-006: Отсутствие production infrastructure (мониторинг, backup, CI/CD, очереди)

**Пункты ТЗ:** 16.2–16.6

**Статус:** 📅 DEFERRED

**Обоснование:**
- Docker Compose достаточен для разработки и пилота
- Production-инфраструктура требует отдельного этапа
- Нагрузочное тестирование не имеет смысла до физического пилота

**Target:** v1 KSO production.

---

## Сводка отклонений

| ID | Категория | Статус | Target |
|---|---|---|---|
| DEV-001 | Frontend (React → HTML) | ⚠️ DEVIATION v1 | v2 пересмотр |
| DEV-002 | Display (768×1024 → Full HD) | ⚠️ DEVIATION v1 pilot | v1 production Full HD |
| DEV-003 | Архитектура (монолит → μ-services) | ⚠️ DEVIATION v1 | v2 |
| DEV-004 | Мультиканальность | 📅 DEFERRED | v2 |
| DEV-005 | AD/SSO/MFA | 📅 DEFERRED | v1 production |
| DEV-006 | Production infra | 📅 DEFERRED | v1 production |
| DEV-007 | AV scanner | ⚠️ DEVIATION v1 pilot | v1 production |

### DEV-007: AV Scanner — pilot/dev mode without real scanner

**Статус:** ⚠️ DEVIATION v1 pilot
**Дата:** 2026-06-16 (44.2.1)
**Target:** v1 production

**Описание:**
В v1 pilot/dev режиме AV сканер не подключён (`scan_status=not_configured`). Креатив может быть одобрен вручную после модерации. В production режиме (`av_policy_mode=production`) публикация без `scan_status=clean` запрещена.

**Обоснование:**
- Реальный AV сканер (ClamAV или аналог) требует отдельной интеграции и тестирования
- Fake AV pass (имитация проверки) запрещён — честный контракт
- Интерфейс `CreativeAVScanner` готов для подключения реального сканера

**Mitigation:**
- Явный `av_policy_mode: pilot_dev` в policy endpoint
- `require_av_clean_for_publication: false` — документировано
- Audit trail для manual approval без AV
- UI: «Проверка безопасности не настроена»
- При переходе в production: установить `av_policy_mode=production`, интегрировать реальный AV сканер
