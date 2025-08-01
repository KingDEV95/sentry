import datetime
import os
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import SimpleTestCase
from django.utils import timezone

from sentry.api.event_search import (
    AggregateFilter,
    AggregateKey,
    ParenExpression,
    SearchConfig,
    SearchFilter,
    SearchKey,
    SearchValue,
    _RecursiveList,
    default_config,
    flatten,
    parse_search_query,
    translate_wildcard_as_clickhouse_pattern,
)
from sentry.constants import MODULE_ROOT
from sentry.exceptions import InvalidSearchQuery
from sentry.search.utils import parse_datetime_string, parse_duration, parse_numeric_value
from sentry.testutils.helpers.datetime import freeze_time
from sentry.utils import json

fixture_path = "fixtures/search-syntax"
abs_fixtures_path = os.path.join(MODULE_ROOT, os.pardir, os.pardir, fixture_path)


def register_fixture_tests(cls, skipped):
    """
    Registers test fixtures onto a class with a run_test_case method
    """

    def assign_test_case(name, tests):
        if name in skipped:
            return

        def runner(self):
            for case in tests:
                self.run_test_case(name, case)

        setattr(cls, f"test_{name}", runner)

    for file in (f for f in os.listdir(abs_fixtures_path)):
        name = file[: len(".json") * -1]

        with open(os.path.join(abs_fixtures_path, file)) as fp:
            tests = json.load(fp)
        assign_test_case(name, tests)


def result_transformer(result):
    """
    This is used to translate the expected token results from the format used
    in the JSON test data (which is more close to the lossless frontend AST) to
    the backend version, which is much more lossy (meaning spaces, and other
    un-important syntax is removed).

    This includes various transformations (which are tested elsewhere) that are
    done in the SearchVisitor.
    """

    def node_visitor(token):
        if token["type"] == "spaces":
            return None

        if token["type"] == "filter":
            # Filters with an invalid reason raises to signal to the test
            # runner that we should expect this exception
            if token.get("invalid"):
                raise InvalidSearchQuery(token["invalid"]["reason"])

            # Transform the operator to match for list values
            if token["value"]["type"] in ["valueTextList", "valueNumberList"]:
                operator = "NOT IN" if token["negated"] else "IN"
            else:
                # Negate the operator if the filter is negated to match
                operator = token["operator"] or "="
                operator = f"!{operator}" if token["negated"] else operator

            key = node_visitor(token["key"])
            value = node_visitor(token["value"])

            if token["filter"] == "boolean" and token["negated"]:
                operator = "="
                value = SearchValue(raw_value=1 if value.raw_value == 0 else 0)

            return SearchFilter(key, operator, value)

        if token["type"] == "keySimple":
            return SearchKey(name=token["value"])

        if token["type"] == "keyExplicitTag":
            return SearchKey(name=f"tags[{token['key']['value']}]")

        if token["type"] == "keyExplicitStringTag":
            return SearchKey(name=f"tags[{token['key']['value']},string]")

        if token["type"] == "keyExplicitNumberTag":
            return SearchKey(name=f"tags[{token['key']['value']},number]")

        if token["type"] == "keyExplicitFlag":
            return SearchKey(name=f"flags[{token['key']['value']}]")

        if token["type"] == "keyExplicitStringFlag":
            return SearchKey(name=f"flags[{token['key']['value']},string]")

        if token["type"] == "keyExplicitNumberFlag":
            return SearchKey(name=f"flags[{token['key']['value']},number]")

        if token["type"] == "keyAggregate":
            name = node_visitor(token["name"]).name
            # Consistent join aggregate function parameters
            args = ", ".join(arg["value"]["value"] for arg in token["args"]["args"])
            return AggregateKey(name=f"{name}({args})")

        if token["type"] == "valueText":
            # Noramlize values by removing the escaped quotes
            value = token["value"].replace('\\"', '"')
            return SearchValue(raw_value=value)

        if token["type"] == "valueNumber":
            return SearchValue(raw_value=parse_numeric_value(token["value"], token["unit"]))

        if token["type"] == "valueTextList":
            return SearchValue(raw_value=[item["value"]["value"] for item in token["items"]])

        if token["type"] == "valueNumberList":
            return SearchValue(
                raw_value=[
                    parse_numeric_value(item["value"]["value"], item["value"]["unit"])
                    for item in token["items"]
                ]
            )

        if token["type"] == "valueIso8601Date":
            return SearchValue(raw_value=parse_datetime_string(token["value"]))

        if token["type"] == "valueDuration":
            return SearchValue(raw_value=parse_duration(token["value"], token["unit"]))

        if token["type"] == "valueRelativeDate":
            return SearchValue(raw_value=parse_duration(token["value"], token["unit"]))

        if token["type"] == "valueBoolean":
            return SearchValue(raw_value=int(token["value"].lower() in ("1", "true")))

        if token["type"] == "freeText":
            if token["quoted"]:
                # Normalize quotes
                value = token["value"].replace('\\"', '"')
            else:
                # Normalize spacing
                value = token["value"].strip(" ")

            if value == "":
                return None

            return SearchFilter(
                key=SearchKey(name="message"),
                operator="=",
                value=SearchValue(raw_value=value),
            )

    return [token for token in map(node_visitor, result) if token is not None]


class ParseSearchQueryTest(SimpleTestCase):
    """
    All test cases in this class are dynamically defined via the test fixtures
    which are shared with the frontend.

    See the `assign_test_case` function.
    """

    def run_test_case(self, name, case):
        expected = None
        expect_error = None

        query = case["query"]

        # We include the path to the test data in the case of failure
        path = os.path.join(fixture_path, f"{name}.json")
        failure_help = f'Mismatch for query "{query}"\nExpected test data located in {path}'

        # Generically bad search query that is marked to raise an error
        if case.get("raisesError"):
            expect_error = True

        try:
            expected = result_transformer(case["result"])
        except InvalidSearchQuery:
            # If our expected result will raise an InvalidSearchQuery from one
            # of the filters we handle that here
            expect_error = True

        if expect_error:
            with pytest.raises(InvalidSearchQuery):
                parse_search_query(query)
            return

        assert parse_search_query(query) == expected, failure_help


# Shared test cases which should not be run. Usually because we have a test
# case in ParseSearchQueryBackendTest that covers something that differs
# between the backend and frontend parser.
shared_tests_skipped = [
    "rel_time_filter",
    "aggregate_rel_time_filter",
    "specific_time_filter",
    "timestamp_rollup",
    "has_tag",
    "not_has_tag",
    "supported_tags",
    "invalid_aggregate_column_with_duration_filter",
    "invalid_numeric_aggregate_filter",
    "disallow_wildcard_filter",
]

register_fixture_tests(ParseSearchQueryTest, shared_tests_skipped)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        pytest.param([], [], id="noop"),
        pytest.param([1, 2, 3], [1, 2, 3], id="flat"),
        pytest.param([[1], [2]], [1, 2], id="nested"),
        # technically this isn't supported by the annotations but it works
        pytest.param([[1], 2], [1, 2], id="staggered"),
        pytest.param([1, [2]], [1, 2], id="staggered reversed"),
    ),
)
def test_flatten(value: _RecursiveList[int], expected: list[int]) -> None:
    assert flatten(value) == expected


class ParseSearchQueryBackendTest(SimpleTestCase):
    """
    These test cases cannot be represented by the test data used to drive the
    ParseSearchQueryTest.
    """

    def test_key_remapping(self) -> None:
        config = SearchConfig(key_mappings={"target_value": ["someValue", "legacy-value"]})

        assert parse_search_query(
            "someValue:123 legacy-value:456 normal_value:hello", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="target_value"), operator="=", value=SearchValue("123")
            ),
            SearchFilter(
                key=SearchKey(name="target_value"), operator="=", value=SearchValue("456")
            ),
            SearchFilter(
                key=SearchKey(name="normal_value"), operator="=", value=SearchValue("hello")
            ),
        ]

    def test_paren_expression(self) -> None:
        assert parse_search_query("(x:1 OR y:1) AND z:1") == [
            ParenExpression(
                children=[
                    SearchFilter(
                        key=SearchKey(name="x"), operator="=", value=SearchValue(raw_value="1")
                    ),
                    "OR",
                    SearchFilter(
                        key=SearchKey(name="y"), operator="=", value=SearchValue(raw_value="1")
                    ),
                ]
            ),
            "AND",
            SearchFilter(key=SearchKey(name="z"), operator="=", value=SearchValue(raw_value="1")),
        ]

    def test_paren_expression_of_empty_string(self) -> None:
        assert parse_search_query('("")') == parse_search_query('""') == []

    def test_paren_expression_with_bool_disabled(self) -> None:
        config = SearchConfig.create_from(default_config, allow_boolean=False)
        ret = parse_search_query("( x:1 )", config=config)
        assert ret == [
            SearchFilter(
                key=SearchKey(name="message"), operator="=", value=SearchValue(raw_value="( x:1 )")
            )
        ]

    def test_paren_expression_to_query_string(self) -> None:
        (val,) = parse_search_query("(has:1 random():<5)")
        assert isinstance(val, ParenExpression)
        assert val.to_query_string() == "(has:=1 random():<5.0)"

    def test_bool_operator_with_bool_disabled(self) -> None:
        config = SearchConfig.create_from(default_config, allow_boolean=False)
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("x:1 OR y:1", config=config)
        (msg,) = excinfo.value.args
        assert msg == 'Boolean statements containing "OR" or "AND" are not supported in this search'

    def test_wildcard_free_text(self) -> None:
        config = SearchConfig.create_from(default_config, wildcard_free_text=True)
        assert parse_search_query("foo", config=config) == [
            SearchFilter(
                key=SearchKey(name="message"), operator="=", value=SearchValue(raw_value="*foo*")
            )
        ]
        # already wildcarded
        assert parse_search_query("*foo", config=config) == [
            SearchFilter(
                key=SearchKey(name="message"), operator="=", value=SearchValue(raw_value="*foo")
            )
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_size_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "gigabyte"

        assert parse_search_query("measurements.foo:>5gb measurements.bar:<3pb", config=config) == [
            SearchFilter(
                key=SearchKey(name="measurements.foo"),
                operator=">",
                value=SearchValue(5 * 1000**3),
            ),
            SearchFilter(
                key=SearchKey(name="measurements.bar"),
                operator="<",
                value=SearchValue(3 * 1000**5),
            ),
        ]

    def test_size_field_unrelated_field(self) -> None:
        assert parse_search_query("something:5gb") == [
            SearchFilter(
                key=SearchKey(name="something"), operator="=", value=SearchValue(raw_value="5gb")
            )
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_ibyte_size_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "gibibyte"

        assert parse_search_query(
            "measurements.foo:>5gib measurements.bar:<3pib", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="measurements.foo"),
                operator=">",
                value=SearchValue(5 * 1024**3),
            ),
            SearchFilter(
                key=SearchKey(name="measurements.bar"),
                operator="<",
                value=SearchValue(3 * 1024**5),
            ),
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_aggregate_size_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "gigabyte"

        assert parse_search_query(
            "p50(measurements.foo):>5gb p100(measurements.bar):<3pb", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="p50(measurements.foo)"),
                operator=">",
                value=SearchValue(5 * 1000**3),
            ),
            SearchFilter(
                key=SearchKey(name="p100(measurements.bar)"),
                operator="<",
                value=SearchValue(3 * 1000**5),
            ),
        ]

    def test_aggregate_empty_quoted_arg(self) -> None:
        assert parse_search_query('p50(""):5') == [
            AggregateFilter(
                key=AggregateKey(name='p50("")'), operator="=", value=SearchValue(raw_value=5.0)
            )
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_aggregate_ibyte_size_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "gibibyte"

        assert parse_search_query(
            "p50(measurements.foo):>5gib p100(measurements.bar):<3pib", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="p50(measurements.foo)"),
                operator=">",
                value=SearchValue(5 * 1024**3),
            ),
            SearchFilter(
                key=SearchKey(name="p100(measurements.bar)"),
                operator="<",
                value=SearchValue(3 * 1024**5),
            ),
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_duration_measurement_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "second"

        assert parse_search_query("measurements.foo:>5s measurements.bar:<3m", config=config) == [
            SearchFilter(
                key=SearchKey(name="measurements.foo"),
                operator=">",
                value=SearchValue(5 * 1000),
            ),
            SearchFilter(
                key=SearchKey(name="measurements.bar"),
                operator="<",
                value=SearchValue(3 * 1000 * 60),
            ),
        ]

    def test_invalid_duration(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("transaction.duration:>1111111111w")
        (msg,) = excinfo.value.args
        assert msg == "1111111111w is too large of a value, the maximum value is 999999999 days"

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_aggregate_duration_measurement_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "minute"

        assert parse_search_query(
            "p50(measurements.foo):>5s p100(measurements.bar):<3m", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="p50(measurements.foo)"),
                operator=">",
                value=SearchValue(5 * 1000),
            ),
            SearchFilter(
                key=SearchKey(name="p100(measurements.bar)"),
                operator="<",
                value=SearchValue(3 * 1000 * 60),
            ),
        ]

    def test_invalid_aggregate_duration(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("trend_difference():>1111111111w")
        (msg,) = excinfo.value.args
        assert msg == "1111111111w is too large of a value, the maximum value is 999999999 days"

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_numeric_measurement_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "number"

        assert parse_search_query("measurements.foo:>5k measurements.bar:<3m", config=config) == [
            SearchFilter(
                key=SearchKey(name="measurements.foo"),
                operator=">",
                value=SearchValue(5 * 1000),
            ),
            SearchFilter(
                key=SearchKey(name="measurements.bar"),
                operator="<",
                value=SearchValue(3 * 1_000_000),
            ),
        ]

    @patch("sentry.search.events.builder.base.BaseQueryBuilder.get_field_type")
    def test_aggregate_numeric_measurement_filter(self, mock_type: MagicMock) -> None:
        config = SearchConfig()
        mock_type.return_value = "number"

        assert parse_search_query(
            "p50(measurements.foo):>5k p100(measurements.bar):<3m", config=config
        ) == [
            SearchFilter(
                key=SearchKey(name="p50(measurements.foo)"),
                operator=">",
                value=SearchValue(5 * 1000),
            ),
            SearchFilter(
                key=SearchKey(name="p100(measurements.bar)"),
                operator="<",
                value=SearchValue(3 * 1_000_000),
            ),
        ]

    def test_rel_time_filter(self) -> None:
        now = timezone.now()
        with freeze_time(now):
            assert parse_search_query("time:+7d") == [
                SearchFilter(
                    key=SearchKey(name="time"),
                    operator="<=",
                    value=SearchValue(raw_value=now - timedelta(days=7)),
                )
            ]
            assert parse_search_query("time:-2w") == [
                SearchFilter(
                    key=SearchKey(name="time"),
                    operator=">=",
                    value=SearchValue(raw_value=now - timedelta(days=14)),
                )
            ]
            assert parse_search_query("random:-2w") == [
                SearchFilter(key=SearchKey(name="random"), operator="=", value=SearchValue("-2w"))
            ]

    def test_invalid_rel_time_filter(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query(f'time:+{"1" * 9999}d')
        (msg,) = excinfo.value.args
        assert msg.endswith(" is not a valid datetime query")

    def test_aggregate_rel_time_filter(self) -> None:
        now = timezone.now()
        with freeze_time(now):
            assert parse_search_query("last_seen():+7d") == [
                AggregateFilter(
                    key=AggregateKey(name="last_seen()"),
                    operator="<=",
                    value=SearchValue(raw_value=now - timedelta(days=7)),
                )
            ]
            assert parse_search_query("last_seen():-2w") == [
                AggregateFilter(
                    key=AggregateKey(name="last_seen()"),
                    operator=">=",
                    value=SearchValue(raw_value=now - timedelta(days=14)),
                )
            ]
            assert parse_search_query("random():-2w") == [
                SearchFilter(key=SearchKey(name="random()"), operator="=", value=SearchValue("-2w"))
            ]

    def test_invalid_aggregate_rel_time_filter(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query(f'last_seen():+{"1" * 9999}d')
        (msg,) = excinfo.value.args
        assert msg.endswith(" is not a valid datetime query")

    def test_invalid_date_filter(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("time:>0000-00-00")
        (msg,) = excinfo.value.args
        assert msg == "0000-00-00 is not a valid ISO8601 date query"

    def test_specific_time_filter(self) -> None:
        assert parse_search_query("time:2018-01-01") == [
            SearchFilter(
                key=SearchKey(name="time"),
                operator=">=",
                value=SearchValue(raw_value=datetime.datetime(2018, 1, 1, tzinfo=datetime.UTC)),
            ),
            SearchFilter(
                key=SearchKey(name="time"),
                operator="<",
                value=SearchValue(raw_value=datetime.datetime(2018, 1, 2, tzinfo=datetime.UTC)),
            ),
        ]

        assert parse_search_query("time:2018-01-01T05:06:07Z") == [
            SearchFilter(
                key=SearchKey(name="time"),
                operator=">=",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 1, 7, tzinfo=datetime.UTC)
                ),
            ),
            SearchFilter(
                key=SearchKey(name="time"),
                operator="<",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 12, 7, tzinfo=datetime.UTC)
                ),
            ),
        ]

        assert parse_search_query("time:2018-01-01T05:06:07+00:00") == [
            SearchFilter(
                key=SearchKey(name="time"),
                operator=">=",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 1, 7, tzinfo=datetime.UTC)
                ),
            ),
            SearchFilter(
                key=SearchKey(name="time"),
                operator="<",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 12, 7, tzinfo=datetime.UTC)
                ),
            ),
        ]

        assert parse_search_query("random:2018-01-01T05:06:07") == [
            SearchFilter(
                key=SearchKey(name="random"),
                operator="=",
                value=SearchValue(raw_value="2018-01-01T05:06:07"),
            )
        ]

    def test_invalid_time_format(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("time:0000-00-00")
        (msg,) = excinfo.value.args
        assert msg == "0000-00-00 is not a valid datetime query"

    def test_aggregate_time_filter(self) -> None:
        assert parse_search_query("last_seen():>2025-01-01") == [
            AggregateFilter(
                key=AggregateKey(name="last_seen()"),
                operator=">",
                value=SearchValue(
                    raw_value=datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.UTC)
                ),
            )
        ]
        assert parse_search_query("random():>2025-01-01") == [
            AggregateFilter(
                key=AggregateKey(name="random()"),
                operator="=",
                value=SearchValue(raw_value=">2025-01-01"),
            )
        ]

    def test_aggregate_time_filter_invalid_date_format(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("last_seen():>0000-00-00")
        (msg,) = excinfo.value.args
        assert msg == "0000-00-00 is not a valid ISO8601 date query"

    def test_timestamp_rollup(self) -> None:
        assert parse_search_query("timestamp.to_hour:2018-01-01T05:06:07+00:00") == [
            SearchFilter(
                key=SearchKey(name="timestamp.to_hour"),
                operator=">=",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 1, 7, tzinfo=datetime.UTC)
                ),
            ),
            SearchFilter(
                key=SearchKey(name="timestamp.to_hour"),
                operator="<",
                value=SearchValue(
                    raw_value=datetime.datetime(2018, 1, 1, 5, 12, 7, tzinfo=datetime.UTC)
                ),
            ),
        ]

    def test_percentage_filter(self) -> None:
        assert parse_search_query("failure_rate():<5%") == [
            AggregateFilter(
                key=AggregateKey(name="failure_rate()"),
                operator="<",
                value=SearchValue(raw_value=0.05),
            )
        ]
        assert parse_search_query("last_seen():<5%") == [
            AggregateFilter(
                key=AggregateKey(name="last_seen()"),
                operator="=",
                value=SearchValue(raw_value="<5"),
            )
        ]

    def test_percentage_filter_unknown_column(self) -> None:
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("unknown():<5%")
        (msg,) = excinfo.value.args
        assert msg == "unknown is not a valid function"

    def test_binary_operators(self) -> None:
        ret_or = parse_search_query("has:release or has:something_else")
        assert ret_or == [
            SearchFilter(
                key=SearchKey(name="release"), operator="!=", value=SearchValue(raw_value="")
            ),
            "OR",
            SearchFilter(
                key=SearchKey(name="something_else"), operator="!=", value=SearchValue(raw_value="")
            ),
        ]

        ret_and = parse_search_query("has:release and has:something_else")
        assert ret_and == [
            SearchFilter(
                key=SearchKey(name="release"), operator="!=", value=SearchValue(raw_value="")
            ),
            "AND",
            SearchFilter(
                key=SearchKey(name="something_else"), operator="!=", value=SearchValue(raw_value="")
            ),
        ]

    def test_flags(self) -> None:
        ret_flags = parse_search_query("flags[feature.one]:true")
        assert ret_flags == [
            SearchFilter(
                key=SearchKey(name="flags[feature.one]"),
                operator="=",
                value=SearchValue(raw_value="true"),
            )
        ]

        ret_flags_numeric = parse_search_query("flags[feature.two,number]:123")
        assert ret_flags_numeric == [
            SearchFilter(
                key=SearchKey(name="flags[feature.two,number]"),
                operator="=",
                value=SearchValue(raw_value="123"),
            )
        ]

        ret_flags_string = parse_search_query("flags[feature.three,string]:prod")
        assert ret_flags_string == [
            SearchFilter(
                key=SearchKey(name="flags[feature.three,string]"),
                operator="=",
                value=SearchValue(raw_value="prod"),
            )
        ]

    def test_has_tag(self) -> None:
        # unquoted key
        assert parse_search_query("has:release") == [
            SearchFilter(
                key=SearchKey(name="release"), operator="!=", value=SearchValue(raw_value="")
            )
        ]

        # quoted key
        assert parse_search_query('has:"hi:there"') == [
            SearchFilter(
                key=SearchKey(name="hi:there"), operator="!=", value=SearchValue(raw_value="")
            )
        ]

        # malformed key
        with pytest.raises(InvalidSearchQuery):
            parse_search_query('has:"hi there"')

    def test_not_has_tag(self) -> None:
        # unquoted key
        assert parse_search_query("!has:release") == [
            SearchFilter(key=SearchKey(name="release"), operator="=", value=SearchValue(""))
        ]

        # quoted key
        assert parse_search_query('!has:"hi:there"') == [
            SearchFilter(key=SearchKey(name="hi:there"), operator="=", value=SearchValue(""))
        ]

    def test_allowed_keys(self) -> None:
        config = SearchConfig(allowed_keys={"good_key"})

        assert parse_search_query("good_key:123 bad_key:123 text") == [
            SearchFilter(key=SearchKey(name="good_key"), operator="=", value=SearchValue("123")),
            SearchFilter(key=SearchKey(name="bad_key"), operator="=", value=SearchValue("123")),
            SearchFilter(key=SearchKey(name="message"), operator="=", value=SearchValue("text")),
        ]

        with pytest.raises(InvalidSearchQuery, match="Invalid key for this search"):
            assert parse_search_query("good_key:123 bad_key:123 text", config=config)

        assert parse_search_query("good_key:123 text", config=config) == [
            SearchFilter(key=SearchKey(name="good_key"), operator="=", value=SearchValue("123")),
            SearchFilter(key=SearchKey(name="message"), operator="=", value=SearchValue("text")),
        ]

    def test_blocked_keys(self) -> None:
        config = SearchConfig(blocked_keys={"bad_key"})

        assert parse_search_query("some_key:123 bad_key:123 text") == [
            SearchFilter(key=SearchKey(name="some_key"), operator="=", value=SearchValue("123")),
            SearchFilter(key=SearchKey(name="bad_key"), operator="=", value=SearchValue("123")),
            SearchFilter(key=SearchKey(name="message"), operator="=", value=SearchValue("text")),
        ]

        with pytest.raises(InvalidSearchQuery, match="Invalid key for this search: bad_key"):
            assert parse_search_query("some_key:123 bad_key:123 text", config=config)

        assert parse_search_query("some_key:123 some_other_key:456 text", config=config) == [
            SearchFilter(key=SearchKey(name="some_key"), operator="=", value=SearchValue("123")),
            SearchFilter(
                key=SearchKey(name="some_other_key"), operator="=", value=SearchValue("456")
            ),
            SearchFilter(key=SearchKey(name="message"), operator="=", value=SearchValue("text")),
        ]

    def test_invalid_aggregate_column_with_duration_filter(self) -> None:
        with self.assertRaisesMessage(
            InvalidSearchQuery,
            expected_message="avg: column argument invalid: stack.colno is not a numeric column",
        ):
            parse_search_query("avg(stack.colno):>500s")

    def test_invalid_numeric_aggregate_filter(self) -> None:
        with self.assertRaisesMessage(
            InvalidSearchQuery, "is not a valid number suffix, must be k, m or b"
        ):
            parse_search_query("min(measurements.size):3s")

        with self.assertRaisesMessage(
            InvalidSearchQuery, "is not a valid number suffix, must be k, m or b"
        ):
            parse_search_query("count_if(measurements.fcp, greater, 5s):3s")

    def test_is_query_unsupported(self) -> None:
        with pytest.raises(
            InvalidSearchQuery, match=".*queries are not supported in this search.*"
        ):
            parse_search_query("is:unassigned")

    def test_is_query_when_configured(self) -> None:
        config = SearchConfig.create_from(
            default_config,
            is_filter_translation={
                "assigned": ("status", ("unassigned", False)),
                "unassigned": ("status", ("unasssigned", True)),
            },
        )
        ret = parse_search_query("is:assigned", config=config)
        assert ret == [
            SearchFilter(
                key=SearchKey(name="status"),
                operator="=",
                value=SearchValue(raw_value=("unassigned", False)),  # type: ignore[arg-type]  # XXX: soon
            )
        ]

    def test_is_query_invalid_is_value_when_configured(self) -> None:
        config = SearchConfig.create_from(
            default_config,
            is_filter_translation={
                "assigned": ("status", ("unassigned", False)),
                "unassigned": ("status", ("unasssigned", True)),
            },
        )
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("is:unrelated", config=config)
        (msg,) = excinfo.value.args
        assert msg == "Invalid value for \"is\" search, valid values are ['assigned', 'unassigned']"

    def test_is_query_invalid_is_value_syntax(self) -> None:
        config = SearchConfig.create_from(
            default_config,
            is_filter_translation={
                "assigned": ("status", ("unassigned", False)),
                "unassigned": ("status", ("unasssigned", True)),
            },
        )
        with pytest.raises(InvalidSearchQuery) as excinfo:
            parse_search_query("is:[assigned]", config=config)
        (msg,) = excinfo.value.args
        assert msg == '"in" syntax invalid for "is" search'

    def test_escaping_asterisk(self) -> None:
        # the asterisk is escaped with a preceding backslash, so it's a literal and not a wildcard
        search_filters = parse_search_query(r"title:a\*b")
        assert search_filters == [
            SearchFilter(key=SearchKey(name="title"), operator="=", value=SearchValue(r"a\*b"))
        ]
        search_filter = search_filters[0]
        # the slash should be removed in the final value
        assert isinstance(search_filter, SearchFilter)
        assert search_filter.value.value == "a*b"

        # the first and last asterisks arent escaped with a preceding backslash, so they're
        # wildcards and not literals
        search_filters = parse_search_query(r"title:*\**")
        assert search_filters == [
            SearchFilter(key=SearchKey(name="title"), operator="=", value=SearchValue(r"*\**"))
        ]
        search_filter = search_filters[0]
        assert isinstance(search_filter, SearchFilter)
        assert search_filter.value.value == r"^.*\*.*$"

    @pytest.mark.xfail(reason="escaping backslashes is not supported yet")
    def test_escaping_backslashes(self) -> None:
        search_filters = parse_search_query(r"title:a\\b")
        assert search_filters == [
            SearchFilter(key=SearchKey(name="title"), operator="=", value=SearchValue(r"a\\b"))
        ]
        search_filter = search_filters[0]
        # the extra slash should be removed in the final value
        assert isinstance(search_filter, SearchFilter)
        assert search_filter.value.value == r"a\b"

    @pytest.mark.xfail(reason="escaping backslashes is not supported yet")
    def test_trailing_escaping_backslashes(self) -> None:
        search_filters = parse_search_query(r"title:a\\")
        assert search_filters == [
            SearchFilter(key=SearchKey(name="title"), operator="=", value=SearchValue(r"a\\"))
        ]
        search_filter = search_filters[0]
        # the extra slash should be removed in the final value
        assert isinstance(search_filter, SearchFilter)
        assert search_filter.value.value == "a\\"

    def test_escaping_quotes(self) -> None:
        search_filters = parse_search_query(r"title:a\"b")
        assert search_filters == [
            SearchFilter(key=SearchKey(name="title"), operator="=", value=SearchValue(r'a"b'))
        ]
        search_filter = search_filters[0]
        # the slash should be removed in the final value
        assert isinstance(search_filter, SearchFilter)
        assert search_filter.value.value == 'a"b'


@pytest.mark.parametrize(
    "raw,result",
    [
        (r"", r""),
        (r"foo", r"foo"),
        (r"foo*bar", r"^foo.*bar$"),
        (r"foo\*bar", r"foo*bar"),
        (r"foo\\*bar", r"^foo\\.*bar$"),
        (r"foo\\\*bar", r"foo\\*bar"),
        (r"foo*", r"^foo.*$"),
        (r"foo\*", r"foo*"),
        (r"foo\\*", r"^foo\\.*$"),
        (r"foo\\\*", r"foo\\*"),
        (r"*bar", r"^.*bar$"),
        (r"\*bar", r"*bar"),
        (r"\\*bar", r"^\\.*bar$"),
        (r"\\\*bar", r"\\*bar"),
        (r"*\**", r"^.*\*.*$"),
        (r"\*a\*b\*c\*", r"*a*b*c*"),
        (r"\*\*\*aaa\*\*\*", r"***aaa***"),
    ],
)
def test_search_value(raw, result) -> None:
    search_value = SearchValue(raw)
    assert search_value.value == result


@pytest.mark.parametrize(
    "query",
    [
        "event.type:=transaction",
        "!event.type:[transaction]",
        "event.type:[transaction, event]",
        "event.type:[1, 2]",
        "transaction.duration:>=1.0",
        "transaction.duration:>1.0",
        "transaction.duration:=1.0",
        "transaction.duration:<=1.0",
        "transaction.duration:<1.0",
    ],
)
def test_search_filter_to_query_string(query) -> None:
    """
    Does a round trip (from query string to tokens and back to query string)
    """

    filters = parse_search_query(query)
    assert len(filters) == 1
    assert isinstance(filters[0], SearchFilter)
    actual = filters[0].to_query_string()
    assert actual == query


@pytest.mark.parametrize(
    "value,expected_query_string",
    [
        (1, "1"),
        ("abc", "abc"),
        ([1, 2, 3], "[1, 2, 3]"),
        (["a", "b", "c"], "[a, b, c]"),
        (datetime.datetime(2023, 10, 15, 11, 12, 13), "2023-10-15T11:12:13"),
    ],
)
def test_search_value_to_query_string(value, expected_query_string) -> None:
    """
    Test turning a QueryValue back to a string usable in a query string
    """

    search_value = SearchValue(value)
    actual = search_value.to_query_string()

    assert actual == expected_query_string


@pytest.mark.parametrize(
    ["value", "expected_kind", "expected_value"],
    [
        (1, "other", 1),
        ("1", "other", "1"),
        ("*", "suffix", ""),  # consider special casing this
        ("*foo", "suffix", "foo"),
        ("foo*", "prefix", "foo"),
        ("*foo*", "infix", "foo"),
        (r"\*foo", "other", r"*foo"),
        (r"\\*foo", "other", r"^\\.*foo$"),
        (r"foo\*", "other", r"foo*"),
        (r"foo\\*", "prefix", r"foo\\"),
        ("*f*o*o*", "other", "^.*f.*o.*o.*$"),
        (r"*foo\*", "suffix", r"foo*"),
        (r"*foo\\*", "infix", r"foo\\"),
        pytest.param("*Case*", "infix", "Case", id="infix casing is kept"),
        pytest.param("*Case", "suffix", "case", id="suffix is lower cased"),
        pytest.param("Case*", "prefix", "case", id="prefix is lower cased"),
    ],
)
def test_search_value_classify_and_format_wildcard(value, expected_kind, expected_value) -> None:
    """
    Test classifying the wildcard type into one of prefix/suffix/infix/other
    and formatting the value according to the classification results.
    """
    search_value = SearchValue(value)
    kind, wildcard = search_value.classify_and_format_wildcard()
    assert (kind, wildcard) == (expected_kind, expected_value)


@pytest.mark.parametrize(
    ["pattern", "clickhouse"],
    [
        pytest.param("simple", "simple", id="simple"),
        pytest.param("wild * card", "wild % card", id="wildcard"),
        pytest.param("under_score", "under\\_score", id="underscore"),
        pytest.param("per%centage", "per\\%centage", id="percentage"),
        pytest.param("ast\\*erisk", "ast*erisk", id="asterisk"),
        pytest.param("c*o_m%p\\*lex", "c%o\\_m\\%p*lex", id="complex"),
    ],
)
def test_translate_wildcard_as_clickhouse_pattern(pattern, clickhouse) -> None:
    assert translate_wildcard_as_clickhouse_pattern(pattern) == clickhouse


@pytest.mark.parametrize(
    ["pattern"],
    [
        pytest.param("\\."),
        pytest.param("\\%"),
        pytest.param("\\_"),
    ],
)
def test_invalid_translate_wildcard_as_clickhouse_pattern(pattern) -> None:
    with pytest.raises(InvalidSearchQuery):
        assert translate_wildcard_as_clickhouse_pattern(pattern)


@pytest.mark.parametrize(
    ["query", "key", "value"],
    [
        pytest.param("tags[foo/bar]:baz", "message", "tags[foo/bar]:baz"),
        pytest.param("flags[foo/bar]:baz", "message", "flags[foo/bar]:baz"),
        pytest.param("tags[foo]:true", "tags[foo]", "true"),
        pytest.param("tags[foo,string]:true", "tags[foo,string]", "true"),
        pytest.param("tags[foo:bar,string]:true", "tags[foo:bar,string]", "true"),
        pytest.param("tags[foo,number]:0", "tags[foo,number]", "0"),
        pytest.param("tags[foo:bar,number]:0", "tags[foo:bar,number]", "0"),
        pytest.param("flags[foo]:true", "flags[foo]", "true"),
        pytest.param("flags[foo,string]:true", "flags[foo,string]", "true"),
        pytest.param("flags[foo:bar,string]:true", "flags[foo:bar,string]", "true"),
        pytest.param("flags[foo,number]:0", "flags[foo,number]", "0"),
        pytest.param("flags[foo:bar,number]:0", "flags[foo:bar,number]", "0"),
    ],
)
def test_handles_special_character_in_tags_and_flags(query, key, value) -> None:
    parsed = parse_search_query(query)
    assert parsed == [SearchFilter(SearchKey(key), "=", SearchValue(value))]


@pytest.mark.parametrize(
    ["query", "key"],
    [
        pytest.param("has:tags[foo]", "tags[foo]"),
        pytest.param("has:tags[foo,string]", "tags[foo,string]"),
        pytest.param("has:tags[foo,number]", "tags[foo,number]"),
        pytest.param("has:tags[foo:bar]", "tags[foo:bar]"),
        pytest.param("has:tags[foo:bar,string]", "tags[foo:bar,string]"),
        pytest.param("has:tags[foo:bar,number]", "tags[foo:bar,number]"),
        pytest.param("has:flags[foo]", "flags[foo]"),
        pytest.param("has:flags[foo,string]", "flags[foo,string]"),
        pytest.param("has:flags[foo,number]", "flags[foo,number]"),
        pytest.param("has:flags[foo:bar]", "flags[foo:bar]"),
        pytest.param("has:flags[foo:bar,string]", "flags[foo:bar,string]"),
        pytest.param("has:flags[foo:bar,number]", "flags[foo:bar,number]"),
    ],
)
def test_handles_has_tags_and_flags(query, key) -> None:
    parsed = parse_search_query(query)
    assert parsed == [SearchFilter(SearchKey(key), "!=", SearchValue(""))]
