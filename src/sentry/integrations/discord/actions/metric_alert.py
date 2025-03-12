from __future__ import annotations

import sentry_sdk

from sentry import features
from sentry.incidents.charts import build_metric_alert_chart
from sentry.incidents.models.alert_rule import AlertRuleTriggerAction
from sentry.incidents.models.incident import Incident, IncidentStatus
from sentry.incidents.typings.metric_detector import AlertContext
from sentry.integrations.discord.client import DiscordClient
from sentry.integrations.discord.message_builder.metric_alerts import (
    DiscordMetricAlertMessageBuilder,
)
from sentry.integrations.discord.spec import DiscordMessagingSpec
from sentry.integrations.discord.utils.metrics import record_lifecycle_termination_level
from sentry.integrations.messaging.metrics import (
    MessagingInteractionEvent,
    MessagingInteractionType,
)
from sentry.integrations.metric_alerts import get_metric_count_from_incident
from sentry.shared_integrations.exceptions import ApiError

from ..utils import logger


def send_incident_alert_notification(
    action: AlertRuleTriggerAction,
    incident: Incident,
    metric_value: int | float | None,
    new_status: IncidentStatus,
    notification_uuid: str | None = None,
) -> bool:
    chart_url = None
    if features.has("organizations:metric-alert-chartcuterie", incident.organization):
        try:
            chart_url = build_metric_alert_chart(
                organization=incident.organization,
                alert_rule=incident.alert_rule,
                selected_incident=incident,
                subscription=incident.subscription,
            )
        except Exception as e:
            sentry_sdk.capture_exception(e)

    channel = action.target_identifier

    if not channel:
        # We can't send a message if we don't know the channel
        logger.warning(
            "discord.metric_alert.no_channel",
            extra={"incident_id": incident.id},
        )
        return False

    if metric_value is None:
        metric_value = get_metric_count_from_incident(incident)

    message = DiscordMetricAlertMessageBuilder(
        alert_context=AlertContext.from_alert_rule_incident(incident.alert_rule),
        open_period_identifier=incident.identifier,
        snuba_query=incident.alert_rule.snuba_query,
        organization=incident.organization,
        date_started=incident.date_started,
        new_status=new_status,
        metric_value=metric_value,
        chart_url=chart_url,
    ).build(notification_uuid=notification_uuid)

    client = DiscordClient()
    with MessagingInteractionEvent(
        interaction_type=MessagingInteractionType.SEND_INCIDENT_ALERT_NOTIFICATION,
        spec=DiscordMessagingSpec(),
    ).capture() as lifecycle:
        try:
            client.send_message(channel, message)
        except ApiError as error:
            # Errors that we recieve from the Discord API
            record_lifecycle_termination_level(lifecycle, error)
            return False
        except Exception as error:
            lifecycle.add_extras(
                {
                    "incident_id": incident.id,
                    "channel_id": channel,
                }
            )

            lifecycle.record_failure(error)
            return False
        return True
