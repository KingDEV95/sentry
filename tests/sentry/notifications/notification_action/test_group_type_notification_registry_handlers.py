from unittest import mock

import pytest

from sentry.incidents.grouptype import MetricIssue
from sentry.notifications.notification_action.group_type_notification_registry.handlers.issue_alert_registry_handler import (
    IssueAlertRegistryHandler,
)
from sentry.notifications.notification_action.group_type_notification_registry.handlers.metric_alert_registry_handler import (
    MetricAlertRegistryHandler,
)
from sentry.notifications.notification_action.utils import execute_via_group_type_registry
from sentry.types.activity import ActivityType
from sentry.utils.registry import NoRegistrationExistsError
from sentry.workflow_engine.models import Action
from sentry.workflow_engine.types import WorkflowEventData
from tests.sentry.workflow_engine.test_base import BaseWorkflowTest


class TestIssueAlertRegistryInvoker(BaseWorkflowTest):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.create_project()
        self.detector = self.create_detector(project=self.project)
        self.action = Action(type=Action.Type.DISCORD)
        self.group, self.event, self.group_event = self.create_group_event()
        self.event_data = WorkflowEventData(event=self.group_event, group=self.group)

    @mock.patch(
        "sentry.notifications.notification_action.registry.issue_alert_handler_registry.get"
    )
    def test_handle_workflow_action_no_handler(self, mock_registry_get: mock.MagicMock) -> None:
        """Test that handle_workflow_action raises NoRegistrationExistsError when no handler exists"""
        mock_registry_get.side_effect = NoRegistrationExistsError()

        with pytest.raises(NoRegistrationExistsError):
            IssueAlertRegistryHandler.handle_workflow_action(
                self.event_data, self.action, self.detector
            )


class TestMetricAlertRegistryInvoker(BaseWorkflowTest):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.create_project()
        self.detector = self.create_detector(project=self.project)
        self.action = Action(type=Action.Type.DISCORD)
        self.group, self.event, self.group_event = self.create_group_event()
        self.event_data = WorkflowEventData(event=self.group_event, group=self.group)

    @mock.patch(
        "sentry.notifications.notification_action.registry.metric_alert_handler_registry.get"
    )
    def test_handle_workflow_action_no_handler(self, mock_registry_get: mock.MagicMock) -> None:
        """Test that handle_workflow_action raises NoRegistrationExistsError when no handler exists"""
        mock_registry_get.side_effect = NoRegistrationExistsError()

        with pytest.raises(NoRegistrationExistsError):
            MetricAlertRegistryHandler.handle_workflow_action(
                self.event_data, self.action, self.detector
            )

    def test_handle_activity_update(self) -> None:
        self.event_data = WorkflowEventData(event=self.activity, group=self.group)

        with mock.patch.object(self.activity, "send_notification"):
            execute_via_group_type_registry(self.event_data, self.action, self.detector)
            self.activity.send_notification.assert_called_once_with()

    @mock.patch("sentry.notifications.notification_action.utils.execute_via_metric_alert_handler")
    def test_handle_metric_issue_resolution(self, mock_execute_metric_alert_handler) -> None:
        group = self.create_group(type=MetricIssue.type_id)
        activity = self.create_group_activity(
            group=group,
            type=ActivityType.SET_RESOLVED.value,
        )
        self.event_data = WorkflowEventData(event=activity, group=group)

        execute_via_group_type_registry(self.event_data, self.action, self.detector)
        mock_execute_metric_alert_handler.assert_called_once_with(
            self.event_data, self.action, self.detector
        )
