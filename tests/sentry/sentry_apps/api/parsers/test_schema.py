import unittest

from fixtures.schema_validation import invalid_schema_with_error_message
from sentry.sentry_apps.api.parsers.schema import validate_ui_element_schema


class TestSchemaValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = {
            "elements": [
                {
                    "type": "issue-link",
                    "link": {
                        "uri": "/sentry/issues/link",
                        "required_fields": [
                            {
                                "type": "select",
                                "name": "assignee",
                                "label": "Assignee",
                                "uri": "/sentry/members",
                            }
                        ],
                    },
                    "create": {
                        "uri": "/sentry/issues/create",
                        "required_fields": [
                            {"type": "text", "name": "title", "label": "Title"},
                            {"type": "text", "name": "summary", "label": "Summary"},
                        ],
                        "optional_fields": [
                            {
                                "type": "select",
                                "name": "points",
                                "label": "Points",
                                "options": [
                                    ["1", "1"],
                                    ["2", "2"],
                                    ["3", "3"],
                                    ["5", "5"],
                                    ["8", "8"],
                                ],
                            },
                            {
                                "type": "select",
                                "name": "assignee",
                                "label": "Assignee",
                                "uri": "/sentry/members",
                            },
                        ],
                    },
                },
                {
                    "type": "alert-rule-action",
                    "title": "Create task",
                    "settings": {
                        "type": "alert-rule-settings",
                        "uri": "/sentry/alert-rule",
                        "required_fields": [
                            {"type": "text", "name": "channel", "label": "Channel"},
                            {
                                "type": "select",
                                "name": "send_email",
                                "label": "Send Email?",
                                "options": [["Yes", "yes"], ["No", "no"]],
                            },
                        ],
                    },
                },
                {
                    "type": "issue-media",
                    "title": "Feature Demo",
                    "elements": [{"type": "video", "url": "/sentry/issues/video"}],
                },
                {"type": "stacktrace-link", "uri": "/sentry/issue"},
            ]
        }

    def test_valid_schema_with_options(self) -> None:
        validate_ui_element_schema(self.schema)

    @invalid_schema_with_error_message("'elements' is a required property")
    def test_invalid_schema_elements_missing(self) -> None:
        schema = {"type": "nothing"}
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message("'elements' should be an array of objects")
    def test_invalid_schema_elements_not_array(self) -> None:
        schema = {"elements": {"type": "issue-link"}}
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message("Each element needs a 'type' field")
    def test_invalid_schema_type_missing(self) -> None:
        schema = {"elements": [{"key": "issue-link"}]}
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message(
        "Element has type 'other'. Type must be one of the following: ['issue-link', 'alert-rule-action', 'issue-media', 'stacktrace-link']"
    )
    def test_invalid_schema_type_invalid(self) -> None:
        schema = {"elements": [{"type": "other"}]}
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message(
        "'uri' is a required property for element of type 'stacktrace-link'"
    )
    def test_invalid_schema_element_missing_uri(self) -> None:
        schema = {
            "elements": [{"url": "/stacktrace/github/getsentry/sentry", "type": "stacktrace-link"}]
        }
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message("Multiple elements of type: stacktrace-link")
    def test_multiple_of_same_element_type(self) -> None:
        schema = {
            "elements": [
                {"uri": "/stacktrace/github/getsentry/sentry", "type": "stacktrace-link"},
                {"uri": "/stacktrace/github/getsentry/sentry", "type": "stacktrace-link"},
            ]
        }
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message(
        "Elements of type ['text', 'textarea'] may only have a default value of the following: ['issue.title', 'issue.description'], but issue.something was found."
    )
    def test_invalid_textarea_default_value(self) -> None:
        schema = {
            "elements": [
                {
                    "type": "alert-rule-action",
                    "title": "Mudpuppy",
                    "settings": {
                        "type": "alert-rule-settings",
                        "uri": "/alert-rule-action",
                        "required_fields": [
                            {
                                "label": "Team",
                                "type": "textarea",
                                "name": "teamId",
                                "default": "issue.something",
                            }
                        ],
                    },
                }
            ]
        }
        validate_ui_element_schema(schema)

    @invalid_schema_with_error_message(
        "Elements of type ['text', 'textarea'] may only have a default value of the following: ['issue.title', 'issue.description'], but issue.someone was found."
    )
    def test_invalid_text_default_value(self) -> None:
        schema = {
            "elements": [
                {
                    "type": "alert-rule-action",
                    "title": "Tater Tots",
                    "settings": {
                        "type": "alert-rule-settings",
                        "uri": "/alert-rule-action",
                        "optional_fields": [
                            {
                                "label": "Team",
                                "type": "text",
                                "name": "teamId",
                                "default": "issue.someone",
                            }
                        ],
                    },
                }
            ]
        }
        validate_ui_element_schema(schema)
