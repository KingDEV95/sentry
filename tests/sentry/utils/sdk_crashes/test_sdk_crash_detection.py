import abc
from collections.abc import Sequence
from unittest.mock import MagicMock, call, patch

import pytest

from fixtures.sdk_crash_detection.crash_event_cocoa import get_crash_event
from sentry.eventstore.snuba.backend import SnubaEventStorage
from sentry.issues.grouptype import PerformanceNPlusOneGroupType
from sentry.testutils.cases import BaseTestCase, SnubaTestCase, TestCase
from sentry.testutils.helpers.options import override_options
from sentry.testutils.performance_issues.store_transaction import store_transaction
from sentry.testutils.pytest.fixtures import django_db_all
from sentry.utils.safe import get_path, set_path
from sentry.utils.sdk_crashes.sdk_crash_detection import sdk_crash_detection
from sentry.utils.sdk_crashes.sdk_crash_detection_config import (
    SDKCrashDetectionConfig,
    build_sdk_crash_detection_configs,
)


@override_options(
    {
        "issues.sdk_crash_detection.cocoa.project_id": 1234,
        "issues.sdk_crash_detection.cocoa.sample_rate": 1.0,
        "issues.sdk_crash_detection.react-native.project_id": 2,
    }
)
def build_sdk_configs() -> Sequence[SDKCrashDetectionConfig]:
    return build_sdk_crash_detection_configs()


class BaseSDKCrashDetectionMixin(BaseTestCase, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def create_event(self, data, project_id, assert_no_errors=True):
        pass

    def execute_test(self, event_data, should_be_reported, mock_sdk_crash_reporter):
        event = self.create_event(
            data=event_data,
            project_id=self.project.id,
        )

        sdk_crash_detection.detect_sdk_crash(event=event, configs=build_sdk_configs())

        if should_be_reported:
            assert mock_sdk_crash_reporter.report.call_count == 1

            reported_event_data = mock_sdk_crash_reporter.report.call_args.args[0]
            assert reported_event_data["contexts"]["sdk_crash_detection"] == {
                "original_project_id": event.project_id,
                "original_event_id": event.event_id,
            }
            assert reported_event_data["user"] == {
                "id": event.project_id,
            }

            assert reported_event_data["release"] == get_path(event_data, "sdk", "version")
        else:
            assert mock_sdk_crash_reporter.report.call_count == 0


@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
class PerformanceEventTestMixin(BaseSDKCrashDetectionMixin, SnubaTestCase):
    def test_performance_event_not_detected(self, mock_sdk_crash_reporter: MagicMock) -> None:
        fingerprint = "some_group"
        fingerprint = f"{PerformanceNPlusOneGroupType.type_id}-{fingerprint}"
        event = store_transaction(
            test_case=self,
            project_id=self.project.id,
            user_id="hi",
            fingerprint=[fingerprint],
        )

        sdk_crash_detection.detect_sdk_crash(event=event, configs=build_sdk_configs())

        assert mock_sdk_crash_reporter.report.call_count == 0

    @patch("sentry.utils.metrics.incr")
    def test_performance_event_increments_counter(
        self, incr: MagicMock, mock_sdk_crash_reporter: MagicMock
    ) -> None:
        fingerprint = "some_group"
        fingerprint = f"{PerformanceNPlusOneGroupType.type_id}-{fingerprint}"
        event = store_transaction(
            test_case=self,
            project_id=self.project.id,
            user_id="hi",
            fingerprint=[fingerprint],
        )
        set_path(event.data, "sdk", "name", value="sentry.cocoa")
        set_path(event.data, "sdk", "version", value="8.2.0")

        sdk_crash_detection.detect_sdk_crash(event=event, configs=build_sdk_configs())

        incr.assert_called_with(
            "post_process.sdk_crash_monitoring.sdk_event",
            tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
        )

        # Ensure that no counter is incremented
        for call_args in incr.call_args_list:
            assert call_args[0][0] != "post_process.sdk_crash_monitoring.detecting_sdk_crash"
            assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_crash_detected"


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@pytest.mark.parametrize(
    ["sdk_name", "detected"],
    [
        ("sentry.cocoa", True),
        ("sentry.coco", False),
        ("sentry.cocoa.react-native", True),
        ("sentry.cocoa.capacitor", True),
        ("sentry.cocoa.react-native", True),
        ("sentry.cocoa.dotnet", True),
        ("sentry.cocoa.flutter", True),
        ("sentry.cocoa.kmp", True),
        ("sentry.cocoa.unity", True),
        ("sentry.cocoa.unreal", True),
    ],
)
def test_sdks_detected(mock_sdk_crash_reporter, store_event, sdk_name, detected) -> None:
    event_data = get_crash_event()
    set_path(event_data, "sdk", "name", value=sdk_name)
    event = store_event(data=event_data)

    sdk_crash_detection.detect_sdk_crash(event=event, configs=build_sdk_configs())

    if detected:
        assert mock_sdk_crash_reporter.report.call_count == 1
    else:
        assert mock_sdk_crash_reporter.report.call_count == 0


class SDKCrashReportTestMixin(BaseSDKCrashDetectionMixin, SnubaTestCase):
    @django_db_all
    def test_sdk_crash_event_stored_to_sdk_crash_project(self) -> None:
        cocoa_sdk_crashes_project = self.create_project(
            name="Cocoa SDK Crashes",
            slug="cocoa-sdk-crashes",
            teams=[self.team],
            fire_project_created=True,
        )

        event = self.create_event(
            data=get_crash_event(),
            project_id=self.project.id,
        )

        configs = build_sdk_configs()
        configs[0].project_id = cocoa_sdk_crashes_project.id
        sdk_crash_event = sdk_crash_detection.detect_sdk_crash(event=event, configs=configs)

        assert sdk_crash_event is not None

        event_store = SnubaEventStorage()
        fetched_sdk_crash_event = event_store.get_event_by_id(
            cocoa_sdk_crashes_project.id, sdk_crash_event.event_id
        )

        assert fetched_sdk_crash_event is not None
        assert cocoa_sdk_crashes_project.id == fetched_sdk_crash_event.project_id
        assert sdk_crash_event.event_id == fetched_sdk_crash_event.event_id


class SDKCrashDetectionTest(
    TestCase,
    PerformanceEventTestMixin,
    SDKCrashReportTestMixin,
):
    def create_event(self, data, project_id, assert_no_errors=True):
        return self.store_event(data=data, project_id=project_id, assert_no_errors=assert_no_errors)


@pytest.mark.parametrize(
    ["sample_rate", "random_value", "sampled"],
    [
        (0.0, 0.0001, False),
        (0.0, 0.5, False),
        (1.0, 0.0001, True),
        (1.0, 0.9999, True),
        (0.1, 0.0001, True),
        (0.1, 0.09, True),
        (0.1, 0.1, True),
        (0.1, 0.11, False),
        (0.1, 0.5, False),
        (0.1, 0.999, False),
    ],
)
@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
def test_sample_rate(
    mock_sdk_crash_reporter, store_event, sample_rate, random_value, sampled
) -> None:
    event = store_event(data=get_crash_event())

    with patch("random.random", return_value=random_value):
        configs = build_sdk_configs()
        configs[0].sample_rate = sample_rate

        sdk_crash_detection.detect_sdk_crash(event=event, configs=configs)

        if sampled:
            assert mock_sdk_crash_reporter.report.call_count == 1
        else:
            assert mock_sdk_crash_reporter.report.call_count == 0


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
def test_multiple_configs_first_one_picked(mock_sdk_crash_reporter, store_event) -> None:
    event = store_event(data=get_crash_event())

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=event, configs=configs)

    assert mock_sdk_crash_reporter.report.call_count == 1
    project_id = mock_sdk_crash_reporter.report.call_args.args[1]
    assert project_id == 1234


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@patch("sentry.utils.metrics.incr")
def test_should_increment_counters_for_sdk_crash(incr, sdk_crash_reporter, store_event) -> None:
    event = store_event(data=get_crash_event())

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=event, configs=configs)

    incr.assert_has_calls(
        [
            call(
                "post_process.sdk_crash_monitoring.sdk_event",
                tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
            ),
            call(
                "post_process.sdk_crash_monitoring.detecting_sdk_crash",
                tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
            ),
            call(
                "post_process.sdk_crash_monitoring.sdk_crash_detected",
                tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
            ),
        ],
        any_order=True,
    )


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@patch("sentry.utils.metrics.incr")
def test_should_only_increment_detecting_counter_for_non_crash_event(
    incr, sdk_crash_reporter, store_event
):
    non_crash_event = store_event(data=get_crash_event(function="+[SentrySDK crash]"))

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=non_crash_event, configs=configs)

    incr.assert_has_calls(
        [
            call(
                "post_process.sdk_crash_monitoring.sdk_event",
                tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
            ),
            call(
                "post_process.sdk_crash_monitoring.detecting_sdk_crash",
                tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
            ),
        ],
        any_order=True,
    )

    # Ensure that the counter sdk_crash_detected is not incremented
    for call_args in incr.call_args_list:
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_crash_detected"


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@patch("sentry.utils.metrics.incr")
def test_should_not_increment_counters_for_not_supported_sdk(
    incr, sdk_crash_reporter, store_event
) -> None:
    event_data = get_crash_event()
    set_path(event_data, "sdk", "name", value="sentry.coco")
    crash_event = store_event(data=event_data)

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=crash_event, configs=configs)

    # Ensure that no counter is incremented
    for call_args in incr.call_args_list:
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_error_event"
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.detecting_sdk_crash"
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_crash_detected"


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@patch("sentry.utils.metrics.incr")
def test_should_increment_counter_for_non_crash_event(
    incr, sdk_crash_reporter, store_event
) -> None:
    event_data = get_crash_event(handled=True)
    crash_event = store_event(data=event_data)

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=crash_event, configs=configs)

    incr.assert_called_with(
        "post_process.sdk_crash_monitoring.sdk_event",
        tags={"sdk_name": "sentry.cocoa", "sdk_version": "8.2.0"},
    )

    # Ensure that no counter is incremented
    for call_args in incr.call_args_list:
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.detecting_sdk_crash"
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_crash_detected"


@django_db_all
@pytest.mark.snuba
@patch("sentry.utils.sdk_crashes.sdk_crash_detection.sdk_crash_detection.sdk_crash_reporter")
@patch("sentry.utils.metrics.incr")
def test_should_not_increment_counters_already_reported_sdk_crash(
    incr, sdk_crash_reporter, store_event
):
    event_data = get_crash_event()
    set_path(
        event_data,
        "contexts",
        "sdk_crash_detection",
        value={"original_project_id": 1234, "original_event_id": 1234},
    )
    crash_event = store_event(data=event_data)

    sdk_configs = build_sdk_configs()
    configs = [sdk_configs[0], sdk_configs[0]]

    sdk_crash_detection.detect_sdk_crash(event=crash_event, configs=configs)

    # Ensure that no counter is incremented
    for call_args in incr.call_args_list:
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_event"
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.detecting_sdk_crash"
        assert call_args[0][0] != "post_process.sdk_crash_monitoring.sdk_crash_detected"
