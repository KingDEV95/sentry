from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Self
from uuid import uuid4

from django.apps import apps
from django.db import models
from django.utils import timezone

from sentry.backup.scopes import RelocationScope
from sentry.db.models import (
    BoundedBigIntegerField,
    JSONField,
    Model,
    control_silo_model,
    region_silo_model,
)
from sentry.deletions import RELOCATED_MODELS
from sentry.silo.base import SiloLimit, SiloMode
from sentry.users.services.user import RpcUser
from sentry.users.services.user.service import user_service

delete_logger = logging.getLogger("sentry.deletions.api")


def default_guid() -> str:
    return uuid4().hex


def default_date_schedule() -> datetime:
    return timezone.now() + timedelta(days=30)


class BaseScheduledDeletion(Model):
    """
    ScheduledDeletions are, well, relations to arbitrary records in a particular silo that are due for deletion by
    the tasks/deletion/scheduled.py job in the future.  They are cancellable, and provide automatic, batched cascade
    in an async way for performance reasons.

    Note that BOTH region AND control silos need to be able to schedule deletions of different records that will be
    reconciled in different places.  For that reason, the ScheduledDeletion model is split into two identical models
    representing this split.  Use the corresponding ScheduledDeletion based on the silo of the model being scheduled
    for deletion.
    """

    class Meta:
        abstract = True

    __relocation_scope__ = RelocationScope.Excluded

    guid = models.CharField(max_length=32, unique=True, default=default_guid)
    app_label = models.CharField(max_length=64)
    model_name = models.CharField(max_length=64)
    object_id = BoundedBigIntegerField()
    date_added = models.DateTimeField(default=timezone.now)
    date_scheduled = models.DateTimeField(default=default_date_schedule)
    actor_id = BoundedBigIntegerField(null=True)
    data = JSONField(default=dict)
    in_progress = models.BooleanField(default=False)

    @classmethod
    def schedule(
        cls, instance: Model, days: int = 30, hours: int = 0, data: Any = None, actor: Any = None
    ) -> Self:
        model = type(instance)
        silo_mode = SiloMode.get_current_mode()
        model_silo = getattr(model._meta, "silo_limit", None)
        assert (
            model_silo
        ), "model._meta.silo_limit undefined. This model cannot be used with deletions"
        if silo_mode not in model_silo.modes and silo_mode != SiloMode.MONOLITH:
            # Pre-empt the fact that our silo protections wouldn't fire for mismatched model <-> silo deletion objects.
            raise SiloLimit.AvailabilityError(
                f"{model!r} was scheduled for deletion by {cls!r}, but is unavailable in {silo_mode!r}"
            )

        model_name = model.__name__
        record, created = cls.objects.update_or_create(
            app_label=instance._meta.app_label,
            model_name=model_name,
            object_id=instance.pk,
            defaults={
                "date_scheduled": timezone.now() + timedelta(days=days, hours=hours),
                "data": data or {},
                "actor_id": actor.id if actor else None,
            },
        )

        delete_logger.info(
            "object.delete.queued",
            extra={
                "object_id": instance.id,
                "transaction_id": record.guid,
                "model": type(instance).__name__,
            },
        )
        return record

    @classmethod
    def cancel(cls, instance: Model) -> None:
        model_name = type(instance).__name__
        try:
            deletion = cls.objects.get(
                model_name=model_name, object_id=instance.pk, in_progress=False
            )
        except cls.DoesNotExist:
            delete_logger.info(
                "object.delete.canceled.failed",
                extra={"object_id": instance.pk, "model": model_name},
            )
            return

        deletion.delete()
        delete_logger.info(
            "object.delete.canceled",
            extra={"object_id": instance.pk, "model": model_name},
        )

    def get_model(self) -> type[Any]:
        key = (self.app_label, self.model_name)
        app_label, model_name = RELOCATED_MODELS.get(key, key)
        return apps.get_model(app_label, model_name)

    def get_instance(self) -> Model:
        from sentry import deletions
        from sentry.deletions.base import ModelDeletionTask

        model = self.get_model()
        deletion_task = deletions.get(model=model, query=None)
        query_manager = model.objects
        if isinstance(deletion_task, ModelDeletionTask):
            query_manager = getattr(model, deletion_task.manager_name)
        return query_manager.get(pk=self.object_id)

    def get_actor(self) -> RpcUser | None:
        if not self.actor_id:
            return None

        return user_service.get_user(user_id=self.actor_id)


@control_silo_model
class ScheduledDeletion(BaseScheduledDeletion):
    """
    This model schedules deletions to be processed in control and monolith silo modes.  All historic schedule deletions
    occur in this table.  In the future, when RegionScheduledDeletions have proliferated for the appropriate models,
    we will allow any region models scheduled in this table to finish processing before ensuring that all models discretely
    process in either this table or the region table.
    """

    class Meta:
        unique_together = (("app_label", "model_name", "object_id"),)
        app_label = "sentry"
        db_table = "sentry_scheduleddeletion"


@region_silo_model
class RegionScheduledDeletion(BaseScheduledDeletion):
    """
    This model schedules deletions to be processed in region and monolith silo modes.  As new region silo test coverage
    increases, new scheduled deletions will begin to occur in this table.  Monolith (current saas) will continue
    processing them alongside the original scheduleddeletions table, but in the future this table will only be
    processed by region silos.
    """

    class Meta:
        unique_together = (("app_label", "model_name", "object_id"),)
        app_label = "sentry"
        db_table = "sentry_regionscheduleddeletion"


def get_regional_scheduled_deletion(mode: SiloMode) -> type[BaseScheduledDeletion]:
    if mode != SiloMode.CONTROL:
        return RegionScheduledDeletion
    return ScheduledDeletion
