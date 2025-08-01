import styled from '@emotion/styled';

import {Alert} from 'sentry/components/core/alert';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import type {UseApiQueryResult} from 'sentry/utils/queryClient';
import type RequestError from 'sentry/utils/requestError/requestError';
import {AppSizeInsights} from 'sentry/views/preprod/main/appSizeInsights';
import {AppSizeTreemap} from 'sentry/views/preprod/main/appSizeTreemap';
import type {AppSizeApiResponse} from 'sentry/views/preprod/types/appSizeTypes';

interface BuildDetailsMainContentProps {
  appSizeQuery: UseApiQueryResult<AppSizeApiResponse, RequestError>;
}

export function BuildDetailsMainContent(props: BuildDetailsMainContentProps) {
  const {
    data: appSizeData,
    isPending: isAppSizePending,
    isError: isAppSizeError,
    error: appSizeError,
  } = props.appSizeQuery;

  if (isAppSizePending) {
    return (
      <MainContentContainer>
        <LoadingIndicator />
      </MainContentContainer>
    );
  }

  if (isAppSizeError) {
    return (
      <MainContentContainer>
        <Alert type="error">{appSizeError?.message}</Alert>
      </MainContentContainer>
    );
  }

  if (!appSizeData) {
    return (
      <MainContentContainer>
        <Alert type="error">No app size data found</Alert>
      </MainContentContainer>
    );
  }

  return (
    <MainContentContainer>
      <TreemapContainer>
        <AppSizeTreemap treemapData={appSizeData.treemap} />
      </TreemapContainer>
      {appSizeData.insights && (
        <AppSizeInsights
          insights={appSizeData.insights}
          totalSize={appSizeData.treemap.root.size || 0}
        />
      )}
    </MainContentContainer>
  );
}

const MainContentContainer = styled('div')`
  width: 100%;
`;

const TreemapContainer = styled('div')`
  width: 100%;
  height: 508px;
`;
