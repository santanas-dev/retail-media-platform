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
                      "Ошибки", "Без heartbeat", "Требуют обновления"):
            self.assertIn(card, self.html,
                          f"Devices page must render summary card '{card}'")

    def test_has_filters_block(self):
        for flt in ("Филиал", "Магазин", "Статус", "Версия KSO"):
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

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: КСО-01", self.html)
        self.assertIn("DEMO: Магазин 001", self.html)

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
        for flt in ("Филиал", "Регион", "Формат", "Статус КСО",
                     "Готовность", "Версия KSO"):
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

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: Магазин 001", self.html)
        self.assertIn("DEMO: Северный", self.html)
        self.assertIn("Супермаркет", self.html)

    def test_mentions_kso_components(self):
        self.assertIn("State Adapter", self.html)
        self.assertIn("Sidecar", self.html)
        self.assertIn("Player", self.html)

    def test_has_readiness_legend(self):
        for badge in ("Готов", "Hold", "Ошибка", "Нет связи", "Нет КСО"):
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

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: Тестовый баннер 1", self.html)
        self.assertIn("DEMO: Тестовое видео 1", self.html)

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

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: Весенняя акция", self.html)
        self.assertIn("В эфире", self.html)
        self.assertIn("На согласовании", self.html)

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

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: Весенняя акция", self.html)
        self.assertIn("75%", self.html)

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

    def test_table_shows_demo_data(self):
        self.assertIn("Менеджер А", self.html)
        self.assertIn("Руководитель Б", self.html)
        self.assertIn("Согласовано", self.html)

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


# ══════════════════════════════════════════════════════════════════════
# Publications page tests
# ══════════════════════════════════════════════════════════════════════

class TestPublicationsPage(unittest.TestCase):
    """KSO Publications page — cards, flow, approval-gate, filters, table, legend."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/publications")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Готовы к публикации", "Ожидают approval", "Опубликованы",
                      "Ошибки публикации", "КСО получили manifest", "Требуют внимания"):
            self.assertIn(card, self.html,
                          f"Publications page must render summary card '{card}'")

    def test_has_publication_flow(self):
        for step in ("Кампания согласована", "Расписание согласовано",
                      "Manifest подготовлен", "Готов к публикации",
                      "Опубликован на Gateway", "Получен sidecar",
                      "Применён player", "Подтверждён PoP"):
            self.assertIn(step, self.html,
                          f"Publication flow must contain step '{step}'")

    def test_flow_has_terminal_states(self):
        for state in ("Ожидает approval", "Ошибка подготовки",
                       "Ошибка доставки", "Остановлено"):
            self.assertIn(state, self.html,
                          f"Flow terminals must contain '{state}'")

    def test_has_approval_gate_block(self):
        for rule in ("нельзя публиковать без финального approval",
                      "публикация заблокирована",
                      "Останавливает публикацию",
                      "Требует причины и попадает в аудит",
                      "Сохраняется для отчётности"):
            self.assertIn(rule, self.html,
                          f"Approval gate must contain '{rule[:50]}'")

    def test_mentions_final_approval_required(self):
        self.assertIn("финального approval", self.html)
        self.assertIn("невозможна", self.html.lower())

    def test_has_filters_block(self):
        for flt in ("Кампания", "Период", "Филиал", "Статус approval",
                     "Статус публикации", "Статус доставки"):
            self.assertIn(flt, self.html,
                          f"Publications page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Кампания", "Период", "Approval", "Manifest",
                     "Публикация", "Доставка", "КСО", "PoP",
                     "Последнее событие", "Действия"):
            self.assertIn(col, self.html,
                          f"Publications table must have column '{col}'")

    def test_table_shows_demo_data(self):
        self.assertIn("Опубликован", self.html)
        self.assertIn("Согласовано", self.html)

    def test_mentions_sidecar_player_pop(self):
        for term in ("sidecar", "player", "Proof of Play"):
            self.assertIn(term.lower(), self.html.lower(),
                          f"Publications page must mention '{term}'")

    def test_mentions_bi_reporting(self):
        self.assertIn("BI-отчётности", self.html)
        self.assertIn("Excel", self.html)

    def test_has_status_legend(self):
        for badge in ("Ожидает approval", "Готов", "Опубликовано",
                       "Доставлено", "Ошибка", "Остановлено",
                       "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Publications page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "manifest_id", "manifest_version_id",
                           "storage_key", "minio", "sha256",
                           "file_path", "filename", "token",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Publications page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-delivered", ".badge-stopped",
                          ".badge-published", ".badge-ready",
                          ".badge-error", ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_publications_route_returns_200(self):
        resp = self.client.get("/publications")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Proof of Play page tests
# ══════════════════════════════════════════════════════════════════════

class TestProofOfPlayPage(unittest.TestCase):
    """KSO Proof of Play page — cards, flow, filters, table, legend, notes."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/proof-of-play")
        self.html = resp.text

    def test_renders_summary_cards(self):
        for card in ("Подтверждённые показы", "Ожидают отправки", "Отправлены",
                      "Ошибки PoP", "КСО без подтверждений", "Кампании без факта"):
            self.assertIn(card, self.html,
                          f"PoP page must render summary card '{card}'")

    def test_has_pop_flow_block(self):
        for step in ("Player показал креатив", "Создан PoP event",
                      "Sidecar забрал event", "Сформирован batch",
                      "Backend принял", "Показ подтверждён"):
            self.assertIn(step, self.html,
                          f"PoP flow must contain step '{step}'")

    def test_flow_has_event_states(self):
        for state in ("pending", "sent", "confirmed", "duplicate",
                       "failed", "unknown"):
            self.assertIn(state, self.html.lower(),
                          f"PoP flow must contain state '{state}'")

    def test_has_filters_block(self):
        for flt in ("Период", "Кампания", "Креатив", "Филиал",
                     "КСО", "Статус PoP"):
            self.assertIn(flt, self.html,
                          f"PoP page must have filter '{flt}'")

    def test_filters_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_table_structure(self):
        for col in ("Период", "Кампания", "Креатив", "Магазин",
                     "Публикация", "Статус PoP", "Показы",
                     "Последнее событие", "Ошибка", "Действия"):
            self.assertIn(col, self.html,
                          f"PoP table must have column '{col}'")

    def test_table_shows_demo_data(self):
        self.assertIn("Подтверждено", self.html)
        self.assertIn("DEMO: КСО-01", self.html)

    def test_mentions_player_sidecar_backend(self):
        for term in ("player", "sidecar", "backend"):
            self.assertIn(term, self.html.lower(),
                          f"PoP page must mention '{term}'")

    def test_mentions_event_states_in_note(self):
        for state in ("pending", "sent", "confirmed", "duplicate", "failed"):
            self.assertIn(state, self.html.lower(),
                          f"PoP note must mention state '{state}'")

    def test_mentions_bi_reporting(self):
        self.assertIn("BI-отчётности", self.html)
        self.assertIn("Excel", self.html)
        self.assertIn("план/факт", self.html.lower())

    def test_mentions_power_bi_drill_down(self):
        self.assertIn("Power BI", self.html)
        self.assertIn("drill-down", self.html)
        self.assertIn("срезы", self.html)

    def test_has_status_legend(self):
        for badge in ("Ожидает отправки", "Отправлено", "Подтверждено",
                       "Дубликат", "Ошибка", "Нет данных"):
            self.assertIn(badge, self.html,
                          f"Legend must contain status '{badge}'")

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"PoP page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "device_event_id", "batch_id",
                           "fingerprint", "sha256", "storage_key",
                           "minio", "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"PoP page must NOT contain '{forbidden}'")

    def test_no_raw_pop_payload(self):
        lower = self.html.lower()
        for forbidden in ("raw payload", "pop payload", "event payload",
                           "payload body", "manifest_item_id"):
            self.assertNotIn(forbidden, lower,
                             f"PoP page must NOT contain '{forbidden}'")

    def test_status_badge_classes_in_css(self):
        css = (_PORTAL_DIR / "static" / "styles.css").read_text()
        for cls_name in (".badge-confirmed", ".badge-pending",
                          ".badge-duplicate", ".badge-error",
                          ".badge-unknown"):
            self.assertIn(cls_name, css,
                          f"CSS must define '{cls_name}'")

    def test_pop_route_returns_200(self):
        resp = self.client.get("/proof-of-play")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Reports / BI page tests
# ══════════════════════════════════════════════════════════════════════

class TestReportsPage(unittest.TestCase):
    """KSO Reports / BI page — KPI, slicers, drill-down, charts, table, Excel, notes."""

    def setUp(self):
        self.client = TestClient(app)
        resp = self.client.get("/reports")
        self.html = resp.text

    def test_renders_kpi_cards(self):
        for card in ("Показы план", "Показы факт", "Выполнение",
                      "КСО онлайн", "Кампании без факта",
                      "Ошибки публикации / PoP"):
            self.assertIn(card, self.html,
                          f"Reports page must render KPI card '{card}'")

    def test_has_bi_slicers(self):
        for slc in ("Период", "Кампания", "Креатив", "Филиал",
                     "КСО", "Статус публикации", "Статус PoP",
                     "Статус согласования"):
            self.assertIn(slc, self.html,
                          f"Reports page must have slicer '{slc}'")

    def test_slicers_disabled(self):
        self.assertIn("disabled", self.html)

    def test_has_drill_down_block(self):
        for level in ("Сеть", "Филиал", "Магазин", "КСО",
                       "Кампания", "Креатив", "День"):
            self.assertIn(level, self.html,
                          f"Drill-down must contain level '{level}'")

    def test_drill_down_mentions_aggregated_data(self):
        self.assertIn("агрегированным данным", self.html)
        self.assertIn("raw ID", self.html)
        self.assertIn("hash", self.html.lower())

    def test_has_chart_placeholders(self):
        for chart in ("План / факт показов", "Показы по дням",
                       "Показы по магазинам", "Ошибки по КСО",
                       "Статусы публикаций", "Статусы согласований"):
            self.assertIn(chart, self.html,
                          f"Reports page must have chart placeholder '{chart}'")

    def test_no_js_chart_libraries(self):
        self.assertNotIn("Chart.js", self.html)
        self.assertNotIn("chartjs", self.html.lower())
        self.assertNotIn("recharts", self.html.lower())

    def test_has_report_table_columns(self):
        for col in ("Кампания", "Период", "Магазины", "Креативы",
                     "Показы план", "Показы факт", "Выполнение",
                     "PoP", "Публикация", "Approval"):
            self.assertIn(col, self.html,
                          f"Reports table must have column '{col}'")

    def test_table_shows_demo_data(self):
        self.assertIn("DEMO: Весенняя акция", self.html)
        self.assertIn("24.9%", self.html)

    def test_has_excel_export_block(self):
        self.assertIn("Выгрузка в Excel", self.html)
        self.assertIn(".xlsx", self.html)

    def test_has_excel_export_requirements(self):
        for req in ("несколько листов", "выбранные срезы",
                     "Дата формирования", "Агрегированные KPI",
                     "Plan/fact", "raw ID"):
            self.assertIn(req, self.html,
                          f"Excel block must contain '{req}'")

    def test_excel_export_button_disabled(self):
        self.assertIn("Выгрузить в Excel", self.html)
        self.assertIn("btn-disabled", self.html)
        self.assertIn("disabled", self.html)

    def test_mentions_power_bi(self):
        self.assertIn("Power BI", self.html)

    def test_mentions_plan_fact(self):
        self.assertIn("план/факт", self.html.lower())

    def test_mentions_aggregated_data_only(self):
        self.assertIn("агрегированные данные", self.html.lower())
        self.assertIn("raw pop payload", self.html.lower())
        self.assertIn("технические hash", self.html)

    def test_no_forbidden_content(self):
        _assert_safe(self, self.html)

    def test_no_out_of_scope_channels(self):
        for banned in ("Android TV", "LED", "ESL", "Mobile App",
                        "Ценники", "Price Checker"):
            self.assertNotIn(banned, self.html,
                             f"Reports page must NOT contain '{banned}'")

    def test_no_raw_ids_secrets_hashes(self):
        lower = self.html.lower()
        for forbidden in ("device_secret", "access_token", "manifest_hash",
                           "campaign_id", "creative_id", "backend_url",
                           "rendition_id", "store_id", "device_id",
                           "schedule_item_id", "manifest_item_id",
                           "booking_id", "device_event_id", "batch_id",
                           "fingerprint", "sha256", "storage_key",
                           "minio", "file_path", "filename",
                           "http://", "https://backend"):
            self.assertNotIn(forbidden, lower,
                             f"Reports page must NOT contain '{forbidden}'")

    def test_no_js_cdn(self):
        for cdn in ("cdnjs", "unpkg", "jsdelivr", "googleapis"):
            self.assertNotIn(cdn, self.html.lower(),
                             f"Reports page must NOT contain CDN '{cdn}'")

    def test_reports_route_returns_200(self):
        resp = self.client.get("/reports")
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


class TestDemoData(unittest.TestCase):
    """Demo data is safe, synthetic, and marked as DEMO."""

    def setUp(self):
        self.client = TestClient(app)

    # ── Demo banner ────────────────────────────────

    def _assert_demo_banner(self, html: str, route: str):
        self.assertIn("Демо-данные", html,
                      f"{route}: must show demo banner")
        self.assertIn("Не являются реальными данными сети", html,
                      f"{route}: must show demo disclaimer")

    def test_demo_banner_on_all_pages(self):
        """Every page with demo data has the DEMO banner."""
        routes = ["/dashboard", "/campaigns", "/creatives", "/schedule",
                   "/publications", "/stores", "/devices", "/proof-of-play",
                   "/approvals", "/reports"]
        for route in routes:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200,
                             f"{route} must return 200")
            self._assert_demo_banner(resp.text, route)

    # ── Demo data is marked DEMO ───────────────────

    def test_demo_data_has_demo_prefix(self):
        """Demo data contains 'DEMO:' prefix."""
        resp = self.client.get("/campaigns")
        self.assertIn("DEMO:", resp.text,
                      "Demo data must be marked with DEMO: prefix")

    def test_stores_has_demo_data(self):
        resp = self.client.get("/stores")
        self.assertIn("DEMO: Магазин 001", resp.text)
        self.assertIn("DEMO: Северный", resp.text)

    def test_devices_has_demo_data(self):
        resp = self.client.get("/devices")
        self.assertIn("DEMO: КСО-01", resp.text)

    def test_campaigns_has_demo_data(self):
        resp = self.client.get("/campaigns")
        self.assertIn("DEMO: Весенняя акция", resp.text)
        self.assertIn("В эфире", resp.text)

    def test_creatives_has_demo_data(self):
        resp = self.client.get("/creatives")
        self.assertIn("DEMO: Тестовый баннер 1", resp.text)

    def test_schedule_has_demo_data(self):
        resp = self.client.get("/schedule")
        self.assertIn("DEMO: Весенняя акция", resp.text)

    def test_publications_has_demo_data(self):
        resp = self.client.get("/publications")
        self.assertIn("Опубликован", resp.text)

    def test_pop_has_demo_data(self):
        resp = self.client.get("/proof-of-play")
        self.assertIn("Подтверждено", resp.text)

    def test_approvals_has_demo_data(self):
        resp = self.client.get("/approvals")
        self.assertIn("Менеджер А", resp.text)
        self.assertIn("Руководитель Б", resp.text)

    def test_reports_has_demo_kpi(self):
        resp = self.client.get("/reports")
        self.assertIn("16 000", resp.text)
        self.assertIn("1 247", resp.text)
        self.assertIn("7.8%", resp.text)

    # ── No raw IDs/secrets/hash ────────────────────

    def test_no_raw_ids_in_demo_pages(self):
        """Demo pages must not contain raw IDs or hashes."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            _assert_safe(self, resp.text)
            # Extra: no UUID-like patterns
            self.assertNotIn("11111111-1111", resp.text.lower(),
                             f"{route}: must not contain UUID-like IDs")

    def test_no_filenames_paths_in_demo(self):
        """Demo data must not contain filenames, paths, storage keys."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("file_path", "filename", "storage_key",
                        "minio", "sha256", "/var/", "/opt/", "/etc/"):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    def test_no_phone_email_customer_payment(self):
        """Demo data must not contain personal/payment data."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("receipt", "payment", "card_data", "customer_data",
                        "phone", "fiscal", "@", "руб.", "skuid", "sku_id"):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    # ── Dangerous actions disabled ─────────────────

    def test_dangerous_actions_disabled_or_absent(self):
        """Publish/approve/reject/start/stop/restart/delete actions
        must be disabled or absent."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            # Buttons with these labels should not be active
            for action in ("опубликовать", "отправить", "удалить",
                            "перезапустить", "остановить", "запустить",
                            "загрузить"):
                # If present, must be in disabled context
                if action in lower:
                    self.assertIn("disabled", lower,
                                  f"{route}: '{action}' must be disabled")

    def test_excel_export_disabled(self):
        """Excel export button must remain disabled."""
        resp = self.client.get("/reports")
        self.assertIn("disabled", resp.text.lower())
        self.assertIn("Выгрузить в Excel", resp.text)
        self.assertIn("btn-disabled", resp.text)

    # ── No external deps ───────────────────────────

    def test_no_external_cdn_or_js_in_demo(self):
        """Demo pages must not pull external CDN/scripts/fonts/JS."""
        for route in ["/campaigns", "/creatives", "/schedule",
                       "/publications", "/stores", "/devices",
                       "/proof-of-play", "/approvals", "/reports",
                       "/deployment", "/admin", "/dashboard"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for fb in ("fonts.googleapis", "cdn.jsdelivr", "unpkg.com",
                        "chart.js", "chartjs", "recharts",
                        "fontawesome", "<script src="):
                self.assertNotIn(fb, lower,
                                 f"{route}: must not contain '{fb}'")

    def test_no_android_led_esl_mobile(self):
        """Android/LED/ESL/mobile app must NOT be in v1 UI."""
        for route in ["/dashboard", "/devices", "/stores", "/campaigns",
                       "/creatives", "/schedule", "/publications",
                       "/proof-of-play", "/approvals", "/reports"]:
            resp = self.client.get(route)
            lower = resp.text.lower()
            for banned in ("android tv", "led-шелф", "esl",
                            "mobile app", "price checker"):
                self.assertNotIn(banned, lower,
                                 f"{route}: must not contain '{banned}'")

    def test_deployment_admin_no_demo_banner(self):
        """Deployment and Admin pages are static, no demo banner required."""
        for route in ["/deployment", "/admin"]:
            resp = self.client.get(route)
            self.assertEqual(resp.status_code, 200)

    # ── Dashboard demo values ──────────────────────

    def test_dashboard_shows_demo_values(self):
        resp = self.client.get("/dashboard")
        self.assertIn("12", resp.text)      # kso_devices
        self.assertIn("1 247", resp.text)   # pop_today
        self.assertIn("3", resp.text)       # active_campaigns


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
