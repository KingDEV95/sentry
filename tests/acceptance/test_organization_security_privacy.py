from sentry.testutils.cases import AcceptanceTestCase
from sentry.testutils.silo import no_silo_test
from sentry.utils import json


@no_silo_test
class OrganizationSecurityAndPrivacyTest(AcceptanceTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user("owner@example.com")
        self.org = self.create_organization(owner=self.user, name="Rowdy Tiger")
        self.login_as(self.user)
        self.path = f"/settings/{self.org.slug}/security-and-privacy/"

    def load_organization_helper(self):
        self.browser.wait_until_not('[data-test-id="loading-indicator"]')
        assert self.browser.wait_until(
            '[data-test-id="organization-settings-security-and-privacy"]'
        )

    def renders_2fa_setting(self):
        return self.browser.wait_until("#require2FA")

    def test_renders_2fa_setting_for_owner(self) -> None:
        self.browser.get(self.path)
        self.load_organization_helper()
        assert self.renders_2fa_setting()

    def test_renders_2fa_setting_for_manager(self) -> None:
        manager_user = self.create_user("manager@example.com")
        self.create_member(organization=self.org, user=manager_user, role="manager")
        self.login_as(manager_user)
        self.browser.get(self.path)
        self.load_organization_helper()
        assert self.renders_2fa_setting()

    def test_setting_2fa_without_2fa_enabled(self) -> None:
        self.browser.get(self.path)
        self.browser.wait_until_not('[data-test-id="loading-indicator"]')
        assert not self.browser.element_exists(
            '[data-test-id="organization-settings-security-and-privacy"] .error'
        )
        self.browser.click("#require2FA")
        self.browser.wait_until("[role='dialog']")
        self.browser.click("[role='dialog'] [data-test-id='confirm-button']")
        self.browser.wait_until_not("[role='dialog']")
        self.browser.wait_until_test_id("toast-error")
        self.load_organization_helper()

    def test_renders_advanced_data_scrubbing_without_rule(self) -> None:
        self.browser.get(self.path)
        self.browser.wait_until_not('[data-test-id="loading-indicator"]')
        assert self.browser.wait_until('[data-test-id="advanced-data-scrubbing"]')
        self.load_organization_helper()

    def test_renders_advanced_data_scrubbing_with_rules(self) -> None:
        relayPiiConfig = json.dumps(
            {
                "rules": {
                    "0": {
                        "type": "password",
                        "redaction": {"method": "replace", "text": "Scrubbed"},
                    },
                    "1": {"type": "creditcard", "redaction": {"method": "mask"}},
                },
                "applications": {"password": ["0"], "$message": ["1"]},
            }
        )
        self.org.update_option("sentry:relay_pii_config", relayPiiConfig)
        self.browser.get(self.path)
        self.browser.wait_until_not('[data-test-id="loading-indicator"]')
        assert self.browser.wait_until('[data-test-id="advanced-data-scrubbing"]')
        assert self.browser.wait_until('[data-test-id="advanced-data-scrubbing-rules"]')
        self.load_organization_helper()

    def test_renders_advanced_data_scrubbing_add_rule_modal(self) -> None:
        self.browser.get(self.path)
        self.browser.wait_until_not('[data-test-id="loading-indicator"]')
        assert self.browser.wait_until('[data-test-id="advanced-data-scrubbing"]')
        self.browser.click_when_visible("[aria-label='Add Rule']")
        self.load_organization_helper()
