import {useCallback, useLayoutEffect, useRef, useState} from 'react';
import styled from '@emotion/styled';
import {useResizeObserver} from '@react-aria/utils';

import {Button} from 'sentry/components/core/button';
import {ButtonBar} from 'sentry/components/core/button/buttonBar';
import ReplayPreferenceDropdown from 'sentry/components/replays/preferences/replayPreferenceDropdown';
import {useReplayContext} from 'sentry/components/replays/replayContext';
import {ReplayFullscreenButton} from 'sentry/components/replays/replayFullscreenButton';
import ReplayPlayPauseButton from 'sentry/components/replays/replayPlayPauseButton';
import TimeAndScrubberGrid from 'sentry/components/replays/timeAndScrubberGrid';
import {IconNext, IconRewind10} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import {getNextReplayFrame} from 'sentry/utils/replays/getReplayEvent';
import {TimelineScaleContextProvider} from 'sentry/utils/replays/hooks/useTimelineScale';
import {useReplayReader} from 'sentry/utils/replays/playback/providers/replayReaderProvider';

const SECOND = 1000;

const COMPACT_WIDTH_BREAKPOINT = 500;

interface Props {
  toggleFullscreen: () => void;
  hideFastForward?: boolean;
  isLoading?: boolean;
  speedOptions?: number[];
}

function ReplayPlayPauseBar({isLoading}: {isLoading?: boolean}) {
  const replay = useReplayReader();
  const {currentTime, setCurrentTime} = useReplayContext();

  return (
    <ButtonBar>
      <Button
        size="sm"
        title={t('Rewind 10s')}
        icon={<IconRewind10 size="sm" />}
        onClick={() => setCurrentTime(currentTime - 10 * SECOND)}
        aria-label={t('Rewind 10 seconds')}
        disabled={isLoading}
      />
      <ReplayPlayPauseButton isLoading={isLoading} />
      <Button
        disabled={isLoading}
        size="sm"
        title={t('Next breadcrumb')}
        icon={<IconNext size="sm" />}
        onClick={() => {
          if (!replay) {
            return;
          }
          const next = getNextReplayFrame({
            frames: replay.getChapterFrames(),
            targetOffsetMs: currentTime,
          });

          if (next) {
            setCurrentTime(next.offsetMs);
          }
        }}
        aria-label={t('Fast-forward to next breadcrumb')}
      />
    </ButtonBar>
  );
}

export default function ReplayController({
  toggleFullscreen,
  hideFastForward = false,
  speedOptions = [0.1, 0.25, 0.5, 1, 2, 4, 8, 16],
  isLoading,
}: Props) {
  const barRef = useRef<HTMLDivElement>(null);
  const [isCompact, setIsCompact] = useState(false);

  const updateIsCompact = useCallback(() => {
    const {width} = barRef.current?.getBoundingClientRect() ?? {
      width: COMPACT_WIDTH_BREAKPOINT,
    };
    setIsCompact(width < COMPACT_WIDTH_BREAKPOINT);
  }, []);

  useResizeObserver({
    ref: barRef,
    onResize: updateIsCompact,
  });
  useLayoutEffect(() => updateIsCompact, [updateIsCompact]);

  return (
    <ButtonGrid ref={barRef} isCompact={isCompact}>
      <ReplayPlayPauseBar isLoading={isLoading} />

      <TimelineScaleContextProvider>
        <TimeAndScrubberGrid isCompact={isCompact} showZoom isLoading={isLoading} />
      </TimelineScaleContextProvider>

      <ButtonBar>
        <ReplayPreferenceDropdown
          isLoading={isLoading}
          speedOptions={speedOptions}
          hideFastForward={hideFastForward}
        />
        <ReplayFullscreenButton toggleFullscreen={toggleFullscreen} />
      </ButtonBar>
    </ButtonGrid>
  );
}

const ButtonGrid = styled('div')<{isCompact: boolean}>`
  display: flex;
  gap: 0 ${space(2)};
  flex-direction: row;
  justify-content: space-between;
  ${p => (p.isCompact ? `flex-wrap: wrap;` : '')}
`;
