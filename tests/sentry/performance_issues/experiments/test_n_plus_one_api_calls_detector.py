from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from sentry.issues.grouptype import PerformanceNPlusOneAPICallsExperimentalGroupType
from sentry.performance_issues.base import DetectorType, parameterize_url
from sentry.performance_issues.detectors.experiments.n_plus_one_api_calls_detector import (
    NPlusOneAPICallsExperimentalDetector,
)
from sentry.performance_issues.performance_detection import (
    get_detection_settings,
    run_detector_on_data,
)
from sentry.performance_issues.performance_problem import PerformanceProblem
from sentry.testutils.cases import TestCase
from sentry.testutils.performance_issues.event_generators import (
    create_event,
    create_span,
    get_event,
)


@pytest.mark.django_db
class NPlusOneAPICallsExperimentalDetectorTest(TestCase):
    type_id = PerformanceNPlusOneAPICallsExperimentalGroupType.type_id

    def setUp(self) -> None:
        super().setUp()
        self._settings = get_detection_settings()

    def find_problems(self, event: dict[str, Any]) -> list[PerformanceProblem]:
        detector = NPlusOneAPICallsExperimentalDetector(self._settings, event)
        run_detector_on_data(detector, event)
        return list(detector.stored_problems.values())

    def create_event(self, description_maker: Callable[[int], str]) -> dict[str, Any]:
        total_duration = (
            self._settings[DetectorType.EXPERIMENTAL_N_PLUS_ONE_API_CALLS]["total_duration"] + 1
        )
        count = self._settings[DetectorType.EXPERIMENTAL_N_PLUS_ONE_API_CALLS]["count"] + 1
        hash = uuid4().hex[:16]

        return create_event(
            [
                create_span(
                    "http.client",
                    total_duration / count,
                    description_maker(i),
                    hash=hash,
                )
                for i in range(count)
            ]
        )

    def create_eligible_spans(self, duration: float, count: int) -> list:
        spans = []

        for i in range(count):
            spans.append(
                create_span(
                    "http.client",
                    duration,
                    f"GET /api/0/organizations/books?book_id={i}",
                    f"hash{i}",
                )
            )

        return spans

    def test_detects_problems_with_many_concurrent_calls_to_same_url(self) -> None:
        event = get_event("n-plus-one-api-calls/n-plus-one-api-calls-in-issue-stream")

        problems = self.find_problems(event)
        assert self.find_problems(event) == [
            PerformanceProblem(
                fingerprint=f"1-{self.type_id}-d750ce46bb1b13dd5780aac48098d5e20eea682c",
                op="http.client",
                type=PerformanceNPlusOneAPICallsExperimentalGroupType,
                desc="GET /api/0/organizations/sentry/events/?field=replayId&field=count%28%29&per_page=50&query=issue.id%3A",
                parent_span_ids=["a0c39078d1570b00"],
                cause_span_ids=[],
                offender_span_ids=[
                    "ba198ace55bdb20f",
                    "8a20c71faa0fb6a7",
                    "9269c825d935b33a",
                    "9ea82f759505e0f3",
                    "8c55019639e94ab3",
                    "9b86746e9cc7fbf0",
                    "806aa31fe1874495",
                    "bf409b62d9c30197",
                    "896ac7d28addb37f",
                    "9c859aeaf6bfaea9",
                    "950d8f569bbe3d9e",
                    "b19a2811b457e87a",
                    "b566d4ce5b46d4f0",
                    "b33e9da4441a4800",
                    "8b68818410aa45d8",
                    "8ac4e73b53fc2077",
                    "9fe4a1aff019e39e",
                    "b29cd0c0cd85ae85",
                    "b3ff0062caa3ea51",
                    "a3fde2e38a66cc2c",
                    "b78802cd80762f57",
                    "9e2ea4d33b1c1bc6",
                    "bb827dc7a11085f4",
                    "a34089b08b6d0646",
                    "950801c0d7576650",
                ],
                evidence_data={
                    "op": "http.client",
                    "parent_span_ids": ["a0c39078d1570b00"],
                    "cause_span_ids": [],
                    "offender_span_ids": [
                        "ba198ace55bdb20f",
                        "8a20c71faa0fb6a7",
                        "9269c825d935b33a",
                        "9ea82f759505e0f3",
                        "8c55019639e94ab3",
                        "9b86746e9cc7fbf0",
                        "806aa31fe1874495",
                        "bf409b62d9c30197",
                        "896ac7d28addb37f",
                        "9c859aeaf6bfaea9",
                        "950d8f569bbe3d9e",
                        "b19a2811b457e87a",
                        "b566d4ce5b46d4f0",
                        "b33e9da4441a4800",
                        "8b68818410aa45d8",
                        "8ac4e73b53fc2077",
                        "9fe4a1aff019e39e",
                        "b29cd0c0cd85ae85",
                        "b3ff0062caa3ea51",
                        "a3fde2e38a66cc2c",
                        "b78802cd80762f57",
                        "9e2ea4d33b1c1bc6",
                        "bb827dc7a11085f4",
                        "a34089b08b6d0646",
                        "950801c0d7576650",
                    ],
                },
                evidence_display=[],
            )
        ]
        assert problems[0].title == "N+1 API Call (Experimental)"

    def test_does_not_detect_problems_with_low_total_duration_of_spans(self) -> None:
        event = get_event("n-plus-one-api-calls/n-plus-one-api-calls-in-issue-stream")
        event["spans"] = self.create_eligible_spans(
            100, 10
        )  # total duration is 1s, greater than default

        problems = self.find_problems(event)
        assert len(problems) == 1

        event["spans"] = self.create_eligible_spans(
            10, 5
        )  # total duration is 50ms, lower than default

        problems = self.find_problems(event)
        assert problems == []

    def test_detects_problems_with_low_span_duration_high_total_duration(self) -> None:
        event = get_event("n-plus-one-api-calls/n-plus-one-api-calls-in-issue-stream")
        event["spans"] = self.create_eligible_spans(100, 10)  # total duration is 1s

        problems = self.find_problems(event)
        assert len(problems) == 1

        event["spans"] = self.create_eligible_spans(10, 50)  # total duration is 500ms

        problems = self.find_problems(event)
        assert len(problems) == 1

    def test_does_not_detect_problems_with_low_span_count(self) -> None:
        event = get_event("n-plus-one-api-calls/n-plus-one-api-calls-in-issue-stream")
        event["spans"] = self.create_eligible_spans(
            1000, self._settings[DetectorType.EXPERIMENTAL_N_PLUS_ONE_API_CALLS]["count"]
        )

        problems = self.find_problems(event)
        assert len(problems) == 1

        event["spans"] = self.create_eligible_spans(
            1000, self._settings[DetectorType.EXPERIMENTAL_N_PLUS_ONE_API_CALLS]["count"] - 1
        )

        problems = self.find_problems(event)
        assert problems == []

    def test_does_detect_problem_with_unparameterized_urls(self) -> None:
        event = get_event("n-plus-one-api-calls/n-plus-one-api-calls-in-weather-app")
        [problem] = self.find_problems(event)

        assert problem.fingerprint == f"1-{self.type_id}-bf7ad6b20bb345ae327362c849427956862bf839"

    def test_does_detect_problem_with_parameterized_urls(self) -> None:
        event = self.create_event(lambda i: f"GET /clients/{i}/info/{i*100}/?id={i}")
        [problem] = self.find_problems(event)
        assert problem.desc == "/clients/*/info/*/?id=*"
        assert problem.evidence_data is not None
        assert problem.evidence_data["common_url"] == "/clients/*/info/*/?id=*"
        path_params = problem.evidence_data.get("path_parameters", [])
        # It should sequentially store sets of path parameters on the evidence data
        for i in range(len(path_params)):
            assert path_params[i] == f"{i}, {i*100}"
        query_params = problem.evidence_data.get("parameters", [])
        assert query_params == ["id: 0, 1, 2, 3, 4, 5"]
        assert problem.fingerprint == f"1-{self.type_id}-8bf177290e2d78550fef5a1f6e9ddf115e4b0614"

    def test_does_not_detect_problem_with_concurrent_calls_to_different_urls(self) -> None:
        event = get_event("n-plus-one-api-calls/not-n-plus-one-api-calls")
        assert self.find_problems(event) == []

    def test_fingerprints_events(self) -> None:
        event = self.create_event(lambda i: "GET /clients/11/info")
        [problem] = self.find_problems(event)

        assert problem.fingerprint == f"1-{self.type_id}-e9daac10ea509a0bf84a8b8da45d36394868ad67"

    def test_fingerprints_identical_relative_urls_together(self) -> None:
        event1 = self.create_event(lambda i: "GET /clients/11/info")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: "GET /clients/11/info")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint

    def test_fingerprints_same_relative_urls_together(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/42/info?id={i}")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/42/info?id={i*2}")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint

    def test_fingerprints_same_parameterized_integer_relative_urls_together(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/{i}/info?id={i}")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/{i}/info?id={i*2}")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint

    def test_fingerprints_different_relative_url_separately(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/{i}/info?id={i}")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /projects/{i}/details?pid={i}")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint != problem2.fingerprint

    def test_fingerprints_relative_urls_with_query_params_together(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/{i}/info")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/{i}/info?id={i}")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint

    def test_fingerprints_multiple_parameterized_integer_relative_urls_together(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/{i}/organization/{i}/info")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/{i*100}/organization/{i*100}/info")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint

    def test_fingerprints_different_parameterized_integer_relative_urls_separately(self) -> None:
        event1 = self.create_event(lambda i: f"GET /clients/{i}/mario/{i}/info")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/{i}/luigi/{i}/info")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint != problem2.fingerprint

    def test_does_not_fingerprint_file_urls(self) -> None:
        event = self.create_event(lambda i: f"GET /clients/info/{i}.json")
        assert self.find_problems(event) == []

        event = self.create_event(lambda i: f"GET /clients/{i}/info/file.json")
        assert self.find_problems(event) == []

    def test_ignores_hostname_for_fingerprinting(self) -> None:
        event1 = self.create_event(lambda i: f"GET http://service.io/clients/{i}/info?id={i}")
        [problem1] = self.find_problems(event1)

        event2 = self.create_event(lambda i: f"GET /clients/{i}/info?id={i}")
        [problem2] = self.find_problems(event2)

        assert problem1.fingerprint == problem2.fingerprint


@pytest.mark.parametrize(
    "url,parameterized_url",
    [
        (
            "",
            "",
        ),
        (
            "http://service.io",
            "http://service.io",
        ),
        (
            "https://www.service.io/resources/11",
            "https://www.service.io/resources/*",
        ),
        (
            "https://www.service.io/resources/11/details",
            "https://www.service.io/resources/*/details",
        ),
        (
            "https://www.service.io/resources/11/details?id=1&sort=down",
            "https://www.service.io/resources/*/details?id=*&sort=*",
        ),
        (
            "https://www.service.io/resources/11/details?sort=down&id=1",
            "https://www.service.io/resources/*/details?id=*&sort=*",
        ),
        (
            "https://service.io/clients/somecord/details?id=17",
            "https://service.io/clients/somecord/details?id=*",
        ),
        (
            "/clients/11/project/1343",
            "/clients/*/project/*",
        ),
        (
            "/clients/1.2/project/3.4.5",
            "/clients/*/project/*",
        ),
        (
            "/clients/11/project/1343-turtles",
            "/clients/*/project/*",
        ),
        (
            "/clients/11/project/1343turtles",
            "/clients/*/project/1343turtles",
        ),
        (
            "/clients/563712f9722fb0996ac8f3905b40786f/project/1343",  # md5
            "/clients/*/project/*",
        ),
        (
            "/clients/563712f9722fb0996z/project/",  # md5-like
            "/clients/563712f9722fb0996z/project/",
        ),
        (
            "/clients/403926033d001b5279df37cbbe5287b7c7c267fa/project/1343",  # sha1
            "/clients/*/project/*",
        ),
        (
            "/clients/8ff81d74-606d-4c75-ac5e-cee65cbbc866/project/1343",  # uuid
            "/clients/*/project/*",
        ),
        (
            "/clients/hello-123s/project/1343",  # uuid-like
            "/clients/hello-123s/project/*",
        ),
        (
            "/item/5c9b9b609c172be2a013f534/details",  # short hash
            "/item/*/details",
        ),
        (
            "/item/be9a25322d/details",  # shorter short hash
            "/item/*/details",
        ),
        (
            "/item/defaced12/details",  # false short hash
            "/item/defaced12/details",
        ),
        (
            "/item/defaced12-abba/details",  # false short hash 2
            "/item/defaced12-abba/details",
        ),
    ],
)
def test_parameterizes_url(url, parameterized_url) -> None:
    r = parameterize_url(url)
    assert r == parameterized_url


@pytest.mark.parametrize(
    "span",
    [
        {
            "span_id": "a",
            "op": "http.client",
            "hash": "b",
            "description": "GET http://service.io/resource",
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource",
            "hash": "a",
            "data": {
                "url": "/resource",
            },
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource",
            "hash": "a",
            "data": {
                "url": {
                    "pathname": "/resource",
                }
            },
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource.json?param=something",
            "hash": "a",
        },
    ],
)
def test_allows_eligible_spans(span) -> None:
    assert NPlusOneAPICallsExperimentalDetector.is_span_eligible(span)


@pytest.mark.parametrize(
    "span",
    [
        {"span_id": "a", "op": None},
        {"op": "http.client"},
        {
            "span_id": "a",
            "op": "http.client",
            "hash": "a",
            "description": "POST http://service.io/resource",
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource.js",
            "hash": "a",
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET /resource.js",
            "hash": "a",
            "data": {"url": "/resource.js"},
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource?graphql=somequery",
            "hash": "a",
        },
        {
            "span_id": "a",
            "op": "http.client",
            "description": "GET http://service.io/resource",  # New JS SDK removes query string from description
            "hash": "a",
            "data": {
                "http.query": "graphql=somequery",
                "url": "http://service.io/resource",
            },
        },
        {
            "span_id": "a",
            "op": "http.client",
            "hash": "b",
            "description": "GET /_next/data/LjdprRSkUtLP0bMUoWLur/items.json?collection=hello",
        },
        {
            "span_id": "a",
            "op": "http.client",
            "hash": "b",
            "description": "GET /__nextjs_original-stack-frame?isServerSide=false&file=webpack-internal%3A%2F%2F%2F.%2Fnode_modules%2Freact-dom%2Fcjs%2Freact-dom.development.js&methodName=Object.invokeGuardedCallbackDev&arguments=&lineNumber=73&column=3`",
        },
    ],
)
def test_rejects_ineligible_spans(span) -> None:
    assert not NPlusOneAPICallsExperimentalDetector.is_span_eligible(span)


@pytest.mark.parametrize(
    "event",
    [get_event("n-plus-one-api-calls/not-n-plus-one-api-calls")],
)
def test_allows_eligible_events(event) -> None:
    assert NPlusOneAPICallsExperimentalDetector.is_event_eligible(event)


@pytest.mark.parametrize(
    "event",
    [
        {"contexts": {"trace": {"op": "task"}}},
    ],
)
def test_rejects_ineligible_events(event) -> None:
    assert not NPlusOneAPICallsExperimentalDetector.is_event_eligible(event)
