import {ErrorDetectorFixture} from 'sentry-fixture/detectors';
import {GroupFixture} from 'sentry-fixture/group';
import {ProjectFixture} from 'sentry-fixture/project';

import {render, screen} from 'sentry-test/reactTestingLibrary';

import {ErrorDetectorDetails} from 'sentry/views/detectors/components/details/error';

describe('ErrorDetectorDetails', function () {
  const defaultProps = {
    detector: ErrorDetectorFixture(),
    project: ProjectFixture(),
  };

  beforeEach(function () {
    MockApiClient.addMockResponse({
      url: '/projects/org-slug/project-slug/',
      method: 'GET',
      body: ProjectFixture(),
    });
    MockApiClient.addMockResponse({
      url: '/organizations/org-slug/users/',
      method: 'GET',
      body: [],
    });
    MockApiClient.addMockResponse({
      url: '/organizations/org-slug/issues/?limit=5&query=is%3Aunresolved%20detector%3A2&statsPeriod=14d',
      method: 'GET',
      body: [GroupFixture()],
    });
  });

  describe('Resolve section', function () {
    it('displays the auto-resolve time when it is configured', async function () {
      MockApiClient.addMockResponse({
        url: '/projects/org-slug/project-slug/',
        method: 'GET',
        body: ProjectFixture({
          resolveAge: 30 * 24,
        }),
      });

      render(<ErrorDetectorDetails {...defaultProps} />);

      expect(
        await screen.findByText('Auto-resolve after 30 days of inactivity.')
      ).toBeInTheDocument();
    });

    it('displays correct text when auto-resolve is disabled', async function () {
      const project = ProjectFixture({resolveAge: 0});

      render(<ErrorDetectorDetails {...defaultProps} project={project} />);

      expect(await screen.findByText('Auto-resolution disabled.')).toBeInTheDocument();
    });
  });
});
