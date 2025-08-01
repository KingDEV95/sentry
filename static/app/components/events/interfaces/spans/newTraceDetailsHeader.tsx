import {Fragment} from 'react';
import styled from '@emotion/styled';

import {Flex} from 'sentry/components/core/layout';
import {generateStats} from 'sentry/components/events/opsBreakdown';
import {DividerSpacer} from 'sentry/components/performance/waterfall/miniHeader';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import type {EventTransaction} from 'sentry/types/event';
import type {Organization} from 'sentry/types/organization';
import getDuration from 'sentry/utils/duration/getDuration';
import toPercent from 'sentry/utils/number/toPercent';
import {TraceShape} from 'sentry/views/performance/newTraceDetails/traceModels/traceTree';
import type {TraceInfo} from 'sentry/views/performance/traceDetails/types';

import * as DividerHandlerManager from './dividerHandlerManager';

type PropType = {
  event: EventTransaction | undefined;
  organization: Organization;
  traceInfo: TraceInfo;
  traceType: TraceShape;
  traceViewHeaderRef: React.RefObject<HTMLDivElement | null>;
};

function ServiceBreakdown({
  rootEvent,
  displayBreakdown,
}: {
  displayBreakdown: boolean;
  rootEvent: EventTransaction;
}) {
  if (!displayBreakdown) {
    return (
      <BreakDownWrapper>
        <Flex align="center" justify="between">
          <div>{t('server side')}</div>
          <Flex>
            <span>{'N/A'}</span>
          </Flex>
        </Flex>
        <Flex align="center" justify="between">
          <div>{t('client side')}</div>
          <Flex>
            <span>{'N/A'}</span>
          </Flex>
        </Flex>
      </BreakDownWrapper>
    );
  }

  const totalDuration = rootEvent.endTimestamp - rootEvent.startTimestamp;
  const breakdown = generateStats(rootEvent, {type: 'no_filter'});
  const httpOp = breakdown.find(obj => obj.name === 'http.client');
  const httpDuration = httpOp?.totalInterval ?? 0;
  const serverSidePct = ((httpDuration / totalDuration) * 100).toFixed();
  const clientSidePct = 100 - Number(serverSidePct);

  return httpDuration ? (
    <BreakDownWrapper>
      <Flex align="center" justify="between">
        <div>{t('server side')}</div>
        <Flex>
          <Dur>{getDuration(httpDuration, 2, true)}</Dur>
          <Pct>{serverSidePct}%</Pct>
        </Flex>
      </Flex>
      <Flex align="center" justify="between">
        <div>{t('client side')}</div>
        <Flex>
          <Dur>{getDuration(totalDuration - httpDuration, 2, true)}</Dur>
          <Pct>{clientSidePct}%</Pct>
        </Flex>
      </Flex>
    </BreakDownWrapper>
  ) : null;
}

function TraceViewHeader(props: PropType) {
  const {event} = props;
  if (!event) {
    return null;
  }

  const opsBreakdown = generateStats(event, {type: 'no_filter'});
  const httpOp = opsBreakdown.find(obj => obj.name === 'http.client');
  const hasServiceBreakdown = httpOp && props.traceType === TraceShape.ONE_ROOT;

  return (
    <HeaderContainer ref={props.traceViewHeaderRef} hasProfileMeasurementsChart={false}>
      <DividerHandlerManager.Consumer>
        {dividerHandlerChildrenProps => {
          const {dividerPosition} = dividerHandlerChildrenProps;
          return (
            <Fragment>
              <OperationsBreakdown
                style={{
                  width: `calc(${toPercent(dividerPosition)} - 0.5px)`,
                }}
              >
                {props.event && (
                  <ServiceBreakdown
                    displayBreakdown={!!hasServiceBreakdown}
                    rootEvent={props.event}
                  />
                )}
              </OperationsBreakdown>
              <DividerSpacer
                style={{
                  position: 'absolute',
                  top: 0,
                  left: `calc(${toPercent(dividerPosition)} - 0.5px)`,
                  height: `100px`,
                }}
              />
            </Fragment>
          );
        }}
      </DividerHandlerManager.Consumer>
    </HeaderContainer>
  );
}

const HeaderContainer = styled('div')<{hasProfileMeasurementsChart: boolean}>`
  width: 100%;
  left: 0;
  top: 0;
  z-index: ${p => p.theme.zIndex.traceView.minimapContainer};
  background-color: ${p => p.theme.background};
  border-bottom: 1px solid ${p => p.theme.border};
  height: 100px;
  border-top-left-radius: ${p => p.theme.borderRadius};
  border-top-right-radius: ${p => p.theme.borderRadius};
`;

const OperationsBreakdown = styled('div')`
  height: 100px;
  position: absolute;
  left: 0;
  top: 0;
  overflow: hidden;
`;

const Dur = styled('div')`
  color: ${p => p.theme.subText};
  font-variant-numeric: tabular-nums;
`;

const Pct = styled('div')`
  min-width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
`;

const BreakDownWrapper = styled('div')`
  display: flex;
  flex-direction: column;
  padding: ${space(2)};
`;

export default TraceViewHeader;
