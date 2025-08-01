from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal
from uuid import uuid4

import sentry_sdk
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import audit_log
from sentry.api.base import audit_logger
from sentry.deletions.defaults.group import GROUP_CHUNK_SIZE
from sentry.deletions.tasks.groups import delete_groups_for_project
from sentry.issues.grouptype import GroupCategory
from sentry.models.group import Group, GroupStatus
from sentry.models.grouphash import GroupHash
from sentry.models.groupinbox import GroupInbox
from sentry.models.project import Project
from sentry.signals import issue_deleted
from sentry.tasks.delete_seer_grouping_records import may_schedule_task_to_delete_hashes_from_seer
from sentry.utils.audit import create_audit_entry

from . import BULK_MUTATION_LIMIT, SearchFunction
from .validators import ValidationError

delete_logger = logging.getLogger("sentry.deletions.api")


def delete_group_list(
    request: Request,
    project: Project,
    group_list: list[Group],
    delete_type: Literal["delete", "discard"],
) -> None:
    """Deletes a list of groups which belong to a single project.

    :param request: The request object.
    :param project: The project the groups belong to.
    :param group_list: The list of groups to delete.
    :param delete_type: The type of deletion to perform. This is used to determine the type of audit log to create.
    """
    if not group_list:
        return

    # deterministic sort for sanity, and for very large deletions we'll
    # delete the "smaller" groups first
    group_list.sort(key=lambda g: (g.times_seen, g.id))

    # Assert that all groups belong to the same project
    if not all(g.project_id == project.id for g in group_list):
        raise ValueError("All groups must belong to the same project")

    group_ids = []
    error_ids = []
    for g in group_list:
        group_ids.append(g.id)
        if g.issue_category == GroupCategory.ERROR:
            error_ids.append(g.id)

    transaction_id = uuid4().hex
    delete_logger.info(
        "object.delete.api",
        extra={
            "objects": group_ids,
            "project_id": project.id,
            "transaction_id": transaction_id,
        },
    )
    # The tags can be used if we want to find errors for when a task fails
    sentry_sdk.set_tags(
        {
            "project_id": project.id,
            "transaction_id": transaction_id,
            "group_deletion_project_id": project.id,
            "group_deletion_group_ids": str(group_ids),
        },
    )

    # Tell seer to delete grouping records for these groups
    may_schedule_task_to_delete_hashes_from_seer(error_ids)

    Group.objects.filter(id__in=group_ids).exclude(
        status__in=[GroupStatus.PENDING_DELETION, GroupStatus.DELETION_IN_PROGRESS]
    ).update(status=GroupStatus.PENDING_DELETION, substatus=None)

    # The moment groups are marked as pending deletion, we create audit entries
    # so that we can see who requested the deletion. Even if anything after this point
    # fails, we will still have a record of who requested the deletion.
    create_audit_entries(request, project, group_list, delete_type, transaction_id)

    # Removing GroupHash rows prevents new events from associating to the groups
    # we just deleted.
    GroupHash.objects.filter(project_id=project.id, group__id__in=group_ids).delete()

    # We remove `GroupInbox` rows here so that they don't end up influencing queries for
    # `Group` instances that are pending deletion
    GroupInbox.objects.filter(project_id=project.id, group__id__in=group_ids).delete()

    # Schedule a task per GROUP_CHUNK_SIZE batch of groups
    for i in range(0, len(group_ids), GROUP_CHUNK_SIZE):
        delete_groups_for_project.apply_async(
            kwargs={
                "project_id": project.id,
                "object_ids": group_ids[i : i + GROUP_CHUNK_SIZE],
                "transaction_id": str(transaction_id),
            }
        )


def create_audit_entries(
    request: Request,
    project: Project,
    group_list: Sequence[Group],
    delete_type: Literal["delete", "discard"],
    transaction_id: str,
) -> None:
    for group in group_list:
        create_audit_entry(
            request=request,
            transaction_id=transaction_id,
            logger=audit_logger,
            organization_id=project.organization_id,
            target_object=group.id,
            event=audit_log.get_event_id("ISSUE_DELETE"),
            data={
                "issue_id": group.id,
                "project_slug": project.slug,
            },
        )

        issue_deleted.send_robust(
            group=group, user=request.user, delete_type=delete_type, sender=delete_group_list
        )


def schedule_tasks_to_delete_groups(
    request: Request,
    projects: Sequence[Project],
    organization_id: int,
    search_fn: SearchFunction | None = None,
) -> Response:
    """
    `search_fn` refers to the `search.query` method with the appropriate
    project, org, environment, and search params already bound
    """
    group_ids = request.GET.getlist("id")
    if group_ids:
        group_list = list(
            Group.objects.filter(
                project__in=projects,
                project__organization_id=organization_id,
                id__in=set(group_ids),
            ).exclude(status__in=[GroupStatus.PENDING_DELETION, GroupStatus.DELETION_IN_PROGRESS])
        )
    elif search_fn:
        try:
            cursor_result, _ = search_fn(
                {
                    "limit": BULK_MUTATION_LIMIT,
                    "paginator_options": {"max_limit": BULK_MUTATION_LIMIT},
                }
            )
        except ValidationError as exc:
            return Response({"detail": str(exc)}, status=400)

        group_list = list(cursor_result)

    if not group_list:
        return Response(status=204)

    groups_by_project_id = defaultdict(list)
    for group in group_list:
        groups_by_project_id[group.project_id].append(group)

    for project in sorted(projects, key=lambda p: p.id):
        delete_group_list(
            request, project, groups_by_project_id.get(project.id, []), delete_type="delete"
        )

    return Response(status=204)
