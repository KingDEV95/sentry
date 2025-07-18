import {css} from '@emotion/react';
import styled from '@emotion/styled';

import {space} from 'sentry/styles/space';

/**
 * Common performance layouts
 */

export const PerformanceLayoutBodyRow = styled('div')<{
  minSize: number;
  columns?: number;
}>`
  display: grid;
  grid-template-columns: 1fr;
  grid-column-gap: ${space(2)};
  grid-row-gap: ${space(2)};

  @media (min-width: ${p => p.theme.breakpoints.sm}) {
    grid-template-columns: repeat(2, 1fr);
  }

  @media (min-width: ${p => p.theme.breakpoints.md}) {
    ${p =>
      p.columns
        ? css`
            grid-template-columns: repeat(${p.columns}, 1fr);
          `
        : css`
            grid-template-columns: repeat(auto-fit, minmax(${p.minSize}px, 1fr));
          `}
  }
`;
