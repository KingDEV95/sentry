import logging
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, NotRequired, TypedDict

import sentry_sdk
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.response import Response

from sentry import features, options
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases import NoProjects, OrganizationEventsV2EndpointBase
from sentry.api.helpers.error_upsampling import (
    is_errors_query_for_error_upsampled_projects,
    transform_query_columns_for_error_upsampling,
)
from sentry.api.paginator import GenericOffsetPaginator
from sentry.api.utils import handle_query_errors
from sentry.apidocs import constants as api_constants
from sentry.apidocs.examples.discover_performance_examples import DiscoverAndPerformanceExamples
from sentry.apidocs.parameters import GlobalParams, OrganizationParams, VisibilityParams
from sentry.apidocs.utils import inline_sentry_response_serializer
from sentry.discover.models import DiscoverSavedQuery, DiscoverSavedQueryTypes
from sentry.exceptions import InvalidParams
from sentry.models.dashboard_widget import DashboardWidget, DashboardWidgetTypes
from sentry.models.organization import Organization
from sentry.search.eap.types import FieldsACL, SearchResolverConfig
from sentry.snuba import (
    discover,
    errors,
    metrics_enhanced_performance,
    metrics_performance,
    transactions,
    uptime_results,
)
from sentry.snuba.metrics.extraction import MetricSpecType
from sentry.snuba.ourlogs import OurLogs
from sentry.snuba.referrer import Referrer, is_valid_referrer
from sentry.snuba.spans_rpc import Spans
from sentry.snuba.types import DatasetQuery
from sentry.snuba.utils import RPC_DATASETS, dataset_split_decision_inferred_from_query, get_dataset
from sentry.types.ratelimit import RateLimit, RateLimitCategory
from sentry.utils.snuba import SnubaError

logger = logging.getLogger(__name__)

METRICS_ENHANCED_REFERRERS = {Referrer.API_PERFORMANCE_LANDING_TABLE.value}
SAVED_QUERY_DATASET_MAP = {
    DiscoverSavedQueryTypes.TRANSACTION_LIKE: get_dataset("transactions"),
    DiscoverSavedQueryTypes.ERROR_EVENTS: get_dataset("errors"),
}
# TODO: Adjust this once we make a decision in the DACI for global views restriction
# Do not add more referrers to this list as it is a temporary solution
GLOBAL_VIEW_ALLOWLIST = {Referrer.API_ISSUES_ISSUE_EVENTS.value}


class DiscoverDatasetSplitException(Exception):
    pass


LEGACY_RATE_LIMIT = dict(limit=30, window=1, concurrent_limit=15)
# reduced limit will be the future default for all organizations not explicitly on increased limit
DEFAULT_REDUCED_RATE_LIMIT = dict(
    limit=1000, window=300, concurrent_limit=15  # 1000 requests per 5 minutes
)
DEFAULT_INCREASED_RATE_LIMIT = dict(limit=50, window=1, concurrent_limit=50)


class EventsMeta(TypedDict):
    fields: dict[str, str]
    datasetReason: NotRequired[str]
    isMetricsData: NotRequired[bool]
    isMetricsExtractedData: NotRequired[bool]


# Only used for api docs
class EventsApiResponse(TypedDict):
    data: list[dict[str, Any]]
    meta: EventsMeta


def rate_limit_events(
    request: Request, organization_id_or_slug: str | None = None, *args, **kwargs
) -> dict[str, dict[RateLimitCategory, RateLimit]]:
    """
    Decision tree for rate limiting for organization events endpoint.
    ```mermaid
     flowchart TD
         A[Get organization] --> B{Organization\nexists}
         B -->|No| C[Return legacy rate limit]
         B -->|Yes| D{Organization\nin increased\nrate limit}
         D -->|Yes| E[Return increased rate limit]
         D -->|No| F{Organization in\nreduced limit\nroll-out}
         F -->|Yes| G[Return reduced rate limit]
         F -->|No| H[Return legacy rate limit]
     ```
    """

    def _config_for_limit(limit: RateLimit) -> dict[str, dict[RateLimitCategory, RateLimit]]:
        return {
            "GET": {
                RateLimitCategory.IP: limit,
                RateLimitCategory.USER: limit,
                RateLimitCategory.ORGANIZATION: limit,
            }
        }

    def _validated_limits(limits: dict[str, Any], fallback: dict[str, Any]) -> RateLimit:
        """
        Validate the rate limit configuration has required values of correct type.
        """
        try:
            # dataclass doesn't check types, so forcing int which will raise if not int or numeric string
            limits = {k: int(v) for k, v in limits.items()}
            return RateLimit(**limits)
        except Exception:
            logger.exception("invalid rate limit config", extra={"limits": limits})
            return RateLimit(**fallback)

    rate_limit = RateLimit(**LEGACY_RATE_LIMIT)

    try:
        if str(organization_id_or_slug).isdecimal():
            organization = Organization.objects.get_from_cache(id=organization_id_or_slug)
        else:
            organization = Organization.objects.get_from_cache(slug=organization_id_or_slug)
    except Organization.DoesNotExist:
        logger.warning(
            "organization.slug.invalid", extra={"organization_id_or_slug": organization_id_or_slug}
        )
        return _config_for_limit(rate_limit)

    if organization.id in options.get("api.organization_events.rate-limit-increased.orgs", []):
        rate_limit = _validated_limits(
            options.get("api.organization_events.rate-limit-increased.limits"),
            DEFAULT_INCREASED_RATE_LIMIT,
        )

    elif features.has(
        "organizations:api-organization_events-rate-limit-reduced-rollout",
        organization=organization,
    ):

        rate_limit = _validated_limits(
            options.get("api.organization_events.rate-limit-reduced.limits"),
            DEFAULT_REDUCED_RATE_LIMIT,
        )

    return _config_for_limit(rate_limit)


@extend_schema(tags=["Discover"])
@region_silo_endpoint
class OrganizationEventsEndpoint(OrganizationEventsV2EndpointBase):
    publish_status = {
        "GET": ApiPublishStatus.PUBLIC,
    }

    enforce_rate_limit = True

    rate_limits = rate_limit_events

    def get_features(self, organization: Organization, request: Request) -> Mapping[str, bool]:
        feature_names = [
            "organizations:dashboards-mep",
            "organizations:mep-rollout-flag",
            "organizations:performance-use-metrics",
            "organizations:profiling",
            "organizations:dynamic-sampling",
            "organizations:use-metrics-layer",
            "organizations:starfish-view",
            "organizations:on-demand-metrics-extraction",
            "organizations:on-demand-metrics-extraction-widgets",
            "organizations:on-demand-metrics-extraction-experimental",
        ]
        batch_features = features.batch_has(
            feature_names,
            organization=organization,
            actor=request.user,
        )

        all_features: dict[str, bool] = {}

        if batch_features is not None:
            for feature_name, result in batch_features.get(
                f"organization:{organization.id}", {}
            ).items():
                all_features[feature_name] = bool(result)

        for feature_name in feature_names:
            if feature_name not in all_features:
                all_features[feature_name] = features.has(
                    feature_name, organization=organization, actor=request.user
                )

        return all_features

    @extend_schema(
        operation_id="Query Discover Events in Table Format",
        parameters=[
            GlobalParams.END,
            GlobalParams.ENVIRONMENT,
            GlobalParams.ORG_ID_OR_SLUG,
            OrganizationParams.PROJECT,
            GlobalParams.START,
            GlobalParams.STATS_PERIOD,
            VisibilityParams.FIELD,
            VisibilityParams.PER_PAGE,
            VisibilityParams.QUERY,
            VisibilityParams.SORT,
        ],
        responses={
            200: inline_sentry_response_serializer(
                "OrganizationEventsResponseDict", EventsApiResponse
            ),
            400: OpenApiResponse(description="Invalid Query"),
            404: api_constants.RESPONSE_NOT_FOUND,
        },
        examples=DiscoverAndPerformanceExamples.QUERY_DISCOVER_EVENTS,
    )
    def get(self, request: Request, organization: Organization) -> Response:
        """
        Retrieves discover (also known as events) data for a given organization.

        **Eventsv2 Deprecation Note**: Users who may be using the `eventsv2` endpoint should update their requests to the `events` endpoint outline in this document.
        The `eventsv2` endpoint is not a public endpoint and has no guaranteed availability. If you are not making any API calls to `eventsv2`, you can safely ignore this.
        Changes between `eventsv2` and `events` include:
        - Field keys in the response now match the keys in the requested `field` param exactly.
        - The `meta` object in the response now shows types in the nested `field` object.

        Aside from the url change, there are no changes to the request payload itself.

        **Note**: This endpoint is intended to get a table of results, and is not for doing a full export of data sent to
        Sentry.

        The `field` query parameter determines what fields will be selected in the `data` and `meta` keys of the endpoint response.
        - The `data` key contains a list of results row by row that match the `query` made
        - The `meta` key contains information about the response, including the unit or type of the fields requested
        """
        if not self.has_feature(organization, request):
            return Response(status=404)

        referrer = request.GET.get("referrer")

        try:
            snuba_params = self.get_snuba_params(
                request,
                organization,
                # This is only temporary until we come to a decision on global views
                # checking for referrer for an allowlist is a brittle check since referrer
                # can easily be set by the caller
                check_global_views=not (
                    referrer in GLOBAL_VIEW_ALLOWLIST and bool(organization.flags.allow_joinleave)
                ),
            )
        except NoProjects:
            return Response(
                {
                    "data": [],
                    "meta": {
                        "tips": {
                            "query": "Need at least one valid project to query.",
                        },
                    },
                }
            )
        except InvalidParams as err:
            raise ParseError(detail=str(err))

        batch_features = self.get_features(organization, request)

        use_metrics = (
            (
                batch_features.get("organizations:mep-rollout-flag", False)
                and batch_features.get("organizations:dynamic-sampling", False)
            )
            or batch_features.get("organizations:performance-use-metrics", False)
            or batch_features.get("organizations:dashboards-mep", False)
        )

        try:
            use_on_demand_metrics, on_demand_metrics_type = self.handle_on_demand(request)
        except ValueError:
            metric_type_values = [e.value for e in MetricSpecType]
            metric_types = ",".join(metric_type_values)
            return Response(
                {"detail": f"On demand metric type must be one of: {metric_types}"}, status=400
            )

        on_demand_metrics_enabled = (
            batch_features.get("organizations:on-demand-metrics-extraction", False)
            or batch_features.get("organizations:on-demand-metrics-extraction-widgets", False)
        ) and use_on_demand_metrics

        save_discover_dataset_decision = True

        dataset = self.get_dataset(request)
        metrics_enhanced = dataset in {metrics_performance, metrics_enhanced_performance}

        sentry_sdk.set_tag("performance.metrics_enhanced", metrics_enhanced)
        allow_metric_aggregates = request.GET.get("preventMetricAggregates") != "1"

        # Force the referrer to "api.auth-token.events" for events requests authorized through a bearer token
        if request.auth:
            referrer = Referrer.API_AUTH_TOKEN_EVENTS.value
        elif referrer is None or not referrer:
            referrer = Referrer.API_ORGANIZATION_EVENTS.value
        elif not is_valid_referrer(referrer):
            referrer = Referrer.API_ORGANIZATION_EVENTS.value

        use_aggregate_conditions = request.GET.get("allowAggregateConditions", "1") == "1"
        debug = request.user.is_superuser and "debug" in request.GET

        def _data_fn(
            dataset_query: DatasetQuery,
            offset: int,
            limit: int,
            query: str | None,
        ):
            selected_columns = self.get_field_list(organization, request)
            if is_errors_query_for_error_upsampled_projects(
                snuba_params, organization, dataset, request
            ):
                selected_columns = transform_query_columns_for_error_upsampling(
                    selected_columns, False
                )
            query_source = self.get_request_source(request)
            return dataset_query(
                selected_columns=selected_columns,
                query=query or "",
                snuba_params=snuba_params,
                equations=self.get_equation_list(organization, request),
                orderby=self.get_orderby(request),
                offset=offset,
                limit=limit,
                referrer=referrer,
                auto_fields=True,
                auto_aggregations=True,
                allow_metric_aggregates=allow_metric_aggregates,
                use_aggregate_conditions=use_aggregate_conditions,
                transform_alias_to_input_format=True,
                # Whether the flag is enabled or not, regardless of the referrer
                has_metrics=use_metrics,
                use_metrics_layer=batch_features.get("organizations:use-metrics-layer", False),
                on_demand_metrics_enabled=on_demand_metrics_enabled,
                on_demand_metrics_type=on_demand_metrics_type,
                fallback_to_transactions=True,
                query_source=query_source,
                debug=debug,
            )

        @sentry_sdk.tracing.trace
        def _dashboards_data_fn(
            scoped_dataset_query: DatasetQuery,
            offset: int,
            limit: int,
            scoped_query: str | None,
            dashboard_widget_id: str,
        ):
            try:
                widget = DashboardWidget.objects.get(id=dashboard_widget_id)
                does_widget_have_split = widget.discover_widget_split is not None

                if does_widget_have_split:
                    dataset_query: DatasetQuery

                    # This is essentially cached behaviour and we skip the check
                    if widget.discover_widget_split == DashboardWidgetTypes.ERROR_EVENTS:
                        dataset_query = errors.query
                    elif widget.discover_widget_split == DashboardWidgetTypes.TRANSACTION_LIKE:
                        # We can't add event.type:transaction for now because of on-demand.
                        dataset_query = scoped_dataset_query
                    else:
                        dataset_query = discover.query

                    return _data_fn(dataset_query, offset, limit, scoped_query)

                with handle_query_errors():
                    try:
                        error_results = _data_fn(errors.query, offset, limit, scoped_query)
                        # Widget has not split the discover dataset yet, so we need to check if there are errors etc.
                        has_errors = len(error_results["data"]) > 0
                    except SnubaError:
                        has_errors = False
                        error_results = None

                    original_results = _data_fn(scoped_dataset_query, offset, limit, scoped_query)
                    if original_results.get("data") is not None:
                        dataset_meta = original_results.get("meta", {})
                    else:
                        dataset_meta = (
                            list(original_results.values())[0].get("data").get("meta", {})
                        )
                    using_metrics = dataset_meta.get("isMetricsData", False) or dataset_meta.get(
                        "isMetricsExtractedData", False
                    )
                    has_other_data = len(original_results["data"]) > 0

                    has_transactions = has_other_data
                    transaction_results = None
                    if has_errors and has_other_data and not using_metrics:
                        # In the case that the original request was not using the metrics dataset, we cannot be certain that other data is solely transactions.
                        sentry_sdk.set_tag("third_split_query", True)
                        transaction_results = _data_fn(
                            transactions.query, offset, limit, scoped_query
                        )
                        has_transactions = len(transaction_results["data"]) > 0

                    decision = self.save_split_decision(
                        widget, has_errors, has_transactions, organization, request.user
                    )

                    if decision == DashboardWidgetTypes.DISCOVER:
                        return _data_fn(discover.query, offset, limit, scoped_query)
                    elif decision == DashboardWidgetTypes.TRANSACTION_LIKE:
                        original_results["meta"]["discoverSplitDecision"] = (
                            DashboardWidgetTypes.get_type_name(
                                DashboardWidgetTypes.TRANSACTION_LIKE
                            )
                        )
                        return original_results
                    elif decision == DashboardWidgetTypes.ERROR_EVENTS and error_results:
                        error_results["meta"]["discoverSplitDecision"] = (
                            DashboardWidgetTypes.get_type_name(DashboardWidgetTypes.ERROR_EVENTS)
                        )
                        return error_results
                    else:
                        return original_results
            except Exception as e:
                # Swallow the exception if it was due to the discover split, and try again one more time.
                if isinstance(e, ParseError):
                    return _data_fn(scoped_dataset_query, offset, limit, scoped_query)

                sentry_sdk.capture_exception(e)
                return _data_fn(scoped_dataset_query, offset, limit, scoped_query)

        @sentry_sdk.tracing.trace
        def _discover_data_fn(
            scoped_dataset_query: DatasetQuery,
            offset: int,
            limit: int,
            scoped_query: str | None,
            discover_saved_query_id: str,
        ):
            try:
                discover_query = DiscoverSavedQuery.objects.get(
                    id=discover_saved_query_id, organization=organization
                )
                does_widget_have_split = (
                    discover_query.dataset is not DiscoverSavedQueryTypes.DISCOVER
                )
                if does_widget_have_split:
                    with handle_query_errors():
                        return _data_fn(scoped_dataset_query, offset, limit, scoped_query)

                dataset_inferred_from_query = dataset_split_decision_inferred_from_query(
                    self.get_field_list(organization, request),
                    scoped_query,
                )
                has_errors = False
                has_transactions = False

                # See if we can infer which dataset based on selected columns and query string.
                with handle_query_errors():
                    if (
                        dataset := SAVED_QUERY_DATASET_MAP.get(dataset_inferred_from_query)
                    ) is not None:
                        result = _data_fn(
                            dataset.query,
                            offset,
                            limit,
                            scoped_query,
                        )
                        result["meta"]["discoverSplitDecision"] = (
                            DiscoverSavedQueryTypes.get_type_name(dataset_inferred_from_query)
                        )

                        self.save_discover_saved_query_split_decision(
                            discover_query,
                            dataset_inferred_from_query,
                            has_errors,
                            has_transactions,
                        )

                        return result

                    # Unable to infer based on selected fields and query string, so run both queries.
                    else:
                        map = {}
                        with ThreadPoolExecutor(max_workers=3) as exe:
                            futures = {
                                exe.submit(
                                    _data_fn, dataset_query, offset, limit, scoped_query
                                ): dataset_name
                                for dataset_name, dataset_query in [
                                    ("errors", errors.query),
                                    ("transactions", transactions.query),
                                ]
                            }

                            for future in as_completed(futures):
                                dataset_ = futures[future]
                                try:
                                    result = future.result()
                                    map[dataset_] = result
                                except SnubaError:
                                    pass

                        try:
                            error_results = map["errors"]
                            error_results["meta"]["discoverSplitDecision"] = (
                                DiscoverSavedQueryTypes.get_type_name(
                                    DiscoverSavedQueryTypes.ERROR_EVENTS
                                )
                            )
                            has_errors = len(error_results["data"]) > 0
                        except KeyError:
                            error_results = None

                        try:
                            transaction_results = map["transactions"]
                            transaction_results["meta"]["discoverSplitDecision"] = (
                                DiscoverSavedQueryTypes.get_type_name(
                                    DiscoverSavedQueryTypes.TRANSACTION_LIKE
                                )
                            )
                            has_transactions = len(transaction_results["data"]) > 0
                        except KeyError:
                            transaction_results = None

                        decision = self.save_discover_saved_query_split_decision(
                            discover_query,
                            dataset_inferred_from_query,
                            has_errors,
                            has_transactions,
                        )

                        if (
                            decision == DiscoverSavedQueryTypes.TRANSACTION_LIKE
                            and transaction_results
                        ):
                            return transaction_results
                        elif error_results:
                            return error_results
                        else:
                            raise DiscoverDatasetSplitException

            except Exception as e:
                # Swallow the exception if it was due to the discover split, and try again one more time.
                if isinstance(e, ParseError):
                    return _data_fn(scoped_dataset_query, offset, limit, scoped_query)

                sentry_sdk.capture_exception(e)
                return _data_fn(scoped_dataset_query, offset, limit, scoped_query)

        def data_fn_factory(scoped_dataset):
            """
            This factory closes over query and dataset in order to make an additional request to the errors dataset
            in the case that this request is from a dashboard widget or a discover query and we're trying to split
            their discover dataset.

            This should be removed once the discover dataset is completely split in dashboards and discover.
            """
            scoped_query = request.GET.get("query")
            dashboard_widget_id = request.GET.get("dashboardWidgetId", None)
            discover_saved_query_id = request.GET.get("discoverSavedQueryId", None)

            def fn(offset, limit):
                if scoped_dataset in RPC_DATASETS:
                    if scoped_dataset == Spans:
                        config = SearchResolverConfig(
                            auto_fields=True,
                            use_aggregate_conditions=use_aggregate_conditions,
                            fields_acl=FieldsACL(functions={"time_spent_percentage"}),
                            disable_aggregate_extrapolation="disableAggregateExtrapolation"
                            in request.GET,
                        )
                    elif scoped_dataset == OurLogs:
                        # ourlogs doesn't have use aggregate conditions
                        config = SearchResolverConfig(
                            use_aggregate_conditions=False,
                        )
                    elif scoped_dataset == uptime_results.UptimeResults:
                        config = SearchResolverConfig(
                            use_aggregate_conditions=use_aggregate_conditions, auto_fields=True
                        )
                    else:
                        config = SearchResolverConfig(
                            use_aggregate_conditions=use_aggregate_conditions,
                        )

                    return scoped_dataset.run_table_query(
                        params=snuba_params,
                        query_string=scoped_query or "",
                        selected_columns=self.get_field_list(organization, request),
                        equations=self.get_equation_list(organization, request),
                        orderby=self.get_orderby(request),
                        offset=offset,
                        limit=limit,
                        referrer=referrer,
                        config=config,
                        sampling_mode=snuba_params.sampling_mode,
                    )

                if save_discover_dataset_decision and discover_saved_query_id:
                    return _discover_data_fn(
                        scoped_dataset.query, offset, limit, scoped_query, discover_saved_query_id
                    )

                if not (metrics_enhanced and dashboard_widget_id):
                    return _data_fn(scoped_dataset.query, offset, limit, scoped_query)

                return _dashboards_data_fn(
                    scoped_dataset.query, offset, limit, scoped_query, dashboard_widget_id
                )

            return fn

        data_fn = data_fn_factory(dataset)

        max_per_page = 9999 if dataset == OurLogs else None

        def _handle_results(results):
            # Apply error upsampling for regular Events API
            self.handle_error_upsampling(snuba_params.project_ids, results)
            return self.handle_results_with_meta(
                request,
                organization,
                snuba_params.project_ids,
                results,
                standard_meta=True,
                dataset=dataset,
            )

        with handle_query_errors():
            # Don't include cursor headers if the client won't be using them
            if request.GET.get("noPagination"):
                return Response(_handle_results(data_fn(0, self.get_per_page(request))))
            else:
                return self.paginate(
                    request=request,
                    paginator=GenericOffsetPaginator(data_fn=data_fn),
                    on_results=_handle_results,
                    max_per_page=max_per_page,
                )
