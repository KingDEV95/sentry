import {Fragment, useEffect, useRef} from 'react';

import {IssueViewNavItems} from 'sentry/components/nav/issueViews/issueViewNavItems';
import {useUpdateGroupSearchViewLastVisited} from 'sentry/components/nav/issueViews/useUpdateGroupSearchViewLastVisited';
import {usePrefersStackedNav} from 'sentry/components/nav/prefersStackedNav';
import {SecondaryNav} from 'sentry/components/nav/secondary';
import {PrimaryNavGroup} from 'sentry/components/nav/types';
import {t} from 'sentry/locale';
import type {RouteComponentProps} from 'sentry/types/legacyReactRouter';
import useOrganization from 'sentry/utils/useOrganization';
import {useParams} from 'sentry/utils/useParams';
import type {IssueView} from 'sentry/views/issueList/issueViews/issueViews';
import {useFetchGroupSearchViews} from 'sentry/views/issueList/queries/useFetchGroupSearchViews';

interface IssuesWrapperProps extends RouteComponentProps {
  children: React.ReactNode;
}

export function IssueNavigation({children}: IssuesWrapperProps) {
  const organization = useOrganization();

  const sectionRef = useRef<HTMLDivElement>(null);
  const {viewId} = useParams<{viewId?: string}>();

  const {data: groupSearchViews} = useFetchGroupSearchViews({
    orgSlug: organization.slug,
  });
  const {mutate: updateViewLastVisited} = useUpdateGroupSearchViewLastVisited();

  useEffect(() => {
    if (groupSearchViews && viewId) {
      const view = groupSearchViews.find(v => v.id === viewId);
      if (view) {
        updateViewLastVisited({viewId: view.id});
      }
    }
  }, [groupSearchViews, viewId, updateViewLastVisited]);

  const prefersStackedNav = usePrefersStackedNav();

  if (!prefersStackedNav) {
    return children;
  }

  const baseUrl = `/organizations/${organization.slug}/issues`;

  return (
    <Fragment>
      <SecondaryNav group={PrimaryNavGroup.ISSUES}>
        <SecondaryNav.Header>{t('Issues')}</SecondaryNav.Header>
        <SecondaryNav.Body>
          <SecondaryNav.Section>
            <SecondaryNav.Item to={`${baseUrl}/`} end>
              {t('Feed')}
            </SecondaryNav.Item>
            <SecondaryNav.Item to={`${baseUrl}/feedback/`}>
              {t('Feedback')}
            </SecondaryNav.Item>
          </SecondaryNav.Section>
          {groupSearchViews && (
            <SecondaryNav.Section title={t('Starred Views')}>
              <IssueViewNavItems
                loadedViews={groupSearchViews.map(
                  (
                    {
                      id,
                      name,
                      query: viewQuery,
                      querySort: viewQuerySort,
                      environments: viewEnvironments,
                      projects: viewProjects,
                      timeFilters: viewTimeFilters,
                      isAllProjects,
                    },
                    index
                  ): IssueView => {
                    const tabId = id ?? `default${index.toString()}`;

                    return {
                      id: tabId,
                      key: tabId,
                      label: name,
                      query: viewQuery,
                      querySort: viewQuerySort,
                      environments: viewEnvironments,
                      projects: isAllProjects ? [-1] : viewProjects,
                      timeFilters: viewTimeFilters,
                      isCommitted: true,
                    };
                  }
                )}
                sectionRef={sectionRef}
                baseUrl={baseUrl}
              />
            </SecondaryNav.Section>
          )}
          <SecondaryNav.Section title={t('Configure')}>
            <SecondaryNav.Item
              to={`${baseUrl}/alerts/rules/`}
              activeTo={`${baseUrl}/alerts/`}
            >
              {t('Alerts')}
            </SecondaryNav.Item>
          </SecondaryNav.Section>
        </SecondaryNav.Body>
      </SecondaryNav>
      {children}
    </Fragment>
  );
}
