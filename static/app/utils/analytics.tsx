import type {Span} from '@sentry/core';
import * as Sentry from '@sentry/react';

import HookStore from 'sentry/stores/hookStore';
import type {Hooks} from 'sentry/types/hooks';
import {
  alertsEventMap,
  type AlertsEventParameters,
} from 'sentry/utils/analytics/alertsAnalyticsEvents';
import {
  featureFlagEventMap,
  type FeatureFlagEventParameters,
} from 'sentry/utils/analytics/featureFlagAnalyticsEvents';
import {
  type GamingAnalyticsEventParameters,
  gamingEventMap,
} from 'sentry/utils/analytics/gamingAnalyticsEvents';
import {
  logsAnalyticsEventMap,
  type LogsAnalyticsEventParameters,
} from 'sentry/utils/analytics/logsAnalyticsEvent';
import {navigationAnalyticsEventMap} from 'sentry/utils/analytics/navigationAnalyticsEvents';
import {nextJsInsightsEventMap} from 'sentry/utils/analytics/nextJsInsightsAnalyticsEvents';
import {
  quickStartEventMap,
  type QuickStartEventParameters,
} from 'sentry/utils/analytics/quickStartAnalyticsEvents';
import {
  statsEventMap,
  type StatsEventParameters,
} from 'sentry/utils/analytics/statsAnalyticsEvents';

import type {AgentMonitoringEventParameters} from './analytics/agentMonitoringAnalyticsEvents';
import {agentMonitoringEventMap} from './analytics/agentMonitoringAnalyticsEvents';
import type {CoreUIEventParameters} from './analytics/coreuiAnalyticsEvents';
import {coreUIEventMap} from './analytics/coreuiAnalyticsEvents';
import type {DashboardsEventParameters} from './analytics/dashboardsAnalyticsEvents';
import {dashboardsEventMap} from './analytics/dashboardsAnalyticsEvents';
import type {DiscoverEventParameters} from './analytics/discoverAnalyticsEvents';
import {discoverEventMap} from './analytics/discoverAnalyticsEvents';
import type {DynamicSamplingEventParameters} from './analytics/dynamicSamplingAnalyticsEvents';
import {dynamicSamplingEventMap} from './analytics/dynamicSamplingAnalyticsEvents';
import type {EcosystemEventParameters} from './analytics/ecosystemAnalyticsEvents';
import {ecosystemEventMap} from './analytics/ecosystemAnalyticsEvents';
import type {FeedbackEventParameters} from './analytics/feedbackAnalyticsEvents';
import {feedbackEventMap} from './analytics/feedbackAnalyticsEvents';
import type {GrowthEventParameters} from './analytics/growthAnalyticsEvents';
import {growthEventMap} from './analytics/growthAnalyticsEvents';
import type {InsightEventParameters} from './analytics/insightAnalyticEvents';
import {insightEventMap} from './analytics/insightAnalyticEvents';
import type {IntegrationEventParameters} from './analytics/integrations';
import {integrationEventMap} from './analytics/integrations';
import type {IssueEventParameters} from './analytics/issueAnalyticsEvents';
import {issueEventMap} from './analytics/issueAnalyticsEvents';
import type {LaravelInsightsEventParameters} from './analytics/laravelInsightsAnalyticsEvents';
import {laravelInsightsEventMap} from './analytics/laravelInsightsAnalyticsEvents';
import makeAnalyticsFunction from './analytics/makeAnalyticsFunction';
import type {McpMonitoringEventParameters} from './analytics/mcpMonitoringAnalyticsEvents';
import {mcpMonitoringEventMap} from './analytics/mcpMonitoringAnalyticsEvents';
import type {MonitorsEventParameters} from './analytics/monitorsAnalyticsEvents';
import {monitorsEventMap} from './analytics/monitorsAnalyticsEvents';
import type {OnboardingEventParameters} from './analytics/onboardingAnalyticsEvents';
import {onboardingEventMap} from './analytics/onboardingAnalyticsEvents';
import type {PerformanceEventParameters} from './analytics/performanceAnalyticsEvents';
import {performanceEventMap} from './analytics/performanceAnalyticsEvents';
import type {ProfilingEventParameters} from './analytics/profilingAnalyticsEvents';
import {profilingEventMap} from './analytics/profilingAnalyticsEvents';
import type {ProjectCreationEventParameters} from './analytics/projectCreationAnalyticsEvents';
import {projectCreationEventMap} from './analytics/projectCreationAnalyticsEvents';
import type {ReleasesEventParameters} from './analytics/releasesAnalyticsEvents';
import {releasesEventMap} from './analytics/releasesAnalyticsEvents';
import type {ReplayEventParameters} from './analytics/replayAnalyticsEvents';
import {replayEventMap} from './analytics/replayAnalyticsEvents';
import type {SearchEventParameters} from './analytics/searchAnalyticsEvents';
import {searchEventMap} from './analytics/searchAnalyticsEvents';
import type {SettingsEventParameters} from './analytics/settingsAnalyticsEvents';
import {settingsEventMap} from './analytics/settingsAnalyticsEvents';
import type {SignupAnalyticsParameters} from './analytics/signupAnalyticsEvents';
import {signupEventMap} from './analytics/signupAnalyticsEvents';
import type {StackTraceEventParameters} from './analytics/stackTraceAnalyticsEvents';
import {stackTraceEventMap} from './analytics/stackTraceAnalyticsEvents';
import {starfishEventMap} from './analytics/starfishAnalyticsEvents';
import type {TempestEventParameters} from './analytics/tempestAnalyticsEvents';
import {tempestEventMap} from './analytics/tempestAnalyticsEvents';
import {tracingEventMap, type TracingEventParameters} from './analytics/tracingEventMap';
import type {TeamInsightsEventParameters} from './analytics/workflowAnalyticsEvents';
import {workflowEventMap} from './analytics/workflowAnalyticsEvents';

interface EventParameters
  extends GrowthEventParameters,
    AgentMonitoringEventParameters,
    AlertsEventParameters,
    CoreUIEventParameters,
    DashboardsEventParameters,
    DiscoverEventParameters,
    FeatureFlagEventParameters,
    FeedbackEventParameters,
    InsightEventParameters,
    IssueEventParameters,
    LaravelInsightsEventParameters,
    McpMonitoringEventParameters,
    MonitorsEventParameters,
    PerformanceEventParameters,
    ProfilingEventParameters,
    ReleasesEventParameters,
    ReplayEventParameters,
    SearchEventParameters,
    SettingsEventParameters,
    TeamInsightsEventParameters,
    DynamicSamplingEventParameters,
    OnboardingEventParameters,
    GamingAnalyticsEventParameters,
    StackTraceEventParameters,
    EcosystemEventParameters,
    IntegrationEventParameters,
    ProjectCreationEventParameters,
    SignupAnalyticsParameters,
    LogsAnalyticsEventParameters,
    TracingEventParameters,
    StatsEventParameters,
    QuickStartEventParameters,
    TempestEventParameters,
    Record<string, Record<string, any>> {}

const allEventMap: Record<string, string | null> = {
  ...agentMonitoringEventMap,
  ...alertsEventMap,
  ...coreUIEventMap,
  ...dashboardsEventMap,
  ...discoverEventMap,
  ...featureFlagEventMap,
  ...feedbackEventMap,
  ...growthEventMap,
  ...insightEventMap,
  ...issueEventMap,
  ...laravelInsightsEventMap,
  ...monitorsEventMap,
  ...nextJsInsightsEventMap,
  ...performanceEventMap,
  ...tracingEventMap,
  ...profilingEventMap,
  ...logsAnalyticsEventMap,
  ...releasesEventMap,
  ...replayEventMap,
  ...searchEventMap,
  ...settingsEventMap,
  ...workflowEventMap,
  ...dynamicSamplingEventMap,
  ...onboardingEventMap,
  ...gamingEventMap,
  ...stackTraceEventMap,
  ...ecosystemEventMap,
  ...integrationEventMap,
  ...projectCreationEventMap,
  ...starfishEventMap,
  ...signupEventMap,
  ...statsEventMap,
  ...quickStartEventMap,
  ...navigationAnalyticsEventMap,
  ...tempestEventMap,
  ...mcpMonitoringEventMap,
};

/**
 * Analytics and metric tracking functionality.
 *
 * These are primarily driven through hooks provided through the hookstore. For
 * sentry.io these are currently mapped to our in-house analytics backend
 * 'Reload' and the Amplitude service.
 *
 * NOTE: sentry.io contributors, you will need to ensure that the eventKey
 *       passed exists as an event key in the Reload events.py configuration:
 *
 *       https://github.com/getsentry/reload/blob/master/reload_app/events.py
 *
 * NOTE: sentry.io contributors, if you are using `gauge` or `increment` the
 *       name must be added to the Reload metrics module:
 *
 *       https://github.com/getsentry/reload/blob/master/reload_app/metrics/__init__.py
 */

/**
 * This should be used with all analytics events regardless of the analytics
 * destination which includes Reload, Amplitude, and Google Analytics. All
 * events go to Reload. If eventName is defined, events also go to Amplitude.
 * For more details, refer to makeAnalyticsFunction.
 *
 * Should be used for all analytics that are defined in Sentry.
 */
export const trackAnalytics = makeAnalyticsFunction<EventParameters>(allEventMap);

/**
 * Should NOT be used directly. Instead, use makeAnalyticsFunction to generate
 * an analytics function.
 */
export const rawTrackAnalyticsEvent: Hooks['analytics:raw-track-event'] = (
  data,
  options
) => HookStore.get('analytics:raw-track-event').forEach(cb => cb(data, options));

type RecordMetric = Hooks['metrics:event'] & {
  endSpan: (opts: {
    /**
     * Name of the transaction to end
     */
    name: string;
  }) => void;

  mark: (opts: {
    /**
     * Name of the metric event
     */
    name: string;
    /**
     * Additional data that will be sent with measure()
     * This is useful if you want to track initial state
     */
    data?: Record<PropertyKey, unknown>;
  }) => void;

  measure: (opts: {
    /**
     * Additional data to send with metric event.
     * If a key collide with the data in mark(), this will overwrite them
     */
    data?: Record<PropertyKey, unknown>;
    /**
     * Name of ending mark
     */
    end?: string;
    /**
     * Name of the metric event
     */
    name?: string;
    /**
     * Do not clean up marks and measurements when completed
     */
    noCleanup?: boolean;
    /**
     * Name of starting mark
     */
    start?: string;
  }) => void;

  startSpan: (opts: {
    /**
     * Name of transaction
     */
    name: string;
    /**
     * Optional op code
     */
    op?: string;
  }) => Span | undefined;
};

/**
 * Used to pass data between metric.mark() and metric.measure()
 */
const metricDataStore = new Map<string, Record<PropertyKey, unknown>>();

/**
 * Record metrics.
 */
export const metric: RecordMetric = (name, value, tags) =>
  HookStore.get('metrics:event').forEach(cb => cb(name, value, tags));

// JSDOM implements window.performance but not window.performance.mark
const CAN_MARK =
  window.performance &&
  typeof window.performance.mark === 'function' &&
  typeof window.performance.measure === 'function' &&
  typeof window.performance.getEntriesByName === 'function' &&
  typeof window.performance.clearMeasures === 'function';

metric.mark = function metricMark({name, data = {}}) {
  // Just ignore if browser is old enough that it doesn't support this
  if (!CAN_MARK) {
    return;
  }

  if (!name) {
    throw new Error('Invalid argument provided to `metric.mark`');
  }

  window.performance.mark(name);
  metricDataStore.set(name, data);
};

/**
 * Performs a measurement between `start` and `end` (or now if `end` is not
 * specified) Calls `metric` with `name` and the measured time difference.
 */
metric.measure = function metricMeasure({name, start, end, data = {}, noCleanup} = {}) {
  // Just ignore if browser is old enough that it doesn't support this
  if (!CAN_MARK) {
    return;
  }

  if (!name || !start) {
    throw new Error('Invalid arguments provided to `metric.measure`');
  }

  let endMarkName = end;

  // Can't destructure from performance
  const {performance} = window;

  // NOTE: Edge REQUIRES an end mark if it is given a start mark
  // If we don't have an end mark, create one now.
  if (!end) {
    endMarkName = `${start}-end`;
    performance.mark(endMarkName);
  }

  // Check if starting mark exists
  if (!performance.getEntriesByName(start, 'mark').length) {
    return;
  }

  performance.measure(name, start, endMarkName);
  const startData = metricDataStore.get(start) || {};

  // Retrieve measurement entries
  performance
    .getEntriesByName(name, 'measure')
    .forEach(measurement =>
      metric(measurement.name, measurement.duration, {...startData, ...data})
    );

  // By default, clean up measurements
  if (!noCleanup) {
    performance.clearMeasures(name);
    performance.clearMarks(start);
    performance.clearMarks(endMarkName);
    metricDataStore.delete(start);
  }
};

/**
 * Used to pass data between startTransaction and endTransaction
 */
const spanDataStore = new Map<string, Span | undefined>();

metric.startSpan = ({name, op}) => {
  const span = Sentry.startInactiveSpan({
    name,
    op,
    forceTransaction: true,
  });
  spanDataStore.set(name, span);
  return span;
};

metric.endSpan = ({name}) => {
  const span = spanDataStore.get(name);
  span?.end();
};
