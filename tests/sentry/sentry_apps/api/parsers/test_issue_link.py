from __future__ import annotations

import unittest
from typing import Any

from fixtures.schema_validation import invalid_schema
from sentry.sentry_apps.api.parsers.schema import validate_component


class TestIssueLinkSchemaValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.schema: dict[str, Any] = {
            "type": "issue-link",
            "link": {
                "uri": "/sentry/tasks/link",
                "required_fields": [
                    {
                        "type": "select",
                        "name": "task_id",
                        "label": "Task ID",
                        "uri": "/sentry/tasks",
                    }
                ],
                "optional_fields": [{"type": "text", "name": "owner", "label": "Owner"}],
            },
            "create": {
                "uri": "/sentry/tasks/create",
                "required_fields": [
                    {"type": "text", "name": "title", "label": "Title"},
                    {"type": "text", "name": "description", "label": "Description"},
                    {
                        "type": "select",
                        "uri": "/sentry/tasks/projects",
                        "name": "project_id",
                        "label": "Project",
                    },
                    {
                        "depends_on": ["project_id"],
                        "type": "select",
                        "uri": "/sentry/tasks/boards",
                        "name": "board_id",
                        "label": "Board",
                    },
                ],
                "optional_fields": [{"type": "text", "name": "owner", "label": "Owner"}],
            },
        }

    def test_valid_schema(self) -> None:
        validate_component(self.schema)

    @invalid_schema
    def test_missing_create_fails(self) -> None:
        del self.schema["create"]
        validate_component(self.schema)

    @invalid_schema
    def test_missing_create_uri(self) -> None:
        del self.schema["create"]["uri"]
        validate_component(self.schema)

    @invalid_schema
    def test_missing_create_required_fields(self) -> None:
        del self.schema["create"]["required_fields"]
        validate_component(self.schema)

    @invalid_schema
    def test_create_required_fields_no_elements(self) -> None:
        self.schema["create"]["required_fields"] = []
        validate_component(self.schema)

    @invalid_schema
    def test_create_required_fields_invalid_element(self) -> None:
        self.schema["create"]["required_fields"] = [{"type": "markdown"}]
        validate_component(self.schema)

    def test_missing_create_optional_fields(self) -> None:
        del self.schema["create"]["optional_fields"]
        validate_component(self.schema)

    @invalid_schema
    def test_create_optional_fields_invalid_element(self) -> None:
        self.schema["create"]["optional_fields"] = [{"type": "markdown"}]
        validate_component(self.schema)

    @invalid_schema
    def test_missing_link(self) -> None:
        del self.schema["link"]
        validate_component(self.schema)

    @invalid_schema
    def test_missing_link_uri(self) -> None:
        del self.schema["link"]["uri"]
        validate_component(self.schema)

    @invalid_schema
    def test_missing_link_required_fields(self) -> None:
        del self.schema["link"]["required_fields"]
        validate_component(self.schema)

    def test_missing_link_optional_fields(self) -> None:
        del self.schema["link"]["optional_fields"]
        validate_component(self.schema)

    @invalid_schema
    def test_invalid_async_option(self) -> None:
        self.schema["create"]["required_fields"][2]["async"] = "cat"
        validate_component(self.schema)

    @invalid_schema
    def test_invalid_skip_load_on_open_option(self) -> None:
        self.schema["create"]["required_fields"][2]["skip_load_on_open"] = "cat"
        validate_component(self.schema)
