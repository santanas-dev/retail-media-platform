# One-KSO E2E Dry Run Readiness Gate

> **Статус:** 📋 Readiness Gate (38.3)
> **Дата:** 2026-06-24
> **Назначение:** Подготовить безопасный план реального end-to-end dry run на test KSO.
> **ВАЖНО:** Этот документ — readiness gate, НЕ разрешение на запуск.
> Физический запуск Phase D требует отдельного explicit manual approval.
>
> **НЕ:** запускать physical run, создавать X11 окна, менять КСО, читать чеки/БД УКМ5.

---

## 1. Scope

Этот документ определяет готовность к controlled one-KSO E2E dry run:

- **Целевая цепочка:** portal/backend → campaign → placement → manifest → sidecar fetch → media cache → X11 guarded runner → PoP JSONL → sidecar upload → backend ingest → portal report
- **Целевое устройство:** test KSO 192.168.110.223 (Sherman-J 5.1, УКМ5, Chromium kiosk 768×1024)
- **Режим:** read-only audit + однократный временный dry run (не production, не fleet)

---

## 2. Что уже доказано

### 2.1 Dev-only (без КСО, без X11, без Chromium)

| # | Что доказано | Шаг | Доказательство |
|---|---|---|---|
| D1 | Backend manifest generation + publication | 37.7–37.8 | Backend tests 169+ |
| D2 | Sidecar manifest fetch + device gateway | 37.9 | Sidecar tests |
| D3 | Backend PoP ingest + correlation chain | 37.10 | Backend tests |
| D4 | Portal PoP report + creative_code filter | 37.11 | Portal tests |
| D5 | Portrait overlay profile design | 38.0.5–38.0.7 | 71+59 tests |
| D6 | Kill-switch contract + integration | 38.0.8 | 41 tests |
| D7 | State observer contract + forbidden fields | 38.0.9 | 114 tests |
| D8 | Backend creative_code preserved through player chain | 38.2.1 | 17 tests |
| D9 | Sidecar media cache bridge | 38.2.2 | 59 tests |
| D10 | PoP event queue bridge (screensaver → sidecar) | 38.2.3 | 44 tests |
| D11 | Dev E2E PoP validation (9-step chain) | 38.2.4 | 31 tests |
| D12 | Backend PoP ingest + portal integration | 38.2.5 | 18 tests |
| D13 | Backend integration E2E with test DB (SQLite) | 38.2.6 | 32 tests |
| D14 | Full dev E2E: player → sidecar → backend → report | 38.2.7 | 19 tests |
| D15 | Regression baseline stable | все | **4855/4855** green |

### 2.2 Physical KSO (на устройстве 192.168.110.223)

| # | Что доказано | Шаг | Доказательство |
|---|---|---|---|
| P1 | SSH доступ, УКМ5 active, Chromium 114 kiosk | 38.1 Phase 0 | Physical audit |
| P2 | Smoke 6/6 на Python 3.6.9 (idle/ks/unknown/stale/payment/busy-error-offline) | 38.1 Phase 1 | Standalone скрипт, screenshots |
| P3 | X11 click-through proof: окно создаётся, не крадёт фокус | 38.1.8 | Physical screenshots |
| P4 | Guarded physical run: fullscreen 768×1024 overlay confirmed | 38.1.10 | 100% красных пикселей, visual proof |
| P5 | Negative A: kill-switch active → hidden | 38.1.10 | Physical proof |
| P6 | Negative B: state=payment → hidden | 38.1.10 | Physical proof |
| P7 | Negative C: post-rollback → UKM5 restored | 38.1.10 | Physical proof, 90.8% gray match |
| P8 | Rollback focus restore implemented (code) | 38.1.11.1 | +14 tests, `restore_focus()` |

### 2.3 НЕ доказано на физической КСО

| # | Что | Причина |
|---|---|---|
| N1 | X11 overlay с реальным creative (не сплошной цвет) | Не запускалось |
| N2 | Sidecar fetch manifest от реального backend | Не запускалось |
| N3 | Media cache с реальным creative | Не запускалось |
| N4 | PoP JSONL от реального playback | Не запускалось |
| N5 | Sidecar upload PoP в backend | Не запускалось |
| N6 | Portal report по реальному событию | Не запускалось |
| N7 | HW Scanner E2E | Сканер отсутствовал, postponed |
| N8 | Focus restore physical verification | Не запускалось (со scanner retest) |

---

## 3. Оставшиеся блокеры

### 3.1 Технические блокеры

| # | Блокер | Статус | Что нужно |
|---|---|---|---|
| B1 | Backend НЕ развёрнут (нет доступного URL) | **P0** | Backend URL + health check |
| B2 | Device НЕ зарегистрирован в test backend | **P0** | KsoDevice + device_code |
| B3 | Creative НЕ загружен в backend | **P0** | Synthetic creative через portal/API |
| B4 | Campaign + placement НЕ созданы | **P0** | Campaign + KsoPlacement для test KSO |
| B5 | Manifest НЕ опубликован для test KSO | **P0** | GeneratedManifest status=published |
| B6 | Sidecar НЕ настроен на test backend | **P0** | Sidecar config: backend URL, device_code |
| B7 | Media cache пуст | **P0** | Sidecar download creative в media/current/ |
| B8 | HW Scanner недоступен | **P1** | Физический сканер (scanner E2E postponed) |
| B9 | Focus restore НЕ проверен физически | **P1** | Проверить вместе с Phase D |

### 3.2 Approval-блокеры

| # | Блокер | Кто |
|---|---|---|
| A1 | Explicit manual approval Phase D (physical window) | Сергей Пащенко |
| A2 | Подтверждение: оператор смотрит на экран во время теста | Оператор |
| A3 | Подтверждение: время окна теста (10–30 sec) | Оператор/Сергей |
| A4 | Подтверждение: нет покупателей/транзакций во время теста | Оператор |

---

## 4. Данные, необходимые от оператора

Эти данные НЕ коммитятся, НЕ пишутся в docs/chat в открытом виде:

| # | Данные | Назначение | Где хранить |
|---|---|---|---|
| D1 | Backend base URL | Sidecar fetch + PoP upload | `.env` на КСО, НЕ в repo |
| D2 | device_code test KSO | Device registry + manifest + PoP | `.env` на КСО |
| D3 | Device secret / token | Sidecar auth | `.env` на КСО, НИКОГДА в чат/docs |
| D4 | Путь установки sidecar/player на КСО | Запуск команд | Известен (инфра) |
| D5 | Время окна теста | Когда можно перекрыть экран на 10–30s | Согласовать |
| D6 | Кто смотрит экран | Visual verification | Оператор |
| D7 | Наличие физического сканера | Scanner E2E | Если нет — postponed |

**Категорически запрещено:**
- Писать device_secret/token в chat, docs, commit messages, test fixtures
- Сохранять backend URL в репозитории
- Логировать barcode/scanner/key payload/чековые данные

---

## 5. План dry run (фазы)

### Phase A — Backend Readiness (без КСО)

**Команды/проверки (выполняет оператор или Hermes через SSH/API):**

1. Backend health: `GET /health` → 200
2. Backend имеет synthetic creative: `GET /api/creatives` → creative со статусом active
3. Campaign создана: `GET /api/campaigns` → campaign со статусом active
4. KsoPlacement создан: placement_code → campaign_code + creative_code + device_code
5. KsoDevice зарегистрирован: device_code в `kso_devices`
6. GeneratedManifest published: status=published, содержит `creativeCode` в items
7. Manifest items: каждый item имеет `mediaRef`, `slotOrder`, `contentType`
8. Без forbidden fields: manifest_body_json без barcode/scanner/receipt/payment/fiscal/PII

**Pass criteria:**
- Health OK
- Published manifest exists для test KSO device_code
- Manifest содержит ≥1 item с creativeCode и mediaRef
- Manifest_body_json: 0 forbidden keys, 0 forbidden values

### Phase B — Sidecar Readiness (на КСО, без X11)

**Команды (на КСО, через SSH):**

1. Sidecar fetch manifest: `hermes-sidecar fetch` или прямой вызов
2. Проверить `current_manifest.json` в sidecar root
3. Media cache: `hermes-sidecar media status` → все mediaRef присутствуют
4. Проверить `media/current/` — файлы на месте, не symlinks
5. Sidecar logs: 0 forbidden substrings (token/secret/backend_url/barcode/scanner)
6. State adapter: `state.json` содержит `state: idle`
7. Kill-switch: `/run/verny/kso/kill_switch` НЕ существует (или содержит `active: false`)

**Pass criteria:**
- Manifest fetched, creative_code в каждом item
- Media cache: все файлы присутствуют (items_total == items_cached)
- Logs: 0 forbidden substrings
- State: idle, kill-switch inactive
- 0 receipt/payment/fiscal/PII данных в любом файле на КСО

**Запрещено:**
- Читать БД УКМ5 (MySQL)
- Читать чеки/оплаты/фискальные данные
- Менять конфигурацию УКМ5

### Phase C — Runner Dry-Run (на КСО, без X11 окна)

**Команды (на КСО, через SSH):**

1. Запустить X11 guarded runner в dry-run режиме (`--dry-run` или preflight check)
2. Проверить: state=idle, kill-switch=inactive → visibility decision = VISIBLE
3. Проверить: media_available=True для всех creative
4. Проверить: creative_code present в playlist
5. Проверить: ScreensaverCreativePayload валиден
6. Проверить: build_screensaver_pop_record() возвращает built=True
7. **НЕ создавать X11 окно** (dry-run только)

**Pass criteria:**
- Preflight: все checks green
- Visibility decision: VISIBLE (не hidden_kill_switch, не hidden_state)
- Creative: valid, media available
- PoP record: built, creative_code preserved
- **X11 окно НЕ создано** (dry-run mode)

### Phase D — Controlled Physical Window (⛔ REQUIRES EXPLICIT APPROVAL)

**⛔ Эта фаза ЗАПРЕЩЕНА без отдельного explicit manual approval.**

**Pre-conditions (перед запуском):**
- [ ] Phase A: backend health OK, manifest published
- [ ] Phase B: sidecar ready, media cache complete, state idle
- [ ] Phase C: dry-run preflight green
- [ ] Explicit approval от Сергея Пащенко получен
- [ ] Оператор смотрит на экран КСО
- [ ] Нет активных покупателей/транзакций
- [ ] Время окна согласовано (10–30 sec)

**Команды (на КСО, через SSH):**

1. Запустить X11 guarded runner на 10–30 sec с реальным creative
2. Оператор подтверждает: creative виден поверх УКМ5
3. Оператор подтверждает: creative исчез через ≤500ms после изменения state
4. После rollback: проверить `_NET_ACTIVE_WINDOW` → УКМ5 Chromium
5. После rollback: проверить `mint.service` active
6. Проверить: lockfile удалён
7. Сделать скриншот (scrot) ДО и ПОСЛЕ overlay
8. Проверить: временные файлы (скрипт, lockfile) удалены

**Stop criteria (немедленное прекращение, если):**

| # | Критерий | Действие |
|---|---|---|
| S1 | УКМ5 focus stolen (active_window ≠ Chromium PID) | STOP, rollback |
| S2 | Chromium PID изменился | STOP, rollback |
| S3 | `mint.service` not active | STOP, rollback |
| S4 | RAM < 500 MB free | STOP, rollback |
| S5 | CPU > 90% sustained | STOP, rollback |
| S6 | SSH/VNC lost | STOP (если возможно), rollback |
| S7 | Overlay не исчезает через 5s после state change | STOP, manual kill |
| S8 | Появились чековые/платёжные/фискальные данные | STOP, rollback |
| S9 | Требуется читать БД УКМ5 | STOP, НЕ читать |

**Скриншоты:**
- Сохранить scrot ДО overlay (baseline УКМ5)
- Сохранить scrot ВО ВРЕМЯ overlay (creative proof)
- Сохранить scrot ПОСЛЕ rollback (restoration proof)
- **НЕ сохранять скриншоты с чеками/персональными данными**

### Phase E — PoP + Report Verification

**После Phase D (или независимо, если Phase D postponed):**

1. Sidecar читает `pop/pending/player_events.jsonl`
2. Sidecar классифицирует событие → CLASS_ELIGIBLE
3. Sidecar отправляет PoP в backend (если backend доступен)
4. Backend принимает событие → status=accepted
5. Portal report: `GET /api/proof-of-play/test-kso?creative_code=...` → событие найдено
6. Проверить creative_code, device_code, campaign_code, placement_code в ответе
7. Проверить: 0 forbidden fields в report response
8. Проверить: 0 raw UUIDs в ответе

**Pass criteria:**
- PoP JSONL создан (event_status=completed)
- Backend ingest: accepted, creative_code matched
- Portal report: событие найдено по creative_code
- Response: 0 forbidden keys, 0 forbidden values

---

## 6. Stop Criteria (для любой фазы)

| # | Критерий | Действие |
|---|---|---|
| S1 | УКМ5 focus stolen | STOP, rollback немедленно |
| S2 | Active window не УКМ5 | STOP, rollback |
| S3 | UKM5 Chromium PID changed | STOP, rollback |
| S4 | `mint.service` not active | STOP, rollback |
| S5 | RAM < 500 MB | STOP, rollback |
| S6 | CPU > 90% sustained | STOP, rollback |
| S7 | VNC/SSH lost | STOP, rollback |
| S8 | Visible overlay не исчезает | STOP, manual kill, rollback |
| S9 | PoP содержит forbidden fields | STOP, не отправлять в backend |
| S10 | Появляются чековые/платёжные/фискальные/PII данные | STOP, не сохранять, не логировать |
| S11 | Требуется читать БД УКМ5/чек/оплату | STOP, НЕ читать |

---

## 7. Rollback Procedure

**Targeted rollback — только своё, никогда не трогать систему:**

1. Активировать kill-switch: `echo '{"active":true,"reason":"rollback"}' > /run/verny/kso/kill_switch`
2. Остановить ТОЛЬКО свой runner/sidecar процесс (если запущен тестом)
3. Удалить lockfile: `rm -f /run/verny/kso/x11_screensaver.lock`
4. Восстановить фокус УКМ5: `xdotool windowactivate $(xdotool search --class chromium | head -1)`
5. Проверить active window → УКМ5 Chromium
6. Проверить `mint.service` active
7. Удалить временные файлы теста (скрипты, lockfile, temp креативы)

**ЗАПРЕЩЕНО при rollback:**
- `pkill chromium` / `killall chromium`
- `systemctl restart mint` / `systemctl stop mysql` / `systemctl restart redis`
- `reboot` / `shutdown`
- Менять `.profile`, `.xinitrc`, `index.html`, `autostart`
- Менять openbox config

---

## 8. Артефакты

### Можно сохранять

| Артефакт | Куда | Примечание |
|---|---|---|
| Скриншоты (без PII) | local, НЕ в repo | Baseline, overlay, post-rollback |
| Run result (ScreensaverRunResult safe fields) | local | Без forbidden |
| PoP report screenshot | local | Без forbidden |
| Log output (отфильтрованный) | local | Без token/secret/backend_url |

### НЕЛЬЗЯ сохранять

| Артефакт | Почему |
|---|---|
| Скриншоты с чеками/персональными данными | PII |
| Backend URL, device_secret, tokens | Secrets |
| PoP JSONL с barcode/scanner/receipt | Forbidden fields |
| Любые данные из БД УКМ5 | Production система |
| Чеки, оплаты, фискальные данные | PII / compliance |
| Barcode / scanner input / key payload | PII |

---

## 9. Security Constraints (на всех фазах)

- ❌ НЕ читать БД УКМ5 (MySQL)
- ❌ НЕ читать чеки/оплаты/фискальные/персональные данные
- ❌ НЕ логировать barcode/key payload/scanner input
- ❌ НЕ использовать реальные секреты в docs/tests
- ❌ НЕ коммитить backend URL/tokens/device_secret/passwords
- ❌ НЕ менять УКМ5, openbox, systemd, .profile, xinitrc, index.html
- ❌ НЕ делать autostart/systemd/fleet
- ❌ НЕ запускать Chromium (runner НЕ запускает Chromium)
- ✅ Все synthetic test data
- ✅ Read-only где возможно
- ✅ Всегда иметь rollback path

---

## 10. Readiness Checklist (перед любым физическим запуском)

- [ ] Backend health OK
- [ ] Published manifest exists для test KSO
- [ ] Manifest содержит creativeCode + mediaRef
- [ ] Manifest_body_json: 0 forbidden fields
- [ ] Sidecar config: backend URL + device_code (НЕ в repo)
- [ ] Sidecar может fetch manifest
- [ ] Media cache содержит все creative файлы
- [ ] State adapter: state.json = idle
- [ ] Kill-switch: inactive или отсутствует
- [ ] X11 guarded runner dry-run preflight green
- [ ] Creative valid (ScreensaverCreativePayload)
- [ ] PoP bridge: built=True, creative_code preserved
- [ ] Phase A–C все green
- [ ] Explicit manual approval получен (для Phase D)
- [ ] Оператор смотрит на экран (для Phase D)
- [ ] Rollback path известен и проверен
- [ ] Stop criteria известны оператору

---

## 11. Что остаётся postponed

| # | Задача | Статус | Когда |
|---|---|---|---|
| 1 | HW Scanner E2E physical validation | ⚠️ POSTPONED | Когда появится сканер |
| 2 | Focus restore physical verification | ⚠️ POSTPONED | Вместе со scanner retest |
| 3 | Physical run Phase D | ⛔ REQUIRES APPROVAL | После Phase A+B+C green + explicit approval |
| 4 | Fleet rollout (3–5 КСО) | ⛔ FUTURE | После successful one-KSO dry run |

---

## 12. Step 38.5 — Seed + Publication Readiness (2026-06-25)

### 12.1 Seed Service (`POST /api/test-kso/seed`)

Создаёт полную синтетическую цепочку для one-KSO E2E dry run:

```
User → Branch → Cluster → Store → KsoDevice →
Campaign → Creative (+ CreativeVersion) → CampaignCreative →
KsoPlacement → GeneratedManifest (published)
```

**Idempotent:** повторный вызов с теми же `_code` не создаёт дубликаты.
**Safe:** возвращает `SeedSummary` без UUID, без secrets, без path/URL.

### 12.2 Расширенный Readiness Status

Добавлены поля:
- `device_status`, `campaign_status`, `creative_status`, `placement_status`
- `creative_ready`, `creative_content_type`
- `campaign_creative_linked`
- `publication_exists`, `publication_status`
- `manifest_generated_at`, `manifest_published_at`
- `manifest_status`
- `pop_report_ready`
- `remaining_steps` — человекочитаемый список «что осталось сделать»

### 12.3 Portal /readiness Groups

Страница `/readiness` переработана в группы:
1. 🖥️ Backend
2. 📱 Device
3. 📋 Campaign · Creative · Placement
4. 📦 Publication · Manifest
5. 🔧 Sidecar · Media Cache
6. 📊 PoP · Report
7. ⛔ Physical Phase D Gate

Показаны все статусы, timestamps, «Что осталось сделать». Никаких destructive buttons.

### 12.4 Тесты

- Backend: 292 теста (+16: 8 seed + 8 expanded readiness)
- Portal: 424 теста (+17: readiness page groups, safety, forbidden checks)
- Forbidden fields audit: чисто

### 12.5 Live Blockers (остаются)

| Blocker | Статус |
|---|---|
| Sidecar config на КСО | ⚠️ required |
| Media cache на КСО | ⚠️ required |
| Phase D manual approval | ⛔ blocked |
| Physical run/X11/Chromium | ⛔ disabled |
|| Backend URL в sidecar | ⚠️ не в коде (только field hint) |

## 13. Step 38.6 — Live Config Checklist + Sidecar Config Readiness (2026-06-25)

### 13.1 Config Checklist

Определён полный список полей sidecar-конфигурации для one-KSO E2E dry run:

**Обязательные (4):** `backend_base_url`, `device_code`, `device_secret`, `agent_root`
**Опциональные (8):** `manifest_poll_interval_sec`, `media_cache_path`, `pop_queue_path`,
`pop_upload_endpoint`, `state_file_path`, `kill_switch_path`, `runner_mode`, `display_screen`

Все поля заполняются оператором вручную. Никакие значения не возвращаются в readiness endpoint.

### 13.2 Readiness Status расширен

- `sidecar_config_ready` (bool) — всегда false до подтверждения оператора
- `sidecar_config_required_fields` (list[str]) — имена обязательных полей
- `sidecar_config_missing_fields` (list[str]) — какие обязательные поля не настроены
- `sidecar_config_checklist` (list[SidecarConfigField]) — полный checklist:
  - `name`, `required`, `present`, `filled_by`, `description`
  - **Никаких значений!** Только имена полей и статус.

### 13.3 Portal /readiness

- Выделенная секция «Sidecar Config Checklist» с таблицей всех 12 полей
- Field: имя + описание (visible)
- Required: ✅/— (visible)
- Present: ✅/❌ (visible — всегда ❌ для required полей)
- Filled By: "operator" (visible — всегда)
- **Значения:** НЕ показываются. Специальное предупреждение внизу таблицы.

### 13.4 Docs

- `docs/audit/test-kso-live-config-checklist.md` — полный checklist для оператора
- Обновлены: `one-kso-e2e-dry-run-readiness-gate.md`, `one-kso-pilot-readiness-plan.md`, `technical-debt-next-actions.md`

### 13.5 Safety

- Конфиг поля — только имена, без значений
- `backend_base_url` не возвращается (только как field name)
- `device_secret` не возвращается (только как field name)
- Никаких token/path/URL в JSON ответе
- Phase D всё ещё blocked

## 14. Step 38.7 — Live Backend Seed Runbook + Operator Preflight (2026-06-25)

### 14.1 Runbook

`docs/audit/test-kso-live-backend-seed-runbook.md` — полный операторский runbook:

- **Phase A:** Backend readiness — seed, verify manifest, Phase D gate check
- **Phase B:** Sidecar config — заполнение на КСО, проверка без вывода значений
- **Phase C:** Dry preflight — manifest sync, media cache, PoP, kill-switch checklist

Placeholders: `<TEST_BACKEND_BASE_URL>`, `<TEST_KSO_DEVICE_CODE>`, `<DEVICE_SECRET_VALUE>`, `<AGENT_ROOT>` — без реальных значений.

### 14.2 Backend

- `required_operator_steps` — 12 шагов Phases A/B/C в readiness ответе
- Safe: только имена действий, без URL/secrets/tokens

### 14.3 Portal

- Секция «Operator Preflight (Phase A–C)» с пошаговым guidance
- 4 подсказки: config, seed, media cache, Phase D
- Никаких кнопок: «запуск X11», «deploy», «SSH», «restart»

### 14.4 Safety

- Runbook: placeholders, не реальные URL/secrets
- Backend: `required_operator_steps` — только safe action names
- Portal: guidance hints без destructive buttons
- Phase D: ⛔ blocked

## 15. Step 38.8 — Backend-Only Phase A Live Readiness Check (2026-06-26)

### 15.1 Live Execution

Все 4 эндпоинта вызваны против живого backend (`<CONFIGURED>`, localhost dev):
- `/health` → `{"status":"ok","db":"connected"}`
- `POST /api/test-kso/seed` → идемпотентен, `was_already_seeded: true`
- `GET /api/test-kso/readiness?device_code=test-dev-seed` → `overall_ready: false`
- Portal `/readiness` → 8 секций + Phase D Gate

### 15.2 Исправление контракта readiness

**Проблема:** `overall_ready` возвращал `true`, игнорируя `sidecar_config_ready: false` и `media_cache_ready: false`.

**Исправлено:** `overall_ready` теперь требует **оба** `sidecar_config_ready=true` AND `media_cache_ready=true`.

### 15.3 Результат

Backend prerequisites (device, campaign, creative, placement, manifest, creativeCode, mediaRef, publication) — ✅ все зелёные.

Но `overall_ready: false` из-за:
- `sidecar_config_ready: false` (4 обязательных поля не заполнены)
- `media_cache_ready: false` (1 файл не закеширован)

Live blockers: sidecar config (Phase B), media cache (Phase C), manual approval (Phase D).

### 15.4 Result Artifact

`docs/audit/test-kso-phase-a-backend-readiness-result.md` — полный отчёт, безопасный (URL не указан, secrets отсутствуют).

## 16. Step 38.9 — Phase B Sidecar Config Preparation (2026-06-26)

### 16.1 Config Template

`apps/kso_sidecar_agent/config/agent_config.json.example` — безопасный шаблон:
- `backend_base_url: <TEST_BACKEND_BASE_URL>`
- `device_code: <TEST_KSO_DEVICE_CODE>`
- `tls_verify`, `request_timeout_sec`, `local_interface_version`

Заполненный файл (`agent_config.json`) защищён `.gitignore`.

### 16.2 Config Validation

`local_config.validate_no_placeholders()` — проверка без вывода значений:
- `filled: bool` — все плейсхолдеры заменены?
- `placeholder_fields: list[str]` — какие поля ещё шаблонные
- `all_required_present: bool` — ready для Phase B?

`config_status()` теперь возвращает `has_placeholders` и `placeholder_fields`.

### 16.3 Gitignore

Защищены: `agent_config.json`, `device_secret.dev`, `*_filled.json`, `agent-root/`, `kso-agent-root/`, `test-agent-root/`.

### 16.4 Readiness

`sidecar_config_ready` остаётся `false` — backend не может проверить локальный config.
Только `validate_no_placeholders()` на КСО определяет реальную готовность.

### 16.5 Documentation

`test-kso-sidecar-config-preparation.md` — полный анализ config mechanisms, template, operator checklist (Phase B).
