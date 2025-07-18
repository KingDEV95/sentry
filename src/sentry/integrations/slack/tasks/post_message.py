from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from sentry.integrations.slack.service import SlackService
from sentry.silo.base import SiloMode
from sentry.tasks.base import instrumented_task
from sentry.taskworker.config import TaskworkerConfig
from sentry.taskworker.namespaces import integrations_control_tasks, integrations_tasks

logger = logging.getLogger("sentry.integrations.slack.tasks")


@instrumented_task(
    name="sentry.integrations.slack.tasks.post_message",
    queue="integrations",
    max_retries=0,
    silo_mode=SiloMode.REGION,
    taskworker_config=TaskworkerConfig(
        namespace=integrations_tasks,
        processing_deadline_duration=30,
    ),
)
def post_message(
    integration_id: int,
    payload: Mapping[str, Any],
    log_error_message: str,
    log_params: Mapping[str, Any],
) -> None:
    service = SlackService.default()
    service.send_message_to_slack_channel(
        integration_id=integration_id,
        payload=payload,
        log_error_message=log_error_message,
        log_params=log_params,
    )


@instrumented_task(
    name="sentry.integrations.slack.tasks.post_message_control",
    queue="integrations.control",
    max_retries=0,
    silo_mode=SiloMode.CONTROL,
    taskworker_config=TaskworkerConfig(
        namespace=integrations_control_tasks,
        processing_deadline_duration=30,
    ),
)
def post_message_control(
    integration_id: int,
    payload: Mapping[str, Any],
    log_error_message: str,
    log_params: Mapping[str, Any],
) -> None:
    service = SlackService.default()
    service.send_message_to_slack_channel(
        integration_id=integration_id,
        payload=payload,
        log_error_message=log_error_message,
        log_params=log_params,
    )
