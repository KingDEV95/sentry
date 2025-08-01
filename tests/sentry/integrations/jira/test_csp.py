from django.test.utils import override_settings

from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import assume_test_silo_mode
from sentry.utils.http import absolute_uri


class JiraCSPTest(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.issue_key = "APP-123"
        self.path = absolute_uri(f"extensions/jira/issue/{self.issue_key}/") + "?xdm_e=base_url"

    def _split_csp_policy(self, policy):
        csp = {}
        for directive in policy.split("; "):
            parts = directive.split(" ")
            csp[parts[0]] = parts[1:]
        return csp

    def test_xframeoptions_path(self) -> None:
        response = self.client.get(self.path)
        assert "Content-Security-Policy-Report-Only" in response
        assert "X-Frame-Options" not in response

        ui_hook_url = absolute_uri("extensions/jira/ui-hook/")
        with assume_test_silo_mode(SiloMode.CONTROL):
            response = self.client.get(ui_hook_url)
        assert "Content-Security-Policy-Report-Only" in response
        assert "X-Frame-Options" not in response

    def test_csp_frame_ancestors(self) -> None:
        response = self.client.get(self.path)
        csp = self._split_csp_policy(response["Content-Security-Policy-Report-Only"])
        assert "base_url" in csp["frame-ancestors"]
        assert "http://testserver" in csp["frame-ancestors"]

    @override_settings(STATIC_FRONTEND_APP_URL="https://sentry.io/_static/dist/")
    def test_csp_remote_style(self) -> None:
        response = self.client.get(self.path)
        assert "Content-Security-Policy-Report-Only" in response

        csp = self._split_csp_policy(response["Content-Security-Policy-Report-Only"])
        assert "https://sentry.io" in csp["style-src"]

    @override_settings(CSP_REPORT_ONLY=False)
    def test_csp_enforce(self) -> None:
        response = self.client.get(self.path)
        assert "Content-Security-Policy" in response
