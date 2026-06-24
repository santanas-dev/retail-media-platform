# Portrait Overlay Visual Proof Plan — Automated Verification

> **Статус:** 📋 Visual Proof Plan (38.1.3)
>
> Дата: 2026-06-24
> Ревизия: 1
> Предыдущий шаг: 38.1.2 (Phase 2 attempted, visual NOT confirmed)
>
> **⚠️ Phase 2 visual display is NOT yet confirmed.**
> **This plan defines objective proof criteria before any success claim.**

---

## 1. Why Phase 2 Was NOT Confirmed

| # | Факт | Следствие |
|---|------|-----------|
| P1 | Chromium `--app` процесс PID 25714 был запущен | Процесс ≠ окно |
| P2 | `xdotool search --name "Phase 2"` ничего не нашёл | Окно не зарегистрировано в X11 с ожидаемым именем |
| P3 | `scrot` скриншот не был сделан | Нет визуального доказательства |
| P4 | `xwininfo` не был вызван | Нет данных о геометрии окна |
| P5 | Пользователь не увидел overlay на экране | Субъективное подтверждение отсутствия |
| P6 | UKM5 kiosk — fullscreen Chromium на Openbox 3.6.1 | Новое окно могло оказаться ПОД kiosk |

**Вывод:** process-alive ≠ window-visible. Требуется объективное доказательство: X11 window tree + screenshot.

---

## 2. Visual Proof Criteria (объективные)

Следующая попытка Phase 2 считается **визуально подтверждённой** только если ВСЕ критерии выполнены:

| # | Критерий | Метод |
|---|----------|-------|
| V1 | Overlay процесс запущен | `kill -0 $PID` |
| V2 | Окно найдено в X11 root tree | `xwininfo -root -tree` |
| V3 | Геометрия окна: (0,400) 768×240 | `xwininfo -id $WID` |
| V4 | Окно НЕ перекрывает payment (y=720) | y+height ≤ 640 |
| V5 | Окно НЕ перекрывает header (y=0-60) | y ≥ 400 |
| V6 | Screenshot сделан во время теста | `scrot /tmp/kso_test/overlay-proof.png` |
| V7 | Screenshot НЕ содержит чеков/оплат/PII | Визуальная проверка safe-зон |
| V8 | Overlay процесс остановлен targeted | `pkill -f` по точному паттерну |
| V9 | UKM5 Chromium kiosk жив после теста | `ps aux | grep chromium.*kiosk` |

**Если любой критерий V1-V9 не выполнен → тест НЕ считается визуально успешным.**

---

## 3. Controlled Command Sequence

### 3.1 Pre-Flight (безопасно — только проверки)

```bash
# P1 — Проверить UKM5
systemctl is-active mint.service         # must be: active
ps aux | grep "[c]hromium.*kiosk"        # must have process
UKM5_KIOSK_PID=$(ps aux | grep "[c]hromium.*kiosk" | awk '{print $2}' | head -1)

# P2 — Проверить ресурсы
free -h | grep Mem                       # available > 1.5 GB
top -bn1 | grep "Cpu"                    # idle > 90%

# P3 — Создать kill-switch заранее
mkdir -p /tmp/kso_test
touch /tmp/kso_test/kill_switch

# P4 — Создать idle state
CURRENT_UTC=$(date -u +"%Y-%m-%dT%H:%M:%S.000000Z")
cat > /tmp/kso_test/state.json << 'EOF'
{"schema_version":1,"device_code":"a-05954","state":"idle",
 "source":"visual_proof","updated_at_utc":"REPLACE","stale_after_ms":999999999}
EOF
sed -i "s/REPLACE/$CURRENT_UTC/" /tmp/kso_test/state.json

# P5 — Проверить smoke
python3 /tmp/kso_test/smoke_test.py \
    --state-file /tmp/kso_test/state.json \
    --kill-switch /tmp/kso_test/kill_switch
# Expected: visible_plan=hidden (kill-switch active)

# P6 — Сделать скриншот ДО
DISPLAY=:0 scrot /tmp/kso_test/before.png
echo "BEFORE_SCREENSHOT_OK=$?"
```

### 3.2 Найти ВСЕ Chromium окна ДО запуска

```bash
# Сохранить список ВСЕХ окон ДО
DISPLAY=:0 xwininfo -root -tree > /tmp/kso_test/windows_before.txt
echo "WINDOWS_BEFORE_OK=$?"

# Сохранить список Chromium PID + window IDs
DISPLAY=:0 xdotool search --class "Chromium" > /tmp/kso_test/chromium_wids_before.txt 2>/dev/null
echo "CHROMIUM_WIDS_BEFORE=$(wc -l < /tmp/kso_test/chromium_wids_before.txt)"
```

### 3.3 Launch Overlay

```bash
# Удалить kill-switch (окно МОЖЕТ показаться)
rm /tmp/kso_test/kill_switch

# Создать overlay HTML с ярким тестовым блоком
cat > /tmp/kso_test/overlay.html << 'HTML'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>VISUAL_PROOF_OVERLAY</title>
<style>
  body { margin:0; padding:0; background:#ff3366; color:#fff;
         width:768px; height:240px; overflow:hidden;
         display:flex; align-items:center; justify-content:center;
         font-family:Arial,sans-serif; }
  .box { text-align:center; padding:20px; }
  .title { font-size:32px; font-weight:bold; }
  .sub { font-size:18px; margin-top:8px; opacity:0.9; }
</style></head>
<body><div class="box">
  <div class="title">🔴 VISUAL PROOF — Zone C</div>
  <div class="sub">y=400–640 | 768×240 | ярко-красный фон</div>
</div></body>
</html>
HTML

# Запустить Chromium --app с УНИКАЛЬНЫМ title
DISPLAY=:0 nohup chromium-browser \
    --app="file:///tmp/kso_test/overlay.html" \
    --window-position=0,400 \
    --window-size=768,240 \
    --disable-features=DialMediaRouteProvider \
    --disable-translate --disable-save-password-bubble \
    --no-first-run --disable-session-crashed-bubble \
    --noerrdialogs --disable-infobars \
    --disable-component-update --test-type \
    --user-data-dir=/tmp/kso_test/chromium-proof \
    > /tmp/kso_test/overlay.log 2>&1 &

OVERLAY_PID=$!
echo "OVERLAY_PID=$OVERLAY_PID"

# Ждать рендеринга
sleep 4

# Проверить процесс
if kill -0 $OVERLAY_PID 2>/dev/null; then
    echo "OVERLAY_ALIVE=yes"
else
    echo "OVERLAY_ALIVE=NO"
fi
```

### 3.4 Visual Proof — найти окно

```bash
# Сохранить ВСЕ окна ПОСЛЕ
DISPLAY=:0 xwininfo -root -tree > /tmp/kso_test/windows_after.txt

# Найти НОВЫЕ Chromium окна
DISPLAY=:0 xdotool search --class "Chromium" > /tmp/kso_test/chromium_wids_after.txt 2>/dev/null
echo "CHROMIUM_WIDS_AFTER=$(wc -l < /tmp/kso_test/chromium_wids_after.txt)"

# Попробовать найти окно по title
DISPLAY=:0 xdotool search --name "VISUAL_PROOF" > /tmp/kso_test/overlay_wids.txt 2>/dev/null
FOUND_WIDS=$(wc -l < /tmp/kso_test/overlay_wids.txt)
echo "OVERLAY_WINDOWS_FOUND=$FOUND_WIDS"

if [ "$FOUND_WIDS" -gt 0 ]; then
    WID=$(head -1 /tmp/kso_test/overlay_wids.txt)
    echo "OVERLAY_WID=$WID"
    
    # Геометрия окна
    DISPLAY=:0 xwininfo -id $WID > /tmp/kso_test/overlay_geometry.txt
    grep -E "(Absolute|Width|Height|Corners)" /tmp/kso_test/overlay_geometry.txt
    
    # Свойства окна
    DISPLAY=:0 xprop -id $WID > /tmp/kso_test/overlay_props.txt 2>/dev/null
    
    # Попытаться поднять окно (БЕЗОПАСНО — один window id)
    DISPLAY=:0 xdotool windowraise $WID 2>/dev/null
    echo "WINDOWRAISE_OK=$?"
    
    # НЕ использовать windowactivate — может украсть фокус у UKM5
else
    echo "OVERLAY_WINDOW_NOT_FOUND=yes"
    
    # Fallback: найти по PID
    DISPLAY=:0 xdotool search --pid $OVERLAY_PID > /tmp/kso_test/overlay_pid_wids.txt 2>/dev/null
    PID_WIDS=$(wc -l < /tmp/kso_test/overlay_pid_wids.txt)
    echo "OVERLAY_PID_WINDOWS=$PID_WIDS"
fi
```

### 3.5 Screenshot

```bash
DISPLAY=:0 scrot /tmp/kso_test/overlay-proof.png
echo "SCREENSHOT_OK=$?"
```

### 3.6 Rollback

```bash
# Kill ТОЛЬКО test overlay
pkill -f "chromium-browser.*overlay.html"
sleep 2

# Verify overlay dead
if kill -0 $OVERLAY_PID 2>/dev/null; then
    kill -9 $OVERLAY_PID 2>/dev/null
    echo "OVERLAY_FORCE_KILLED=yes"
else
    echo "OVERLAY_KILLED=yes"
fi

# Create kill-switch
touch /tmp/kso_test/kill_switch

# Verify UKM5 alive
echo "UKM5_KIOSK=$(ps aux | grep "[c]hromium.*kiosk" | wc -l)"
echo "MINT_UKM=$(ps aux | grep "[M]intUKM" | wc -l)"
echo "MINT_SVC=$(systemctl is-active mint.service 2>&1)"

# Screenshot AFTER
sleep 2
DISPLAY=:0 scrot /tmp/kso_test/after.png
echo "AFTER_SCREENSHOT_OK=$?"

# Diff screenshots (pixel-level change detection)
which compare >/dev/null 2>&1 && DISPLAY=:0 compare \
    /tmp/kso_test/before.png /tmp/kso_test/overlay-proof.png \
    /tmp/kso_test/diff.png 2>/dev/null && echo "DIFF_OK=0" || echo "DIFF_NA=1"

# Clean up state files (keep screenshots for review)
rm -f /tmp/kso_test/state.json /tmp/kso_test/overlay.html /tmp/kso_test/overlay.log
rm -rf /tmp/kso_test/chromium-proof
```

---

## 4. Stop Criteria

| # | Ситуация | Действие |
|---|----------|----------|
| S1 | `xdotool` не нашёл overlay окно | **STOP** — зафиксировать failure, НЕ продолжать windowraise |
| S2 | Screenshot содержит payment/header/close | **STOP** — удалить screenshot, rollback |
| S3 | Screenshot содержит чеки/оплаты/PII | **STOP** — удалить screenshot, rollback |
| S4 | UKM5 Chromium kiosk PID изменился/пропал | **STOP** — emergency rollback |
| S5 | CPU > 90%, RAM < 500 MB | **STOP** — rollback |
| S6 | `windowraise` сломал kiosk (визуально) | **STOP** — rollback, НЕ использовать windowraise в будущем |
| S7 | Overlay PID не найден после 4 сек | **STOP** — процесс не запустился |

---

## 5. Альтернативы Chromium --app (если stacking не решается)

| Вариант | Плюсы | Минусы | Статус |
|---------|-------|--------|--------|
| `wmctrl -r "title" -b add,above` | Форсирует always-on-top | Не установлен на КСО | ⬜ нужно установить |
| X11 override-redirect окно (Python xlib) | Полный контроль над stacking | Сложно, нужен python3-xlib | ⬜ отдельный design |
| `xdotool windowraise` каждые 500ms | Просто | Может мешать kiosk | ⬜ тестировать осторожно |
| Запустить ДО kiosk в autostart | Гарантированно поверх | Меняет autostart — запрещено | ❌ |

**Recommendation:** сначала `windowraise` + `scrot`. Если stacking не решается — `wmctrl`.

---

## 6. Safe Output Contract

Все артефакты визуального proof (screenshots, window trees, geometry) НЕ должны содержать:

| Запрещено | Почему |
|-----------|--------|
| Чеки / receipt | Фискальные данные |
| Оплаты / payment amounts | Финансовые данные |
| Клиенты / customer names | PII |
| Номера карт / PAN | PCI-DSS |
| Телефоны / email | PII |
| UKM5 DB / MySQL данные | Конфиденциально |
| Backend URL / токены | Секреты |

**Screenshots разрешены только если UKM5 экран в idle (главный экран без чеков/оплат).**

---

## 7. Visual Proof Harness (code)

Автоматизированный helper: `apps/kso_player/scripts/visual_proof_harness.py`

- Запускает Chromium --app с проверкой forbidden flags
- Делает xwininfo/xdotool/scrot
- Сам останавливает child process
- Пишет safe summary JSON
- Без секретов/backend URL/чеков/оплат

См. `apps/kso_player/scripts/visual_proof_harness.py`.

---

## 8. Fullscreen Idle Screensaver Test (будущее)

Отдельный режим: `portrait_fullscreen_idle_screensaver_768` — fullscreen 768×1024 idle screensaver.
Спроектирован в 38.1.4. **Physical fullscreen test НЕ проводился.**

| Параметр | Значение |
|---|---|
| Profile | `portrait_fullscreen_idle_screensaver_768` |
| Triggers | touch, pointer, mouse, click, keydown, input, wheel, state, kill-switch |
| Scanner risk | Первый скан теряется при Chromium overlay (B-FS-1) |
| Pass-through | Невозможен с текущим Chromium --app (B-FS-2) |
| Production | ❌ Запрещён до решения B-FS-1, B-FS-2 |

См. `docs/audit/fullscreen-idle-screensaver-interaction-design.md`.

---

## 9. Файлы

- `docs/audit/portrait-overlay-visual-proof-plan.md` — этот документ
- `apps/kso_player/scripts/visual_proof_harness.py` — automated proof harness
- `apps/kso_player/tests/test_visual_proof_harness.py` — тесты
- `docs/audit/portrait-overlay-phase2-readiness-review.md` — предыдущий аудит

---

## Журнал

### 2026-06-24 — Шаг 38.1.4 (Fullscreen Screensaver Design)

Спроектирован `portrait_fullscreen_idle_screensaver_768` — отдельный fullscreen-режим.
Interaction hide rules: 9 триггеров, приоритеты, scanner safety. 141 тест.
Physical fullscreen test НЕ проводился.

### 2026-06-24 — Шаг 38.1.3 (Visual Proof Plan Created)

Создан план объективной верификации видимости overlay. Определены 9 критериев (V1-V9), command sequence с xdotool/xwininfo/scrot, stop criteria, альтернативы Chromium --app.

Причина: Phase 2 attempted, но visual display NOT confirmed — окно оказалось под kiosk, xdotool не нашёл, пользователь не увидел.

Physical visual proof пока НЕ запускался — только подготовка плана и кода.
