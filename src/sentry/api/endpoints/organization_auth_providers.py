from rest_framework.request import Request
from rest_framework.response import Response

from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization import OrganizationAuthProviderPermission, OrganizationEndpoint
from sentry.api.serializers import serialize
from sentry.auth import manager
from sentry.auth.partnership_configs import ChannelName
from sentry.models.organization import Organization


@region_silo_endpoint
class OrganizationAuthProvidersEndpoint(OrganizationEndpoint):
    publish_status = {
        "GET": ApiPublishStatus.PRIVATE,
    }
    owner = ApiOwner.ENTERPRISE
    permission_classes = (OrganizationAuthProviderPermission,)

    def get(self, request: Request, organization: Organization) -> Response:
        """
        List available auth providers that are available to use for an Organization
        ```````````````````````````````````````````````````````````````````````````

        :pparam string organization_id_or_slug: the id or slug of the organization
        :auth: required
        """
        provider_list = []
        for k, v in manager:
            if not v.is_partner and k != ChannelName.FLY_NON_PARTNER.value:
                provider_list.append(
                    {"key": k, "name": v.name, "requiredFeature": v.required_feature}
                )

        return Response(serialize(provider_list, request.user))
