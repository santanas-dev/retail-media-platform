"""Web Portal UI v1 — Tests.

Validates: routes, navigation, content safety, forbidden strings.
No real API integration. No systemd/Chromium/UKM 4.
"""

import sys as _sys
import unittest
from pathlib import Path

_PORTAL_DIR = Path(__file__).resolve().parent.parent
if str(_PORTAL_DIR) not in _sys.path:
    _sys.path.insert(0, str(_PORTAL_DIR))

from main import app
from starlette.testclient import TestClient

FORBIDDEN = frozenset({
    "device_secret", "access_token", "authorization",
    "backend_url", "api_key", "bearer ",
    "receipt_number", "card_number",
    "customer_id", "phone", "fiscal_data",
    "CHANGE_ME_SECRET",
    "Android TV", "LED-шелф", "ESL", "mobile app",
})


def _assert_safe(test, text: str):
    lower = text.lower()
    for fb in FORBIDDEN:
        test.assertNotIn(fb.lower(), lower,
                         f"Safe output must not contain '{fb}': {text[:200]}")


class TestPortalRoutes(unittest.TestCase):
    """All v1 routes return 200."""

    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_route(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/dashboard")
        self.assertEqual(resp2.status_code, 200)

    def test_campaigns_route(self):
        resp = self.client.get("/campaigns")
        self.assertEqual(resp.status_code, 200)

    def test_creatives_route(self):
        resp = self.client.get("/creatives")
        self.assertEqual(resp.status_code, 200)

    def test_schedule_route(self):
        resp = self.client.get("/schedule")
        self.assertEqual(resp.status_code, 200)

    def test_publications_route(self):
        resp = self.client.get("/publications")
        self.assertEqual(resp.status_code, 200)

    def test_stores_route(self):
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)

    def test_devices_route(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)

    def test_proof_of_play_route(self):
        resp = self.client.get("/proof-of-play")
        self.assertEqual(resp.status_code, 200)

    def test_reports_route(self):
        resp = self.client.get("/reports")
        self.assertEqual(resp.status_code, 200)

    def test_deployment_route(self):
        resp = self.client.get("/deployment")
        self.assertEqual(resp.status_code, 200)

    def test_admin_route(self):
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)

    def test_approvals_route(self):
        resp = self.client.get("/approvals")
        self.assertEqual(resp.status_code, 200)

    def test_health_route(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["portal"], "v1")

    def test_static_css(self):
        resp = self.client.get("/static/styles.css")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("--color-primary", resp.text)


class TestNavigation(unittest.TestCase):
    """Navigation contains KSO v1 menu items."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/dashboard")
        self.html = resp.text

    def test_contains_kso_v1_menu_items(self):
        for item in ("Dashboard", "Кампании", "Креативы", "Расписание",
                      "Публикации", "КСО Устройства", "Proof of Play",
                      "Магазины", "Отчёты", "Развёртывание",
                      "Согласования", "Администрирование"):
            self.assertIn(item, self.html,
                          f"Navigation must contain '{item}'")

    def test_navigation_does_not_contain_out_of_scope(self):
        """Android TV, LED, ESL, mobile app must NOT be in v1 menu."""
        for banned in ("Android TV", "AndroidTV", "LED", "ESL",
                        "mobile app", "Mobile App", "Ценники"):
            self.assertNotIn(banned, self.html,
                             f"Navigation must NOT contain '{banned}'")


class TestDashboardContent(unittest.TestCase):
    """Dashboard renders cards with safe content."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/dashboard")
        self.html = resp.text

    def test_renders_metric_cards(self):
        for card in ("КСО устройств", "Активных кампаний",
                      "Опубликованных манифестов", "Proof of Play сегодня",
                      "Устройств в hold", "Устройств с ошибками"):
            self.assertIn(card, self.html,
                          f"Dashboard must render card '{card}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)


class TestDeploymentPage(unittest.TestCase):
    """Deployment page describes KSO runtime components."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/deployment")
        self.html = resp.text

    def test_mentions_state_adapter(self):
        self.assertIn("State Adapter", self.html)
        self.assertIn("kso_state.json", self.html)

    def test_mentions_sidecar(self):
        self.assertIn("Sidecar", self.html)
        self.assertIn("manifest", self.html.lower())

    def test_mentions_player(self):
        self.assertIn("Player", self.html)
        self.assertIn("Chromium kiosk", self.html)

    def test_mentions_bootstrap(self):
        self.assertIn("Bootstrap", self.html)

    def test_mentions_preflight(self):
        self.assertIn("Preflight", self.html)

    def test_mentions_release_package(self):
        self.assertIn("Release Package", self.html)

    def test_mentions_pilot_runbook(self):
        self.assertIn("Runbook", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)


# ══════════════════════════════════════════════════════════════════════
# Devices page tests
# ══════════════════════════════════════════════════════════════════════

class TestDevicesPage(unittest.TestCase):
    """KSO Devices page — summary cards, filters, table, empty state."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/devices")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Всего КСО", "Онлайн", "В hold",
                      "С ошибками", "Без heartbeat", "Требуют обновления"):
            self.assertIn(card, self.html,
                          f"Devices page must render summary card '{card}'")

    def test_has_filters_block(self):
        for flt in ("Филиал", "Магазин", "Статус", "Версия runtime"):
            self.assertIn(flt, self.html,
                          f"Devices page must have filter '{flt}'")

    def test_filters_disabled(self):
        """Filters are UI-only placeholders — disabled selects."""
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Магазин", "КСО", "State Adapter", "Sidecar",
                     "Player", "Runtime", "Heartbeat", "Manifest", "PoP", "Действия"):
            self.assertIn(col, self.html,
                          f"Devices table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет подключённых КСО", self.html)
        self.assertIn("статус player, sidecar и state-adapter", self.html)

    def test_mentions_kso_components(self):
        self.assertIn("State Adapter", self.html)
        self.assertIn("Sidecar", self.html)
        self.assertIn("Player", self.html)

    def test_has_status_legend(self):
        for badge in ("Онлайн", "Hold", "Ошибка", "Офлайн", "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Devices page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Devices page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-online", ".badge-hold", ".badge-error",
                          ".badge-offline", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_devices_route_returns_200(self):
        resp = self.client.get("/devices")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Stores page tests
# ══════════════════════════════════════════════════════════════════════

class TestStoresPage(unittest.TestCase):
    """Stores & KSO Inventory page — cards, filters, table, legend, note."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/stores")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Всего магазинов", "Магазинов с КСО", "КСО подключено",
                      "Готовы к показу", "В hold", "Требуют внимания"):
            self.assertIn(card, self.html,
                          f"Stores page must render summary card '{card}'")

    def test_has_filters_block(self):
        for flt in ("Филиал", "Город", "Формат магазина", "Статус КСО",
                     "Готовность к рекламе", "Версия runtime"):
            self.assertIn(flt, self.html,
                          f"Stores page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Филиал", "Магазин", "Формат", "КСО",
                     "State Adapter", "Sidecar", "Player",
                     "Готовность", "Heartbeat", "Действия"):
            self.assertIn(col, self.html,
                          f"Stores table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет данных по магазинам", self.html)
        self.assertIn("готовность магазинов к показу рекламы", self.html)

    def test_mentions_kso_components(self):
        self.assertIn("State Adapter", self.html)
        self.assertIn("Sidecar", self.html)
        self.assertIn("Player", self.html)

    def test_has_readiness_legend(self):
        for badge in ("Готов", "В hold", "Ошибка", "Нет связи", "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain readiness '{badge}'")

    def test_mentions_devices_page(self):
        self.assertIn("КСО Устройства", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED-шелф", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Stores page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "store_id", "device_id", "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Stores page must NOT contain '{forbidden}'")

    def test_stores_route_returns_200(self):
        resp = self.client.get("/stores")
        self.assertEqual(resp.status_code, 200)

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-ready", ".badge-no-connection",
                          ".badge-online", ".badge-hold"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")


# ══════════════════════════════════════════════════════════════════════
# Creatives page tests
# ══════════════════════════════════════════════════════════════════════

class TestCreativesPage(unittest.TestCase):
    """KSO Creatives Library page — cards, requirements, filters, table, legend."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/creatives")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Всего креативов", "Готовы к публикации", "На проверке",
                      "С ошибками", "Используются в кампаниях", "Требуют замены"):
            self.assertIn(card, self.html,
                          f"Creatives page must render summary card '{card}'")

    def test_has_filters_block(self):
        for flt in ("Тип материала", "Статус проверки", "Формат",
                     "Использование в кампаниях", "Дата обновления"):
            self.assertIn(flt, self.html,
                          f"Creatives page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_kso_requirements(self):
        for req in ("1440", "1080", "PNG", "JPEG", "MP4",
                     "Запрещено", "sidecar media cache"):
            self.assertIn(req, self.html,
                          f"Requirements must mention '{req}'")

    def test_requirements_audio_forbidden(self):
        self.assertIn("Аудио", self.html)
        self.assertIn("Запрещено", self.html)

    def test_has_table_structure(self):
        for col in ("Название", "Тип", "Формат", "Размер",
                     "Длительность", "Статус", "Используется",
                     "Обновлён", "Действия"):
            self.assertIn(col, self.html,
                          f"Creatives table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет загруженных креативов", self.html)
        self.assertIn("библиотека рекламных файлов для КСО", self.html)

    def test_has_status_legend(self):
        for badge in ("Готов", "На проверке", "Ошибка", "Архив", "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_mentions_campaigns_publications(self):
        self.assertIn("кампаний", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Creatives page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "storage_key", "minio", "sha256", "file_path",
                           "filename", "rendition_id", "creative_version_id",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Creatives page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-ready", ".badge-review", ".badge-archived",
                          ".badge-error", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_creatives_route_returns_200(self):
        resp = self.client.get("/creatives")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Campaigns page tests
# ══════════════════════════════════════════════════════════════════════

class TestCampaignsPage(unittest.TestCase):
    """KSO Campaigns page — cards, lifecycle, filters, table, legend, notes."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/campaigns")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Всего кампаний", "Активные", "Черновики",
                      "На согласовании", "Опубликованы", "Требуют внимания"):
            self.assertIn(card, self.html,
                          f"Campaigns page must render summary card '{card}'")

    def test_has_lifecycle_block(self):
        for step in ("Черновик", "На согласовании", "Готова к публикации",
                      "Опубликована", "В эфире", "Завершена"):
            self.assertIn(step, self.html,
                          f"Lifecycle must contain step '{step}'")

    def test_lifecycle_has_terminal_states(self):
        for state in ("Ошибка публикации", "Остановлена", "Архив"):
            self.assertIn(state, self.html,
                          f"Lifecycle terminals must contain '{state}'")

    def test_has_filters_block(self):
        for flt in ("Статус кампании", "Период", "Креатив",
                     "Филиал", "Готовность публикации", "План / факт"):
            self.assertIn(flt, self.html,
                          f"Campaigns page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Кампания", "Статус", "Период", "Креативы",
                     "Магазины", "Публикация",
                     "Показы план", "Показы факт", "PoP", "Действия"):
            self.assertIn(col, self.html,
                          f"Campaigns table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет рекламных кампаний", self.html)
        self.assertIn("Proof of Play", self.html)

    def test_has_status_legend(self):
        for badge in ("Черновик", "На согласовании", "Готова",
                       "В эфире", "Завершена", "Ошибка", "Архив",
                       "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_mentions_plan_fact_and_pop(self):
        self.assertIn("План / факт", self.html)
        self.assertIn("Proof of Play", self.html)

    def test_mentions_bi_reporting_excel(self):
        self.assertIn("BI-отчётность", self.html)
        self.assertIn("Power BI", self.html)
        self.assertIn("Excel", self.html)
        self.assertIn("Reports", self.html)

    def test_mentions_related_pages(self):
        for term in ("креативы", "магазины", "расписание"):
            self.assertIn(term, self.html.lower(),
                          f"Campaigns page must mention '{term}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Campaigns page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "storage_key", "minio", "sha256",
                           "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Campaigns page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-draft", ".badge-live", ".badge-completed",
                          ".badge-ready", ".badge-review", ".badge-error",
                          ".badge-archived", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_campaigns_route_returns_200(self):
        resp = self.client.get("/campaigns")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Schedule page tests
# ══════════════════════════════════════════════════════════════════════

class TestSchedulePage(unittest.TestCase):
    """KSO Schedule page — cards, planning, filters, table, legend, notes."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/schedule")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Запланировано кампаний", "Активных периодов",
                      "Занято эфирного времени", "Свободно эфирного времени",
                      "Конфликты расписания", "Готово к публикации"):
            self.assertIn(card, self.html,
                          f"Schedule page must render summary card '{card}'")

    def test_has_planning_block(self):
        for item in ("Период кампании", "Слот показа", "Длительность креатива",
                      "Магазины / КСО", "Проверка конфликтов", "Публикация"):
            self.assertIn(item, self.html,
                          f"Planning block must contain '{item}'")

    def test_has_filters_block(self):
        for flt in ("Период", "Кампания", "Филиал", "КСО",
                     "Статус публикации", "Занятость эфирного времени"):
            self.assertIn(flt, self.html,
                          f"Schedule page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Период", "Кампания", "Креативы", "Магазины",
                     "Слот", "Длительность", "Занятость",
                     "Публикация", "Конфликты", "Действия"):
            self.assertIn(col, self.html,
                          f"Schedule table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет расписания", self.html)
        self.assertIn("готовность публикации на КСО", self.html)

    def test_has_status_legend(self):
        for badge in ("Запланировано", "Готово", "Опубликовано",
                       "Конфликт", "Ошибка", "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_mentions_airtime_and_conflicts(self):
        self.assertIn("эфирного времени", self.html)
        self.assertIn("конфликтов", self.html.lower())

    def test_mentions_bi_reporting_excel(self):
        self.assertIn("BI-отчётах", self.html)
        self.assertIn("Excel", self.html)

    def test_mentions_related_pages(self):
        for term in ("кампанию", "креативы", "магазины", "manifest"):
            self.assertIn(term, self.html.lower(),
                          f"Schedule page must mention '{term}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Schedule page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "booking_id",
                           "manifest_item_id", "storage_key", "minio",
                           "sha256", "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Schedule page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-scheduled", ".badge-published",
                          ".badge-conflict", ".badge-ready",
                          ".badge-error", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_schedule_route_returns_200(self):
        resp = self.client.get("/schedule")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Approvals page tests
# ══════════════════════════════════════════════════════════════════════

class TestApprovalsPage(unittest.TestCase):
    """KSO Approval Workflow page — cards, workflow, filters, table, rules, legend."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/approvals")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("На согласовании", "Ожидают моего решения",
                      "Возвращены на доработку", "Просрочены по SLA",
                      "Готовы к публикации", "Заблокированы"):
            self.assertIn(card, self.html,
                          f"Approvals page must render summary card '{card}'")

    def test_has_workflow_block(self):
        for step in ("Черновик", "Отправлено на согласование", "На проверке",
                      "Согласовано", "Готово к публикации",
                      "Возвращено на доработку"):
            self.assertIn(step, self.html,
                          f"Workflow must contain step '{step}'")

    def test_workflow_has_terminal_states(self):
        for state in ("Отклонено", "Просрочено", "Экстренная остановка",
                       "Заблокировано ИБ"):
            self.assertIn(state, self.html,
                          f"Workflow terminals must contain '{state}'")

    def test_has_filters_block(self):
        for flt in ("Тип объекта", "Статус согласования", "Согласующий",
                     "Инициатор", "SLA", "Период кампании"):
            self.assertIn(flt, self.html,
                          f"Approvals page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Объект", "Тип", "Статус", "Инициатор",
                     "Согласующий", "SLA", "Последнее решение",
                     "Комментарий", "Следующий шаг", "Действия"):
            self.assertIn(col, self.html,
                          f"Approvals table must have column '{col}'")

    def test_table_shows_empty_state(self):
        self.assertIn("Пока нет объектов на согласовании", self.html)
        self.assertIn("креативов, кампаний, расписаний", self.html)

    def test_has_approval_rules(self):
        for rule in ("Нельзя использовать в кампании без согласования",
                      "Нельзя отправить в публикацию без согласования",
                      "Нельзя публиковать без согласования",
                      "Нельзя публиковать на КСО без финального approval",
                      "Требует причины и попадает в аудит",
                      "Требует комментария",
                      "Каждое решение сохраняется в истории"):
            self.assertIn(rule, self.html,
                          f"Rules must contain '{rule[:60]}'")

    def test_mentions_covered_objects(self):
        for obj in ("креативы", "кампании", "расписание", "manifest"):
            self.assertIn(obj, self.html.lower(),
                          f"Approvals page must mention '{obj}'")

    def test_mentions_final_approval_required(self):
        self.assertIn("финального approval", self.html)
        self.assertIn("невозможна", self.html.lower())

    def test_mentions_bi_reporting(self):
        self.assertIn("BI-отчётах", self.html)
        self.assertIn("Excel", self.html)

    def test_has_status_legend(self):
        for badge in ("На согласовании", "Согласовано", "На доработке",
                       "Отклонено", "Просрочено", "Заблокировано",
                       "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Approvals page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "approval_id", "user_id",
                           "storage_key", "minio", "sha256",
                           "file_path", "filename", "email",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Approvals page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-rejected", ".badge-overdue",
                          ".badge-blocked", ".badge-review",
                          ".badge-ready", ".badge-error", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_approvals_route_returns_200(self):
        resp = self.client.get("/approvals")
        self.assertEqual(resp.status_code, 200)


class TestPageStubsRender(unittest.TestCase):
    """All page stubs render with title and safe empty state."""

    def setUp(self):
        self.client = TestClient(app)

    def _check_page(self, path: str, title: str):
        resp = self.client.get(path)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(title, resp.text)
        _assert_safe(self, resp.text)

    def test_campaigns_page(self):
        self._check_page("/campaigns", "Кампании")

    def test_creatives_page(self):
        self._check_page("/creatives", "Креативы")

    def test_schedule_page(self):
        self._check_page("/schedule", "Расписание")

    def test_publications_page(self):
        self._check_page("/publications", "Публикации")

    def test_proof_of_play_page(self):
        self._check_page("/proof-of-play", "Proof of Play")

    def test_reports_page(self):
        self._check_page("/reports", "Отчёты")

    def test_admin_page(self):
        self._check_page("/admin", "Администрирование")

    def test_approvals_page(self):
        self._check_page("/approvals", "Согласования")


class TestPortalSafety(unittest.TestCase):
    """Cross-cutting security checks."""

    def setUp(self):
        self.client = TestClient(app)

    def test_no_external_cdn_references(self):
        """HTML must not reference external CDN fonts/scripts."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text()
                    self.assertNotIn("https://fonts.googleapis.com", content)
                    self.assertNotIn("cdnjs.cloudflare.com", content)
                    self.assertNotIn("unpkg.com", content)
                    self.assertNotIn("jsdelivr.net", content)

    def test_css_no_external_resources(self):
        """CSS must not reference external URLs."""
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        self.assertNotIn("url(http", css)
        self.assertNotIn("@import", css)

    def test_no_backend_url_hardcoded(self):
        """Portal must not hardcode backend URLs."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text()
                    self.assertNotIn("https://backend.", content)
                    self.assertNotIn("http://127.0.0.1:8001", content)

    def test_no_real_secrets_in_templates(self):
        """Templates must not contain secrets/tokens."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text().lower()
                    for fb in ("device_secret", "access_token",
                                "bearer ", "api_key"):
                        self.assertNotIn(fb, content,
                                         f"Template {f} contains '{fb}'")

    def test_no_windows_references(self):
        """No Windows/MSI/ProgramData references."""
        import os as _os
        templates_dir = _PORTAL_DIR / "templates"
        for root, _, files in _os.walk(templates_dir):
            for f in files:
                if f.endswith(".html"):
                    content = (Path(root) / f).read_text().lower()
                    self.assertNotIn("C:\\\\", content)
                    self.assertNotIn("programdata", content)
                    self.assertNotIn(".msi", content)

    def test_filter_svg_inline_no_external(self):
        """Filter dropdown arrow must be inline SVG, not external image."""
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        self.assertIn("data:image/svg+xml", css,
                      "Filter arrow must use inline SVG, not external file")


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
