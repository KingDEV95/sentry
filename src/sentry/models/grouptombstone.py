from __future__ import annotations

import logging
from typing import Any

from django.db import models
from django.utils import timezone

from sentry.backup.scopes import RelocationScope
from sentry.constants import LOG_LEVELS, MAX_CULPRIT_LENGTH
from sentry.db.models import (
    BoundedBigIntegerField,
    BoundedPositiveIntegerField,
    FlexibleForeignKey,
    GzippedDictField,
    Model,
    region_silo_model,
)

TOMBSTONE_FIELDS_FROM_GROUP = ("project_id", "level", "message", "culprit", "data")


@region_silo_model
class GroupTombstone(Model):
    __relocation_scope__ = RelocationScope.Excluded

    # Will be null for tombstones created before January 2025
    date_added = models.DateTimeField(default=timezone.now, null=True)
    previous_group_id = BoundedBigIntegerField(unique=True)
    project = FlexibleForeignKey("sentry.Project")
    level = BoundedPositiveIntegerField(
        choices=[(key, str(val)) for key, val in sorted(LOG_LEVELS.items())],
        default=logging.ERROR,
        blank=True,
    )
    message = models.TextField()
    culprit = models.CharField(max_length=MAX_CULPRIT_LENGTH, blank=True, null=True)
    data: models.Field[dict[str, Any] | None, dict[str, Any]] = GzippedDictField(
        blank=True, null=True
    )
    actor_id = BoundedPositiveIntegerField(null=True)
    times_seen = BoundedPositiveIntegerField(db_default=0)
    last_seen = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_grouptombstone"

    def get_event_type(self):
        """
        Return the type of this issue.

        See ``sentry.eventtypes``.
        """
        return self.data.get("type", "default")

    def get_event_metadata(self):
        """
        Return the metadata of this issue.

        See ``sentry.eventtypes``.
        """
        return self.data["metadata"]
