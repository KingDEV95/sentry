from unittest.mock import MagicMock, patch

import orjson
import responses

from sentry.analytics.events.alert_sent import AlertSentEvent
from sentry.integrations.models.organization_integration import OrganizationIntegration
from sentry.integrations.on_call.metrics import OnCallIntegrationsHaltReason
from sentry.integrations.pagerduty.actions.notification import PagerDutyNotifyServiceAction
from sentry.integrations.pagerduty.client import PAGERDUTY_SUMMARY_MAX_LENGTH
from sentry.integrations.pagerduty.utils import add_service
from sentry.integrations.types import EventLifecycleOutcome
from sentry.silo.base import SiloMode
from sentry.testutils.asserts import assert_halt_metric, assert_slo_metric
from sentry.testutils.cases import PerformanceIssueTestCase, RuleTestCase
from sentry.testutils.helpers.analytics import assert_last_analytics_event
from sentry.testutils.helpers.datetime import before_now
from sentry.testutils.helpers.notifications import TEST_ISSUE_OCCURRENCE
from sentry.testutils.silo import assume_test_silo_mode
from sentry.testutils.skips import requires_snuba
from sentry.types.rules import RuleFuture

pytestmark = [requires_snuba]

event_time = before_now(days=3)
# external_id is the account name in pagerduty
EXTERNAL_ID = "example-pagerduty"
SERVICES = [
    {
        "type": "service",
        "integration_key": "PND4F9",
        "service_id": "123",
        "service_name": "Critical",
    }
]


class PagerDutyNotifyActionTest(RuleTestCase, PerformanceIssueTestCase):
    rule_cls = PagerDutyNotifyServiceAction

    def setUp(self) -> None:
        self.project_rule = self.create_project_rule(name="Check #project-channel")
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration, org_integration = self.create_provider_integration_for(
                self.organization,
                self.user,
                provider="pagerduty",
                name="Example",
                external_id=EXTERNAL_ID,
                metadata={"services": SERVICES},
            )
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.service = add_service(
                org_integration,
                service_name=SERVICES[0]["service_name"],
                integration_key=SERVICES[0]["integration_key"],
            )
        self.installation = self.integration.get_installation(self.organization.id)

    @responses.activate
    @patch("sentry.analytics.record")
    def test_applies_correctly(self, mock_record: MagicMock) -> None:
        event = self.store_event(
            data={
                "event_id": "a" * 32,
                "message": "ohhhhhh noooooo",
                "timestamp": event_time.isoformat(),
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )

        rule = self.get_rule(
            data={
                "account": self.integration.id,
                "service": str(self.service["id"]),
                "name": "Test Alert",
            }
        )

        notification_uuid = "123e4567-e89b-12d3-a456-426614174000"

        results = list(
            rule.after(
                event=event,
                notification_uuid=notification_uuid,
            )
        )
        assert len(results) == 1

        responses.add(
            method=responses.POST,
            url="https://events.pagerduty.com/v2/enqueue/",
            json={},
            status=202,
            content_type="application/json",
        )

        # Trigger rule callback
        rule_future = RuleFuture(rule=self.project_rule, kwargs=results[0].kwargs)
        results[0].callback(event, futures=[rule_future])
        data = orjson.loads(responses.calls[0].request.body)

        assert data["event_action"] == "trigger"
        assert data["payload"]["summary"] == f"[{self.project_rule.label}]: {event.message}"
        assert data["payload"]["custom_details"]["message"] == event.message
        assert event.group is not None
        assert data["links"][0]["href"] == event.group.get_absolute_url(
            params={"referrer": "pagerduty_integration", "notification_uuid": notification_uuid}
        )
        assert_last_analytics_event(
            mock_record,
            AlertSentEvent(
                provider="pagerduty",
                alert_id=self.project_rule.id,
                alert_type="issue_alert",
                organization_id=self.organization.id,
                project_id=event.project_id,
                external_id=str(self.service["id"]),
                notification_uuid=notification_uuid,
            ),
        )
        mock_record.assert_any_call(
            "integrations.pagerduty.notification_sent",
            category="issue_alert",
            organization_id=self.organization.id,
            project_id=event.project_id,
            group_id=event.group_id,
            notification_uuid=notification_uuid,
            alert_id=self.project_rule.id,
        )

    @responses.activate
    def test_applies_correctly_performance_issue(self) -> None:
        event = self.create_performance_issue()
        rule = self.get_rule(data={"account": self.integration.id, "service": self.service["id"]})
        results = list(rule.after(event=event))
        assert len(results) == 1

        responses.add(
            method=responses.POST,
            url="https://events.pagerduty.com/v2/enqueue/",
            json={},
            status=202,
            content_type="application/json",
        )

        # Trigger rule callback
        rule_future = RuleFuture(rule=self.project_rule, kwargs=results[0].kwargs)
        results[0].callback(event, futures=[rule_future])
        data = orjson.loads(responses.calls[0].request.body)

        perf_issue_title = "N+1 Query"

        assert data["event_action"] == "trigger"
        assert data["payload"]["summary"] == f"[{self.project_rule.label}]: {perf_issue_title}"
        assert data["payload"]["custom_details"]["title"] == perf_issue_title

    @responses.activate
    def test_applies_correctly_generic_issue(self) -> None:
        occurrence = TEST_ISSUE_OCCURRENCE
        event = self.store_event(
            data={
                "event_id": "a" * 32,
                "timestamp": before_now(minutes=1).isoformat(),
            },
            project_id=self.project.id,
        )
        group_event = event.for_group(event.groups[0])
        group_event.occurrence = occurrence

        rule = self.get_rule(data={"account": self.integration.id, "service": self.service["id"]})
        results = list(rule.after(event=group_event))
        assert len(results) == 1

        responses.add(
            method=responses.POST,
            url="https://events.pagerduty.com/v2/enqueue/",
            json={},
            status=202,
            content_type="application/json",
        )

        # Trigger rule callback
        rule_future = RuleFuture(rule=self.project_rule, kwargs=results[0].kwargs)
        results[0].callback(group_event, futures=[rule_future])
        data = orjson.loads(responses.calls[0].request.body)

        assert data["event_action"] == "trigger"
        assert (
            data["payload"]["summary"] == f"[{self.project_rule.label}]: {occurrence.issue_title}"
        )
        assert data["payload"]["custom_details"]["title"] == occurrence.issue_title

    @responses.activate
    def test_truncates_summary(self) -> None:
        event = self.store_event(
            data={
                "event_id": "a" * 32,
                "message": "ohhh noooo" * 100,
                "timestamp": event_time.isoformat(),
                "fingerprint": ["group-1"],
            },
            project_id=self.project.id,
        )
        rule = self.get_rule(
            data={
                "account": self.integration.id,
                "service": str(self.service["id"]),
                "name": "Test Alert",
            }
        )

        results = list(rule.after(event=event))

        responses.add(
            method=responses.POST,
            url="https://events.pagerduty.com/v2/enqueue/",
            json={},
            status=202,
            content_type="application/json",
        )

        # Trigger rule callback
        rule_future = RuleFuture(rule=self.project_rule, kwargs=results[0].kwargs)
        results[0].callback(event, futures=[rule_future])
        data = orjson.loads(responses.calls[0].request.body)

        assert len(data["payload"]["summary"]) == PAGERDUTY_SUMMARY_MAX_LENGTH
        assert data["payload"]["summary"].endswith("...")

    def test_render_label_without_severity(self) -> None:
        rule_data = {
            "account": self.integration.id,
            "service": self.service["id"],
        }
        rule = self.get_rule(data=rule_data)

        assert (
            rule.render_label()
            == "Send a notification to PagerDuty account Example and service Critical with default severity"
        )

    def test_render_label(self) -> None:
        rule_data = {
            "account": self.integration.id,
            "service": self.service["id"],
            "severity": "warning",
        }
        rule = self.get_rule(data=rule_data)

        assert (
            rule.render_label()
            == "Send a notification to PagerDuty account Example and service Critical with warning severity"
        )

    def test_render_label_without_integration(self) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration.delete()

        rule_data = {
            "account": self.integration.id,
            "service": self.service["id"],
            "severity": "default",
        }
        rule = self.get_rule(data=rule_data)

        assert (
            rule.render_label()
            == "Send a notification to PagerDuty account [removed] and service [removed] with default severity"
        )

    def test_valid_service_options(self) -> None:
        # create new org that has the same pd account but different a service added
        new_org = self.create_organization(name="New Org", owner=self.user)

        # need to create a new project and set it as self.project because rules are
        # project based and we want the project in this case to be associated with the
        # new organization when we call `self.get_rule()`
        new_project = self.create_project(name="new proj", organization=new_org)
        self.project = new_project

        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration.add_organization(new_org, self.user)
            oi = OrganizationIntegration.objects.get(organization_id=new_org.id)
            new_service = add_service(
                oi,
                service_name="New Service",
                integration_key="new_service_key",
            )

        rule = self.get_rule(data={"account": self.integration.id})

        service_options = rule.get_services()
        assert service_options == [(new_service["id"], new_service["service_name"])]
        assert "choice" == rule.form_fields["service"]["type"]
        assert service_options == rule.form_fields["service"]["choices"]

    @responses.activate
    def test_valid_service_selected(self) -> None:
        rule = self.get_rule(data={"account": self.integration.id, "service": self.service["id"]})

        form = rule.get_form_instance()
        assert form.is_valid()

    @responses.activate
    def test_notifies_with_multiple_pd_accounts(self) -> None:
        # make another PagerDuty account and service for the same organization
        service_info = {
            "type": "service",
            "integration_key": "PND352",
            "service_id": "346",
            "service_name": "Informational",
        }
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                provider="pagerduty",
                name="Example 3",
                external_id="example-3",
                metadata={"services": [service_info]},
            )
            integration.add_organization(self.organization, self.user)
            org_integration = OrganizationIntegration.objects.get(
                integration_id=integration.id, organization_id=self.organization.id
            )
            service = add_service(
                org_integration,
                service_name=service_info["service_name"],
                integration_key=service_info["integration_key"],
            )
        self.installation = integration.get_installation(self.organization.id)

        event = self.get_event()

        rule = self.get_rule(data={"account": integration.id, "service": service["id"]})

        results = list(rule.after(event=event))
        assert len(results) == 1

        responses.add(
            method=responses.POST,
            url="https://events.pagerduty.com/v2/enqueue/",
            json={},
            status=202,
            content_type="application/json",
        )

        # Trigger rule callback
        results[0].callback(event, futures=[])
        data = orjson.loads(responses.calls[0].request.body)

        assert data["event_action"] == "trigger"

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_invalid_service_selected(self, mock_record: MagicMock) -> None:
        # make a service associated with a different pagerduty account
        service_info = {
            "type": "service",
            "integration_key": "PND351",
            "service_id": "345",
            "service_name": "Informational",
        }
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_provider_integration(
                provider="pagerduty",
                name="Example 2",
                external_id="example-2",
                metadata={"services": [service_info]},
            )
            integration.add_organization(self.organization, self.user)
            org_integration = integration.organizationintegration_set.get()
            service = add_service(
                org_integration,
                service_name=service_info["service_name"],
                integration_key=service_info["integration_key"],
            )
        self.installation = integration.get_installation(self.organization.id)

        rule = self.get_rule(data={"account": self.integration.id, "service": str(service["id"])})

        form = rule.get_form_instance()
        assert not form.is_valid()
        assert len(form.errors) == 1
        assert_slo_metric(mock_record, EventLifecycleOutcome.HALTED)
        assert_halt_metric(mock_record, OnCallIntegrationsHaltReason.INVALID_SERVICE.value)
