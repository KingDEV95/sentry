import {Component, Fragment, useCallback, useMemo} from 'react';
import styled from '@emotion/styled';
import * as Sentry from '@sentry/react';
import type {Location} from 'history';
import isEqual from 'lodash/isEqual';
import omit from 'lodash/omit';

import {updateSavedQueryVisit} from 'sentry/actionCreators/discoverSavedQueries';
import {fetchTotalCount} from 'sentry/actionCreators/events';
import {fetchProjectsCount} from 'sentry/actionCreators/projects';
import {loadOrganizationTags} from 'sentry/actionCreators/tags';
import {Client} from 'sentry/api';
import Confirm from 'sentry/components/confirm';
import {Alert} from 'sentry/components/core/alert';
import {Button} from 'sentry/components/core/button';
import {ExternalLink} from 'sentry/components/core/link';
import * as Layout from 'sentry/components/layouts/thirds';
import LoadingError from 'sentry/components/loadingError';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import {DatePageFilter} from 'sentry/components/organizations/datePageFilter';
import {EnvironmentPageFilter} from 'sentry/components/organizations/environmentPageFilter';
import PageFilterBar from 'sentry/components/organizations/pageFilterBar';
import PageFiltersContainer from 'sentry/components/organizations/pageFilters/container';
import {
  normalizeDateTimeParams,
  normalizeDateTimeString,
} from 'sentry/components/organizations/pageFilters/parse';
import {ProjectPageFilter} from 'sentry/components/organizations/projectPageFilter';
import type {CursorHandler} from 'sentry/components/pagination';
import SentryDocumentTitle from 'sentry/components/sentryDocumentTitle';
import {IconClose} from 'sentry/icons/iconClose';
import {t, tct} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {PageFilters} from 'sentry/types/core';
import {SavedSearchType} from 'sentry/types/group';
import type {InjectedRouter} from 'sentry/types/legacyReactRouter';
import type {NewQuery, Organization, SavedQuery} from 'sentry/types/organization';
import {defined, generateQueryWithTag} from 'sentry/utils';
import {trackAnalytics} from 'sentry/utils/analytics';
import {browserHistory} from 'sentry/utils/browserHistory';
import type {CustomMeasurementCollection} from 'sentry/utils/customMeasurements/customMeasurements';
import {CustomMeasurementsContext} from 'sentry/utils/customMeasurements/customMeasurementsContext';
import {CustomMeasurementsProvider} from 'sentry/utils/customMeasurements/customMeasurementsProvider';
import EventView, {isAPIPayloadSimilar} from 'sentry/utils/discover/eventView';
import {formatTagKey, generateAggregateFields} from 'sentry/utils/discover/fields';
import {
  DatasetSource,
  DiscoverDatasets,
  DisplayModes,
  MULTI_Y_AXIS_SUPPORTED_DISPLAY_MODES,
  SavedQueryDatasets,
} from 'sentry/utils/discover/types';
import localStorage from 'sentry/utils/localStorage';
import {MarkedText} from 'sentry/utils/marked/markedText';
import {MetricsCardinalityProvider} from 'sentry/utils/performance/contexts/metricsCardinality';
import type {ApiQueryKey} from 'sentry/utils/queryClient';
import {setApiQueryData, useApiQuery, useQueryClient} from 'sentry/utils/queryClient';
import {decodeList, decodeScalar} from 'sentry/utils/queryString';
import normalizeUrl from 'sentry/utils/url/normalizeUrl';
import useApi from 'sentry/utils/useApi';
import useOrganization from 'sentry/utils/useOrganization';
import usePageFilters from 'sentry/utils/usePageFilters';
import {hasDatasetSelector} from 'sentry/views/dashboards/utils';
import {
  DEFAULT_EVENT_VIEW,
  DEFAULT_EVENT_VIEW_MAP,
} from 'sentry/views/discover/results/data';
import ResultsChart from 'sentry/views/discover/results/resultsChart';
import ResultsHeader from 'sentry/views/discover/results/resultsHeader';
import ResultsSearchQueryBuilder from 'sentry/views/discover/results/resultsSearchQueryBuilder';
import {SampleDataAlert} from 'sentry/views/discover/results/sampleDataAlert';
import Tags from 'sentry/views/discover/results/tags';
import {DATASET_LABEL_MAP} from 'sentry/views/discover/savedQuery/datasetSelectorTabs';
import {
  getDatasetFromLocationOrSavedQueryDataset,
  getSavedQueryDataset,
  getSavedQueryWithDataset,
} from 'sentry/views/discover/savedQuery/utils';
import Table from 'sentry/views/discover/table';
import {generateTitle} from 'sentry/views/discover/utils';
import {addRoutePerformanceContext} from 'sentry/views/performance/utils';

type Props = {
  api: Client;
  loading: boolean;
  location: Location;
  organization: Organization;
  router: InjectedRouter;
  selection: PageFilters;
  setSavedQuery: (savedQuery?: SavedQuery) => void;
  isHomepage?: boolean;
  savedQuery?: SavedQuery;
};

type State = {
  confirmedQuery: boolean;
  error: string;
  errorCode: number;
  eventView: EventView;
  needConfirmation: boolean;
  showTags: boolean;
  tips: string[];
  totalValues: null | number;
  homepageQuery?: SavedQuery;
  savedQuery?: SavedQuery;
  savedQueryDataset?: SavedQueryDatasets;
  showForcedDatasetAlert?: boolean;
  showMetricsAlert?: boolean;
  showQueryIncompatibleWithDataset?: boolean;
  showUnparameterizedBanner?: boolean;
  splitDecision?: SavedQueryDatasets;
};
const SHOW_TAGS_STORAGE_KEY = 'discover2:show-tags';
const SHOW_UNPARAM_BANNER = 'showUnparameterizedBanner';

function readShowTagsState() {
  const value = localStorage.getItem(SHOW_TAGS_STORAGE_KEY);
  return value === '1';
}

function getYAxis(location: Location, eventView: EventView, savedQuery?: SavedQuery) {
  if (location.query.yAxis) {
    return decodeList(location.query.yAxis);
  }
  if (location.query.yAxis === null) {
    return [];
  }
  return savedQuery?.yAxis && savedQuery?.yAxis.length > 0
    ? decodeList(savedQuery?.yAxis)
    : [eventView.getYAxis()];
}

export class Results extends Component<Props, State> {
  static getDerivedStateFromProps(nextProps: Readonly<Props>, prevState: State): State {
    const savedQueryDataset = getSavedQueryDataset(
      nextProps.organization,
      nextProps.location,
      nextProps.savedQuery,
      undefined
    );
    const eventViewFromQuery = EventView.fromSavedQueryOrLocation(
      nextProps.savedQuery,
      nextProps.location
    );
    const eventView =
      hasDatasetSelector(nextProps.organization) && !eventViewFromQuery.dataset
        ? eventViewFromQuery.withDataset(
            getDatasetFromLocationOrSavedQueryDataset(undefined, savedQueryDataset)
          )
        : eventViewFromQuery;
    return {...prevState, eventView, savedQuery: nextProps.savedQuery, savedQueryDataset};
  }

  state: State = {
    eventView: EventView.fromSavedQueryOrLocation(
      this.props.savedQuery,
      this.props.location
    ),
    savedQueryDataset: getSavedQueryDataset(
      this.props.organization,
      this.props.location,
      this.props.savedQuery,
      undefined
    ),
    error: '',
    homepageQuery: undefined,
    errorCode: 200,
    totalValues: null,
    showTags: readShowTagsState(),
    needConfirmation: false,
    confirmedQuery: false,
    tips: [],
    showForcedDatasetAlert: true,
    showQueryIncompatibleWithDataset: false,
  };

  componentDidMount() {
    const {organization, selection, location, isHomepage} = this.props;
    if (location.query.fromMetric) {
      this.setState({showMetricsAlert: true});
      browserHistory.replace({
        ...location,
        query: {...location.query, fromMetric: undefined},
      });
    }
    if (location.query[SHOW_UNPARAM_BANNER]) {
      this.setState({showUnparameterizedBanner: true});
      browserHistory.replace({
        ...location,
        query: {...location.query, [SHOW_UNPARAM_BANNER]: undefined},
      });
    }
    loadOrganizationTags(this.tagsApi, organization.slug, selection);
    addRoutePerformanceContext(selection);
    this.checkEventView();
    this.canLoadEvents();
    if (!isHomepage && defined(location.query.id)) {
      updateSavedQueryVisit(organization.slug, location.query.id);
    }
  }

  componentDidUpdate(prevProps: Props, prevState: State) {
    const {location, organization, selection} = this.props;
    const {eventView, confirmedQuery, savedQuery} = this.state;

    if (location.query.incompatible) {
      this.setState({showQueryIncompatibleWithDataset: true});
      browserHistory.replace({
        ...location,
        query: {...location.query, incompatible: undefined},
      });
    }

    this.checkEventView();
    const currentQuery = eventView.getEventsAPIPayload(location);
    const prevQuery = prevState.eventView.getEventsAPIPayload(prevProps.location);
    const yAxisArray = getYAxis(location, eventView, savedQuery);
    const prevYAxisArray = getYAxis(prevProps.location, eventView, prevState.savedQuery);

    const savedQueryDataset =
      decodeScalar(location.query.queryDataset) ?? savedQuery?.queryDataset;
    const prevSavedQueryDataset =
      decodeScalar(prevProps.location.query.queryDataset) ??
      prevState.savedQuery?.queryDataset;

    const datasetChanged = !isEqual(savedQueryDataset, prevSavedQueryDataset);

    if (
      !isAPIPayloadSimilar(currentQuery, prevQuery) ||
      this.hasChartParametersChanged(
        prevState.eventView,
        eventView,
        prevYAxisArray,
        yAxisArray
      ) ||
      datasetChanged
    ) {
      this.canLoadEvents();
    }
    if (
      !isEqual(prevProps.selection.datetime, selection.datetime) ||
      !isEqual(prevProps.selection.projects, selection.projects)
    ) {
      loadOrganizationTags(this.tagsApi, organization.slug, selection);
      addRoutePerformanceContext(selection);
    }

    if (prevState.confirmedQuery !== confirmedQuery) {
      this.fetchTotalCount();
    }
  }

  tagsApi: Client = new Client();

  hasChartParametersChanged(
    prevEventView: EventView,
    eventView: EventView,
    prevYAxisArray: string[],
    yAxisArray: string[]
  ) {
    if (!isEqual(prevYAxisArray, yAxisArray)) {
      return true;
    }

    const prevDisplay = prevEventView.getDisplayMode();
    const display = eventView.getDisplayMode();

    return prevDisplay !== display;
  }

  canLoadEvents = async () => {
    const {api, location, organization} = this.props;
    const {eventView} = this.state;
    let needConfirmation = false;
    let confirmedQuery = true;
    const currentQuery = eventView.getEventsAPIPayload(location);
    const duration = eventView.getDays();

    if (duration > 30 && currentQuery.project) {
      let projectLength = currentQuery.project.length;

      if (
        projectLength === 0 ||
        (projectLength === 1 && currentQuery.project[0] === '-1')
      ) {
        try {
          const results = await fetchProjectsCount(api, organization.slug);

          if (projectLength === 0) {
            projectLength = results.myProjects;
          } else {
            projectLength = results.allProjects;
          }
        } catch (err) {
          // do nothing, so the length is 0 or 1 and the query is assumed safe
        }
      }

      if (projectLength > 10) {
        needConfirmation = true;
        confirmedQuery = false;
      }
    }
    // Once confirmed, a change of project or datetime will happen before this can set it to false,
    // this means a query will still happen even if the new conditions need confirmation
    // using a state callback to return this to false
    this.setState({needConfirmation, confirmedQuery}, () => {
      this.setState({confirmedQuery: false});
    });

    if (needConfirmation) {
      this.openConfirm();
    }
  };

  openConfirm = () => {};

  setOpenFunction = ({open}: any) => {
    this.openConfirm = open;
    return null;
  };

  handleConfirmed = () => {
    this.setState({needConfirmation: false, confirmedQuery: true}, () => {
      this.setState({confirmedQuery: false});
    });
  };

  handleCancelled = () => {
    this.setState({needConfirmation: false, confirmedQuery: false});
  };

  async fetchTotalCount() {
    const {api, organization, location} = this.props;
    const {eventView, confirmedQuery} = this.state;

    if (confirmedQuery === false || !eventView.isValid()) {
      return;
    }

    try {
      const totals = await fetchTotalCount(
        api,
        organization.slug,
        eventView.getEventsAPIPayload(location)
      );
      this.setState({totalValues: totals});
    } catch (err) {
      Sentry.captureException(err);
    }
  }

  checkEventView() {
    const {eventView, splitDecision, savedQueryDataset} = this.state;
    const {loading} = this.props;
    if (eventView.isValid() || loading) {
      return;
    }

    // If the view is not valid, redirect to a known valid state.
    const {location, organization, selection, isHomepage, savedQuery} = this.props;

    const value = getSavedQueryDataset(organization, location, savedQuery, splitDecision);
    const defaultEventView = hasDatasetSelector(organization)
      ? (getSavedQueryWithDataset(DEFAULT_EVENT_VIEW_MAP[value]) as NewQuery)
      : DEFAULT_EVENT_VIEW;

    const query = isHomepage && savedQuery ? omit(savedQuery, 'id') : defaultEventView;
    const nextEventView = EventView.fromNewQueryWithLocation(query, location);
    if (nextEventView.project.length === 0 && selection.projects) {
      nextEventView.project = selection.projects;
    }
    if (nextEventView.environment.length === 0 && selection.environments) {
      nextEventView.environment = selection.environments;
    }
    if (selection.datetime) {
      const {period, utc, start, end} = selection.datetime;
      nextEventView.statsPeriod = period ?? undefined;
      nextEventView.utc = utc?.toString();
      nextEventView.start = normalizeDateTimeString(start);
      nextEventView.end = normalizeDateTimeString(end);
    }
    if (location.query?.query) {
      nextEventView.query = decodeScalar(location.query.query, '');
    }

    if (isHomepage && !this.state.savedQuery) {
      this.setState({savedQuery, eventView: nextEventView});
    }
    browserHistory.replace(
      normalizeUrl(
        nextEventView.getResultsViewUrlTarget(
          organization,
          isHomepage,
          hasDatasetSelector(organization) ? savedQueryDataset : undefined
        )
      )
    );
  }

  handleCursor: CursorHandler = (cursor, path, query, _direction) => {
    const {router} = this.props;
    router.push({
      pathname: path,
      query: {...query, cursor},
    });
    // Treat pagination like the user already confirmed the query
    if (!this.state.needConfirmation) {
      this.handleConfirmed();
    }
  };

  handleChangeShowTags = () => {
    const {organization} = this.props;
    trackAnalytics('discover_v2.results.toggle_tag_facets', {
      organization,
    });
    this.setState(state => {
      const newValue = !state.showTags;
      localStorage.setItem(SHOW_TAGS_STORAGE_KEY, newValue ? '1' : '0');
      return {...state, showTags: newValue};
    });
  };

  handleSearch = (query: string) => {
    const {router, location} = this.props;

    const queryParams = normalizeDateTimeParams({
      ...location.query,
      query,
    });

    // do not propagate pagination when making a new search
    const searchQueryParams = omit(queryParams, 'cursor');

    router.push({
      pathname: location.pathname,
      query: searchQueryParams,
    });
  };

  handleYAxisChange = (value: string[]) => {
    const {router, location} = this.props;
    const isDisplayMultiYAxisSupported = MULTI_Y_AXIS_SUPPORTED_DISPLAY_MODES.includes(
      location.query.display as DisplayModes
    );

    const newQuery = {
      ...location.query,
      yAxis: value.length > 0 ? value : [null],
      // If using Multi Y-axis and not in a supported display, change to the default display mode
      display:
        value.length > 1 && !isDisplayMultiYAxisSupported
          ? location.query.display === DisplayModes.DAILYTOP5
            ? DisplayModes.DAILY
            : DisplayModes.DEFAULT
          : location.query.display,
    };

    router.push({
      pathname: location.pathname,
      query: newQuery,
    });

    // Treat axis changing like the user already confirmed the query
    if (!this.state.needConfirmation) {
      this.handleConfirmed();
    }

    trackAnalytics('discover_v2.y_axis_change', {
      organization: this.props.organization,
      y_axis_value: value,
    });
  };

  handleDisplayChange = (value: string) => {
    const {router, location} = this.props;

    const newQuery = {
      ...location.query,
      display: value,
    };

    router.push({
      pathname: location.pathname,
      query: newQuery,
    });

    // Treat display changing like the user already confirmed the query
    if (!this.state.needConfirmation) {
      this.handleConfirmed();
    }
  };

  handleIntervalChange = (value: string | undefined) => {
    const {router, location} = this.props;

    const newQuery = {
      ...location.query,
      interval: value,
    };

    if (location.query.interval !== value) {
      router.push({
        pathname: location.pathname,
        query: newQuery,
      });

      // Treat display changing like the user already confirmed the query
      if (!this.state.needConfirmation) {
        this.handleConfirmed();
      }
    }
  };

  handleTopEventsChange = (value: string) => {
    const {router, location} = this.props;

    const newQuery = {
      ...location.query,
      topEvents: value,
    };

    router.push({
      pathname: location.pathname,
      query: newQuery,
    });

    // Treat display changing like the user already confirmed the query
    if (!this.state.needConfirmation) {
      this.handleConfirmed();
    }
  };

  getDocumentTitle(): string {
    const {eventView} = this.state;
    const {isHomepage} = this.props;
    if (!eventView) {
      return '';
    }
    return generateTitle({eventView, isHomepage});
  }

  renderTagsTable() {
    const {organization, location} = this.props;
    const {eventView, totalValues, confirmedQuery} = this.state;

    return (
      <Layout.Side>
        <Tags
          generateUrl={this.generateTagUrl}
          totalValues={totalValues}
          eventView={eventView}
          organization={organization}
          location={location}
          confirmedQuery={confirmedQuery}
        />
      </Layout.Side>
    );
  }

  generateTagUrl = (key: string, value: string) => {
    const {organization, isHomepage} = this.props;
    const {eventView, savedQueryDataset} = this.state;

    const url = eventView.getResultsViewUrlTarget(
      organization,
      isHomepage,
      hasDatasetSelector(organization) ? savedQueryDataset : undefined
    );
    url.query = generateQueryWithTag(url.query, {
      key: formatTagKey(key),
      value,
    });
    return url;
  };

  renderError(error: string) {
    if (!error) {
      return null;
    }
    return (
      <Alert.Container>
        <Alert type="error">{error}</Alert>
      </Alert.Container>
    );
  }

  setError = (error: string, errorCode: number) => {
    this.setState({error, errorCode});
  };

  renderMetricsFallbackBanner() {
    const {organization} = this.props;
    if (
      !organization.features.includes('performance-mep-bannerless-ui') &&
      this.state.showMetricsAlert
    ) {
      return (
        <Alert.Container>
          <Alert type="info">
            {t(
              "You've navigated to this page from a performance metric widget generated from processed events. The results here only show indexed events."
            )}
          </Alert>
        </Alert.Container>
      );
    }
    if (this.state.showUnparameterizedBanner) {
      return (
        <Alert.Container>
          <Alert type="info">
            {tct(
              'These are unparameterized transactions. To better organize your transactions, [link:set transaction names manually].',
              {
                link: (
                  <ExternalLink href="https://docs.sentry.io/platforms/javascript/tracing/instrumentation/automatic-instrumentation/#beforenavigate" />
                ),
              }
            )}
          </Alert>
        </Alert.Container>
      );
    }
    return null;
  }

  renderQueryIncompatibleWithDatasetBanner() {
    const {organization} = this.props;
    if (hasDatasetSelector(organization) && this.state.showQueryIncompatibleWithDataset) {
      return (
        <Alert.Container>
          <Alert
            type="warning"
            trailingItems={
              <StyledCloseButton
                icon={<IconClose size="sm" />}
                aria-label={t('Close')}
                onClick={() => {
                  this.setState({showQueryIncompatibleWithDataset: false});
                }}
                size="zero"
                borderless
              />
            }
          >
            {t('Your query was updated to make it compatible with this dataset.')}
          </Alert>
        </Alert.Container>
      );
    }
    return null;
  }

  renderForcedDatasetBanner() {
    const {organization, savedQuery} = this.props;
    if (
      hasDatasetSelector(organization) &&
      this.state.showForcedDatasetAlert &&
      (this.state.splitDecision || savedQuery?.datasetSource === DatasetSource.FORCED)
    ) {
      const splitDecision = this.state.splitDecision ?? savedQuery?.queryDataset;
      if (!splitDecision) {
        return null;
      }
      return (
        <Alert.Container>
          <Alert
            type="warning"
            trailingItems={
              <StyledCloseButton
                icon={<IconClose size="sm" />}
                aria-label={t('Close')}
                onClick={() => {
                  this.setState({showForcedDatasetAlert: false});
                }}
                size="zero"
                borderless
              />
            }
          >
            {tct(
              "We're splitting our datasets up to make it a bit easier to digest. We defaulted this query to [splitDecision]. Edit as you see fit.",
              {splitDecision: DATASET_LABEL_MAP[splitDecision]}
            )}
          </Alert>
        </Alert.Container>
      );
    }
    return null;
  }

  renderTips() {
    const {tips} = this.state;
    if (tips) {
      return tips.map((tip, index) => (
        <Alert.Container key={`tip-${index}`}>
          <Alert type="info" key={`tip-${index}`}>
            <TipContainer as="span" text={tip} />
          </Alert>
        </Alert.Container>
      ));
    }
    return null;
  }

  setTips = (tips: string[]) => {
    // If there are currently no tips set and the new tips are empty, do nothing
    // and bail out of an expensive entire table rerender
    if (!tips.length && !this.state.tips.length) {
      return;
    }
    this.setState({tips});
  };

  setSplitDecision = (value?: SavedQueryDatasets) => {
    const {eventView} = this.state;
    const newEventView = eventView.withDataset(
      getDatasetFromLocationOrSavedQueryDataset(undefined, value)
    );
    this.setState({
      splitDecision: value,
      savedQueryDataset: value,
      eventView: newEventView,
    });
  };

  renderSearchBar(customMeasurements: CustomMeasurementCollection | undefined) {
    const {organization} = this.props;
    const {eventView} = this.state;
    const fields = eventView.hasAggregateField()
      ? generateAggregateFields(organization, eventView.fields)
      : eventView.fields;

    let savedSearchType: SavedSearchType | undefined = SavedSearchType.EVENT;
    if (hasDatasetSelector(organization)) {
      savedSearchType =
        eventView.dataset === DiscoverDatasets.TRANSACTIONS
          ? SavedSearchType.TRANSACTION
          : SavedSearchType.ERROR;
    }

    return (
      <Wrapper>
        <ResultsSearchQueryBuilder
          projectIds={eventView.project}
          query={eventView.query}
          fields={fields}
          onSearch={this.handleSearch}
          customMeasurements={customMeasurements}
          dataset={eventView.dataset}
          includeTransactions
          recentSearches={savedSearchType}
        />
      </Wrapper>
    );
  }

  render() {
    const {organization, location, router, selection, api, setSavedQuery, isHomepage} =
      this.props;
    const {
      eventView,
      error,
      errorCode,
      totalValues,
      showTags,
      confirmedQuery,
      savedQuery,
      splitDecision,
      savedQueryDataset,
    } = this.state;
    const hasDatasetSelectorFeature = hasDatasetSelector(organization);

    const query = eventView.query;
    const title = this.getDocumentTitle();
    const yAxisArray = getYAxis(location, eventView, savedQuery);

    if (!eventView.isValid()) {
      return <LoadingIndicator />;
    }

    return (
      <SentryDocumentTitle title={title} orgSlug={organization.slug}>
        <Fragment>
          <ResultsHeader
            setSavedQuery={setSavedQuery}
            errorCode={errorCode}
            organization={organization}
            location={location}
            eventView={eventView}
            yAxis={yAxisArray}
            router={router}
            isHomepage={isHomepage}
            splitDecision={splitDecision}
          />
          <Layout.Body>
            <CustomMeasurementsProvider organization={organization} selection={selection}>
              <Top fullWidth>
                {this.renderMetricsFallbackBanner()}
                {this.renderError(error)}
                {this.renderTips()}
                {this.renderForcedDatasetBanner()}
                {this.renderQueryIncompatibleWithDatasetBanner()}
                {!hasDatasetSelectorFeature && <SampleDataAlert query={query} />}

                <Wrapper>
                  <PageFilterBar condensed>
                    <ProjectPageFilter />
                    <EnvironmentPageFilter />
                    <DatePageFilter />
                  </PageFilterBar>
                </Wrapper>
                <CustomMeasurementsContext.Consumer>
                  {contextValue =>
                    this.renderSearchBar(contextValue?.customMeasurements ?? undefined)
                  }
                </CustomMeasurementsContext.Consumer>
                <MetricsCardinalityProvider
                  organization={organization}
                  location={location}
                >
                  <ResultsChart
                    api={api}
                    organization={organization}
                    eventView={eventView}
                    location={location}
                    onAxisChange={this.handleYAxisChange}
                    onDisplayChange={this.handleDisplayChange}
                    onTopEventsChange={this.handleTopEventsChange}
                    onIntervalChange={this.handleIntervalChange}
                    total={totalValues}
                    confirmedQuery={confirmedQuery}
                    yAxis={yAxisArray}
                  />
                </MetricsCardinalityProvider>
              </Top>
              <Layout.Main fullWidth={!showTags}>
                <Table
                  organization={organization}
                  eventView={eventView}
                  location={location}
                  title={title}
                  setError={this.setError}
                  onChangeShowTags={this.handleChangeShowTags}
                  showTags={showTags}
                  confirmedQuery={confirmedQuery}
                  onCursor={this.handleCursor}
                  isHomepage={isHomepage}
                  setTips={this.setTips}
                  queryDataset={savedQueryDataset}
                  setSplitDecision={(value?: SavedQueryDatasets) => {
                    if (
                      hasDatasetSelectorFeature &&
                      value !== SavedQueryDatasets.DISCOVER &&
                      value !== savedQuery?.dataset
                    ) {
                      this.setSplitDecision(value);
                    }
                  }}
                  dataset={hasDatasetSelectorFeature ? eventView.dataset : undefined}
                />
              </Layout.Main>
              {showTags ? this.renderTagsTable() : null}
              <Confirm
                priority="primary"
                header={<strong>{t('May lead to thumb twiddling')}</strong>}
                confirmText={t('Do it')}
                cancelText={t('Nevermind')}
                onConfirm={this.handleConfirmed}
                onCancel={this.handleCancelled}
                message={
                  <p>
                    {tct(
                      `You've created a query that will search for events made
                      [dayLimit:over more than 30 days] for [projectLimit:more than 10 projects].
                      A lot has happened during that time, so this might take awhile.
                      Are you sure you want to do this?`,
                      {
                        dayLimit: <strong />,
                        projectLimit: <strong />,
                      }
                    )}
                  </p>
                }
              >
                {this.setOpenFunction}
              </Confirm>
            </CustomMeasurementsProvider>
          </Layout.Body>
        </Fragment>
      </SentryDocumentTitle>
    );
  }
}

const Wrapper = styled('div')`
  display: flex;
  flex-direction: row;
  gap: ${space(1)};
  margin-bottom: ${space(2)};

  @media (max-width: ${p => p.theme.breakpoints.sm}) {
    display: grid;
    grid-auto-flow: row;
  }
`;

const Top = styled(Layout.Main)`
  flex-grow: 0;
`;

const TipContainer = styled(MarkedText)`
  > p {
    margin: 0;
  }
`;

function SavedQueryAPI(props: Omit<Props, 'savedQuery' | 'loading' | 'setSavedQuery'>) {
  const queryClient = useQueryClient();
  const {organization, location} = props;

  const queryKey = useMemo(
    (): ApiQueryKey => [
      `/organizations/${organization.slug}/discover/saved/${location.query.id}/`,
    ],
    [organization, location.query.id]
  );
  const {data, isError, isFetching, refetch} = useApiQuery<SavedQuery | undefined>(
    queryKey,
    {
      enabled: Boolean(location.query.id),
      staleTime: 0,
    }
  );

  const setSavedQuery = useCallback(
    (newQuery?: SavedQuery) => {
      setApiQueryData(queryClient, queryKey, newQuery);
      queryClient.refetchQueries({queryKey});
    },
    [queryClient, queryKey]
  );

  if (isFetching) {
    return <LoadingIndicator />;
  }

  if (isError) {
    return <LoadingError message={t('Failed to load saved query')} onRetry={refetch} />;
  }

  return (
    <Results
      {...props}
      savedQuery={
        hasDatasetSelector(organization) ? getSavedQueryWithDataset(data) : data
      }
      loading={isFetching}
      setSavedQuery={setSavedQuery}
    />
  );
}

export default function ResultsContainer(
  props: Omit<Props, 'api' | 'organization' | 'selection' | 'loading' | 'setSavedQuery'>
) {
  const api = useApi();
  const organization = useOrganization();
  const {selection} = usePageFilters();

  /**
   * Block `<Results>` from mounting until GSH is ready since there are API
   * requests being performed on mount.
   *
   * Also, we skip loading last used projects if you have multiple projects feature as
   * you no longer need to enforce a project if it is empty. We assume an empty project is
   * the desired behavior because saved queries can contain a project filter. The only
   * exception is if we are showing a prebuilt saved query in which case we want to
   * respect pinned filters.
   */

  return (
    <PageFiltersContainer
      disablePersistence={
        organization.features.includes('discover-query') &&
        !!(props.savedQuery || props.location.query.id)
      }
      skipLoadLastUsed={
        organization.features.includes('global-views') && !!props.savedQuery
      }
      // The Discover Results component will manage URL params, including page filters state
      // This avoids an unnecessary re-render when forcing a project filter for team plan users
      skipInitializeUrlParams
    >
      <SavedQueryAPI
        api={api}
        organization={organization}
        selection={selection}
        {...props}
      />
    </PageFiltersContainer>
  );
}

const StyledCloseButton = styled(Button)`
  background-color: transparent;
  transition: opacity 0.1s linear;

  &:hover,
  &:focus {
    background-color: transparent;
    opacity: 1;
  }
`;
