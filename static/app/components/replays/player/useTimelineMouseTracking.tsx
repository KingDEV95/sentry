import type {RefObject} from 'react';
import {useCallback} from 'react';

import {useReplayContext} from 'sentry/components/replays/replayContext';
import divide from 'sentry/utils/number/divide';
import {useReplayReader} from 'sentry/utils/replays/playback/providers/replayReaderProvider';
import useCurrentHoverTime from 'sentry/utils/replays/playback/providers/useCurrentHoverTime';
import useMouseTracking from 'sentry/utils/useMouseTracking';

type Opts<T extends Element> = {
  elem: RefObject<T | null>;
};

/**
 * This provides scale-aware logic for accurate hover time and position
 * calculations on a zoomed timeline, accounting for the zoom level, current
 * playback position, and timeline boundaries.
 */
export default function useTimelineMouseTracking<T extends Element>({
  elem,
  scale,
}: Opts<T> & {scale: number}) {
  const replay = useReplayReader();
  const {currentTime} = useReplayContext();

  const [, setCurrentHoverTime] = useCurrentHoverTime();
  const durationMs = replay?.getDurationMs();

  const handlePositionChange = useCallback(
    (params: any) => {
      if (!params || durationMs === undefined) {
        setCurrentHoverTime(undefined);
        return;
      }
      const {left, width} = params;
      const initialTranslate = 0.5 / scale;
      const percentComplete = divide(currentTime, durationMs);

      const starting = percentComplete < initialTranslate;
      const ending = percentComplete + initialTranslate > 1;

      if (left >= 0) {
        const time = () => {
          let percent = left / width;
          if (starting) {
            return (percent * durationMs) / scale;
          }
          if (ending) {
            return (percent * durationMs) / scale + (1 - 1 / scale) * durationMs;
          }
          percent = (left - width / 2) / width;
          return currentTime + (percent * durationMs) / scale;
        };
        setCurrentHoverTime(time());
      } else {
        setCurrentHoverTime(undefined);
      }
    },
    [durationMs, setCurrentHoverTime, currentTime, scale]
  );

  const mouseTrackingProps = useMouseTracking({
    elem,
    onPositionChange: handlePositionChange,
  });
  return mouseTrackingProps;
}
