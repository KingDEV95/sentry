import {Fragment} from 'react';
import styled from '@emotion/styled';

import * as Layout from 'sentry/components/layouts/thirds';
import LoadingError from 'sentry/components/loadingError';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import NoProjectMessage from 'sentry/components/noProjectMessage';
import SentryDocumentTitle from 'sentry/components/sentryDocumentTitle';
import {t} from 'sentry/locale';
import type {RouteComponentProps} from 'sentry/types/legacyReactRouter';
import type {TeamWithProjects} from 'sentry/types/project';
import localStorage from 'sentry/utils/localStorage';
import useRouteAnalyticsEventNames from 'sentry/utils/routeAnalytics/useRouteAnalyticsEventNames';
import useOrganization from 'sentry/utils/useOrganization';
import {useUserTeams} from 'sentry/utils/useUserTeams';
import {usePrefersStackedNav} from 'sentry/views/nav/usePrefersStackedNav';
import Header from 'sentry/views/organizationStats/header';

import TeamStatsControls from './controls';
import DescriptionCard from './descriptionCard';
import TeamIssuesAge from './teamIssuesAge';
import TeamIssuesBreakdown from './teamIssuesBreakdown';
import TeamResolutionTime from './teamResolutionTime';
import {TeamUnresolvedIssues} from './teamUnresolvedIssues';
import {dataDatetime} from './utils';

type Props = RouteComponentProps;

function TeamStatsIssues({location, router}: Props) {
  const organization = useOrganization();
  const {teams, isLoading, isError} = useUserTeams();
  const prefersStackedNav = usePrefersStackedNav();

  useRouteAnalyticsEventNames('team_insights.viewed', 'Team Insights: Viewed');

  const query = location?.query ?? {};
  const localStorageKey = `teamInsightsSelectedTeamId:${organization.slug}`;

  let localTeamId: string | null | undefined =
    query.team ?? localStorage.getItem(localStorageKey);
  if (localTeamId && !teams.some(team => team.id === localTeamId)) {
    localTeamId = null;
  }
  const currentTeamId = localTeamId ?? teams[0]?.id;
  const currentTeam = teams.find(team => team.id === currentTeamId) as
    | TeamWithProjects
    | undefined;
  const projects = currentTeam?.projects ?? [];
  const environment = query.environment;

  const {period, start, end, utc} = dataDatetime(query);

  if (teams.length === 0) {
    return (
      <NoProjectMessage organization={organization} superuserNeedsToBeProjectMember />
    );
  }

  if (isError) {
    return <LoadingError />;
  }

  const BodyWrapper = prefersStackedNav ? NewLayoutBody : Body;

  return (
    <Fragment>
      <SentryDocumentTitle title={t('Team Issues')} orgSlug={organization.slug} />
      <Header organization={organization} activeTab="issues" />

      <BodyWrapper>
        <TeamStatsControls
          showEnvironment
          location={location}
          router={router}
          currentTeam={currentTeam}
          currentEnvironment={environment}
        />

        {isLoading && <LoadingIndicator />}
        {!isLoading && (
          <Layout.Main fullWidth>
            <DescriptionCard
              title={t('All Unresolved Issues')}
              description={t(
                'This includes New and Returning issues in the last 7 days as well as those that haven’t been resolved or archived in the past.'
              )}
            >
              <TeamUnresolvedIssues
                projects={projects}
                organization={organization}
                teamSlug={currentTeam!.slug}
                environment={environment}
                period={period}
                start={start}
                end={end}
                utc={utc}
              />
            </DescriptionCard>

            <DescriptionCard
              title={t('New and Returning Issues')}
              description={t(
                'The new, regressed, and escalating issues that were assigned to your team.'
              )}
            >
              <TeamIssuesBreakdown
                organization={organization}
                projects={projects}
                teamSlug={currentTeam!.slug}
                environment={environment}
                period={period}
                start={start?.toString()}
                end={end?.toString()}
                statuses={['new', 'regressed', 'escalating']}
              />
            </DescriptionCard>

            <DescriptionCard
              title={t('Issues Triaged')}
              description={t(
                'How many new and returning issues were reviewed by your team each week. Reviewing an issue includes marking as reviewed, resolving, assigning to another team, or deleting.'
              )}
            >
              <TeamIssuesBreakdown
                organization={organization}
                projects={projects}
                teamSlug={currentTeam!.slug}
                environment={environment}
                period={period}
                start={start?.toString()}
                end={end?.toString()}
                statuses={[
                  'resolved',
                  'deleted',
                  'archived_until_escalating',
                  'archived_forever',
                  'archived_until_condition_met',
                ]}
              />
            </DescriptionCard>

            <DescriptionCard
              title={t('Age of Unresolved Issues')}
              description={t('How long ago since unresolved issues were first created.')}
            >
              <TeamIssuesAge organization={organization} teamSlug={currentTeam!.slug} />
            </DescriptionCard>

            <DescriptionCard
              title={t('Time to Resolution')}
              description={t(
                `The mean time it took for issues to be resolved by your team.`
              )}
            >
              <TeamResolutionTime
                organization={organization}
                environment={environment}
                teamSlug={currentTeam!.slug}
                period={period}
                start={start?.toString()}
                end={end?.toString()}
              />
            </DescriptionCard>
          </Layout.Main>
        )}
      </BodyWrapper>
    </Fragment>
  );
}

export default TeamStatsIssues;

const Body = styled(Layout.Body)`
  @media (min-width: ${p => p.theme.breakpoints.md}) {
    display: block;
  }
`;

const NewLayoutBody = styled('div')``;
