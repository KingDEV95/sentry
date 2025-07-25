from __future__ import annotations

import datetime
from typing import Any, Self

from django.db import models
from django.db.models import Case, ExpressionWrapper, F, IntegerField, Q, TextChoices, Value, When
from django.http import HttpRequest
from django.utils import timezone

from sentry.backup.scopes import RelocationScope
from sentry.db.models import Model, control_silo_model, sane_repr
from sentry.utils import json, metrics

THE_PAST = datetime.datetime(2016, 8, 1, 0, 0, 0, 0, tzinfo=datetime.UTC)
MAX_ATTEMPTS = 10

BACKOFF_INTERVAL = 3
BACKOFF_RATE = 1.4


class DestinationType(TextChoices):
    SENTRY_REGION = "sentry_region"
    CODECOV = "codecov"


@control_silo_model
class WebhookPayload(Model):
    __relocation_scope__ = RelocationScope.Excluded

    mailbox_name = models.CharField(null=False, blank=False)
    provider = models.CharField(null=True, blank=True)

    # Destination attributes
    # Table is constantly being deleted from so let's make this non-nullable with a default value, since the table should be small at any given point in time.
    destination_type = models.CharField(
        choices=DestinationType.choices, null=False, db_default=DestinationType.SENTRY_REGION
    )
    region_name = models.CharField(null=True)

    # May need to add organization_id in the future for debugging.
    integration_id = models.BigIntegerField(null=True)

    date_added = models.DateTimeField(default=timezone.now, null=False)

    # Scheduling attributes
    schedule_for = models.DateTimeField(default=THE_PAST, null=False)
    attempts = models.IntegerField(default=0, null=False)

    # payload attributes
    request_method = models.CharField(null=False)
    request_path = models.CharField(null=False)
    request_headers = models.TextField()
    request_body = models.TextField()

    class Meta:
        app_label = "hybridcloud"
        db_table = "hybridcloud_webhookpayload"

        indexes = (
            models.Index(fields=["mailbox_name"]),
            models.Index(fields=["schedule_for"]),
            models.Index(fields=["provider"], name="webhookpayload_provider_idx"),
            models.Index(
                fields=["mailbox_name", "id"],
                name="webhookpayload_mailbox_id_idx",
            ),
            models.Index(
                ExpressionWrapper(
                    Case(
                        When(provider="stripe", then=Value(1)),
                        default=Value(10),
                        output_field=IntegerField(),
                    ),
                    output_field=IntegerField(),
                ),
                F("id"),
                name="webhookpayload_priority_idx",
            ),
        )

        constraints = [
            models.CheckConstraint(
                condition=~Q(destination_type=DestinationType.SENTRY_REGION)
                | Q(region_name__isnull=False),
                name="webhookpayload_region_name_not_null",
            ),
        ]

    __repr__ = sane_repr(
        "mailbox_name",
        "destination_type",
        "region_name",
        "schedule_for",
        "attempts",
        "integration_id",
        "request_method",
        "request_path",
    )

    @classmethod
    def get_attributes_from_request(
        cls,
        request: HttpRequest,
    ) -> dict[str, Any]:
        return dict(
            request_method=request.method,
            request_path=request.get_full_path(),
            request_headers=json.dumps({k: v for k, v in request.headers.items()}),
            request_body=request.body.decode(encoding="utf-8"),
        )

    @classmethod
    def create_from_request(
        cls,
        *,
        region: str,
        provider: str,
        identifier: int | str,
        request: HttpRequest,
        integration_id: int | None = None,
    ) -> Self:
        metrics.incr("hybridcloud.deliver_webhooks.saved")
        return cls.objects.create(
            mailbox_name=f"{provider}:{identifier}",
            provider=provider,
            region_name=region,
            integration_id=integration_id,
            **cls.get_attributes_from_request(request),
        )

    def schedule_next_attempt(self) -> None:
        attempts = self.attempts + 1
        backoff = BACKOFF_INTERVAL * BACKOFF_RATE**attempts
        backoff_delta = datetime.timedelta(minutes=min(backoff, 60))
        new_time = timezone.now() + backoff_delta

        self.update(attempts=attempts, schedule_for=max(new_time, self.schedule_for))
