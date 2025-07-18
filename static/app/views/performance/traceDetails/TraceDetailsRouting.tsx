import type {LocationDescriptorObject} from 'history';

import {getEventTimestampInSeconds} from 'sentry/components/events/interfaces/utils';
import {normalizeDateTimeParams} from 'sentry/components/organizations/pageFilters/parse';
import type {Event} from 'sentry/types/event';
import {browserHistory} from 'sentry/utils/browserHistory';
import {useLocation} from 'sentry/utils/useLocation';
import useOrganization from 'sentry/utils/useOrganization';

import {getTraceDetailsUrl, shouldForceRouteToOldView} from './utils';

type Props = {
  children: React.JSX.Element;
  event: Event;
};

function TraceDetailsRouting(props: Props) {
  const {event, children} = props;
  const organization = useOrganization();
  const location = useLocation();
  const datetimeSelection = normalizeDateTimeParams(location.query);
  const traceId = event.contexts?.trace?.trace_id ?? '';

  if (location.query?.legacy) {
    return children;
  }

  const timestamp = getEventTimestampInSeconds(event);
  if (!shouldForceRouteToOldView(organization, timestamp)) {
    if (event?.groupID && event?.eventID) {
      const issuesLocation = `/organizations/${organization.slug}/issues/${event.groupID}/events/${event.eventID}`;
      browserHistory.replace({
        pathname: issuesLocation,
      });
    } else {
      const traceDetailsLocation: LocationDescriptorObject = getTraceDetailsUrl({
        organization,
        traceSlug: traceId,
        dateSelection: datetimeSelection,
        timestamp,
        eventId: event.eventID,
        location,
      });

      const query = {...traceDetailsLocation.query};
      if (location.hash.includes('span')) {
        const spanHashValue = location.hash
          .split('#')
          .find(value => value.includes('span'))!;
        const spanId = spanHashValue.split('-')[1];

        if (spanId) {
          query.node = [`span-${spanId}`, `txn-${event.eventID}`];
        }
      }

      browserHistory.replace({
        pathname: traceDetailsLocation.pathname,
        query,
      });
    }
  }

  return children;
}

export default TraceDetailsRouting;
