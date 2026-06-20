# KSO Sidecar Agent — Skeleton

**Статус:** 🏗 Skeleton. Production-код ещё не реализован.

## Что это

KSO Sidecar Agent — будущий production-агент, который будет работать на КСО-терминале рядом с КСО ПО. Он синхронизирует manifest и media с backend, раскладывает их в локальную папку по контракту `docs/kso_local_interface_contract.md`, и отправляет PoP-события и heartbeat'ы.

**Пока это ТОЛЬКО каркас (skeleton).**

## Что сейчас работает

| Команда | Описание |
|---|---|
| `version` | Показать версию |
| `init-local-root` | Создать структуру папок + `agent_status.json` |
| `set-status` | Обновить статус агента (running/stopped/warning/...) |
| `write-config` | Создать/обновить локальный config |
| `config-status` | Проверить валидность config |
| `doctor` | Проверить здоровье папок, статуса и config |
| `secret-store-check` | Проверить состояние dev secret store |
| `secret-store-set` | Записать dev secret (только через stdin) |
|| `secret-store-delete` | Удалить dev secret |
|| `auth-check` | Проверить device auth (только safe summary, без токена) |
|| `runtime-config-status` | Показать здоровье runtime config |
|| `sync-runtime-config` | Полный пайплайн auth→fetch→save runtime config |
|| `heartbeat-once` | Отправить одиночный heartbeat |
|| `manifest-status` | Показать локальный manifest |
|| `sync-manifest` | Sync manifest: auth→fetch→save |
|| `sync-media` | Sync media: auth→download→media/current |
|| `media-cache-status` | Показать локальный media cache |
|| `report-media-cache` | Send media cache report: auth→build payload→POST /media/cache/report |
|| `run-once` | Run one cycle: local readiness preflight (--local-only required) |

## PoP Pickup Design

📝 **Mini-design создан:** `docs/pop_pickup_design.md`. Описывает будущий шаг run-cycle, в котором sidecar забирает локальные player events из `pop/pending/player_events.jsonl`, валидирует, классифицирует по статусу и готовит eligible-события к отправке в backend. Draft-события не являются фактом показа и не отправляются как PoP. Реализация pickup — отдельный шаг.

## PoP Pickup Classifier Core

🔎 **Реализован:** `pop_pickup.py`. Безопасный read-only сканер/классификатор для player events.

### `scan_pending_pop_events(root) -> PopPickupScanResult`

- Читает `pop/pending/player_events.jsonl` построчно
- Валидирует schema + forbidden fields
- Классифицирует: `draft` / `eligible` / `diagnostic` / `quarantine` / `invalid`
- Возвращает только safe агрегаты (counts), без raw events
- Read-only: не удаляет, не перемещает, не отправляет в backend
- Draft-события НЕ являются eligible для backend

**Backend send / rotation / move будут отдельными шагами.**

## PoP Eligible Batch Builder Core

📦 **Реализован:** `pop_batch.py`. Собирает in-memory batch только из eligible-кандидатов.

### `build_pop_eligible_batch(root, max_events=100) -> PopBatchBuildResult`

- Читает `pop/pending/player_events.jsonl`
- Классифицирует каждое событие через pop_pickup
- Включает в batch ТОЛЬКО `eligible` (completed + idle + manifest mapping + media complete)
- Draft/blocked/failed/invalid/quarantine → пропускает
- Read-only: не удаляет, не перемещает, не отправляет в backend

### Когда событие попадает в batch

Только при ВСЕХ условиях:
- `event_status: completed`
- `event_type: would_play`
- `safety_state: idle`
- `selected_order` найден в current manifest
- Media cache complete
- Schema valid, forbidden fields absent

**draft/blocked/failed не являются PoP и не попадают в batch.**

### PopBatchCandidate

Только safe поля (14 полей из ALLOWED_RECORD_KEYS). Без filename, manifest_item_id, sha256, paths, secrets.

## CLI: `pop-batch-preview`

```bash
cd apps/kso_sidecar_agent

# Построить in-memory batch eligible candidates — только агрегаты
python3 -m kso_sidecar_agent.cli pop-batch-preview --root /tmp/kso-agent-root

# С лимитом
python3 -m kso_sidecar_agent.cli pop-batch-preview --root /tmp/kso-agent-root --max-events 50
```

**Важно:** только превью. НЕ отправляет backend, НЕ удаляет/перемещает файлы. Только completed+idle+manifest mapping+media complete события являются кандидатами. Draft/blocked/failed не являются PoP.

### Exit codes

| Код | Значение |
|---|---|
| 0 | Batch preview ok |
| 1 | Warning/error/invalid/quarantine |
| 2 | Invalid CLI args (включая --max-events <= 0) |

## PoP Backend Payload Design

📝 **Mini-design создан:** `docs/pop_backend_payload_design.md`. Описан безопасный backend payload для `POST /device-gateway/pop/events/batch` на основе существующих таблиц `proof_of_play_events` + `proof_of_play_batches`. Payload формируется только из eligible completed событий. Backend payload builder + HTTP sender будут отдельными шагами. Draft/blocked/failed не являются PoP.

## PoP Backend Payload Builder Core

📦 **Реализован:** `pop_payload.py`. Собирает in-memory backend payload из eligible событий с manifest mapping.

### `build_pop_backend_payload(root, max_events=100) -> PopPayloadBuildResult`

- Читает `pop/pending/player_events.jsonl`
- Классифицирует через pop_pickup
- Только CLASS_ELIGIBLE → manifest mapping → PopPayloadEvent
- PopPayloadEnvelope (batch_id + events) — внутренний, repr=False
- PopPayloadBuildResult — только safe aggregates

**Backend send / move / rotation будут отдельными шагами.** Payload body не логируется. manifest_item_id используется только внутри payload и не выводится в safe output.

## CLI: `pop-payload-preview`

```bash
cd apps/kso_sidecar_agent

# Построить in-memory backend payload — только агрегаты
python3 -m kso_sidecar_agent.cli pop-payload-preview --root /tmp/kso-agent-root

# С лимитом
python3 -m kso_sidecar_agent.cli pop-payload-preview --root /tmp/kso-agent-root --max-events 50
```

**Важно:** только превью. НЕ отправляет backend, НЕ делает HTTP, payload body не печатается. Только completed eligible events могут попасть в payload. Draft/blocked/failed не являются PoP.

### Exit codes

| Код | Значение |
|---|---|
| 0 | Payload preview ok |
| 1 | Warning/error/invalid/quarantine |
| 2 | Invalid CLI args (включая --max-events <= 0) |

## CLI: `pop-rotation-plan`

```bash
cd apps/kso_sidecar_agent

# Построить in-memory rotation plan — только безопасные агрегаты
python3 -m kso_sidecar_agent.cli pop-rotation-plan --root /tmp/kso-agent-root

# С лимитом
python3 -m kso_sidecar_agent.cli pop-rotation-plan --root /tmp/kso-agent-root --max-lines 500
```

**Важно:** только preview. НЕ перемещает файлы, НЕ удаляет pending, НЕ создаёт sent/quarantine/dry_run/failed, НЕ делает backend send. Lock используется тот же: `pop/pending/player_events.lock`.

**Без backend confirmation `sent_lines` всегда 0.** Даже если в pending есть completed eligible события, без подтверждённого успеха отправки они остаются в pending.

Destructive rotation будет отдельным шагом.

### Аргументы

| Аргумент | Обязательный | По умолчанию | Описание |
|---|---|---|---|
| `--root` | ✅ | — | Root path |
| `--max-lines` | ❌ | 10000 | Max lines to read (> 0) |

### Exit codes

| Код | Значение |
|---|---|
| 0 | Plan ok |
| 1 | Warning/error/invalid/quarantine/lock_unavailable/plan_limited |
| 2 | Invalid CLI args (--root missing, --max-lines <= 0) |

## PoP Sender Response Classifier Core

🧠 **Реализован:** `pop_sender.py`. Безопасная классификация будущего ответа backend после отправки PoP batch.

### `classify_pop_send_response(http_status, response_json, error_type, elapsed_ms, attempted_events) -> PopSendResult`

- Pure logic — без HTTP, backend send, retry runner, file I/O
- Классифицирует ответ backend: HTTP статус + JSON response body → safe result
- Извлекает только safe count-поля (accepted/duplicate/rejected) из backend response
- Forbidden поля в response → `invalid_response`, pending_should_remain=True
- `pending_should_remain=False` ТОЛЬКО при подтверждённом `processed` или `duplicate_batch`

### Response cases

| Статус/ошибка | send_status | reason | retryable | pending_remain |
|---|---|---|---|---|
| 200 + status=processed | ok | processed | false | **false** |
| 200 + partial (accepted + rejected) | warning | partial_success | false | true |
| 200 + all duplicate (no accepted/rejected) | ok | duplicate_events | false | false |
| 200 + status=duplicate_batch | warning | duplicate_batch | false | false |
| 200 + invalid schema | warning | invalid_response | false | true |
| 400 | error | bad_request | false | true |
| 401 | warning | unauthorized | **true** | true |
| 403 | error | forbidden | false | true |
| 404 | error | not_found | false | true |
| 409 | warning | duplicate_batch | false | **true** |
| 422 | error | validation_error | false | true |
| 429 | warning | rate_limited | **true** | true |
| 5xx | error | server_error | **true** | true |
| network error | error | network_error | **true** | true |
| timeout | error | timeout | **true** | true |
| unknown | error | unknown_response | false | true |

> **🛡 409 Hardening (26.24.1):** 409 Duplicate batch — `pending_should_remain=True` по умолчанию. Backend видел batch_id, но без явного accepted/processed подтверждения pending НЕ удалять. Duplicate-safe removal возможен только если будущий backend response contract явно это подтвердит.

### `PopSendResult`

Safe dataclass: send_status, attempted/accepted/duplicate/rejected_events, http_status, elapsed_ms, retryable, auth_refresh_required, pending_should_remain, reason. Никогда не содержит payload body, raw backend response, IDs, token, backend URL, filename, sha256, paths.

### `format_pop_send_result(result) -> str`

Только safe aggregates. Без raw response/IDs/secrets.

**HTTP sender — отдельный шаг (26.24+).** Rotation/move — отдельный шаг (26.25+). Pending не трогать без confirmed backend success.

## PoP Backend Sender HTTP Core

📡 **Реализован:** `send_pop_payload_batch()` в `pop_sender.py`. Single-attempt HTTP core для отправки in-memory PoP payload в backend.

### `send_pop_payload_batch(http_client, payload_envelope, access_token=None, now=None) -> PopSendResult`

- Принимает существующий `SafeHttpClient`, `PopPayloadEnvelope`, и опциональный access token
- Использует только allowlisted endpoint: `/api/device-gateway/pop/events/batch`
- Single attempt — без retry loop, auth refresh, CLI, run cycle
- Token только in-memory аргумент, не читается из файлов
- При ошибке HTTP/сети → классифицирует через `classify_pop_send_response()`
- При отсутствии payload → `REASON_NO_PAYLOAD`, HTTP не вызывается
- Никогда не логирует: token, Authorization header, payload body, batch_id, manifest_item_id

### Endpoint

`/api/device-gateway/pop/events/batch` — покрыт префиксом `_ALLOWED_PREFIXES` в `http_client.py`.

### Что НЕ делает (будет отдельными шагами)

- ❌ CLI команда (26.25+)
- ❌ Retry loop / auth refresh (26.26+)
- ❌ Run cycle integration (26.27+)
- ❌ File rotation / move (26.28+)
- ❌ Чтение secret/config/token файлов
- ❌ Real backend calls (только fake в тестах)

## PoP Sender Retry Decision Core

🧭 **Реализован:** `pop_sender_retry.py`. Безопасное ядро принятия решения по retry после PopSendResult.

### `decide_pop_send_retry(result, attempt_number, max_attempts, auth_refresh_attempted) -> PopSendRetryDecision`

- Pure logic — без HTTP, sleep, auth refresh, file I/O
- Принимает `PopSendResult` и параметры попытки → возвращает `PopSendRetryDecision`
- Действия: `stop`, `retry`, `refresh_auth_then_retry`

### Правила (в порядке приоритета)

| Условие | action | reason | pending_remain |
|---|---|---|---|
| success (ok, !pending_remain) | stop | success | **false** |
| no_payload | stop | no_payload | true |
| 401 + не было refresh + попытки есть | refresh_auth_then_retry | auth_refresh_required | true |
| 401 + refresh был | stop | auth_refresh_failed | true |
| 409 duplicate_batch | stop | duplicate_batch_pending_remains | true |
| retryable + попытки есть | retry | retryable_error | true |
| retryable + попытки кончились | stop | retry_exhausted | true |
| не-retryable + pending | stop | non_retryable_pending_remains | true |

### `calculate_pop_retry_delay_ms(attempt_number, base_delay_ms=1000, max_delay_ms=30000) -> int`

Exponential backoff без jitter: 1→1000, 2→2000, 3→4000, capped.

### `format_pop_send_retry_decision(decision) -> str`

Только safe aggregates. Без payload/IDs/token/backend URL.

**Retry runner / auth refresh / run cycle — отдельные шаги.** Sleep не выполняется. Pending не трогать без confirmed backend success.

## PoP Sender Retry Runner Core

🔁 **Реализован:** `pop_sender_runner.py`. Orchestration core для отправки PoP payload с retry decisions.

### `run_pop_send_with_retry(http_client, payload_envelope, access_token, refresh_auth_callback, max_attempts) -> PopSendRunResult`

- Принимает готовый envelope, не строит payload самостоятельно
- Цикл: send → classify → retry decision → retry / refresh_auth / stop
- `refresh_auth_callback` — опциональный callable → новый token in-memory (без реального auth client)
- Без sleep/wait, без чтения файлов, без file rotation
- Fake HTTP в тестах, real backend не вызывается

### Сценарии

| Сценарий | attempts_made | run_status | pending_remain |
|---|---|---|---|
| 200 с первой попытки | 1 | ok | false |
| 500 → 200 | 2 | ok | false |
| 429 / network / timeout → 200 | 2 | ok | false |
| 500 все попытки | 3 | error | true |
| 401 → refresh → 200 | 2 | ok | false |
| 401 без callback | 1 | warning | true |
| 400/403/404/422 | 1 | warning | true |
| 409 | 1 | warning | true |

### `format_pop_send_run_result(result) -> str`

Только safe aggregates. Без payload/IDs/token/backend URL.

**CLI / run cycle / rotation — отдельные шаги.** Pending не трогать без confirmed backend success.

## PoP Local Rotation Design

📝 **Mini-design создан:** `docs/pop_local_rotation_design.md`. Спроектирована безопасная локальная rotation/move политика для PoP events после будущей отправки в backend.

### Ключевые правила

- Rotation выполняется **только после backend confirmation** (`run_status=ok`, `pending_should_remain=false`)
- **`pending_should_remain=true` → pending нельзя удалять, перезаписывать, обрезать или перемещать**
- **409 duplicate batch НЕ разрешает удалять pending**
- **Partial success без event-level mapping → pending untouched**
- Atomic rotation: ошибка на любом шаге → pending нетронут
- Lock contract (player ↔ sidecar) предотвращает гонки
- Draft/blocked/failed → `dry_run/`, не `sent/`
- Unsafe/сомнительные → `quarantine/`, не `sent/`
- Retry-exhausted → `failed/` для audit trail

**Реализация rotation — отдельный шаг (26.28+).**

## PoP Pending Lock Core

🔒 **Реализован:** `pop_pending_lock.py`. Безопасный file lock на стороне sidecar для будущей rotation/pickup.

### Lock path

`{root}/pop/pending/player_events.lock` — **тот же lock-файл, что у player writer.**

### API

- `try_acquire_pop_pending_lock(root) -> PopPendingLockResult` — атомарный acquire (`O_CREAT | O_EXCL`), неблокирующий
- `release_pop_pending_lock(lock_result) -> PopPendingLockResult` — удаляет lock, fail-silent
- `pop_pending_lock(lock_result)` — context manager (релиз в `__exit__`)

### Правила

- Lock маркер: `"locked\n"` (без secrets/paths/IDs)
- Если lock занят → `status=skipped, reason=lock_unavailable`
- `release` не бросает исключений
- `PopPendingLockResult` не содержит absolute paths, lock path, token, IDs

**Rotation пока не реализована. Destructive rotation запрещена без lock.**

## PoP Local Rotation Plan Core

🧭 **Реализован:** `pop_rotation_plan.py`. In-memory rotation plan — классифицирует pending события без записи на диск.

### `build_pop_rotation_plan(root, send_run_result=None, max_lines=10000) -> PopRotationPlanResult`

- Берёт lock → читает JSONL → классифицирует → строит план → отпускает lock
- **Никогда не пишет, не перемещает, не удаляет файлы**
- Использует тот же lock: `pop/pending/player_events.lock`

### Планирование по результату отправки

| send_run_result | sent_lines | reason |
|---|---|---|
| `None` | 0 | pending_should_remain |
| `pending_should_remain=true` | 0 | pending_should_remain |
| 409 duplicate | 0 | duplicate_pending_remains |
| `run_status=ok, pending_should_remain=false` | eligible → sent | planned |

### Классификация событий

| Статус | План |
|---|---|
| draft | → dry_run |
| blocked/failed | → dry_run |
| invalid JSON/forbidden | → quarantine |
| eligible (completed+idle+manifest+media) + send ok | → sent |
| eligible + send not ok | → stays pending |

**Destructive rotation пока не реализована.**

### CLI: `pop-rotation-plan`

```bash
cd apps/kso_sidecar_agent
python3 -m kso_sidecar_agent.cli pop-rotation-plan --root /tmp/kso-agent-root
python3 -m kso_sidecar_agent.cli pop-rotation-plan --root /tmp/kso-agent-root --max-lines 500
```

Подробнее см. секцию **CLI: `pop-rotation-plan`**.

## PoP Rotation Atomic File Ops Core

🧱 **Реализован:** `pop_rotation_files.py`. Атомарная запись safe JSONL records в rotation target directories.

### `write_pop_rotation_records_atomic(root, target, records, now=None) -> PopRotationFileWriteResult`

- Принимает только валидированные safe records (list[dict])
- Пишет только в разрешённые target: `sent`, `quarantine`, `dry_run`, `failed`
- Atomic модель: `.tmp` → flush → fsync → `os.replace` → fsync dir
- При любом сбое — tmp удаляется, функция не бросает исключений
- Каждый record проверяется на forbidden keys/values (два уровня вложенности)
- Файлы именуются: `rotation_<YYYYMMDDThhmmssZ>.jsonl`

### Что НЕ делает

- ❌ Не читает pending
- ❌ Не меняет/не удаляет pending
- ❌ Не делает HTTP/backend send
- ❌ Не читает secret/config/token
- ❌ Не читает media bytes
- ❌ Не создаёт backend payload

### PopRotationFileWriteResult

Safe dataclass: status (written|skipped|error), target, records_written, line_size_bytes, reason. Никогда не содержит file paths, tmp paths, filenames, exception text, raw records, IDs, secrets.

### Разрешённые target

| Target | Назначение |
|---|---|
| `sent` | Подтверждённые backend события |
| `quarantine` | Unsafe/schema/mismatch события |
| `dry_run` | Draft/diagnostic события (не PoP) |
| `failed` | Retry-exhausted события |

**Actual rotation apply — отдельный шаг.** Этот модуль только пишет файлы, не оркестрирует rotation.

## PoP Rotation Materializer Core

🧩 **Реализован:** `pop_rotation_materializer.py`. In-memory bucket builder — читает pending под lock, классифицирует, готовит записи для sent/quarantine/dry_run/failed/retained_pending.

### `materialize_pop_rotation_records(root, send_run_result=None, max_lines=10000) -> PopRotationMaterializeResult`

- Берёт lock → читает JSONL → классифицирует (pop_pickup) → распределяет по in-memory buckets → отпускает lock
- **Никогда не пишет, не перемещает, не удаляет файлы**
- **Не вызывает `write_pop_rotation_records_atomic`**
- Использует тот же lock: `pop/pending/player_events.lock`

### Buckets

| Статус события | Bucket | Тип записи |
|---|---|---|
| draft | `_dry_run_records` | sanitized `rotation_dry_run` |
| blocked | `_dry_run_records` | sanitized `rotation_dry_run` |
| failed | `_dry_run_records` | sanitized `rotation_dry_run` |
| invalid JSON / forbidden | `_quarantine_records` | sanitized `rotation_quarantine` |
| completed eligible + send ok | `_sent_records` | original safe event |
| completed eligible + no send / pending_should_remain | `_retained_pending_records` | original safe event |

### Sanitized записи

Quarantine/dry_run/failed записи **никогда не содержат raw JSON**. Формат:
```json
{"schema_version": 1, "record_type": "rotation_quarantine", "reason": "invalid_json", "created_at": "ISO8601", "source": "player_events", "line_number": 3}
```

### PopRotationMaterializeResult

Safe aggregates + internal `_*` buckets (repr=False). Никогда не содержит raw JSON, paths, IDs, secrets.

### Что НЕ делает

- ❌ Не вызывает atomic file writer
- ❌ Не создаёт sent/quarantine/dry_run/failed
- ❌ Не меняет/не удаляет pending
- ❌ Не делает HTTP/backend send
- ❌ Не читает secret/config/token/media bytes

**Actual rotation apply — отдельный шаг.** Материализатор только готовит in-memory данные. Запись на диск делает atomic file writer, оркестрацию — rotation apply.

### Locked Materializer

🔒 **Добавлен:** `materialize_pop_rotation_records_locked(root, lock_result, ...)` — вариант для будущего rotation apply, где lock держится на весь цикл.

- **Не берёт и не освобождает lock** — caller сам управляет lock
- Если `lock_result` отсутствует или `acquired=False` → `warning / lock_required`
- Обычный `materialize_pop_rotation_records()` остаётся удобной обёрткой (acquire → locked → release)

Будущий rotation apply cycle:
```
acquire lock
  → materialize locked (читает, классифицирует)
  → write sent/quarantine/dry_run/failed (atomic writer)
  → rewrite pending (atomic rewrite helper)
release lock
```

## PoP Pending Rewrite Atomic Helper

🧱 **Реализован:** `pop_pending_rewrite.py`. Атомарная перезапись `pop/pending/player_events.jsonl` с новым списком retained pending records.

### `rewrite_pending_pop_events_atomic(root, records, lock_result) -> PopPendingRewriteResult`

- **Требует lock** — caller должен уже держать `PopPendingLockResult` (acquired=True)
- Helper не берёт и не освобождает lock сам
- Atomic модель: `.tmp` → flush → fsync → `os.replace`
- Пустой records допустим — создаёт пустой pending файл
- Каждый record валидируется на forbidden keys/values

### Что НЕ делает

- ❌ Не берёт/не освобождает lock
- ❌ Не читает существующий pending
- ❌ Не создаёт sent/quarantine/dry_run/failed
- ❌ Не делает HTTP/backend send
- ❌ Не читает secret/config/token/media bytes

### PopPendingRewriteResult

Safe dataclass: status (written|skipped|error), records_written, line_size_bytes, reason. Никогда не содержит file paths, lock paths, записи, ID, secrets.

## PoP Local Rotation Apply Core

🔁 **Реализован:** `pop_rotation_apply.py`. Полный цикл rotation под одним lock.

### `apply_pop_rotation_local(root, send_run_result=None, max_lines=10000) -> PopRotationApplyResult`

```
acquire lock
  → materialize_pop_rotation_records_locked()  ← читает + классифицирует
  → write_pop_rotation_records_atomic()         ← sent/quarantine/dry_run/failed
  → rewrite_pending_pop_events_atomic()         ← retained pending
release lock (finally)
```

**Sent bucket только при backend confirmation:** `run_status=ok`, `pending_should_remain=false`.
**409 / pending_should_remain — sent не создаётся, pending нетронут.**

### Правила

| Условие | Поведение |
|---|---|
| Target write failure | Pending untouched, error |
| Pending rewrite failure | Target files могли создаться, pending untouched, error |
| Empty bucket | Пропускается, директория не создаётся |
| Все события ушли из pending | Создаётся пустой `player_events.jsonl` |

### PopRotationApplyResult

Safe aggregate: status, applied, lock_acquired, pending_untouched, target_files_written, pending_rewritten, counts. Без paths/IDs/raw JSON/secrets.

**CLI / run_cycle integration — отдельные шаги.**

### Sent Scope Guard

🛡️ **Реализован:** `PopRotationSentScope` в `pop_rotation_materializer.py`. Ограничивает перенос completed событий в `sent/` только теми, что были в отправленном payload.

**Проблема:** агрегатный `send_run_result.run_status=ok` не гарантирует, что все pending completed события были в отправленном batch. Между send и rotation player мог добавить новые completed.

**Решение:** `PopRotationSentScope` хранит internal `frozenset` line numbers отправленных событий. Completed eligible → sent только если `line_number ∈ sent_scope`.

| Условие | sent_records |
|---|---|
| send ok + scope match | → sent |
| send ok + scope None | 0 (sent_scope_required) |
| send ok + line not in scope | 0 (retained) |
| pending_should_remain / 409 | 0 |
| run_status != ok | 0 |

**Агрегаты в result (без line numbers):** `sent_scope_required`, `sent_scope_lines`, `sent_scope_matched`, `sent_scope_fingerprinted`, `sent_scope_mismatched`.

### Sent Scope Fingerprint Guard

🔐 **Реализован:** двухуровневая защита — `line_number` + `fingerprint` в `PopRotationSentScope`. Между `build_pop_send_package` и будущим `rotation apply` pending может измениться — fingerprinted scope ловит in-place изменения.

**Проблема:** номер строки сам по себе недостаточен. Если между send и rotation строка была перезаписана другим контентом, её нельзя переносить в sent.

**Решение:** при построении send package вычисляется `SHA-256(line)` для каждой eligible строки. При materialization проверяется `line_number ∈ scope AND fingerprint == stored`.

| Условие | sent_records |
|---|---|
| line in scope + fingerprint match | → sent |
| line in scope + fingerprint mismatch | 0 (sent_scope_mismatch) |
| line in scope + legacy scope (no fingerprints) | → sent (backward compat) |
| line not in scope | 0 (retained) |

**Fingerprint:** SHA-256 stripped JSONL line. Internal-only — НЕ печатается, НЕ логируется, НЕ отправляется в backend, НЕ включается в payload.

**`PopRotationSentScope` repr:** `PopRotationSentScope(size=N, fingerprinted)` / `PopRotationSentScope(size=N, line-only)`.

**`build_pop_send_package()` всегда создаёт fingerprinted scope.**
**`run_pop_scoped_send()` сохраняет fingerprinted scope в `_sent_scope`.**

### CLI: `pop-rotation-apply`

```bash
cd apps/kso_sidecar_agent

# Guarded destructive operation — requires confirmation
python3 -m kso_sidecar_agent.cli pop-rotation-apply --root /tmp/kso-agent-root --confirm-local-rotation
```

**Guarded:** без `--confirm-local-rotation` → exit 2, ничего не меняет.
**Без backend confirmation:** `send_run_result=None` → `sent_records=0`, completed eligible остаются в pending.
**Локальные категории всё равно применяются:** draft/blocked/failed → dry_run, invalid/forbidden → quarantine.

### Exit codes

| Код | Условие |
|---|---|
| 0 | Apply ok / no-op |
| 1 | Warning/error: lock unavailable, write/rewrite failed, invalid/limited |
| 2 | `--confirm-local-rotation` missing, `--root` missing, `--max-lines` <= 0 |

---

## PoP Send Package Scope Core

📦 **Реализован:** `pop_send_package.py`. In-memory сборка пакета отправки из ОДНОГО snapshot pending под lock.

### `build_pop_send_package(root, max_lines=10000) -> PopSendPackageResult`

- Берёт lock → читает pending snapshot → классифицирует eligible completed → строит payload (**PopPayloadEnvelope**) + sent scope (**PopRotationSentScope**) → отпускает lock
- **Один snapshot гарантирует:** payload и sent_scope используют одни и те же pending line numbers — нет гонки между build и rotation
- **Не отправляет backend, не делает HTTP, не пишет/удаляет файлы, не вызывает rotation apply**
- Draft/blocked/failed/invalid → не попадают в payload и не попадают в sent scope

### PopSendPackageResult

Safe aggregates: `status`, `package_built`, `lock_acquired`, `pending_lines_read`, `eligible_events`, `payload_events`, `scope_lines`, `reason`.
Внутренние поля (`_payload`, `_sent_scope`) — `repr=False`, никогда не раскрываются.

### PopRotationSentScope

Строится из тех же pending line numbers, что и payload. `frozenset` line numbers — только internal.
`repr`: `PopRotationSentScope(size=N)` — без списка номеров строк.

### Защита от race condition

```
build_pop_send_package (один проход под lock):
  1. snapshot pending
  2. для каждого eligible: build payload event + track line_number
  3. build PopRotationSentScope из tracked line_numbers
  → payload и scope синхронизированы

Будущий sender:
  send(payload) → send_run_result

Будущий rotation apply:
  apply(root, send_run_result, sent_scope=package._sent_scope)
  → sent только для строк, бывших в payload
```

### Безопасность

- ❌ Не делает HTTP/backend send
- ❌ Не пишет/удаляет pending
- ❌ Не создаёт sent/quarantine/dry_run/failed
- ❌ Не вызывает rotation apply
- ❌ Не читает secret/config/token/media bytes
- ❌ Не выводит: raw JSON, payload body, line numbers list, IDs, paths, sha256

### CLI

CLI не добавляется на этом шаге. Модуль вызывается только из будущего sender/run_cycle.

---

## PoP Scoped Send Runner Core

📨 **Реализован:** `pop_scoped_send.py`. Оркестрирует полный цикл: build package → send via retry runner → safe result с sent_scope.

### `run_pop_scoped_send(root, http_client, auth_provider=None, max_lines=10000) -> PopScopedSendResult`

```
Pipeline:
  1. build_pop_send_package(root, max_lines)  → payload + sent_scope
  2. Если нет eligible → safe no-op
  3. run_pop_send_with_retry(http_client, payload, token, auth_cb)
  4. PopScopedSendResult с _send_run_result и _sent_scope (internal)
```

### Ключевые гарантии

- **sent_scope ровно тот, который вернул `build_pop_send_package()`** — без пересканирования pending
- **Pending untouched** — `pending_untouched=True` всегда
- **Rotation НЕ вызывается** — `rotation_applied=False` всегда
- **Backend send через dependency injection** (`http_client`) — тесты только fake
- **Auth через `auth_provider` callable** — без чтения secret/config файлов

### PopScopedSendResult

Safe aggregates: `status`, `send_attempted`, `send_success`, `package_built`, `payload_events`, `scope_lines`, `send_status`, `pending_untouched`, `rotation_applied`, `reason`.
Внутренние поля: `_send_run_result` (repr=False), `_sent_scope` (repr=False) — для будущего rotation apply.

### Send policy

| Условие | send_attempted | send_success |
|---|---|---|
| No pending / draft only / blocked only | false | false |
| Lock unavailable | false | false |
| Limited package | false | false |
| Send ok (run_status=ok, !pending_should_remain) | true | **true** |
| Send failed / retry exhausted | true | false |
| 409 duplicate / pending_should_remain | true | false |

### Будущая интеграция

```python
result = run_pop_scoped_send(root, http_client)
if result.send_success:
    apply_pop_rotation_local(
        root,
        send_run_result=result._send_run_result,
        sent_scope=result._sent_scope,
    )
```

### Безопасность

- ❌ Не вызывает `apply_pop_rotation_local`
- ❌ Не пишет/удаляет pending
- ❌ Не создаёт sent/quarantine/dry_run/failed
- ❌ Не читает secret/config/token из файлов
- ❌ Не читает media bytes
- ❌ Real backend в тестах не вызывается
- ✅ Только fake `FakeHttpClient` в тестах

### CLI

CLI не добавляется на этом шаге.

---

## PoP Backend Sender Design

📝 **Mini-design создан:** `docs/pop_backend_sender_design.md`. Спроектирована безопасная отправка eligible PoP payload в backend через `POST /device-gateway/pop/events/batch`.

### Что описано

- Auth/HTTP модель: существующий `SafeHttpClient` + `DeviceAuthClient` + `RetryBackoffManager`
- Endpoint policy: batch endpoint, allowlist path `/api/device-gateway/pop/`
- Токен только in-memory, Authorization header не логируется
- Success: 2xx + valid response schema → `accepted_events`
- Partial success: accepted + rejected/discarded → `warning`, rejected → quarantine на rotation
- Failure: network/timeout/5xx → retry (до 3 попыток), 4xx → не retry, auth refresh при 401
- **Главное правило: нет подтверждения backend → pending не удалять и не перемещать**
- Idempotency: batch_id + device_event_id, backend duplicate detection
- Safe result: status + accepted/duplicate/rejected counts, без payload body/IDs

### Что НЕ делает sender (будет отдельными шагами)

- ❌ Не перемещает файлы (rotation — шаг 26.24+)
- ❌ Не удаляет pending
- ❌ Не создаёт sent/quarantine/dry_run
- ❌ Не читает media bytes
- ❌ Не логирует payload body
- ❌ Не делает произвольные URL (только allowlisted paths)
- ❌ Не отправляет draft/blocked/failed

**Реализация HTTP sender — отдельный шаг (26.23+).** Rotation/move sent/quarantine — отдельный шаг (26.24+). Pending нельзя трогать без backend confirmation.

---

## CLI: `pop-pickup-scan`

```bash
cd apps/kso_sidecar_agent

# Сканировать pending events — только агрегаты
python3 -m kso_sidecar_agent.cli pop-pickup-scan --root /tmp/kso-agent-root
```

**Важно:** только сканирует. НЕ отправляет backend, НЕ удаляет/перемещает файлы, НЕ создаёт sent/quarantine/dry_run. Выводит только safe агрегаты (counts). Draft-события не являются PoP.

### Exit codes

| Код | Значение |
|---|---|
| 0 | Scan ok |
| 1 | Warning/error/invalid/quarantine |
| 2 | Invalid CLI args |

---

## Что НЕ работает (будет отдельными шагами)

- ✅ Device auth + retry/backoff (базовый `auth-check` + `--retry-auth`)
- ✅ Runtime config sync (`/config/current`) — полный пайплайн auth→fetch→save в CLI `sync-runtime-config`
- ✅ Heartbeat (`/heartbeat`) — одиночная отправка с опциональным retry (`heartbeat-once --retry-heartbeat`)
- ✅ Manifest sync (`/manifest/current`, `/manifest/{id}`) — внутренний клиент + локальный store + CLI sync
- ✅ MediaClient (внутренний): `GET /media/{id}/metadata`, `GET /media/{id}` — metadata и content
- ✅ Media cache (локальный): atomic write staging→current, sha256 verify, quarantine, `media-cache-status` CLI
- ✅ Media sync (`sync-media`): auth → read local manifest → download media → `media/current/`
- ✅ MediaCacheReportClient (внутренний): `POST /media/cache/report` — отправка отчёта о состоянии кэша
- ✅ Media cache report CLI (`report-media-cache`): auth→build payload→POST report
- ✅ Run cycle core skeleton (`run_cycle.py`): dataclasses + status classification + `_cycle` agent_status
- ✅ Run cycle local readiness: проверка config/runtime_config/manifest/media_cache без backend
- ✅ Run-once CLI (`run-once --local-only`): local readiness preflight, без backend/auth/secret
- ✅ Run cycle auth step (`run_cycle_auth.py`): device auth с memory-only token, fake server в тестах
- ✅ Run cycle runtime config step (`run_cycle_runtime_config.py`): sync runtime config в backend режиме
- ✅ Run cycle heartbeat step (`run_cycle_heartbeat.py`): отправка heartbeat в backend режиме
- ✅ Run cycle manifest step (`run_cycle_manifest.py`): получение и синхронизация manifest в backend режиме
- ✅ Run cycle media sync step (`run_cycle_media.py`): скачивание media в backend режиме
- ✅ Run cycle media report step (`run_cycle_media_report.py`): отправка media cache report в backend режиме
- ✅ Run cycle final heartbeat: initial + final heartbeat в backend режиме
- ✅ Full run-cycle E2E smoke test на fake backend
- ✅ Run-once CLI backend mode: `run-once --backend --dev-secret-store`
- ✅ Degraded/offline fallback: backend outage + local cache complete → degraded
- ❌ Run loop / scheduler
- ❌ Media retry (retry для media download пока не подключён)
- ❌ PoP flush (`/pop/events/batch`)
- ❌ Offline mode
- ❌ KSO status reading

## Быстрый старт

```bash
cd apps/kso_sidecar_agent

# Инициализация
python3 -m kso_sidecar_agent.cli init-local-root --root /tmp/kso-agent-root

# Записать config (non-secret!)
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url https://retail-media.example.local \
  --device-code a-05954

# Опциональные параметры config
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url https://example.com \
  --device-code a-05954 \
  --tls-verify true \
  --request-timeout-sec 10 \
  --local-interface-version 1.0

# Проверить config
python3 -m kso_sidecar_agent.cli config-status --root /tmp/kso-agent-root

# Установить статус
python3 -m kso_sidecar_agent.cli set-status \
  --root /tmp/kso-agent-root --status running

# Полная проверка здоровье
python3 -m kso_sidecar_agent.cli doctor --root /tmp/kso-agent-root
```

### Allowed statuses

`stopped` | `starting` | `running` | `warning` | `error` | `offline`

### agent_config.json (non-secret!)

```json
{
  "backend_base_url": "https://retail-media.example.local",
  "device_code": "a-05954",
  "tls_verify": true,
  "request_timeout_sec": 10,
  "local_interface_version": "1.0"
}
```

**Что НЕ хранится в config:**
- ❌ `device_secret`
- ❌ JWT / refresh token
- ❌ Пароли / API-ключи
- ❌ `private_key` / `payment_card` / `receipt`

**Валидация:**
- `backend_base_url` — только http/https, без username/password, без forbidden query параметров
- `device_code` — 3-64 символа (`[a-zA-Z0-9._-]`)
- `tls_verify` — bool (default true)
- `request_timeout_sec` — 1-120 (default 10)
- Forbidden substrings во всех полях: token, jwt, password, secret, api_key, private_key, payment_card, receipt, local_path, file_path

## agent_status.json

```json
{
  "status": "running",
  "updated_at": "2026-06-18T10:00:00Z",
  "offline_mode": false,
  "cached_items": 0,
  "invalid_hash_items": 0,
  "errors": []
}
```

**Правила:** max 20 errors, каждая ≤200 символов, forbidden substrings — reject. Атомарная запись через `.tmp` → `os.replace()`.

## Dev Secret Store (dev-only)

**Production secret storage ещё не реализован.** Только dev-only fallback.

```bash
# Включить dev режим: флаг --dev-secret-store или KSO_DEV_SECRET_STORE=1
# Secret только через stdin, НЕ через CLI аргументы

printf "dev-value-1234567890" | python3 -m kso_sidecar_agent.cli secret-store-set \
  --root /tmp/kso-agent-root --dev-secret-store --stdin

python3 -m kso_sidecar_agent.cli secret-store-check \
  --root /tmp/kso-agent-root --dev-secret-store

python3 -m kso_sidecar_agent.cli secret-store-delete \
  --root /tmp/kso-agent-root --dev-secret-store
```

**Secret НЕ передаётся через CLI аргументы** (видны в /proc). Только stdin или env.

## TokenState (внутренний модуль)

Внутренний Python-модуль `token_state.py` для будущего Device Auth Client:

- **HTTP auth ещё не реализован** — backend-вызовов нет
- **Access token хранится только в памяти** (`TokenState` dataclass)
- **Access token не пишется на диск** (ни в `config/`, ни в `status/`, ни в `logs/`)
- **Access token не выводится в logs/status/doctor**
- `safe_summary()` возвращает только метаданные (authenticated, device_code, expires_at, status) — без значения токена
- `repr()` и `str()` не раскрывают токен
- CLI-команд для token нет

**Когда Device Auth Client будет реализован (будущие шаги), `TokenState` будет хранить JWT, полученный от `POST /api/device-gateway/auth/token`.**

## SafeHttpClient (внутренний модуль)

Внутренний Python-модуль `http_client.py` — безопасный HTTP-клиент на stdlib:

- **Нет новых зависимостей** — только `urllib.request`
- **Пока не используется для device auth** — backend-вызовы ещё не реализованы
- Не логирует request/response body
- Не логирует Authorization headers
- Не логирует secrets/passwords/api_keys
- Path validation: только `/`, без `..`, без forbidden substrings
- Header validation: reject значений с forbidden substrings
- HTTP ошибки классифицируются как retryable/non-retryable
- Имеет точное allowlist-исключение для `/api/device-gateway/auth/token`

## DeviceAuthClient (базовый)

Внутренний Python-модуль `device_auth_client.py` — базовый клиент для device auth:

- **`DeviceAuthClient`** — выполняет `POST /api/device-gateway/auth/token` и возвращает `TokenState` в память
- **Retry/backoff подключён** — при передаче `retry_manager` делает повторы на transient ошибках (429/5xx/network/timeout)
- **Retry включается явно** — через `--retry-auth` в CLI или `retry_manager=` в API
- **401/403/422 не retry** — не спамим backend при неверных credentials
- **Token refresh не реализован** — будет отдельным шагом
- **Token хранится только в памяти** — не пишется на диск, не логируется, не выводится
- **Secret читается через callable** — не привязан жёстко к dev secret store
- **Для dev используется `--dev-secret-store`** — production secret storage будет отдельным шагом

### CLI: `auth-check`

```bash
# Настроить config и secret
python3 -m kso_sidecar_agent.cli init-local-root --root /tmp/kso-agent-root
python3 -m kso_sidecar_agent.cli write-config \
  --root /tmp/kso-agent-root \
  --backend-base-url http://127.0.0.1:8080 \
  --device-code a-05954
printf "dev-value-1234567890" | python3 -m kso_sidecar_agent.cli secret-store-set \
  --root /tmp/kso-agent-root --dev-secret-store --stdin

# Проверить auth с retry:
python3 -m kso_sidecar_agent.cli auth-check \
  --root /tmp/kso-agent-root --dev-secret-store --retry-auth --auth-max-attempts 5

# Вывод:
#   authenticated:     True
#   device_code:       a-05954
#   device_id:         550e8400-...
#   status:            active
#   expires_in_sec:    3600
```

**Никогда не выводит:** access_token, device_secret.

## RetryBackoffManager (внутренний модуль)

Внутренний Python-модуль `retry_backoff.py` — менеджер retry/backoff для будущих backend-вызовов:

- **`BackoffPolicy`** — конфигурация: max_attempts, base_delay_sec, max_delay_sec, multiplier, jitter_ratio
- **`RetryDecision`** — результат решения: retryable, should_retry, delay_sec, reason (без forbidden substrings)
- **`RetryBackoffManager`** — классификация ошибок, exponential backoff + jitter, принятие решений
- **`execute_with_retries()`** — простой helper для выполнения с повторами
- **Пока не подключён к DeviceAuthClient** — retry для auth будет отдельным шагом
- **Не хранит token/secret** — reason сообщения редактируются: forbidden → `[REDACTED]`
- **Не логирует payload/body**

### Default policy

| Параметр | Значение |
|---|---|
| max_attempts | 3 |
| base_delay_sec | 2.0 |
| max_delay_sec | 60.0 |
| multiplier | 2.0 |
| jitter_ratio | 0.25 ( ±25%) |

### Error classification

| Тип ошибки | Retryable |
|---|---|
| `HttpClientError` (429/5xx/timeout/network) | ✅ |
| `HttpClientError` (400/401/403/404/409/422/TLS) | ❌ |
| `TimeoutError`, `ConnectionError`, `OSError` | ✅ |
| `ValueError`, `RuntimeError` | ❌ |

## RuntimeConfigClient (внутренний модуль)

Внутренний Python-модуль `runtime_config_client.py` — клиент для получения runtime config:

- **`RuntimeConfigClient`** — выполняет `GET /api/device-gateway/config/current` с Authorization header
- **`RuntimeConfigSnapshot`** — результат: status, config_hash, etag, config (в памяти), generated_at
- **Поддержка ETag/304** — `If-None-Match` / `ETag`, при 304 возвращает `not_modified=true`
- **Config пока не пишется на диск** — только в памяти (`RuntimeConfigSnapshot.config`)
- **Retry пока не подключён** — будет отдельным шагом
- **Forbidden keys/values в config → reject** (token, secret, api_key, …)

### Backend endpoint

```
GET /api/device-gateway/config/current
Authorization: Bearer <device_jwt>
If-None-Match: <config_hash>    (optional)

200:
{
  "status": "ok",
  "gateway_device_id": "...",
  "config_hash": "sha256...",
  "config": { ... },
  "generated_at": "2026-06-18T10:00:00+00:00"
}
ETag: "<config_hash>"

304: (empty body)
```

## RuntimeConfigStore (внутренний модуль)

Внутренний Python-модуль `runtime_config_store.py` — локальное сохранение runtime config:

- **`write_runtime_config(root, snapshot)`** — атомарная запись `config/runtime_config.json`
- **`read_runtime_config(root)`** — чтение и валидация
- **`runtime_config_status(root)`** — safe summary без полного config
- **Forbidden keys/values reject** — token, jwt, password, secret, api_key, private_key, payment_card, receipt, local_path, file_path, authorization, bearer
- **Файл `config/runtime_config.json`** — только проверенные данные, без secrets

### CLI: `runtime-config-status`

```bash
python3 -m kso_sidecar_agent.cli runtime-config-status --root /tmp/kso-agent-root
# Runtime config: PRESENT (valid)
#   config_hash:       abc123hash12...
#   etag_present:      True
#   generated_at:      2026-06-18T10:00:00+00:00
#   fetched_at:        2026-06-18T10:01:00+00:00
#   config_keys_count: 2
```

### CLI: `sync-runtime-config`

Полный цикл: auth → config/current → локальное сохранение.

```bash
python3 -m kso_sidecar_agent.cli sync-runtime-config \
  --root /tmp/kso-agent-root --dev-secret-store

# Опционально:
#   --retry-auth           Retry для auth при 5xx/429
#   --auth-max-attempts 5  Максимум попыток auth (default: 3)

# Вывод (updated):
#   runtime_config_sync: updated
#   config_hash:        abc123hash123
#   config_keys_count:  2

# Вывод (not_modified):
#   runtime_config_sync: not_modified
#   etag_present:       true
```

**Никогда не выводит:** access token, device_secret, Authorization header, response body, полный config.

### Doctor integration

`doctor` проверяет `runtime_config.json`:
- Отсутствует → warning (не fatal)
- Валиден → `runtime_config_ok: True`
- Invalid → `runtime_config_ok: False` + error

## MediaCacheReportClient + CLI: `report-media-cache`

Внутренний Python-модуль `media_cache_report_client.py` + CLI-команда для отправки отчёта о состоянии media cache в backend:

- **`MediaCacheReportClient`** (внутренний): `POST /api/device-gateway/media/cache/report` — отправка отчёта
- **`build_media_cache_report_payload(root)`** — строит payload из локального manifest + media cache status
- **CLI `report-media-cache`** — полный пайплайн: config→secret→auth→build payload→POST report

### Backend endpoint

```
POST /api/device-gateway/media/cache/report
Authorization: Bearer ***

Request (MediaCacheReportRequest):
{
  "manifest_version_id": "uuid",
  "manifest_hash": "64 hex chars",
  "device_reported_at": "optional ISO8601",
  "items": [
    {
      "manifest_item_id": "uuid",
      "status": "cached" | "missing" | "failed" | "invalid_hash" | "evicted",
      "reported_sha256": "optional 64 hex (required if cached)",
      "file_size_bytes": "optional int >= 0",
      "cached_at": "optional datetime",
      "error_code": "optional string max 64",
      "message": "optional string max 512",
      "details_json": {}
    }
  ],
  "details_json": {}
}

Response (MediaCacheReportResponse):
{
  "status": "ok",
  "gateway_device_id": "uuid",
  "manifest_version_id": "uuid",
  "total_items": int,
  "cached_count": int,
  "missing_count": int,
  "failed_count": int,
  "invalid_hash_count": int
}
```

### Использование

```bash
# Базовый вызов (auth без retry)
python3 -m kso_sidecar_agent.cli report-media-cache \
  --root /tmp/kso-agent-root --dev-secret-store

# С retry для auth
python3 -m kso_sidecar_agent.cli report-media-cache \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-auth --auth-max-attempts 3

# Вывод:
#   media_cache_report:  sent
#   backend_status:      ok
#   items_total:         2
#   cached_count:        0
#   missing_count:       2
#   failed_count:        0
#   invalid_hash_count:  0
```

**Что делает команда:**
- Auth → build local report (manifest + media cache status) → POST /media/cache/report
- **НЕ** запускает sync-media
- **НЕ** скачивает media
- **НЕ** имеет retry для самого report (только auth retry через `--retry-auth`)
- Token хранится только в памяти
- Secret только из dev secret store

**Никогда не выводит:** access token, device_secret, Authorization header, request body, response body, full manifest, report items list, media bytes, local_path, file_path, media_path.

## HeartbeatClient (внутренний модуль)

Внутренний Python-модуль `heartbeat_client.py` — клиент для отправки heartbeat:

- **`HeartbeatClient`** — выполняет `POST /api/device-gateway/heartbeat` с Authorization header
- **`HeartbeatPayload`** — валидирует status (ok/warning/error), message, device_time, версии, storage, manifest_hash
- **`HeartbeatResult`** — safe результат: status, backend_status, heartbeat_id
- **Heartbeat loop пока не реализован** — только одиночная отправка
- **Retry (опционально)** — `HeartbeatClient` принимает `retry_manager` + `sleep_fn`
  - Retry: 429/5xx/network error/timeout
  - НЕ retry: 400/401/403/404/409/422/invalid JSON/TLS error
  - Invalid payload и expired token — reject до HTTP-запроса
  - Retry включается явно через CLI `--retry-heartbeat`
- **Forbidden substrings в payload reject** — token, secret, api_key, …

### Backend endpoint

```
POST /api/device-gateway/heartbeat
Authorization: Bearer <device_jwt>

Request (DeviceHeartbeatRequest):
{
  "status": "ok",
  "message": "agent alive",           // optional, max 200
  "device_time": "2026-...",          // optional
  "app_version": "0.1.0",            // optional, max 128
  "os_version": "linux",             // optional, max 128
  "storage_free_mb": 1024,           // optional, >=0
  "cache_items_count": 0,            // optional, >=0
  "current_manifest_hash": "ab..64", // optional, 64 hex
  "details_json": {}                 // optional
}

Response (DeviceHeartbeatResponse):
{"id": "uuid", "gateway_device_id": "uuid", "status": "ok", ...}
```

### CLI: `heartbeat-once`

```bash
# Базовый вызов (без retry)
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --status ok --message "agent alive"

# С retry для heartbeat (500/429 → повторы)
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-heartbeat --heartbeat-max-attempts 3

# Retry и для auth и для heartbeat вместе
python3 -m kso_sidecar_agent.cli heartbeat-once \
  --root /tmp/kso-agent-root --dev-secret-store \
  --retry-auth --retry-heartbeat

# Вывод:
#   heartbeat:         sent
#   status:            ok
#   backend_status:    accepted
#   attempts:          1
```

**Retry-флаги:**
- `--retry-heartbeat` — включить retry для heartbeat (exponential backoff + jitter)
- `--heartbeat-max-attempts N` — макс. попыток (по умолчанию 3)
- `--retry-auth` — retry для auth (существующий флаг, работает отдельно)

**Никогда не выводит:** access token, device_secret, Authorization header, request body, response body.

## ManifestClient + ManifestStore (внутренние модули)

Внутренние Python-модули для получения и локального хранения manifest:

**ManifestClient** (`manifest_client.py`):
- `GET /api/device-gateway/manifest/current` и `GET /api/device-gateway/manifest/{id}`
- `ManifestSnapshot` — safe результат с метаданными
- Retry пока не подключён
- Media download не реализован

**ManifestStore** (`manifest_store.py`):
- `normalize_manifest_snapshot(snapshot)` → локальный формат
- `write_current_manifest(root, snapshot)` — атомарная запись
- `read_current_manifest(root)` — чтение + валидация
- `manifest_store_status(root)` — safe summary (CLI `manifest-status`)
- **Локальный файл:** `manifest/current_manifest.json`
- **Совместим с:** `simulator.manifest_reader` и `kso_local_interface_contract.md`
- **Media_path не пишется** в локальный manifest

### Backend endpoints

```
GET /api/device-gateway/manifest/current
# Response: {"status":"served","manifest_version_id":"uuid",
#            "manifest_hash":"64hex","published_at":"...",
#            "manifest":{"items":[...]}}

GET /api/device-gateway/manifest/{manifest_version_id}
# Response: {"manifest_version_id":"uuid","manifest_items":[...]}
```

### Использование

```python
from kso_sidecar_agent.manifest_client import ManifestClient

client = ManifestClient(http_client=...)
snapshot = client.fetch_current(token_state)
# {status: "served", items_count: 5, ...}

summary = snapshot.safe_summary()
# Только метаданные — без полного manifest и без token
```

**Никогда не выводит:** access token, Authorization header, полный manifest, response body.

### CLI: `sync-manifest`

```bash
python3 -m kso_sidecar_agent.cli sync-manifest \
  --root /tmp/kso-agent-root --dev-secret-store

# Вывод:
#   manifest_sync:        updated
#   manifest_version_id:  a0eebc99-9c0b...
#   manifest_hash:       cccccccccccc...
#   items_count:         5

# С retry для auth:
python3 -m kso_sidecar_agent.cli sync-manifest \
  --root /tmp/kso-agent-root --dev-secret-store --retry-auth
```

**Полный пайплайн:** config → secret → auth → manifest/current → normalize → validate → atomic write.

**Обработка статусов:**
- `served` → normalize, validate, атомарная запись `manifest/current_manifest.json`
- `not_modified` → файл не перезаписывается
- `no_manifest` → пустой manifest не создаётся, старый не удаляется

**Retry:** только для auth при `--retry-auth`. Retry манифест-запроса — отдельным шагом.

**Media download:** не реализован. Manifest не содержит media_path.

## Безопасность

- ❌ Не хранит `device_secret`
- ❌ Не хранит JWT
- ❌ Не ходит в backend
- ❌ Не собирает персональные/платёжные/чековые данные
- ✅ Logger: forbidden → `[REDACTED]`
- ✅ Forbidden words в config/status/errors — reject
- ✅ Атомарная запись: не оставляет `.tmp`

## Тесты

```bash
cd apps/kso_sidecar_agent
python3 -m unittest discover -s tests -v
```

## Связанные документы

- `docs/kso_sidecar_agent_design.md` — mini-design агента
- `docs/kso_player_architecture.md` — архитектура (Вариант D)
- `docs/kso_local_interface_contract.md` — контракт локального интерфейса
