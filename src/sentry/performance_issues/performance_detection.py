from __future__ import annotations

import hashlib
import logging
import random
from collections.abc import Sequence
from typing import Any

import sentry_sdk

from sentry import features, nodestore, options, projectoptions
from sentry.eventstore.models import Event, GroupEvent
from sentry.models.options.project_option import ProjectOption
from sentry.models.organization import Organization
from sentry.models.project import Project
from sentry.performance_issues.detectors.experiments.mn_plus_one_db_span_detector import (
    MNPlusOneDBSpanExperimentalDetector,
)
from sentry.performance_issues.detectors.experiments.n_plus_one_db_span_detector import (
    NPlusOneDBSpanExperimentalDetector,
)
from sentry.projectoptions.defaults import DEFAULT_PROJECT_PERFORMANCE_DETECTION_SETTINGS
from sentry.utils import metrics
from sentry.utils.event import is_event_from_browser_javascript_sdk
from sentry.utils.event_frames import get_sdk_name
from sentry.utils.safe import get_path

from .base import DetectorType, PerformanceDetector
from .detectors.consecutive_db_detector import ConsecutiveDBSpanDetector
from .detectors.consecutive_http_detector import ConsecutiveHTTPSpanDetector
from .detectors.experiments.n_plus_one_api_calls_detector import (
    NPlusOneAPICallsExperimentalDetector,
)
from .detectors.http_overhead_detector import HTTPOverheadDetector
from .detectors.io_main_thread_detector import DBMainThreadDetector, FileIOMainThreadDetector
from .detectors.large_payload_detector import LargeHTTPPayloadDetector
from .detectors.mn_plus_one_db_span_detector import MNPlusOneDBSpanDetector
from .detectors.n_plus_one_api_calls_detector import NPlusOneAPICallsDetector
from .detectors.n_plus_one_db_span_detector import NPlusOneDBSpanDetector
from .detectors.query_injection_detector import QueryInjectionDetector
from .detectors.render_blocking_asset_span_detector import RenderBlockingAssetSpanDetector
from .detectors.slow_db_query_detector import SlowDBQueryDetector
from .detectors.sql_injection_detector import SQLInjectionDetector
from .detectors.uncompressed_asset_detector import UncompressedAssetSpanDetector
from .performance_problem import PerformanceProblem

INTEGRATIONS_OF_INTEREST = [
    "django",
    "flask",
    "sqlalchemy",
    "Mongo",  # Node
    "Postgres",  # Node
    "Mysql",  # Node
    "Prisma",  # Node
    "GraphQL",  # Node
]
SDKS_OF_INTEREST = [
    "sentry.javascript.node",
]


class EventPerformanceProblem:
    """
    Wrapper that binds an Event and PerformanceProblem together and allow the problem to be saved
    to and fetch from Nodestore
    """

    def __init__(self, event: Event | GroupEvent, problem: PerformanceProblem):
        self.event = event
        self.problem = problem

    @property
    def identifier(self) -> str:
        return self.build_identifier(self.event.event_id, self.problem.fingerprint)

    @classmethod
    def build_identifier(cls, event_id: str, problem_hash: str) -> str:
        identifier = hashlib.md5(f"{problem_hash}:{event_id}".encode()).hexdigest()
        return f"p-i-e:{identifier}"

    @property
    def evidence_hashes(self) -> dict[str, list[str]]:
        evidence_ids = self.problem.to_dict()
        evidence_hashes = {}

        spans_by_id = {span["span_id"]: span for span in self.event.data.get("spans", [])}

        trace = get_path(self.event.data, "contexts", "trace")
        if trace:
            spans_by_id[trace["span_id"]] = trace

        for key in ["parent", "cause", "offender"]:
            span_ids = evidence_ids.get(key + "_span_ids", []) or []
            spans = [spans_by_id.get(id) for id in span_ids]
            hashes = [span.get("hash") for span in spans if span]
            evidence_hashes[key + "_span_hashes"] = hashes

        return evidence_hashes

    def save(self) -> None:
        nodestore.backend.set(self.identifier, self.problem.to_dict())

    @classmethod
    def fetch(cls, event: Event, problem_hash: str) -> EventPerformanceProblem | None:
        return cls.fetch_multi([(event, problem_hash)])[0]

    @classmethod
    def fetch_multi(
        cls, items: Sequence[tuple[Event | GroupEvent, str]]
    ) -> list[EventPerformanceProblem | None]:
        ids = [cls.build_identifier(event.event_id, problem_hash) for event, problem_hash in items]
        results = nodestore.backend.get_multi(ids)
        ret: list[EventPerformanceProblem | None] = []
        for _id, (event, _) in zip(ids, items):
            result = results.get(_id)
            if result:
                ret.append(cls(event, PerformanceProblem.from_dict(result)))
            else:
                ret.append(None)
        return ret


# Facade in front of performance detection to limit impact of detection on our events ingestion
def detect_performance_problems(
    data: dict[str, Any], project: Project, standalone: bool = False
) -> list[PerformanceProblem]:
    try:
        rate = options.get("performance.issues.all.problem-detection")
        if rate and rate > random.random():
            # Add an experimental tag to be able to find these spans in production while developing. Should be removed later.
            sentry_sdk.set_tag("_did_analyze_performance_issue", "true")
            with (
                metrics.timer("performance.detect_performance_issue", sample_rate=0.01),
                sentry_sdk.start_span(op="py.detect_performance_issue", name="none") as sdk_span,
            ):
                return _detect_performance_problems(data, sdk_span, project, standalone=standalone)
    except Exception:
        logging.exception("Failed to detect performance problems")
    return []


# Merges system defaults, with default project settings and saved project settings.
def get_merged_settings(project_id: int | None = None) -> dict[str | Any, Any]:
    system_settings = {
        "n_plus_one_db_count": options.get("performance.issues.n_plus_one_db.count_threshold"),
        "n_plus_one_db_duration_threshold": options.get(
            "performance.issues.n_plus_one_db.duration_threshold"
        ),
        "slow_db_query_duration_threshold": options.get(
            "performance.issues.slow_db_query.duration_threshold"
        ),
        "render_blocking_fcp_min": options.get(
            "performance.issues.render_blocking_assets.fcp_minimum_threshold"
        ),
        "render_blocking_fcp_max": options.get(
            "performance.issues.render_blocking_assets.fcp_maximum_threshold"
        ),
        "render_blocking_fcp_ratio": options.get(
            "performance.issues.render_blocking_assets.fcp_ratio_threshold"
        ),
        "render_blocking_bytes_min": options.get(
            "performance.issues.render_blocking_assets.size_threshold"
        ),
        "consecutive_http_spans_max_duration_between_spans": options.get(
            "performance.issues.consecutive_http.max_duration_between_spans"
        ),
        "consecutive_http_spans_count_threshold": options.get(
            "performance.issues.consecutive_http.consecutive_count_threshold"
        ),
        "consecutive_http_spans_span_duration_threshold": options.get(
            "performance.issues.consecutive_http.span_duration_threshold"
        ),
        "consecutive_http_spans_min_time_saved_threshold": options.get(
            "performance.issues.consecutive_http.min_time_saved_threshold"
        ),
        "large_http_payload_size_threshold": options.get(
            "performance.issues.large_http_payload.size_threshold"
        ),
        "db_on_main_thread_duration_threshold": options.get(
            "performance.issues.db_on_main_thread.total_spans_duration_threshold"
        ),
        "file_io_on_main_thread_duration_threshold": options.get(
            "performance.issues.file_io_on_main_thread.total_spans_duration_threshold"
        ),
        "uncompressed_asset_duration_threshold": options.get(
            "performance.issues.uncompressed_asset.duration_threshold"
        ),
        "uncompressed_asset_size_threshold": options.get(
            "performance.issues.uncompressed_asset.size_threshold"
        ),
        "consecutive_db_min_time_saved_threshold": options.get(
            "performance.issues.consecutive_db.min_time_saved_threshold"
        ),
        "http_request_delay_threshold": options.get(
            "performance.issues.http_overhead.http_request_delay_threshold"
        ),
        "n_plus_one_api_calls_total_duration_threshold": options.get(
            "performance.issues.n_plus_one_api_calls.total_duration"
        ),
        "sql_injection_query_value_length_threshold": options.get(
            "performance.issues.sql_injection.query_value_length_threshold"
        ),
    }

    default_project_settings = (
        projectoptions.get_well_known_default(
            "sentry:performance_issue_settings",
            project=project_id,
        )
        if project_id
        else {}
    )

    project_option_settings = (
        ProjectOption.objects.get_value(
            project_id, "sentry:performance_issue_settings", default_project_settings
        )
        if project_id
        else DEFAULT_PROJECT_PERFORMANCE_DETECTION_SETTINGS
    )

    project_settings = {
        **default_project_settings,
        **project_option_settings,
    }  # Merge saved project settings into default so updating the default to add new settings works in the future.

    return {**system_settings, **project_settings}


# Gets the thresholds to perform performance detection.
# Duration thresholds are in milliseconds.
# Allowed span ops are allowed span prefixes. (eg. 'http' would work for a span with 'http.client' as its op)
def get_detection_settings(project_id: int | None = None) -> dict[DetectorType, dict[str, Any]]:
    settings = get_merged_settings(project_id)

    return {
        DetectorType.SLOW_DB_QUERY: {
            "duration_threshold": settings["slow_db_query_duration_threshold"],  # ms
            "allowed_span_ops": ["db"],
            "detection_enabled": settings["slow_db_queries_detection_enabled"],
        },
        DetectorType.RENDER_BLOCKING_ASSET_SPAN: {
            "fcp_minimum_threshold": settings["render_blocking_fcp_min"],  # ms
            "fcp_maximum_threshold": settings["render_blocking_fcp_max"],  # ms
            "fcp_ratio_threshold": settings["render_blocking_fcp_ratio"],  # in the range [0, 1]
            "minimum_size_bytes": settings["render_blocking_bytes_min"],  # in bytes
            "maximum_size_bytes": 1_000_000_000,  # 1GB
            "detection_enabled": settings["large_render_blocking_asset_detection_enabled"],
        },
        DetectorType.N_PLUS_ONE_DB_QUERIES: {
            "count": settings["n_plus_one_db_count"],
            "duration_threshold": settings["n_plus_one_db_duration_threshold"],  # ms
            "detection_enabled": settings["n_plus_one_db_queries_detection_enabled"],
        },
        DetectorType.EXPERIMENTAL_N_PLUS_ONE_DB_QUERIES: {
            "count": settings["n_plus_one_db_count"],
            "duration_threshold": settings["n_plus_one_db_duration_threshold"],  # ms
            "detection_enabled": settings["n_plus_one_db_queries_detection_enabled"],
        },
        DetectorType.CONSECUTIVE_DB_OP: {
            # time saved by running all queries in parallel
            "min_time_saved": settings["consecutive_db_min_time_saved_threshold"],  # ms
            # ratio between time saved and total db span durations
            "min_time_saved_ratio": 0.1,
            # The minimum duration of a single independent span in ms, used to prevent scenarios with a ton of small spans
            "span_duration_threshold": 30,  # ms
            "consecutive_count_threshold": 2,
            "detection_enabled": settings["consecutive_db_queries_detection_enabled"],
        },
        DetectorType.FILE_IO_MAIN_THREAD: {
            # 16ms is when frame drops will start being evident
            "duration_threshold": settings["file_io_on_main_thread_duration_threshold"],
            "detection_enabled": settings["file_io_on_main_thread_detection_enabled"],
        },
        DetectorType.DB_MAIN_THREAD: {
            # Basically the same as file io, but db instead, so continue using 16ms
            "duration_threshold": settings["db_on_main_thread_duration_threshold"],
            "detection_enabled": settings["db_on_main_thread_detection_enabled"],
        },
        DetectorType.N_PLUS_ONE_API_CALLS: {
            "total_duration": settings["n_plus_one_api_calls_total_duration_threshold"],  # ms
            "concurrency_threshold": 5,  # ms
            "count": 10,
            "allowed_span_ops": ["http.client"],
            "detection_enabled": settings["n_plus_one_api_calls_detection_enabled"],
        },
        DetectorType.EXPERIMENTAL_N_PLUS_ONE_API_CALLS: {
            "total_duration": settings["n_plus_one_api_calls_total_duration_threshold"],  # ms
            "concurrency_threshold": 10,  # ms
            "count": 5,
            "allowed_span_ops": ["http.client"],
            "detection_enabled": settings["n_plus_one_api_calls_detection_enabled"],
        },
        DetectorType.M_N_PLUS_ONE_DB: {
            "total_duration_threshold": settings["n_plus_one_db_duration_threshold"],  # ms
            "minimum_occurrences_of_pattern": 3,
            "max_sequence_length": 5,
            "detection_enabled": settings["n_plus_one_db_queries_detection_enabled"],
        },
        DetectorType.EXPERIMENTAL_M_N_PLUS_ONE_DB_QUERIES: {
            "total_duration_threshold": settings["n_plus_one_db_duration_threshold"],  # ms
            "minimum_occurrences_of_pattern": 3,
            "max_sequence_length": 8,
            "max_allowable_depth": 3,  # This should not be user-configurable, to avoid O(n^2) complexity and load issues.
            "min_percentage_of_db_spans": 0.05,
            "detection_enabled": settings["n_plus_one_db_queries_detection_enabled"],
        },
        DetectorType.UNCOMPRESSED_ASSETS: {
            "size_threshold_bytes": settings["uncompressed_asset_size_threshold"],
            "duration_threshold": settings["uncompressed_asset_duration_threshold"],  # ms
            "allowed_span_ops": ["resource.css", "resource.script"],
            "detection_enabled": settings["uncompressed_assets_detection_enabled"],
        },
        DetectorType.CONSECUTIVE_HTTP_OP: {
            "span_duration_threshold": settings[
                "consecutive_http_spans_span_duration_threshold"
            ],  # ms
            "min_time_saved": settings["consecutive_http_spans_min_time_saved_threshold"],  # ms
            "consecutive_count_threshold": settings["consecutive_http_spans_count_threshold"],
            "max_duration_between_spans": settings[
                "consecutive_http_spans_max_duration_between_spans"
            ],  # ms
            "detection_enabled": settings["consecutive_http_spans_detection_enabled"],
        },
        DetectorType.LARGE_HTTP_PAYLOAD: {
            "payload_size_threshold": settings["large_http_payload_size_threshold"],
            "detection_enabled": settings["large_http_payload_detection_enabled"],
            "minimum_span_duration": 100,  # ms
        },
        DetectorType.HTTP_OVERHEAD: {
            "http_request_delay_threshold": settings["http_request_delay_threshold"],
            "detection_enabled": settings["http_overhead_detection_enabled"],
        },
        DetectorType.SQL_INJECTION: {
            "detection_enabled": settings["db_query_injection_detection_enabled"],
            "query_value_length_threshold": settings["sql_injection_query_value_length_threshold"],
        },
        DetectorType.QUERY_INJECTION: {
            "detection_enabled": settings["db_query_injection_detection_enabled"]
        },
    }


DETECTOR_CLASSES: list[type[PerformanceDetector]] = [
    ConsecutiveDBSpanDetector,
    ConsecutiveHTTPSpanDetector,
    DBMainThreadDetector,
    SlowDBQueryDetector,
    RenderBlockingAssetSpanDetector,
    NPlusOneDBSpanDetector,
    NPlusOneDBSpanExperimentalDetector,
    FileIOMainThreadDetector,
    NPlusOneAPICallsDetector,
    NPlusOneAPICallsExperimentalDetector,
    MNPlusOneDBSpanDetector,
    MNPlusOneDBSpanExperimentalDetector,
    UncompressedAssetSpanDetector,
    LargeHTTPPayloadDetector,
    HTTPOverheadDetector,
    SQLInjectionDetector,
    QueryInjectionDetector,
]


def _detect_performance_problems(
    data: dict[str, Any], sdk_span: Any, project: Project, standalone: bool = False
) -> list[PerformanceProblem]:
    event_id = data.get("event_id", None)
    organization = project.organization

    with sentry_sdk.start_span(op="function", name="get_detection_settings"):
        detection_settings = get_detection_settings(project.id)

    if standalone or features.has("organizations:issue-detection-sort-spans", organization):
        # The performance detectors expect the span list to be ordered/flattened in the way they
        # are structured in the tree. This is an implicit assumption in the performance detectors.
        # So we build a tree and flatten it depth first.
        # TODO: See if we can update the detectors to work without this assumption so we can
        # just pass it a list of spans.
        with sentry_sdk.start_span(op="performance_detection", name="sort_spans"):
            tree, segment_id = build_tree(data.get("spans", []))
            data = {**data, "spans": flatten_tree(tree, segment_id)}

    with sentry_sdk.start_span(op="initialize", name="PerformanceDetector"):
        detectors: list[PerformanceDetector] = [
            detector_class(detection_settings, data)
            for detector_class in DETECTOR_CLASSES
            if detector_class.is_detection_allowed_for_system()
        ]

    for detector in detectors:
        with sentry_sdk.start_span(
            op="function", name=f"run_detector_on_data.{detector.type.value}"
        ):
            run_detector_on_data(detector, data)

    with sentry_sdk.start_span(op="function", name="report_metrics_for_detectors"):
        # Metrics reporting only for detection, not created issues.
        report_metrics_for_detectors(
            data,
            event_id,
            detectors,
            sdk_span,
            organization,
            standalone=standalone,
        )

    problems: list[PerformanceProblem] = []
    with sentry_sdk.start_span(op="performance_detection", name="is_creation_allowed"):
        for detector in detectors:
            if all(
                [
                    detector.is_creation_allowed_for_organization(organization),
                    detector.is_creation_allowed_for_project(project),
                ]
            ):
                problems.extend(detector.stored_problems.values())
            else:
                continue

    unique_problems = set(problems)

    if len(unique_problems) > 0:
        metrics.incr(
            "performance.performance_issue.performance_problem_emitted",
            len(unique_problems),
            sample_rate=1.0,
        )

    # TODO: Make sure upstream is all compatible with set before switching output type.
    return list(unique_problems)


def run_detector_on_data(detector: PerformanceDetector, data: dict[str, Any]) -> None:
    if not detector.is_event_eligible(data):
        return

    spans = data.get("spans", [])
    for span in spans:
        detector.visit_span(span)

    detector.on_complete()


def build_tree(spans: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    span_tree: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
    segment_id = None

    for span in spans:
        span_id = span["span_id"]
        is_root = span.get("is_segment", False)
        if is_root:
            segment_id = span_id
        if span_id not in span_tree:
            span_tree[span_id] = (span, [])

    for span, _ in span_tree.values():
        parent_id = span.get("parent_span_id")
        if parent_id is not None and parent_id in span_tree:
            _, children = span_tree[parent_id]
            children.append(span)

    return span_tree, segment_id


def dfs(
    visited: set[str], flattened_spans: list[dict[str, Any]], tree: dict[str, Any], span_id: str
) -> None:
    stack = [span_id]

    while len(stack):
        span_id = stack.pop()

        span, children = tree[span_id]

        if span_id not in visited:
            flattened_spans.append(span)
            tree.pop(span_id)
            visited.add(span_id)

        for child in sorted(children, key=lambda span: span["start_timestamp"], reverse=True):
            if child["span_id"] not in visited:
                stack.append(child["span_id"])


def flatten_tree(tree: dict[str, Any], segment_id: str | None) -> list[dict[str, Any]]:
    visited: set[str] = set()
    flattened_spans: list[dict[str, Any]] = []

    if segment_id:
        dfs(visited, flattened_spans, tree, segment_id)

    # Catch all for orphan spans
    remaining = sorted(tree.items(), key=lambda span: span[1][0]["start_timestamp"])
    for span_id, _ in remaining:
        if span_id not in visited:
            dfs(visited, flattened_spans, tree, span_id)

    return flattened_spans


# Reports metrics and creates spans for detection
def report_metrics_for_detectors(
    event: dict[str, Any],
    event_id: str | None,
    detectors: Sequence[PerformanceDetector],
    sdk_span: Any,
    organization: Organization,
    standalone: bool = False,
) -> None:
    all_detected_problems = [i for d in detectors for i in d.stored_problems]
    has_detected_problems = bool(all_detected_problems)
    sdk_name = get_sdk_name(event)

    try:
        # Setting a tag isn't critical, the transaction doesn't exist sometimes, if it's called outside prod code (eg. load-mocks / tests)
        set_tag = sdk_span.containing_transaction.set_tag
    except AttributeError:
        set_tag = lambda *args: None

    if has_detected_problems:
        set_tag("_pi_all_issue_count", len(all_detected_problems))
        set_tag("_pi_sdk_name", sdk_name or "")
        set_tag("is_standalone_spans", standalone)
        metrics.incr(
            "performance.performance_issue.aggregate",
            len(all_detected_problems),
            tags={"sdk_name": sdk_name, "is_standalone_spans": standalone},
        )
        if event_id:
            set_tag("_pi_transaction", event_id)

    tags = event.get("tags", [])
    browser_name = next(
        (tag[1] for tag in tags if tag is not None and tag[0] == "browser.name" and len(tag) == 2),
        None,
    )
    allowed_browser_name = "Other"
    if browser_name in [
        "Chrome",
        "Firefox",
        "Safari",
        "Electron",
        "Chrome Mobile",
        "Edge",
        "Mobile Safari",
        "Opera",
        "Opera Mobile",
        "Chrome Mobile WebView",
        "Chrome Mobile iOS",
        "Samsung Internet",
        "Firefox Mobile",
    ]:
        # Reduce cardinality in case there are custom browser name tags.
        allowed_browser_name = browser_name

    detected_tags = {
        "sdk_name": sdk_name,
        "is_early_adopter": bool(organization.flags.early_adopter),
        "is_standalone_spans": standalone,
    }

    event_integrations = event.get("sdk", {}).get("integrations", []) or []

    for integration_name in INTEGRATIONS_OF_INTEREST:
        if integration_name in event_integrations:
            detected_tags["integration_" + integration_name.lower()] = True

    for allowed_sdk_name in SDKS_OF_INTEREST:
        if allowed_sdk_name == sdk_name:
            detected_tags["sdk_" + allowed_sdk_name.lower()] = True

    for detector in detectors:
        detector_key = detector.type.value
        detected_problems = detector.stored_problems
        detected_problem_keys = list(detected_problems.keys())
        detected_tags[detector_key] = bool(len(detected_problem_keys))

        if not detected_problem_keys:
            continue

        if detector.type in [DetectorType.UNCOMPRESSED_ASSETS]:
            detected_tags["browser_name"] = allowed_browser_name

        if detector.type in [DetectorType.CONSECUTIVE_HTTP_OP]:
            detected_tags["is_frontend"] = is_event_from_browser_javascript_sdk(event)

        first_problem = detected_problems[detected_problem_keys[0]]
        if first_problem.fingerprint:
            set_tag(f"_pi_{detector_key}_fp", first_problem.fingerprint)

        span_id = first_problem.offender_span_ids[0]

        set_tag(f"_pi_{detector_key}", span_id)

        op_tags = {"is_standalone_spans": standalone}
        for problem in detected_problems.values():
            op = problem.op
            op_tags[f"op_{op}"] = True
        metrics.incr(
            f"performance.performance_issue.{detector_key}",
            len(detected_problem_keys),
            tags=op_tags,
        )

    metrics.incr(
        "performance.performance_issue.detected",
        instance=str(has_detected_problems),
        tags=detected_tags,
    )
