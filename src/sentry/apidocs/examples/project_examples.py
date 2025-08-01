from drf_spectacular.utils import OpenApiExample

KEY_RATE_LIMIT = {
    "id": "60120449b6b1d5e45f75561e6dabd80b",
    "name": "Liked Pegasus",
    "label": "Liked Pegasus",
    "public": "60120449b6b1d5e45f75561e6dabd80b",
    "secret": "189485c3b8ccf582bf5e12c530ef8858",
    "projectId": 4505281256090153,
    "isActive": True,
    "rateLimit": {"window": 7200, "count": 1000},
    "dsn": {
        "secret": "https://a785682ddda742d7a8a4088810e67701:bcd99b3790b3441c85ce4b1eaa854f66@o4504765715316736.ingest.sentry.io/4505281256090153",
        "public": "https://a785682ddda742d7a8a4088810e67791@o4504765715316736.ingest.sentry.io/4505281256090153",
        "csp": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/csp-report/?sentry_key=a785682ddda719b7a8a4011110d75598",
        "security": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/security/?sentry_key=a785682ddda719b7a8a4011110d75598",
        "minidump": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/minidump/?sentry_key=a785682ddda719b7a8a4011110d75598",
        "playstation": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/playstation/?sentry_key=a785682ddda719b7a8a4011110d75598",
        "otlp_traces": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/otlp/v1/traces",
        "nel": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/nel/?sentry_key=a785682ddda719b7a8a4011110d75598",
        "unreal": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/unreal/a785682ddda719b7a8a4011110d75598/",
        "cdn": "https://js.sentry-cdn.com/a785682ddda719b7a8a4011110d75598.min.js",
        "crons": "https://o4504765715316736.ingest.sentry.io/api/4505281256090153/crons/___MONITOR_SLUG___/a785682ddda719b7a8a4011110d75598/",
    },
    "browserSdkVersion": "7.x",
    "browserSdk": {"choices": [["latest", "latest"], ["7.x", "7.x"]]},
    "dateCreated": "2023-06-21T19:50:26.036254Z",
    "dynamicSdkLoaderOptions": {
        "hasReplay": True,
        "hasPerformance": True,
        "hasDebug": True,
    },
}

KEY_NO_RATE_LIMIT = {
    **KEY_RATE_LIMIT,
    "id": "da8d69cb17e80677b76e08fde4656b93",
    "name": "Bold Oarfish",
    "label": "Bold Oarfish",
    "public": "da8d69cb17e80677b76e08fde4656b93",
    "secret": "5c241ebc42ccfbec281cbefbedc7ab96",
    "rateLimit": None,
}

BASE_PROJECT = {
    "id": "4505321021243392",
    "slug": "the-spoiled-yoghurt",
    "name": "The Spoiled Yoghurt",
    "platform": "python",
    "dateCreated": "2023-06-08T00:13:06.004534Z",
    "isBookmarked": False,
    "isMember": True,
    "features": [
        "alert-filters",
        "custom-inbound-filters",
        "data-forwarding",
        "discard-groups",
        "minidump",
        "rate-limits",
        "servicehooks",
        "similarity-indexing",
        "similarity-indexing-v2",
        "similarity-view",
        "similarity-view-v2",
    ],
    "firstEvent": None,
    "firstTransactionEvent": False,
    "access": [
        "member:read",
        "event:read",
        "project:admin",
        "team:write",
        "project:write",
        "team:admin",
        "project:read",
        "org:integrations",
        "org:read",
        "project:releases",
        "team:read",
        "alerts:write",
        "event:admin",
        "event:write",
        "alerts:read",
    ],
    "hasAccess": True,
    "hasMinifiedStackTrace": False,
    "hasFeedbacks": False,
    "hasMonitors": False,
    "hasNewFeedbacks": False,
    "hasProfiles": False,
    "hasReplays": False,
    "hasFlags": False,
    "hasSessions": False,
    "hasInsightsHttp": True,
    "hasInsightsDb": False,
    "hasInsightsAssets": True,
    "hasInsightsAppStart": False,
    "hasInsightsScreenLoad": False,
    "hasInsightsVitals": False,
    "hasInsightsCaches": False,
    "hasInsightsQueues": False,
    "hasInsightsLlmMonitoring": False,
    "hasInsightsAgentMonitoring": False,
    "hasInsightsMCP": False,
    "hasLogs": False,
    "isInternal": False,
    "isPublic": False,
    "avatar": {"avatarType": "letter_avatar", "avatarUuid": None},
    "color": "#3f70bf",
    "status": "active",
}

DETAILED_PROJECT = {
    **BASE_PROJECT,
    "id": "4505278496",
    "slug": "pump-station",
    "name": "Pump Station",
    "dateCreated": "2021-01-14T22:08:52.711809Z",
    "firstEvent": "2021-01-14T22:08:52.711809Z",
    "firstTransactionEvent": True,
    "team": {"id": "2", "name": "Powerful Abolitionist", "slug": "powerful-abolitionist"},
    "teams": [{"id": "2", "name": "Powerful Abolitionist", "slug": "powerful-abolitionist"}],
    "latestRelease": {
        "version": "backend@3e90a5d9e767ebcfa70e921d7a7ff6c037461168",
    },
    "options": {
        "sentry:transaction_name_cluster_rules": [],
        "digests:mail:maximum_delay": 600,
        "sentry:scrub_defaults": False,
        "sentry:scrape_javascript": True,
        "mail:subject_prefix": "",
        "sentry:relay_pii_config": None,
        "sentry:scrub_data": False,
        "sentry:token": "e84c8c0fb1c121e988558785885f9cde",
        "sentry:resolve_age": 168,
        "sentry:grouping_config": "newstyle:2012-12-31",
        "quotas:spike-protection-disabled": False,
        "sentry:store_crash_reports": 5,
        "digests:mail:minimum_delay": 180,
        "sentry:secondary_grouping_config": "newstyle:2012-11-21",
        "sentry:secondary_grouping_expiry": 147555024,
        "sentry:builtin_symbol_sources": ["ios", "android", "chromium"],
        "sentry:origins": ["getsentry.com", "app.getsentry.com", "www.getsentry.com", "sentry.io"],
        "sentry:sensitive_fields": ["sudo"],
        "sentry:scrub_ip_address": False,
        "sentry:default_environment": "prod",
        "sentry:verify_ssl": True,
        "sentry:csp_ignored_sources_defaults": True,
        "sentry:csp_ignored_sources": "",
        "filters:blacklisted_ips": "",
        "filters:react-hydration-errors": True,
        "filters:chunk-load-error": True,
        "filters:releases": "",
        "filters:error_messages": "",
        "feedback:branding": True,
    },
    "digestsMinDelay": 180,
    "digestsMaxDelay": 600,
    "subjectPrefix": "",
    "allowedDomains": ["getsentry.com", "app.getsentry.com", "www.getsentry.com", "sentry.io"],
    "resolveAge": 168,
    "dataScrubber": False,
    "dataScrubberDefaults": False,
    "safeFields": [],
    "storeCrashReports": 5,
    "sensitiveFields": ["sudo"],
    "subjectTemplate": "$shortID - $title",
    "securityToken": "e84c8c0fb1c121e988558785885f9cde",
    "securityTokenHeader": None,
    "verifySSL": True,
    "scrubIPAddresses": False,
    "scrapeJavaScript": True,
    "groupingConfig": "newstyle:2012-12-31",
    "groupingEnhancements": "",
    "derivedGroupingEnhancements": "",
    "secondaryGroupingExpiry": 1687010243,
    "secondaryGroupingConfig": "newstyle:2012-11-21",
    "fingerprintingRules": "",
    "organization": {
        "id": "1",
        "slug": "sentry",
        "status": {"id": "active", "name": "active"},
        "name": "Sentry",
        "dateCreated": "2014-12-15T04:06:24.263571Z",
        "isEarlyAdopter": True,
        "allowMemberInvite": True,
        "allowMemberProjectCreation": True,
        "allowSuperuserAccess": False,
        "require2FA": False,
        "avatar": {"avatarType": "upload", "avatarUuid": "24f6f762f7a7473888b259c566da5adb"},
        "features": [
            "global-views",
            "discover-basic",
            "incidents",
            "uptime",
            "monitors",
        ],
        "links": {
            "organizationUrl": "https://sentry.sentry.io",
            "regionUrl": "https://us.sentry.io",
        },
        "hasAuthProvider": True,
    },
    "plugins": [
        {
            "id": "asana",
            "name": "Asana",
            "slug": "asana",
            "shortName": "Asana",
            "type": "issue-tracking",
            "canDisable": True,
            "isTestable": False,
            "hasConfiguration": True,
            "metadata": {},
            "contexts": [],
            "status": "unknown",
            "assets": [],
            "doc": "",
            "firstPartyAlternative": None,
            "deprecationDate": None,
            "altIsSentryApp": None,
            "enabled": True,
            "version": "23.7.0.dev0",
            "author": {"name": "Sentry Team", "url": "https://github.com/getsentry/sentry"},
            "isDeprecated": False,
            "isHidden": False,
            "description": "\nImprove your productivity by creating tasks in Asana directly\nfrom Sentry issues. This integration also allows you to link Sentry\nissues to existing tasks in Asana.\n",
            "features": ["issue-basic"],
            "featureDescriptions": [
                {
                    "description": "Create and link Sentry issue groups directly to an Asana ticket in any of your\n            projects, providing a quick way to jump from a Sentry bug to tracked ticket.",
                    "featureGate": "issue-basic",
                },
                {
                    "description": "Link Sentry issues to existing Asana tickets.",
                    "featureGate": "issue-basic",
                },
            ],
            "resourceLinks": [
                {"title": "Report Issue", "url": "https://github.com/getsentry/sentry/issues"},
                {
                    "title": "View Source",
                    "url": "https://github.com/getsentry/sentry/tree/master/src/sentry_plugins",
                },
            ],
        }
    ],
    "platforms": ["native", "other", "python"],
    "processingIssues": 0,
    "defaultEnvironment": "prod",
    "relayPiiConfig": None,
    "builtinSymbolSources": ["ios", "android", "chromium"],
    "dynamicSamplingBiases": [
        {"id": "boostEnvironments", "active": True},
        {"id": "boostLatestRelease", "active": True},
        {"id": "ignoreHealthChecks", "active": True},
        {"id": "boostKeyTransactions", "active": True},
        {"id": "boostLowVolumeTransactions", "active": True},
        {"id": "boostReplayId", "active": True},
        {"id": "recalibrationRule", "active": True},
    ],
    "symbolSources": "[]",
    "tempestFetchScreenshots": False,
    "tempestFetchDumps": False,
    "isDynamicallySampled": True,
    "autofixAutomationTuning": "off",
    "seerScannerAutomation": True,
    "highlightTags": [],
    "highlightContext": {},
    "highlightPreset": {"tags": [], "context": {}},
}

PROJECT_SUMMARY = {
    "team": {
        "id": "2349234102",
        "name": "Prime Mover",
        "slug": "prime-mover",
    },
    "teams": [
        {
            "id": "2349234102",
            "name": "Prime Mover",
            "slug": "prime-mover",
        },
        {
            "id": "47584447",
            "name": "Powerful Abolitionist",
            "slug": "powerful-abolitionist",
        },
    ],
    "id": "6758470122493650",
    "slug": "the-spoiled-yoghurt",
    "name": "The Spoiled Yoghurt",
    "isBookmarked": False,
    "isMember": True,
    "access": [
        "project:read",
        "event:read",
        "team:read",
        "alerts:read",
        "org:read",
        "event:write",
        "project:releases",
        "member:read",
    ],
    "hasAccess": True,
    "dateCreated": "2023-03-29T15:25:21.344565Z",
    "environments": ["production"],
    "features": [
        "alert-filters",
        "custom-inbound-filters",
        "data-forwarding",
        "discard-groups",
        "minidump",
        "rate-limits",
        "servicehooks",
        "similarity-indexing",
        "similarity-indexing-v2",
        "similarity-view",
        "similarity-view-v2",
    ],
    "firstEvent": None,
    "firstTransactionEvent": True,
    "hasSessions": False,
    "hasProfiles": False,
    "hasReplays": False,
    "hasFlags": False,
    "hasMonitors": False,
    "hasFeedbacks": False,
    "hasNewFeedbacks": False,
    "hasMinifiedStackTrace": False,
    "hasInsightsHttp": True,
    "hasInsightsDb": False,
    "hasInsightsAssets": False,
    "hasInsightsAppStart": False,
    "hasInsightsScreenLoad": False,
    "hasInsightsVitals": False,
    "hasInsightsCaches": True,
    "hasInsightsQueues": True,
    "hasInsightsLlmMonitoring": False,
    "hasInsightsAgentMonitoring": False,
    "hasInsightsMCP": False,
    "hasLogs": False,
    "platform": "node-express",
    "platforms": [],
    "latestRelease": None,
    "hasUserReports": False,
    "latestDeploys": None,
}


SYMBOL_SOURCES = [
    {
        "id": "honk",
        "name": "honk source",
        "layout": {
            "type": "native",
        },
        "type": "http",
        "url": "http://honk.beep",
        "username": "honkhonk",
        "password": {"hidden-secret": True},
    },
    {
        "id": "beep",
        "name": "beep source",
        "layout": {
            "type": "native",
        },
        "type": "gcs",
        "bucket": "mybucket",
        "client_email": "honk@beep.com",
        "private_key": {"hidden-secret": True},
    },
]


def project_with_team(extra_team: bool = False):
    teams = [
        {
            "id": "2349234102",
            "name": "Prime Mover",
            "slug": "prime-mover",
        },
        {
            "id": "47584447",
            "name": "Powerful Abolitionist",
            "slug": "powerful-abolitionist",
        },
    ]
    return {
        **BASE_PROJECT,
        "id": "6758470122493650",
        "slug": "the-spoiled-yoghurt",
        "name": "The Spoiled Yoghurt",
        "platform": "javascript",
        "dateCreated": "2023-03-29T15:25:21.344565Z",
        "color": "#5cbf3f",
        "team": {
            "id": "2349234102",
            "name": "Prime Mover",
            "slug": "prime-mover",
        },
        "teams": teams if extra_team else teams[:1],
    }


class ProjectExamples:
    CLIENT_KEY_RESPONSE = [
        OpenApiExample(
            "Client key with rate limiting",
            value=KEY_RATE_LIMIT,
            status_codes=["200", "201"],
            response_only=True,
        ),
    ]

    DETAILED_PROJECT = [
        OpenApiExample(
            "Get detailed view about a Project",
            value=DETAILED_PROJECT,
            status_codes=["200"],
            response_only=True,
        ),
    ]

    OVERVIEW_PROJECT = [
        OpenApiExample(
            "Get an overview of a Project",
            summary=(
                "Project overviews are high-level summaries of a project. They are intended to provide a "
                "quick and lightweight way to get information about a project."
            ),
            value=BASE_PROJECT,
            status_codes=["200"],
            response_only=True,
        ),
    ]

    CREATE_PROJECT = [
        OpenApiExample(
            "Project successfully created",
            value=PROJECT_SUMMARY,
            status_codes=["201"],
            response_only=True,
        ),
    ]

    LIST_CLIENT_KEYS = [
        OpenApiExample(
            "List Client Keys for a Project",
            value=[
                KEY_RATE_LIMIT,
                KEY_NO_RATE_LIMIT,
            ],
            status_codes=["200"],
            response_only=True,
        ),
    ]

    ADD_TEAM_TO_PROJECT = [
        OpenApiExample(
            "Give a Team Access to a Project",
            value=project_with_team(extra_team=True),
            status_codes=["201"],
            response_only=True,
        ),
    ]

    DELETE_TEAM_FROM_PROJECT = [
        OpenApiExample(
            "Revoke a Team's Access to a Project",
            value=project_with_team(),
            status_codes=["200"],
            response_only=True,
        ),
    ]

    GET_SYMBOL_SOURCES = [
        OpenApiExample(
            "List custom symbol sources configured for a project.",
            value=SYMBOL_SOURCES,
            status_codes=["200"],
            response_only=True,
        ),
    ]

    ADD_SYMBOL_SOURCE = [
        OpenApiExample(
            "List custom symbol sources configured for a project.",
            value=SYMBOL_SOURCES[0],
            status_codes=["201"],
            response_only=True,
        ),
    ]

    ADD_SYMBOL_SOURCE = [
        OpenApiExample(
            "Add a custom symbol source to a project.",
            value=SYMBOL_SOURCES[0],
            status_codes=["201"],
            response_only=True,
        ),
    ]

    UPDATE_SYMBOL_SOURCE = [
        OpenApiExample(
            "Update a custom symbol source in a project.",
            value=SYMBOL_SOURCES[0],
            status_codes=["200"],
            response_only=True,
        ),
    ]

    DELETE_SYMBOL_SOURCE = [
        OpenApiExample(
            "Delete a custom symbol source from a project.",
            status_codes=["204"],
            response_only=True,
        ),
    ]

    GET_PROJECT_FILTERS = [
        OpenApiExample(
            "List a project's filters",
            value=[
                {"id": "browser-extensions", "active": False},
                {"id": "filtered-transaction", "active": True},
                {
                    "id": "legacy-browsers",
                    "active": [
                        "opera",
                        "edge",
                        "safari",
                        "chrome",
                        "ie",
                        "opera_mini",
                        "firefox",
                        "android",
                    ],
                },
                {"id": "localhost", "active": False},
                {"id": "web-crawlers", "active": True},
            ],
            status_codes=["200"],
            response_only=True,
        ),
    ]
