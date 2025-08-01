from __future__ import annotations

from functools import cached_property
from typing import Any

import orjson
import responses
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.urls import reverse

from sentry.testutils.cases import TestCase
from sentry_plugins.jira.plugin import JiraPlugin

create_meta_response = {
    "expand": "projects",
    "projects": [
        {
            "expand": "issuetypes",
            "self": "https://getsentry.atlassian.net/rest/api/2/project/10000",
            "id": "10000",
            "key": "SEN",
            "name": "Sentry",
            "avatarUrls": {
                "48x48": "https://getsentry.atlassian.net/secure/projectavatar?avatarId=10324",
                "24x24": "https://getsentry.atlassian.net/secure/projectavatar?size=small&avatarId=10324",
                "16x16": "https://getsentry.atlassian.net/secure/projectavatar?size=xsmall&avatarId=10324",
                "32x32": "https://getsentry.atlassian.net/secure/projectavatar?size=medium&avatarId=10324",
            },
            "issuetypes": [
                {
                    "self": "https://getsentry.atlassian.net/rest/api/2/issuetype/10002",
                    "id": "10002",
                    "description": "A task that needs to be done.",
                    "iconUrl": "https://getsentry.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
                    "name": "Task",
                    "subtask": False,
                    "expand": "fields",
                    "fields": {
                        "summary": {
                            "required": True,
                            "schema": {"type": "string", "system": "summary"},
                            "name": "Summary",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                        },
                        "issuetype": {
                            "required": True,
                            "schema": {"type": "issuetype", "system": "issuetype"},
                            "name": "Issue Type",
                            "hasDefaultValue": False,
                            "operations": [],
                            "allowedValues": [
                                {
                                    "self": "https://getsentry.atlassian.net/rest/api/2/issuetype/10002",
                                    "id": "10002",
                                    "description": "A task that needs to be done.",
                                    "iconUrl": "https://getsentry.atlassian.net/secure/viewavatar?size=xsmall&avatarId=10318&avatarType=issuetype",
                                    "name": "Task",
                                    "subtask": False,
                                    "avatarId": 10318,
                                }
                            ],
                        },
                        "components": {
                            "required": False,
                            "schema": {
                                "type": "array",
                                "items": "component",
                                "system": "components",
                            },
                            "name": "Component/s",
                            "hasDefaultValue": False,
                            "operations": ["add", "set", "remove"],
                            "allowedValues": [],
                        },
                        "description": {
                            "required": False,
                            "schema": {"type": "string", "system": "description"},
                            "name": "Description",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                        },
                        "project": {
                            "required": True,
                            "schema": {"type": "project", "system": "project"},
                            "name": "Project",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                            "allowedValues": [
                                {
                                    "self": "https://getsentry.atlassian.net/rest/api/2/project/10000",
                                    "id": "10000",
                                    "key": "SEN",
                                    "name": "Sentry",
                                    "avatarUrls": {
                                        "48x48": "https://getsentry.atlassian.net/secure/projectavatar?avatarId=10324",
                                        "24x24": "https://getsentry.atlassian.net/secure/projectavatar?size=small&avatarId=10324",
                                        "16x16": "https://getsentry.atlassian.net/secure/projectavatar?size=xsmall&avatarId=10324",
                                        "32x32": "https://getsentry.atlassian.net/secure/projectavatar?size=medium&avatarId=10324",
                                    },
                                }
                            ],
                        },
                        "reporter": {
                            "required": True,
                            "schema": {"type": "user", "system": "reporter"},
                            "name": "Reporter",
                            "autoCompleteUrl": "https://getsentry.atlassian.net/rest/api/latest/user/search?username=",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                        },
                        "fixVersions": {
                            "required": False,
                            "schema": {
                                "type": "array",
                                "items": "version",
                                "system": "fixVersions",
                            },
                            "name": "Fix Version/s",
                            "hasDefaultValue": False,
                            "operations": ["set", "add", "remove"],
                            "allowedValues": [],
                        },
                        "priority": {
                            "required": False,
                            "schema": {"type": "priority", "system": "priority"},
                            "name": "Priority",
                            "hasDefaultValue": True,
                            "operations": ["set"],
                            "allowedValues": [
                                {
                                    "self": "https://getsentry.atlassian.net/rest/api/2/priority/1",
                                    "iconUrl": "https://getsentry.atlassian.net/images/icons/priorities/highest.svg",
                                    "name": "Highest",
                                    "id": "1",
                                }
                            ],
                        },
                        "customfield_10003": {
                            "required": False,
                            "schema": {
                                "type": "array",
                                "items": "string",
                                "custom": "com.pyxis.greenhopper.jira:gh-sprint",
                                "customId": 10003,
                            },
                            "name": "Sprint",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                        },
                        "labels": {
                            "required": False,
                            "schema": {"type": "array", "items": "string", "system": "labels"},
                            "name": "Labels",
                            "autoCompleteUrl": "https://getsentry.atlassian.net/rest/api/1.0/labels/suggest?query=",
                            "hasDefaultValue": False,
                            "operations": ["add", "set", "remove"],
                        },
                        "attachment": {
                            "required": False,
                            "schema": {
                                "type": "array",
                                "items": "attachment",
                                "system": "attachment",
                            },
                            "name": "Attachment",
                            "hasDefaultValue": False,
                            "operations": [],
                        },
                        "assignee": {
                            "required": False,
                            "schema": {"type": "user", "system": "assignee"},
                            "name": "Assignee",
                            "autoCompleteUrl": "https://getsentry.atlassian.net/rest/api/latest/user/assignable/search?issueKey=null&username=",
                            "hasDefaultValue": False,
                            "operations": ["set"],
                        },
                    },
                }
            ],
        }
    ],
}

issue_response: dict[str, Any] = {
    "key": "SEN-19",
    "id": "10708",
    "fields": {"summary": "TypeError: 'set' object has no attribute '__getitem__'"},
}

user_search_response: list[dict[str, Any]] = [
    {
        "self": "https://getsentry.atlassian.net/rest/api/2/user?username=userexample",
        "key": "JIRAUSER10100",
        "name": "userexample",
        "emailAddress": "user@example.com",
        "avatarUrls": {
            "48x48": "http://www.example.com/jira/secure/useravatar?size=large&ownerId=andrew",
            "24x24": "http://www.example.com/jira/secure/useravatar?size=small&ownerId=andrew",
            "16x16": "http://www.example.com/jira/secure/useravatar?size=xsmall&ownerId=andrew",
            "32x32": "http://www.example.com/jira/secure/useravatar?size=medium&ownerId=andrew",
        },
        "displayName": "User Example",
        "active": True,
        "deleted": False,
        "timeZone": "Europe/Vienna",
        "locale": "en_US",
        "lastLoginTime": "2024-06-24T12:15:00+0200",
    }
]


class JiraPluginTest(TestCase):
    @cached_property
    def plugin(self):
        return JiraPlugin()

    @cached_property
    def request(self):
        return RequestFactory()

    def test_conf_key(self) -> None:
        assert self.plugin.conf_key == "jira"

    def test_get_issue_label(self) -> None:
        group = self.create_group(message="Hello world", culprit="foo.bar")
        assert self.plugin.get_issue_label(group, "SEN-1") == "SEN-1"

    def test_get_issue_url(self) -> None:
        self.plugin.set_option("instance_url", "https://getsentry.atlassian.net", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")
        assert (
            self.plugin.get_issue_url(group, "SEN-1")
            == "https://getsentry.atlassian.net/browse/SEN-1"
        )

    def test_is_configured(self) -> None:
        assert self.plugin.is_configured(self.project) is False
        self.plugin.set_option("default_project", "SEN", self.project)
        assert self.plugin.is_configured(self.project) is True

    @responses.activate
    def test_create_issue(self) -> None:
        responses.add(
            responses.GET,
            "https://getsentry.atlassian.net/rest/api/2/issue/createmeta",
            json=create_meta_response,
        )
        responses.add(
            responses.POST,
            "https://getsentry.atlassian.net/rest/api/2/issue",
            json={"key": "SEN-1"},
        )
        self.plugin.set_option("instance_url", "https://getsentry.atlassian.net", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")

        request = self.request.get("/")
        request.user = AnonymousUser()
        form_data = {
            "title": "Hello",
            "description": "Fix this.",
            "issuetype": "bug",
            "project": "SEN",
        }
        assert self.plugin.create_issue(request, group, form_data) == "SEN-1"

    @responses.activate
    def test_link_issue(self) -> None:
        responses.add(
            responses.GET,
            "https://getsentry.atlassian.net/rest/api/2/issue/SEN-19",
            json=issue_response,
        )
        self.plugin.set_option("instance_url", "https://getsentry.atlassian.net", self.project)
        group = self.create_group(message="Hello world", culprit="foo.bar")

        request = self.request.get("/")
        request.user = AnonymousUser()
        form_data = {"issue_id": "SEN-19"}
        assert (
            self.plugin.link_issue(request, group, form_data)["title"]
            == issue_response["fields"]["summary"]
        )

    def test_no_secrets(self) -> None:
        self.user = self.create_user("foo@example.com")
        self.org = self.create_organization(owner=self.user, name="Rowdy Tiger")
        self.team = self.create_team(organization=self.org, name="Mariachi Band")
        self.project = self.create_project(organization=self.org, teams=[self.team], name="Bengal")
        self.login_as(self.user)
        self.plugin.set_option("password", "abcdef", self.project)
        url = reverse(
            "sentry-api-0-project-plugin-details", args=[self.org.slug, self.project.slug, "jira"]
        )
        res = self.client.get(url)
        config = orjson.loads(res.content)["config"]
        password_config = [item for item in config if item["name"] == "password"][0]
        assert password_config.get("type") == "secret"
        assert password_config.get("value") is None
        assert password_config.get("hasSavedValue") is True
        assert password_config.get("prefix") == ""

    def test_get_formatted_user(self) -> None:
        assert self.plugin._get_formatted_user(
            {"displayName": "Foo Bar", "emailAddress": "foo@sentry.io", "name": "foobar"}
        ) == {"text": "Foo Bar - foo@sentry.io (foobar)", "id": "foobar"}

        # test weird addon users that don't have email addresses
        assert self.plugin._get_formatted_user(
            {
                "name": "robot",
                "avatarUrls": {
                    "16x16": "https://avatar-cdn.atlassian.com/someid",
                    "24x24": "https://avatar-cdn.atlassian.com/someotherid",
                },
                "self": "https://something.atlassian.net/rest/api/2/user?username=someaddon",
            }
        ) == {"id": "robot", "text": "robot (robot)"}

    def _setup_autocomplete_jira(self):
        self.plugin.set_option("instance_url", "https://getsentry.atlassian.net", self.project)
        self.plugin.set_option("default_project", "SEN", self.project)
        self.login_as(user=self.user)
        self.group = self.create_group(message="Hello world", culprit="foo.bar")

    @responses.activate
    def test_autocomplete_issue_id(self) -> None:
        self._setup_autocomplete_jira()
        responses.add(
            responses.GET,
            "https://getsentry.atlassian.net/rest/api/2/search/",
            json={"issues": [issue_response]},
        )

        url = f"/api/0/issues/{self.group.id}/plugins/jira/autocomplete/?autocomplete_query=SEN&autocomplete_field=issue_id"
        response = self.client.get(url)

        assert response.json() == {
            "issue_id": [
                {
                    "text": "(SEN-19) TypeError: 'set' object has no attribute '__getitem__'",
                    "id": "SEN-19",
                }
            ]
        }

    @responses.activate
    def test_autocomplete_jira_url_reporter(self) -> None:
        self._setup_autocomplete_jira()

        responses.add(
            responses.GET,
            "https://getsentry.atlassian.net/rest/api/2/user/search/?username=user&project=SEN",
            json=user_search_response,
        )

        url = f"/api/0/issues/{self.group.id}/plugins/jira/autocomplete/?autocomplete_query=user&autocomplete_field=reporter&jira_url=https://getsentry.atlassian.net/rest/api/2/user/search/"
        response = self.client.get(url)
        assert response.json() == {
            "reporter": [
                {"id": "userexample", "text": "User Example - user@example.com (userexample)"}
            ]
        }

    def test_autocomplete_jira_url_missing(self) -> None:
        self._setup_autocomplete_jira()

        url = f"/api/0/issues/{self.group.id}/plugins/jira/autocomplete/?autocomplete_query=SEN&autocomplete_field=reporter"
        response = self.client.get(url)
        assert response.json() == {
            "error_type": "validation",
            "errors": [{"jira_url": "missing required parameter"}],
        }

    def test_autocomplete_jira_url_mismatch(self) -> None:
        self._setup_autocomplete_jira()

        url = f"/api/0/issues/{self.group.id}/plugins/jira/autocomplete/?autocomplete_query=SEN&autocomplete_field=reporter&jira_url=https://eviljira.com/"
        response = self.client.get(url)
        assert response.json() == {
            "error_type": "validation",
            "errors": [{"jira_url": "domain must match"}],
        }
