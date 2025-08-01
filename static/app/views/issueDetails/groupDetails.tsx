import {Fragment, useCallback, useEffect, useMemo, useState} from 'react';
import {Outlet} from 'react-router-dom';
import styled from '@emotion/styled';
import * as Sentry from '@sentry/react';
import isEqual from 'lodash/isEqual';
import * as qs from 'query-string';

import {TabPanels, Tabs} from 'sentry/components/core/tabs';
import FloatingFeedbackWidget from 'sentry/components/feedback/widget/floatingFeedbackWidget';
import useDrawer from 'sentry/components/globalDrawer';
import LoadingError from 'sentry/components/loadingError';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import PageFiltersContainer from 'sentry/components/organizations/pageFilters/container';
import MissingProjectMembership from 'sentry/components/projects/missingProjectMembership';
import SentryDocumentTitle from 'sentry/components/sentryDocumentTitle';
import {TourContextProvider} from 'sentry/components/tours/components';
import {useAssistant} from 'sentry/components/tours/useAssistant';
import {featureFlagDrawerPlatforms} from 'sentry/data/platformCategories';
import {t} from 'sentry/locale';
import GroupStore from 'sentry/stores/groupStore';
import {space} from 'sentry/styles/space';
import type {Event} from 'sentry/types/event';
import type {Group} from 'sentry/types/group';
import {GroupStatus, IssueCategory, IssueType} from 'sentry/types/group';
import type {Organization} from 'sentry/types/organization';
import type {Project} from 'sentry/types/project';
import {defined} from 'sentry/utils';
import {trackAnalytics} from 'sentry/utils/analytics';
import {getUtcDateString} from 'sentry/utils/dates';
import {
  getAnalyticsDataForEvent,
  getAnalyticsDataForGroup,
  getMessage,
  getTitle,
} from 'sentry/utils/events';
import {getConfigForIssueType} from 'sentry/utils/issueTypeConfig';
import {getAnalyicsDataForProject} from 'sentry/utils/projects';
import {setApiQueryData, useQueryClient} from 'sentry/utils/queryClient';
import {decodeBoolean} from 'sentry/utils/queryString';
import useDisableRouteAnalytics from 'sentry/utils/routeAnalytics/useDisableRouteAnalytics';
import useRouteAnalyticsEventNames from 'sentry/utils/routeAnalytics/useRouteAnalyticsEventNames';
import useRouteAnalyticsParams from 'sentry/utils/routeAnalytics/useRouteAnalyticsParams';
import normalizeUrl from 'sentry/utils/url/normalizeUrl';
import useLocationQuery from 'sentry/utils/url/useLocationQuery';
import useApi from 'sentry/utils/useApi';
import {useDetailedProject} from 'sentry/utils/useDetailedProject';
import {useLocation} from 'sentry/utils/useLocation';
import {useMemoWithPrevious} from 'sentry/utils/useMemoWithPrevious';
import {useNavigate} from 'sentry/utils/useNavigate';
import useOrganization from 'sentry/utils/useOrganization';
import {useParams} from 'sentry/utils/useParams';
import useProjects from 'sentry/utils/useProjects';
import {useUser} from 'sentry/utils/useUser';
import {ERROR_TYPES} from 'sentry/views/issueDetails/constants';
import {useGroupDistributionsDrawer} from 'sentry/views/issueDetails/groupDistributions/useGroupDistributionsDrawer';
import GroupEventDetails from 'sentry/views/issueDetails/groupEventDetails/groupEventDetails';
import GroupHeader from 'sentry/views/issueDetails/header';
import {
  ISSUE_DETAILS_TOUR_GUIDE_KEY,
  type IssueDetailsTour,
  IssueDetailsTourContext,
  ORDERED_ISSUE_DETAILS_TOUR,
} from 'sentry/views/issueDetails/issueDetailsTour';
import {SampleEventAlert} from 'sentry/views/issueDetails/sampleEventAlert';
import {GroupDetailsLayout} from 'sentry/views/issueDetails/streamline/groupDetailsLayout';
import {useIssueActivityDrawer} from 'sentry/views/issueDetails/streamline/hooks/useIssueActivityDrawer';
import {useMergedIssuesDrawer} from 'sentry/views/issueDetails/streamline/hooks/useMergedIssuesDrawer';
import {useSimilarIssuesDrawer} from 'sentry/views/issueDetails/streamline/hooks/useSimilarIssuesDrawer';
import {useOpenSeerDrawer} from 'sentry/views/issueDetails/streamline/sidebar/seerDrawer';
import {Tab} from 'sentry/views/issueDetails/types';
import {makeFetchGroupQueryKey, useGroup} from 'sentry/views/issueDetails/useGroup';
import {useGroupDetailsRoute} from 'sentry/views/issueDetails/useGroupDetailsRoute';
import {useGroupEvent} from 'sentry/views/issueDetails/useGroupEvent';
import {
  getGroupReprocessingStatus,
  markEventSeen,
  ReprocessingStatus,
  useDefaultIssueEvent,
  useEnvironmentsFromUrl,
  useHasStreamlinedUI,
  useIsSampleEvent,
} from 'sentry/views/issueDetails/utils';

type Error = (typeof ERROR_TYPES)[keyof typeof ERROR_TYPES] | null;

type FetchGroupDetailsState = {
  error: boolean;
  errorType: Error;
  event: Event | null;
  group: Group | null;
  loadingGroup: boolean;
  refetchData: () => void;
  refetchGroup: () => void;
};

interface GroupDetailsContentProps {
  children: React.ReactNode;
  event: Event | null;
  group: Group;
  project: Project;
}

function getFetchDataRequestErrorType(status?: number | null): Error {
  if (!status) {
    return null;
  }

  if (status === 404) {
    return ERROR_TYPES.GROUP_NOT_FOUND;
  }

  if (status === 403) {
    return ERROR_TYPES.MISSING_MEMBERSHIP;
  }

  return null;
}

function getReprocessingNewRoute({
  orgSlug,
  group,
  currentTab,
  baseUrl,
  location,
  currentParamGroupId,
}: {
  /**
   * The groupId from the URL params to compare against the group id that was loaded.
   */
  currentParamGroupId: string;
  group: Group;
  location: ReturnType<typeof useLocation>;
  orgSlug: string;
} & ReturnType<typeof useGroupDetailsRoute>) {
  const {id: nextGroupId} = group;

  const reprocessingStatus = getGroupReprocessingStatus(group);

  if (currentParamGroupId !== nextGroupId) {
    // Redirects to the Activities tab
    if (
      reprocessingStatus === ReprocessingStatus.REPROCESSED_AND_HASNT_EVENT &&
      currentTab !== Tab.ACTIVITY
    ) {
      return {
        pathname: `${baseUrl}${Tab.ACTIVITY}/`,
        query: {...location.query, groupId: nextGroupId},
      };
    }

    return normalizeUrl({
      pathname: `/organizations/${orgSlug}/issues/${nextGroupId}/`,
      query: location.query,
    });
  }

  if (
    reprocessingStatus === ReprocessingStatus.REPROCESSING &&
    currentTab !== Tab.DETAILS
  ) {
    return {
      pathname: baseUrl,
      query: location.query,
    };
  }

  if (
    reprocessingStatus === ReprocessingStatus.REPROCESSED_AND_HASNT_EVENT &&
    currentTab !== Tab.ACTIVITY &&
    currentTab !== Tab.USER_FEEDBACK
  ) {
    return {
      pathname: `${baseUrl}${Tab.ACTIVITY}/`,
      query: location.query,
    };
  }

  return undefined;
}

function useRefetchGroupForReprocessing({
  refetchGroup,
}: Pick<FetchGroupDetailsState, 'refetchGroup'>) {
  useEffect(() => {
    const refetchInterval = window.setInterval(refetchGroup, 30000);

    return () => {
      window.clearInterval(refetchInterval);
    };
  }, [refetchGroup]);
}

/**
 * This is a temporary measure to ensure that the GroupStore and query cache
 * are both up to date while we are still using both in the issue details page.
 * Once we remove all references to GroupStore in the issue details page we
 * should remove this.
 */
function useSyncGroupStore(groupId: string, incomingEnvs: string[]) {
  const queryClient = useQueryClient();
  const organization = useOrganization();

  // It's possible the overview page is still unloading the store
  useEffect(() => {
    return GroupStore.listen(() => {
      const [storeGroup] = GroupStore.getState();
      if (
        defined(storeGroup) &&
        storeGroup.id === groupId &&
        // Check for properties that are only set after the group has been loaded
        defined(storeGroup.participants) &&
        defined(storeGroup.activity)
      ) {
        setApiQueryData(
          queryClient,
          makeFetchGroupQueryKey({
            groupId: storeGroup.id,
            organizationSlug: organization.slug,
            environments: incomingEnvs,
          }),
          storeGroup
        );
      }
    }, undefined) as () => void;
  }, [groupId, incomingEnvs, organization.slug, queryClient]);
}

function useFetchGroupDetails(): FetchGroupDetailsState {
  const api = useApi();
  const organization = useOrganization();
  const location = useLocation();
  const params = useParams<{groupId: string; eventId?: string}>();
  const navigate = useNavigate();
  const defaultIssueEvent = useDefaultIssueEvent();
  const hasStreamlinedUI = useHasStreamlinedUI();
  const {projects} = useProjects();

  const [allProjectChanged, setAllProjectChanged] = useState<boolean>(false);

  const {currentTab, baseUrl} = useGroupDetailsRoute();
  const environments = useEnvironmentsFromUrl();

  const groupId = params.groupId;

  const {
    data: event,
    isPending: loadingEvent,
    isError: isEventError,
    refetch: refetchEvent,
  } = useGroupEvent({
    groupId,
    eventId: params.eventId,
  });

  const {
    data: groupData,
    isPending: loadingGroup,
    isError: isGroupError,
    error: groupError,
    refetch: refetchGroupCall,
  } = useGroup({groupId});

  /**
   * TODO(streamline-ui): Remove this whole hook once the legacy UI is removed. The streamlined UI exposes the
   * filters on the page so the user is expected to clear it themselves, and the empty state is actually expected.
   */
  useEffect(() => {
    if (hasStreamlinedUI) {
      return;
    }

    const eventIdUrl = params.eventId ?? defaultIssueEvent;
    const isLatestOrRecommendedEvent =
      eventIdUrl === 'latest' || eventIdUrl === 'recommended';

    if (
      isLatestOrRecommendedEvent &&
      isEventError &&
      // Expanding this list to ensure invalid date ranges get removed as well as queries
      (location.query.query ||
        location.query.start ||
        location.query.end ||
        location.query.statsPeriod)
    ) {
      // If we get an error from the helpful event endpoint, it probably means
      // the query failed validation. We should remove the query to try again if
      // we are not using streamlined UI.
      navigate(
        {
          ...location,
          query: {
            project: location.query.project,
          },
        },
        {replace: true}
      );
    }
  }, [
    defaultIssueEvent,
    isEventError,
    navigate,
    location,
    params.eventId,
    hasStreamlinedUI,
  ]);

  /**
   * Allows the GroupEventHeader to display the previous event while the new event is loading.
   * This is not closer to the GroupEventHeader because it is unmounted
   * between route changes like latest event => eventId
   */
  const previousEvent = useMemoWithPrevious<typeof event | null>(
    previousInstance => {
      if (event) {
        return event;
      }
      return previousInstance;
    },
    [event]
  );

  // If the environment changes, we need to refetch the group, but we can
  // still display the previous group while the new group is loading.
  const previousGroupData = useMemoWithPrevious<{
    cachedGroup: typeof groupData | null;
    previousEnvironments: typeof environments | null;
    previousGroupData: typeof groupData | null;
  }>(
    previousInstance => {
      // Preserve the previous group if:
      // - New group is not yet available
      // - Previously we had group data
      // - The previous group id is the same as the current group id
      // - The previous environments are not the same as the current environments
      if (
        !groupData &&
        previousInstance?.cachedGroup &&
        previousInstance.cachedGroup.id === groupId &&
        !isEqual(previousInstance.previousEnvironments, environments)
      ) {
        return {
          previousGroupData: previousInstance.previousGroupData,
          previousEnvironments: previousInstance.previousEnvironments,
          cachedGroup: previousInstance.cachedGroup,
        };
      }

      // If group data is available, store in memo for comparison later
      return {
        cachedGroup: groupData,
        previousEnvironments: environments,
        previousGroupData: null,
      };
    },
    [groupData, environments, groupId]
  );

  const group = groupData ?? previousGroupData.cachedGroup ?? null;

  useEffect(() => {
    if (defined(group)) {
      GroupStore.loadInitialData([group]);
    }
  }, [groupId, group]);

  useSyncGroupStore(groupId, environments);

  useEffect(() => {
    if (group && event) {
      const reprocessingNewRoute = getReprocessingNewRoute({
        group,
        currentTab,
        location,
        baseUrl,
        currentParamGroupId: params.groupId,
        orgSlug: organization.slug,
      });

      if (reprocessingNewRoute) {
        navigate(reprocessingNewRoute);
      }
    }
  }, [
    group,
    event,
    location,
    currentTab,
    baseUrl,
    navigate,
    organization.slug,
    params.groupId,
  ]);

  useEffect(() => {
    const matchingProjectSlug = group?.project?.slug;

    if (!matchingProjectSlug) {
      return;
    }

    const project = projects.find(p => p.id === group?.project.id);
    if (!group.hasSeen && project?.isMember) {
      markEventSeen(api, organization.slug, matchingProjectSlug, params.groupId);
    }
  }, [api, group?.hasSeen, group?.project, organization.slug, params.groupId, projects]);

  useEffect(() => {
    const locationQuery = qs.parse(window.location.search) || {};
    const allProjectsFlag = locationQuery._allp;

    // We use _allp as a temporary measure to know they came from the
    // issue list page with no project selected (all projects included in
    // filter).
    //
    // If it is not defined, we add the locked project id to the URL
    // (this is because if someone navigates directly to an issue on
    // single-project priveleges, then goes back - they were getting
    // assigned to the first project).
    //
    // If it is defined, we do not so that our back button will bring us
    // to the issue list page with no project selected instead of the
    // locked project.
    if (
      locationQuery.project === undefined &&
      !allProjectsFlag &&
      !allProjectChanged &&
      group?.project.id
    ) {
      locationQuery.project = group?.project.id;
      navigate({...window.location, query: locationQuery}, {replace: true});
    }

    if (allProjectsFlag && !allProjectChanged) {
      delete locationQuery.project;
      // We delete _allp from the URL to keep the hack a bit cleaner, but
      // this is not an ideal solution and will ultimately be replaced with
      // something smarter.
      delete locationQuery._allp;
      navigate({...window.location, query: locationQuery}, {replace: true});
      setAllProjectChanged(true);
    }
  }, [group?.project.id, allProjectChanged, navigate]);

  const errorType = groupError ? getFetchDataRequestErrorType(groupError.status) : null;
  useEffect(() => {
    if (isGroupError) {
      Sentry.captureException(groupError);
    }
  }, [isGroupError, groupError]);

  const refetchGroup = useCallback(() => {
    if (group?.status !== GroupStatus.REPROCESSING || loadingGroup || loadingEvent) {
      return;
    }

    refetchGroupCall();
  }, [group, loadingGroup, loadingEvent, refetchGroupCall]);

  const refetchData = useCallback(() => {
    refetchEvent();
    refetchGroup();
  }, [refetchGroup, refetchEvent]);

  // Refetch when group is stale
  useEffect(() => {
    if (group && (group as Group & {stale?: boolean}).stale) {
      refetchGroup();
    }
  }, [refetchGroup, group]);

  useRefetchGroupForReprocessing({refetchGroup});

  useEffect(() => {
    return () => {
      GroupStore.reset();
    };
  }, []);

  return {
    loadingGroup,
    group,
    // Allow previous event to be displayed while new event is loading
    event: (loadingEvent ? (event ?? previousEvent) : event) ?? null,
    errorType,
    error: isGroupError,
    refetchData,
    refetchGroup,
  };
}

function useLoadedEventType() {
  const params = useParams<{eventId?: string}>();
  const defaultIssueEvent = useDefaultIssueEvent();

  switch (params.eventId) {
    case undefined:
      return defaultIssueEvent;
    case 'latest':
    case 'oldest':
      return params.eventId;
    default:
      return 'event_id';
  }
}

function useTrackView({
  group,
  event,
  project,
  tab,
  organization,
}: {
  event: Event | null;
  group: Group | null;
  organization: Organization;
  tab: Tab;
  project?: Project;
}) {
  const location = useLocation();
  const {alert_date, alert_rule_id, alert_type, ref_fallback, query} = location.query;
  const groupEventType = useLoadedEventType();
  const user = useUser();
  const hasStreamlinedUI = useHasStreamlinedUI();

  useRouteAnalyticsEventNames('issue_details.viewed', 'Issue Details: Viewed');
  useRouteAnalyticsParams({
    ...getAnalyticsDataForGroup(group),
    ...getAnalyticsDataForEvent(event),
    ...getAnalyicsDataForProject(project),
    tab,
    query: typeof query === 'string' ? query : undefined,
    // Alert properties track if the user came from email/slack alerts
    alert_date:
      typeof alert_date === 'string' ? getUtcDateString(Number(alert_date)) : undefined,
    alert_rule_id: typeof alert_rule_id === 'string' ? alert_rule_id : undefined,
    alert_type: typeof alert_type === 'string' ? alert_type : undefined,
    ref_fallback,
    group_event_type: groupEventType,
    prefers_streamlined_ui: user?.options?.prefersIssueDetailsStreamlinedUI ?? false,
    enforced_streamlined_ui:
      organization.features.includes('issue-details-streamline-enforce') &&
      user?.options?.prefersIssueDetailsStreamlinedUI === null,
    org_streamline_only: organization.streamlineOnly ?? undefined,
    has_streamlined_ui: hasStreamlinedUI,
  });
  // Set default values for properties that may be updated in subcomponents.
  // Must be separate from the above values, otherwise the actual values filled in
  // by subcomponents may be overwritten when the above values change.
  useRouteAnalyticsParams({
    // Will be updated by StacktraceLink if there is a stacktrace link
    stacktrace_link_viewed: false,
    // Will be updated by IssueQuickTrace if there is a trace
    trace_status: 'none',
    // Will be updated in GroupDetailsHeader if there are replays
    group_has_replay: false,
    // Will be updated in ReplayPreview if there is a replay
    event_replay_status: 'none',
    // Will be updated in SuspectCommits if there are suspect commits
    num_suspect_commits: 0,
    suspect_commit_calculation: 'no suspect commit',
    // Will be updated in Autofix if enabled
    autofix_status: 'none',
  });
  useDisableRouteAnalytics(!group || !event || !project);
}

const trackTabChanged = ({
  organization,
  project,
  group,
  event,
  tab,
}: {
  event: Event | null;
  group: Group;
  organization: Organization;
  project: Project;
  tab: Tab;
}) => {
  if (!project || !group) {
    return;
  }

  trackAnalytics('issue_details.tab_changed', {
    organization,
    project_id: parseInt(project.id, 10),
    tab,
    ...getAnalyticsDataForGroup(group),
  });

  if (group.issueCategory !== IssueCategory.ERROR) {
    return;
  }

  const analyticsData = event
    ? event.tags
        .filter(({key}) => ['device', 'os', 'browser'].includes(key))
        .reduce<Record<string, string>>((acc, {key, value}) => {
          acc[key] = value;
          return acc;
        }, {})
    : {};

  trackAnalytics('issue_group_details.tab.clicked', {
    organization,
    tab,
    platform: project.platform,
    ...analyticsData,
  });
};

function GroupDetailsContentError({
  errorType,
  onRetry,
}: {
  errorType: Error;
  onRetry: () => void;
}) {
  const organization = useOrganization();
  const location = useLocation();
  const projectId = location.query.project;

  const {projects} = useProjects();
  const project = projects.find(proj => proj.id === projectId);

  switch (errorType) {
    case ERROR_TYPES.GROUP_NOT_FOUND:
      return (
        <StyledLoadingError
          message={t('The issue you were looking for was not found.')}
        />
      );

    case ERROR_TYPES.MISSING_MEMBERSHIP:
      return <MissingProjectMembership organization={organization} project={project} />;
    default:
      return <StyledLoadingError onRetry={onRetry} />;
  }
}

function GroupDetailsContent({
  children,
  group,
  project,
  event,
}: GroupDetailsContentProps) {
  const organization = useOrganization();
  const includeFlagDistributions =
    featureFlagDrawerPlatforms.includes(project.platform ?? 'other') &&
    organization.features.includes('feature-flag-distribution-flyout');
  const {openDistributionsDrawer} = useGroupDistributionsDrawer({
    group,
    includeFeatureFlagsTab: includeFlagDistributions,
  });
  const {openSimilarIssuesDrawer} = useSimilarIssuesDrawer({group, project});
  const {openMergedIssuesDrawer} = useMergedIssuesDrawer({group, project});
  const {openIssueActivityDrawer} = useIssueActivityDrawer({group, project});
  const {openSeerDrawer} = useOpenSeerDrawer({group, project, event});
  const {isDrawerOpen} = useDrawer();

  const {currentTab, baseUrl} = useGroupDetailsRoute();
  const {seerDrawer} = useLocationQuery({
    fields: {
      seerDrawer: decodeBoolean,
    },
  });

  const hasStreamlinedUI = useHasStreamlinedUI();

  useEffect(() => {
    if (isDrawerOpen) {
      return;
    }

    if (seerDrawer) {
      openSeerDrawer();
      return;
    }

    if (!hasStreamlinedUI) {
      return;
    }

    if (currentTab === Tab.DISTRIBUTIONS) {
      // Tag and feature flag distributions.
      openDistributionsDrawer();
    } else if (currentTab === Tab.SIMILAR_ISSUES) {
      openSimilarIssuesDrawer();
    } else if (currentTab === Tab.MERGED) {
      openMergedIssuesDrawer();
    } else if (currentTab === Tab.ACTIVITY) {
      openIssueActivityDrawer();
    }
  }, [
    currentTab,
    hasStreamlinedUI,
    isDrawerOpen,
    seerDrawer,
    openDistributionsDrawer,
    openSimilarIssuesDrawer,
    openMergedIssuesDrawer,
    openIssueActivityDrawer,
    openSeerDrawer,
  ]);

  useTrackView({group, event, project, tab: currentTab, organization});

  const isDisplayingEventDetails = [
    Tab.DETAILS,
    Tab.DISTRIBUTIONS,
    Tab.SIMILAR_ISSUES,
    Tab.MERGED,
    Tab.ACTIVITY,
  ].includes(currentTab);

  return hasStreamlinedUI ? (
    <GroupDetailsLayout group={group} event={event ?? undefined} project={project}>
      {isDisplayingEventDetails ? (
        // The router displays a loading indicator when switching to any of these tabs
        // Avoid lazy loading spinner by force rendering the GroupEventDetails component
        <GroupEventDetails />
      ) : (
        children
      )}
    </GroupDetailsLayout>
  ) : (
    <Tabs
      value={currentTab}
      onChange={tab => trackTabChanged({tab, group, project, event, organization})}
    >
      <GroupHeader
        organization={organization}
        event={event}
        group={group}
        baseUrl={baseUrl}
        project={project}
      />
      <GroupTabPanels>
        <TabPanels.Item key={currentTab}>{children}</TabPanels.Item>
      </GroupTabPanels>
    </Tabs>
  );
}

interface GroupDetailsPageContentProps extends FetchGroupDetailsState {
  children: React.ReactNode;
}

function GroupDetailsPageContent(props: GroupDetailsPageContentProps) {
  const projectSlug = props.group?.project?.slug;
  const api = useApi();
  const organization = useOrganization();
  const [injectedEvent, setInjectedEvent] = useState(null);
  const {
    projects,
    initiallyLoaded: projectsLoaded,
    fetchError: errorFetchingProjects,
  } = useProjects({slugs: projectSlug ? [projectSlug] : []});

  // Preload detailed project data for highlighted data section
  useDetailedProject(
    {
      orgSlug: organization.slug,
      projectSlug: projectSlug ?? '',
    },
    {enabled: !!projectSlug}
  );

  const {data: assistantData} = useAssistant();
  const isIssueDetailsTourCompleted = useMemo(() => {
    const issueDetailsTourData = assistantData?.find(
      item => item.guide === ISSUE_DETAILS_TOUR_GUIDE_KEY
    );

    // Prevent tour from showing until assistant data is loaded
    return issueDetailsTourData?.seen ?? true;
  }, [assistantData]);

  const project = projects.find(({slug}) => slug === projectSlug);
  const projectWithFallback = project ?? projects[0];

  const isRegressionIssue =
    props.group?.issueType === IssueType.PERFORMANCE_ENDPOINT_REGRESSION;

  useEffect(() => {
    if (props.group && projectsLoaded && !project) {
      Sentry.withScope(scope => {
        const projectIds = projects.map(item => item.id);
        scope.setContext('missingProject', {
          projectId: props.group?.project.id,
          availableProjects: projectIds,
        });
        scope.setFingerprint(['group-details-project-not-found']);
        Sentry.captureException(new Error('Project not found'));
      });
    }
  }, [props.group, project, projects, projectsLoaded]);

  useEffect(() => {
    const fetchLatestEvent = async () => {
      const event = await api.requestPromise(
        `/organizations/${organization.slug}/issues/${props.group?.id}/events/latest/`
      );
      setInjectedEvent(event);
    };
    if (isRegressionIssue && !defined(props.event)) {
      fetchLatestEvent();
    }
  }, [
    api,
    organization.slug,
    props.event,
    props.group,
    props.group?.id,
    isRegressionIssue,
  ]);

  if (props.error) {
    return (
      <GroupDetailsContentError errorType={props.errorType} onRetry={props.refetchData} />
    );
  }

  if (errorFetchingProjects) {
    return <StyledLoadingError message={t('Error loading the specified project')} />;
  }

  if (projectSlug && !errorFetchingProjects && projectsLoaded && !projectWithFallback) {
    return (
      <StyledLoadingError message={t('The project %s does not exist', projectSlug)} />
    );
  }

  const regressionIssueLoaded = defined(injectedEvent ?? props.event);
  if (
    !projectsLoaded ||
    !projectWithFallback ||
    !props.group ||
    (isRegressionIssue && !regressionIssueLoaded)
  ) {
    return <LoadingIndicator />;
  }

  return (
    <TourContextProvider<IssueDetailsTour>
      tourKey={ISSUE_DETAILS_TOUR_GUIDE_KEY}
      isCompleted={isIssueDetailsTourCompleted}
      orderedStepIds={ORDERED_ISSUE_DETAILS_TOUR}
      TourContext={IssueDetailsTourContext}
    >
      <GroupDetailsContent
        project={projectWithFallback}
        group={props.group}
        event={props.event ?? injectedEvent}
      >
        {props.children}
      </GroupDetailsContent>
    </TourContextProvider>
  );
}

function GroupDetails() {
  const organization = useOrganization();
  const {group, ...fetchGroupDetailsProps} = useFetchGroupDetails();
  const isSampleError = useIsSampleEvent();

  const getGroupDetailsTitle = () => {
    const defaultTitle = 'Sentry';

    if (!group) {
      return defaultTitle;
    }

    const {title} = getTitle(group);
    const message = getMessage(group);

    const eventDetails = `${organization.slug} — ${group.project.slug}`;

    if (title && message) {
      return `${title}: ${message} — ${eventDetails}`;
    }

    return `${title || message || defaultTitle} — ${eventDetails}`;
  };

  const config = group && getConfigForIssueType(group, group.project);

  return (
    <Fragment>
      {isSampleError && group && (
        <SampleEventAlert project={group.project} organization={organization} />
      )}
      <SentryDocumentTitle noSuffix title={getGroupDetailsTitle()}>
        <PageFiltersContainer
          skipLoadLastUsed
          forceProject={group?.project}
          shouldForceProject
        >
          {config?.showFeedbackWidget && <FloatingFeedbackWidget />}
          <GroupDetailsPageContent {...fetchGroupDetailsProps} group={group}>
            <Outlet />
          </GroupDetailsPageContent>
        </PageFiltersContainer>
      </SentryDocumentTitle>
    </Fragment>
  );
}

export default Sentry.withProfiler(GroupDetails);

const StyledLoadingError = styled(LoadingError)`
  margin: ${space(2)};
`;

const GroupTabPanels = styled(TabPanels)`
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  justify-content: stretch;
`;
