from __future__ import annotations

import logging
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from botocore.exceptions import ClientError
from django.http.request import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.translation import gettext_lazy as _

from sentry import analytics, options
from sentry.analytics.events.integration_serverless_setup import IntegrationServerlessSetup
from sentry.integrations.base import (
    FeatureDescription,
    IntegrationData,
    IntegrationFeatures,
    IntegrationInstallation,
    IntegrationMetadata,
    IntegrationProvider,
)
from sentry.integrations.mixins import ServerlessMixin
from sentry.integrations.models.integration import Integration
from sentry.integrations.models.organization_integration import OrganizationIntegration
from sentry.integrations.pipeline import IntegrationPipeline
from sentry.organizations.services.organization import organization_service
from sentry.organizations.services.organization.model import RpcOrganization
from sentry.pipeline.views.base import PipelineView, render_react_view
from sentry.projects.services.project import project_service
from sentry.silo.base import control_silo_function
from sentry.users.models.user import User
from sentry.users.services.user.serial import serialize_rpc_user
from sentry.utils.sdk import capture_exception

from .client import ConfigurationError, gen_aws_client
from .utils import (
    ALL_AWS_REGIONS,
    disable_single_lambda,
    enable_single_lambda,
    get_dsn_for_project,
    get_function_layer_arns,
    get_index_of_sentry_layer,
    get_latest_layer_for_function,
    get_latest_layer_version,
    get_sentry_err_message,
    get_supported_functions,
    get_version_of_arn,
    wrap_lambda_updater,
)

if TYPE_CHECKING:
    from django.utils.functional import _StrPromise

logger = logging.getLogger("sentry.integrations.aws_lambda")

DESCRIPTION = """
The AWS Lambda integration will automatically instrument your Lambda functions without any code changes. We use CloudFormation Stack ([Learn more about CloudFormation](https://aws.amazon.com/cloudformation/)) to create Sentry role and enable errors and transactions capture from your Lambda functions.
"""


FEATURES = [
    FeatureDescription(
        """
        Instrument your serverless code automatically.
        """,
        IntegrationFeatures.SERVERLESS,
    ),
]

metadata = IntegrationMetadata(
    description=DESCRIPTION.strip(),
    features=FEATURES,
    author="The Sentry Team",
    noun=_("Installation"),
    issue_url="https://github.com/getsentry/sentry/issues/new?assignees=&labels=Component:%20Integrations&template=bug.yml&title=AWS%20Lambda%20Problem",
    source_url="https://github.com/getsentry/sentry/tree/master/src/sentry/integrations/aws_lambda",
    aspects={},
)


class AwsLambdaIntegration(IntegrationInstallation, ServerlessMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._client = None

    @property
    def region(self):
        return self.metadata["region"]

    @property
    def client(self):
        if not self._client:
            region = self.metadata["region"]
            account_number = self.metadata["account_number"]
            aws_external_id = self.metadata["aws_external_id"]
            self._client = gen_aws_client(
                account_number=account_number,
                region=region,
                aws_external_id=aws_external_id,
            )

        return self._client

    def get_client(self) -> Any:
        return self.client

    def get_one_lambda_function(self, name):
        # https://boto3.amazonaws.com/v1/documentation/api/1.22.12/reference/services/lambda.html
        return self.client.get_function(FunctionName=name)["Configuration"]

    def get_serialized_lambda_function(self, name):
        function = self.get_one_lambda_function(name)
        return self.serialize_lambda_function(function)

    def serialize_lambda_function(self, function):
        layers = get_function_layer_arns(function)
        layer_arn = get_latest_layer_for_function(function)
        function_runtime = function["Runtime"]

        # find our sentry layer
        sentry_layer_index = get_index_of_sentry_layer(layers, layer_arn)

        if sentry_layer_index > -1:
            sentry_layer = layers[sentry_layer_index]

            # determine the version and if it's out of date
            latest_version = get_latest_layer_version(function)
            current_version = get_version_of_arn(sentry_layer)
            out_of_date = latest_version > current_version

            if function_runtime.startswith("python"):
                # If env variable "SENTRY_INITIAL_HANDLER" is not present, then
                # it is should be assumed that this function is not enabled!
                env_variables = function.get("Environment", {}).get("Variables", {})
                if "SENTRY_INITIAL_HANDLER" not in env_variables:
                    current_version = -1
                    out_of_date = False
        else:
            current_version = -1
            out_of_date = False

        return {
            "name": function["FunctionName"],
            "runtime": function_runtime,
            "version": current_version,
            "outOfDate": out_of_date,
            "enabled": current_version > -1,
        }

    # ServerlessMixin interface
    def get_serverless_functions(self):
        """
        Returns a list of serverless functions
        """
        functions = get_supported_functions(self.client)
        functions.sort(key=lambda x: x["FunctionName"].lower())

        return [self.serialize_lambda_function(function) for function in functions]

    @wrap_lambda_updater()
    def enable_function(self, target):
        function = self.get_one_lambda_function(target)
        config_data = self.get_config_data()
        project_id = config_data["default_project_id"]

        sentry_project_dsn = get_dsn_for_project(self.organization_id, project_id)

        enable_single_lambda(self.client, function, sentry_project_dsn)

        return self.get_serialized_lambda_function(target)

    @wrap_lambda_updater()
    def disable_function(self, target):
        function = self.get_one_lambda_function(target)
        layer_arn = get_latest_layer_for_function(function)

        disable_single_lambda(self.client, function, layer_arn)

        return self.get_serialized_lambda_function(target)

    @wrap_lambda_updater()
    def update_function_to_latest_version(self, target):
        function = self.get_one_lambda_function(target)
        layer_arn = get_latest_layer_for_function(function)

        layers = get_function_layer_arns(function)

        # update our layer if we find it
        sentry_layer_index = get_index_of_sentry_layer(layers, layer_arn)
        if sentry_layer_index > -1:
            layers[sentry_layer_index] = layer_arn

        self.client.update_function_configuration(
            FunctionName=target,
            Layers=layers,
        )
        return self.get_serialized_lambda_function(target)


class AwsLambdaIntegrationProvider(IntegrationProvider):
    key = "aws_lambda"
    name = "AWS Lambda"
    metadata = metadata
    integration_cls = AwsLambdaIntegration
    features = frozenset([IntegrationFeatures.SERVERLESS])

    def get_pipeline_views(self) -> list[PipelineView[IntegrationPipeline]]:
        return [
            AwsLambdaProjectSelectPipelineView(),
            AwsLambdaCloudFormationPipelineView(),
            AwsLambdaListFunctionsPipelineView(),
            AwsLambdaSetupLayerPipelineView(),
        ]

    @control_silo_function
    def build_integration(self, state: Mapping[str, Any]) -> IntegrationData:
        region = state["region"]
        account_number = state["account_number"]
        aws_external_id = state["aws_external_id"]

        org_client = gen_aws_client(
            account_number, region, aws_external_id, service_name="organizations"
        )
        try:
            account = org_client.describe_account(AccountId=account_number)["Account"]
            account_name = account["Name"]
            integration_name = f"{account_name} {region}"
        except (
            org_client.exceptions.AccessDeniedException,
            org_client.exceptions.AWSOrganizationsNotInUseException,
        ):
            # if the customer won't let us access the org name, use the account
            # number instead we can also get a different error for self-hosted
            # users setting up the integration on an account that doesn't have
            # an organization
            integration_name = f"{account_number} {region}"

        external_id = f"{account_number}-{region}"

        return {
            "name": integration_name,
            "external_id": external_id,
            "metadata": {
                "account_number": account_number,
                "region": region,
                "aws_external_id": aws_external_id,
            },
            "post_install_data": {"default_project_id": state["project_id"]},
        }

    def post_install(
        self,
        integration: Integration,
        organization: RpcOrganization,
        *,
        extra: dict[str, Any],
    ) -> None:
        default_project_id = extra["default_project_id"]
        for oi in OrganizationIntegration.objects.filter(
            organization_id=organization.id, integration=integration
        ):
            oi.update(config={"default_project_id": default_project_id})


class AwsLambdaProjectSelectPipelineView:
    def dispatch(self, request: HttpRequest, pipeline: IntegrationPipeline) -> HttpResponseBase:
        # if we have the projectId, go to the next step
        if "projectId" in request.GET:
            pipeline.bind_state("project_id", request.GET["projectId"])
            return pipeline.next_step()

        assert pipeline.organization is not None
        organization = pipeline.organization
        projects = organization.projects

        # if only one project, automatically use that
        if len(projects) == 1:
            pipeline.bind_state("skipped_project_select", True)
            pipeline.bind_state("project_id", projects[0].id)
            return pipeline.next_step()

        projects = sorted(projects, key=lambda p: p.slug)
        serialized_projects = project_service.serialize_many(
            organization_id=organization.id,
            filter=dict(project_ids=[p.id for p in projects]),
        )
        return render_react_view(
            request, "awsLambdaProjectSelect", {"projects": serialized_projects}
        )


class AwsLambdaCloudFormationPipelineView:
    def dispatch(self, request: HttpRequest, pipeline: IntegrationPipeline) -> HttpResponseBase:
        curr_step = 0 if pipeline.fetch_state("skipped_project_select") else 1

        def render_response(error=None):
            assert pipeline.organization is not None
            serialized_organization = organization_service.serialize_organization(
                id=pipeline.organization.id,
                as_user=(
                    serialize_rpc_user(request.user) if isinstance(request.user, User) else None
                ),
            )
            template_url = options.get("aws-lambda.cloudformation-url")
            context = {
                "baseCloudformationUrl": "https://console.aws.amazon.com/cloudformation/home#/stacks/create/review",
                "templateUrl": template_url,
                "stackName": "Sentry-Monitoring-Stack",
                "regionList": ALL_AWS_REGIONS,
                "accountNumber": pipeline.fetch_state("account_number"),
                "region": pipeline.fetch_state("region"),
                "error": error,
                "initialStepNumber": curr_step,
                "organization": serialized_organization,
                "awsExternalId": pipeline.fetch_state("aws_external_id"),
            }
            return render_react_view(request, "awsLambdaCloudformation", context)

        # form submit adds accountNumber to GET parameters
        if "accountNumber" in request.GET:
            data = request.GET

            # load parameters post request
            account_number = data["accountNumber"]
            region = data["region"]
            aws_external_id = data["awsExternalId"]

            pipeline.bind_state("account_number", account_number)
            pipeline.bind_state("region", region)
            pipeline.bind_state("aws_external_id", aws_external_id)

            # now validate the arn works
            try:
                gen_aws_client(account_number, region, aws_external_id)
            except ClientError:
                return render_response(
                    _("Please validate the Cloudformation stack was created successfully")
                )
            except ConfigurationError:
                # if we have a configuration error, we should blow up the pipeline
                raise
            except Exception as e:
                logger.exception(
                    "AwsLambdaCloudFormationPipelineView.unexpected_error",
                    extra={"error": str(e)},
                )
                return render_response(_("Unknown error"))

            # if no error, continue
            return pipeline.next_step()

        return render_response()


class AwsLambdaListFunctionsPipelineView:
    def dispatch(self, request: HttpRequest, pipeline: IntegrationPipeline) -> HttpResponseBase:
        if request.method == "POST":
            raw_data = request.POST
            data = {}
            for key, val in raw_data.items():
                # form posts have string values for booleans and this form only sends booleans
                data[key] = val == "true"
            pipeline.bind_state("enabled_lambdas", data)
            return pipeline.next_step()

        account_number = pipeline.fetch_state("account_number")
        region = pipeline.fetch_state("region")
        aws_external_id = pipeline.fetch_state("aws_external_id")

        lambda_client = gen_aws_client(account_number, region, aws_external_id)

        lambda_functions = get_supported_functions(lambda_client)

        curr_step = 2 if pipeline.fetch_state("skipped_project_select") else 3

        return render_react_view(
            request,
            "awsLambdaFunctionSelect",
            {"lambdaFunctions": lambda_functions, "initialStepNumber": curr_step},
        )


class AwsLambdaSetupLayerPipelineView:
    def dispatch(self, request: HttpRequest, pipeline: IntegrationPipeline) -> HttpResponseBase:
        if "finish_pipeline" in request.GET:
            return pipeline.finish_pipeline()

        assert pipeline.organization is not None
        organization = pipeline.organization

        account_number = pipeline.fetch_state("account_number")
        region = pipeline.fetch_state("region")

        project_id = pipeline.fetch_state("project_id")
        aws_external_id = pipeline.fetch_state("aws_external_id")
        enabled_lambdas = pipeline.fetch_state("enabled_lambdas")
        assert enabled_lambdas is not None

        sentry_project_dsn = get_dsn_for_project(organization.id, project_id)

        lambda_client = gen_aws_client(account_number, region, aws_external_id)

        lambda_functions = get_supported_functions(lambda_client)
        lambda_functions.sort(key=lambda x: x["FunctionName"].lower())

        def is_lambda_enabled(function):
            name = function["FunctionName"]
            # check to see if the user wants to enable this function
            return enabled_lambdas.get(name)

        lambda_functions = filter(is_lambda_enabled, lambda_functions)

        def _enable_lambda(function):
            try:
                enable_single_lambda(lambda_client, function, sentry_project_dsn)
                return (True, function, None)
            except Exception as e:
                return (False, function, e)

        failures = []
        success_count = 0

        with ThreadPoolExecutor(
            max_workers=options.get("aws-lambda.thread-count")
        ) as _lambda_setup_thread_pool:
            # use threading here to parallelize requests
            # no timeout on the thread since the underlying request will time out
            # if it takes too long
            for success, function, e in _lambda_setup_thread_pool.map(
                _enable_lambda, lambda_functions
            ):
                name = function["FunctionName"]
                if success:
                    success_count += 1
                else:
                    # need to make sure we catch any error to continue to the next function
                    err_message: str | _StrPromise = str(e)
                    is_custom_err, err_message = get_sentry_err_message(err_message)
                    if not is_custom_err:
                        capture_exception(e)
                        err_message = _("Unknown Error")
                    failures.append({"name": function["FunctionName"], "error": err_message})
                    logger.info(
                        "update_function_configuration.error",
                        extra={
                            "organization_id": organization.id,
                            "lambda_name": name,
                            "account_number": account_number,
                            "region": region,
                            "error": str(e),
                        },
                    )

        analytics.record(
            IntegrationServerlessSetup(
                user_id=request.user.id,
                organization_id=organization.id,
                integration="aws_lambda",
                success_count=success_count,
                failure_count=len(failures),
            )
        )

        # if we have failures, show them to the user
        # otherwise, finish

        if failures:
            return render_react_view(
                request,
                "awsLambdaFailureDetails",
                {"lambdaFunctionFailures": failures, "successCount": success_count},
            )
        else:
            return pipeline.finish_pipeline()
