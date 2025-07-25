import {Fragment, useRef} from 'react';
import styled from '@emotion/styled';

import {CheckInPlaceholder} from 'sentry/components/checkInTimeline/checkInPlaceholder';
import {CheckInTimeline} from 'sentry/components/checkInTimeline/checkInTimeline';
import {
  GridLineLabels,
  GridLineOverlay,
} from 'sentry/components/checkInTimeline/gridLines';
import type {TimeWindow} from 'sentry/components/checkInTimeline/types';
import {getConfigFromTimeRange} from 'sentry/components/checkInTimeline/utils/getConfigFromTimeRange';
import {getTimeRangeFromEvent} from 'sentry/components/checkInTimeline/utils/getTimeRangeFromEvent';
import {ButtonBar} from 'sentry/components/core/button/buttonBar';
import {LinkButton} from 'sentry/components/core/button/linkButton';
import {Overlay} from 'sentry/components/overlay';
import Panel from 'sentry/components/panels/panel';
import {IconOpen} from 'sentry/icons';
import {t} from 'sentry/locale';
import {fadeIn} from 'sentry/styles/animations';
import {space} from 'sentry/styles/space';
import type {Event} from 'sentry/types/event';
import type {Organization} from 'sentry/types/organization';
import type {Project} from 'sentry/types/project';
import {useDimensions} from 'sentry/utils/useDimensions';
import {useLocation} from 'sentry/utils/useLocation';
import {makeAlertsPathname} from 'sentry/views/alerts/pathnames';
import {ResolutionSelector} from 'sentry/views/insights/crons/components/overviewTimeline/resolutionSelector';
import {CronServiceIncidents} from 'sentry/views/insights/crons/components/serviceIncidents';
import {
  checkInStatusPrecedent,
  statusToText,
  tickStyle,
} from 'sentry/views/insights/crons/utils';
import {selectCheckInData} from 'sentry/views/insights/crons/utils/selectCheckInData';
import {useMonitorStats} from 'sentry/views/insights/crons/utils/useMonitorStats';
import {SectionKey} from 'sentry/views/issueDetails/streamline/context';
import {InterimSection} from 'sentry/views/issueDetails/streamline/interimSection';

interface Props {
  event: Event;
  organization: Organization;
  project: Project;
}

const DEFAULT_ENVIRONMENT = 'production';

export function CronTimelineSection({event, organization, project}: Props) {
  const location = useLocation();
  const timeWindow = (location.query?.timeWindow as TimeWindow) ?? '24h';
  const monitorId = event.tags.find(({key}) => key === 'monitor.id')?.value;
  const monitorSlug = event.tags.find(({key}) => key === 'monitor.slug')?.value;
  const environment = event.tags.find(({key}) => key === 'environment')?.value;

  const nowRef = useRef(new Date());
  const {start, end} = getTimeRangeFromEvent(event, nowRef.current, timeWindow);
  const elementRef = useRef<HTMLDivElement>(null);
  const {width: timelineWidth} = useDimensions<HTMLDivElement>({elementRef});

  const timeWindowConfig = getConfigFromTimeRange(start, end, timelineWidth);

  const {data: monitorStats, isPending} = useMonitorStats({
    timeWindowConfig,
    monitors: [monitorId ?? ''],
    enabled: monitorId !== undefined,
  });

  if (!monitorId) {
    return null;
  }

  const msPerPixel = (timeWindowConfig.elapsedMinutes * 60 * 1000) / timelineWidth;
  const eventTickLeft =
    (new Date(event.dateReceived).valueOf() - start.valueOf()) / msPerPixel;

  const actions = (
    <ButtonBar>
      <LinkButton
        size="xs"
        icon={<IconOpen />}
        to={{
          pathname: makeAlertsPathname({
            path: `/rules/crons/${project.slug}/${monitorSlug}/details/`,
            organization,
          }),
          query: {environment},
        }}
      >
        {t('View in Monitor Details')}
      </LinkButton>
      <ResolutionSelector />
    </ButtonBar>
  );

  return (
    <InterimSection
      title={t('Check-ins')}
      type={SectionKey.CRON_TIMELINE}
      help={t('A timeline of check-ins that happened before and after this event')}
      actions={actions}
    >
      <TimelineContainer>
        <TimelineWidthTracker ref={elementRef} />
        <StyledGridLineTimeLabels timeWindowConfig={timeWindowConfig} />
        <GridLineOverlay
          timeWindowConfig={timeWindowConfig}
          showCursor={!isPending}
          additionalUi={
            !isPending && <CronServiceIncidents timeWindowConfig={timeWindowConfig} />
          }
          cursorOverlayAnchor="top"
          cursorOverlayAnchorOffset={10}
        />
        {monitorStats && !isPending ? (
          <Fragment>
            <EventLineTick left={eventTickLeft} />
            <EventLineLabel left={eventTickLeft} timelineWidth={timelineWidth}>
              {t('Event Created')}
            </EventLineLabel>
            <FadeInContainer>
              <CheckInTimeline
                statusLabel={statusToText}
                statusStyle={tickStyle}
                statusPrecedent={checkInStatusPrecedent}
                timeWindowConfig={timeWindowConfig}
                bucketedData={selectCheckInData(
                  monitorStats[monitorId] ?? [],
                  environment ?? DEFAULT_ENVIRONMENT
                )}
              />
            </FadeInContainer>
          </Fragment>
        ) : (
          <CheckInPlaceholder />
        )}
      </TimelineContainer>
    </InterimSection>
  );
}

const TimelineContainer = styled(Panel)`
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 40px 100px;
  align-items: center;
`;

const StyledGridLineTimeLabels = styled(GridLineLabels)`
  border-bottom: 1px solid ${p => p.theme.border};
`;

const TimelineWidthTracker = styled('div')`
  position: absolute;
  width: 100%;
  grid-row: 1;
  grid-column: 0;
`;

const EventLineTick = styled('div')<{left: number}>`
  background: ${p => p.theme.translucentBorder};
  width: 2px;
  height: 100%;
  grid-row: 2 / 3;
  position: absolute;
  top: 0;
  left: ${p => p.left}px;
  transform: translateX(-2px);
`;

const EventLineLabel = styled(Overlay, {
  shouldForwardProp: prop => prop !== 'left' && prop !== 'timelineWidth',
})<{left: number; timelineWidth: number}>`
  width: max-content;
  padding: ${space(0.75)} ${space(1)};
  color: ${p => p.theme.textColor};
  font-size: ${p => p.theme.fontSize.sm};
  position: absolute;
  bottom: ${space(1)};
  left: clamp(0px, ${p => p.left}px, calc(${p => p.timelineWidth}px - 50px));
  transform: translateX(-50%);
`;

const FadeInContainer = styled('div')`
  animation: ${fadeIn} 500ms ease-out forwards;
`;
