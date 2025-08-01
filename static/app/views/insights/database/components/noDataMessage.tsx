import {Fragment} from 'react';

import {openHelpSearchModal} from 'sentry/actionCreators/modal';
import {ExternalLink, Link} from 'sentry/components/core/link';
import {t, tct} from 'sentry/locale';
import type {Project} from 'sentry/types/project';
import useOrganization from 'sentry/utils/useOrganization';
import usePageFilters from 'sentry/utils/usePageFilters';
import {useDenylistedProjects} from 'sentry/views/insights/database/queries/useDenylistedProjects';
import {useOutdatedSDKProjects} from 'sentry/views/insights/database/queries/useOutdatedSDKProjects';
import {MODULE_DOC_LINK} from 'sentry/views/insights/database/settings';
import {makeProjectsPathname} from 'sentry/views/projects/pathname';

interface Props {
  Wrapper?: React.ComponentType<any>;
  isDataAvailable?: boolean;
}

function DivWrapper(props: React.ComponentProps<'div'>) {
  return <div {...props} />;
}

export function NoDataMessage({Wrapper = DivWrapper, isDataAvailable}: Props) {
  const organization = useOrganization();
  const {selection, isReady: pageFilterIsReady} = usePageFilters();

  const selectedProjectIds = selection.projects.map(projectId => projectId.toString());

  const {projects: outdatedProjects, isFetching: areOutdatedProjectsFetching} =
    useOutdatedSDKProjects({
      projectId: selectedProjectIds,
      enabled: pageFilterIsReady && !isDataAvailable,
    });

  const {projects: denylistedProjects, isFetching: areDenylistProjectsFetching} =
    useDenylistedProjects({
      projectId: selectedProjectIds,
    });

  const isDataFetching = areOutdatedProjectsFetching || areDenylistProjectsFetching;

  if (isDataFetching) {
    return null;
  }

  const hasAnyProblematicProjects =
    (!areOutdatedProjectsFetching && outdatedProjects.length > 0) ||
    (!areDenylistProjectsFetching && denylistedProjects.length > 0);

  if (isDataAvailable && !hasAnyProblematicProjects) {
    return null;
  }

  return (
    <Wrapper>
      {!isDataAvailable &&
        tct(
          'No queries found. Try updating your filters, or learn more about performance monitoring for queries in our [documentation:documentation].',
          {
            documentation: <ExternalLink href={MODULE_DOC_LINK} />,
          }
        )}{' '}
      {outdatedProjects.length > 0 &&
        tct('You may be missing data due to outdated SDKs: [projectList].', {
          projectList: <ProjectList projects={outdatedProjects} />,
        })}{' '}
      {denylistedProjects.length > 0 &&
        tct(
          'Some of your projects have been omitted from query performance analysis. Please [supportLink]. Omitted projects: [projectList].',
          {
            supportLink: (
              <Link to="" onClick={() => openHelpSearchModal({organization})}>
                {t('Contact Support')}
              </Link>
            ),
            projectList: <ProjectList projects={denylistedProjects} />,
          }
        )}
    </Wrapper>
  );
}

interface ProjectListProps {
  projects: Project[];
  limit?: number;
}

function ProjectList({projects, limit = MAX_LISTED_PROJECTS}: ProjectListProps) {
  const organization = useOrganization();

  const visibleProjects = projects.slice(0, limit + 1);
  const hasMoreProjectsThanVisible = projects.length > MAX_LISTED_PROJECTS;

  return (
    <Fragment>
      {visibleProjects.slice(0, limit).map((project, projectIndex) => {
        return (
          <span key={project.id}>
            <Link
              to={makeProjectsPathname({
                path: `/${project.slug}/`,
                organization,
              })}
            >
              {project.name}
            </Link>
            {projectIndex < visibleProjects.length - 1 && ', '}
          </span>
        );
      })}
      {hasMoreProjectsThanVisible &&
        tct(' and [count] more.', {
          count: projects.length - limit,
        })}{' '}
    </Fragment>
  );
}

const MAX_LISTED_PROJECTS = 3;
