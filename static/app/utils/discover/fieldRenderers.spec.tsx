import {ThemeFixture} from 'sentry-fixture/theme';
import {UserFixture} from 'sentry-fixture/user';

import {initializeOrg} from 'sentry-test/initializeOrg';
import {act, render, screen, waitFor} from 'sentry-test/reactTestingLibrary';

import ProjectsStore from 'sentry/stores/projectsStore';
import EventView from 'sentry/utils/discover/eventView';
import {getFieldRenderer} from 'sentry/utils/discover/fieldRenderers';
import {SPAN_OP_RELATIVE_BREAKDOWN_FIELD} from 'sentry/utils/discover/fields';

const theme = ThemeFixture();

describe('getFieldRenderer', function () {
  let location: any, context: any, project: any, organization: any, data: any, user: any;

  beforeEach(function () {
    context = initializeOrg();
    organization = context.organization;
    project = context.project;
    act(() => ProjectsStore.loadInitialData([project]));
    user = 'email:text@example.com';

    location = {
      pathname: '/events',
      query: {},
    };
    data = {
      id: '1',
      team_key_transaction: 1,
      title: 'ValueError: something bad',
      transaction: 'api.do_things',
      boolValue: 1,
      numeric: 1.23,
      createdAt: new Date(2019, 9, 3, 12, 13, 14),
      url: '/example',
      project: project.slug,
      release: 'F2520C43515BD1F0E8A6BD46233324641A370BF6',
      issue: 'SENTRY-T6P',
      user,
      'span_ops_breakdown.relative': '',
      'spans.browser': 10,
      'spans.db': 30,
      'spans.http': 15,
      'spans.resource': 20,
      'spans.total.time': 75,
      'transaction.duration': 75,
      'timestamp.to_day': '2021-09-05T00:00:00+00:00',
      'issue.id': '123214',
      'http_response_rate(3)': 0.012,
      'http_response_rate(5)': 0.000021,
      lifetimeCount: 10000,
      filteredCount: 3000,
      count: 6000,
      selectionDateString: 'last 7 days',
    };

    MockApiClient.addMockResponse({
      url: `/organizations/${organization.slug}/projects/${project.slug}/`,
      body: project,
    });

    MockApiClient.addMockResponse({
      url: `/organizations/${organization.slug}/key-transactions/`,
      method: 'POST',
    });

    MockApiClient.addMockResponse({
      url: `/organizations/${organization.slug}/key-transactions/`,
      method: 'DELETE',
    });

    MockApiClient.addMockResponse({
      url: `/organizations/${organization.slug}/projects/`,
      body: [project],
    });
  });

  it('can render string fields', function () {
    const renderer = getFieldRenderer('url', {url: 'string'});
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText(data.url)).toBeInTheDocument();
  });

  it('can render empty string fields', function () {
    const renderer = getFieldRenderer('url', {url: 'string'});
    data.url = '';
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText('(empty string)')).toBeInTheDocument();
  });

  it('can render boolean fields', function () {
    const renderer = getFieldRenderer('boolValue', {boolValue: 'boolean'});
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText('true')).toBeInTheDocument();
  });

  it('can render integer fields', function () {
    const renderer = getFieldRenderer('numeric', {numeric: 'integer'});
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText(data.numeric)).toBeInTheDocument();
  });

  describe('percentage', function () {
    it('can render percentage fields', function () {
      const renderer = getFieldRenderer(
        'http_response_rate(3)',
        {
          'http_response_rate(3)': 'percentage',
        },
        false
      );

      render(
        renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
      );
      expect(screen.getByText('1.2%')).toBeInTheDocument();
    });

    it('can render very small percentages', function () {
      const renderer = getFieldRenderer(
        'http_response_rate(5)',
        {
          'http_response_rate(5)': 'percentage',
        },
        false
      );

      render(
        renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
      );
      expect(screen.getByText('<0.01%')).toBeInTheDocument();
    });
  });

  describe('date', function () {
    it('can render date fields', async function () {
      const renderer = getFieldRenderer('createdAt', {createdAt: 'date'});
      render(
        renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
      );

      await screen.findByText('Oct 3, 2019 4:13:14 PM UTC');
    });

    it('can render date fields using utc when query string has utc set to true', async function () {
      const renderer = getFieldRenderer('createdAt', {createdAt: 'date'});
      render(
        renderer(data, {
          location: {...location, query: {utc: 'true'}},
          organization,
          theme,
        }) as React.ReactElement<any, any>
      );

      await screen.findByText('Oct 3, 2019 4:13:14 PM UTC');
    });
  });

  it('can render null date fields', function () {
    const renderer = getFieldRenderer('nope', {nope: 'date'});
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText('(no value)')).toBeInTheDocument();
  });

  it('can render timestamp.to_day', function () {
    const renderer = getFieldRenderer('timestamp.to_day', {'timestamp.to_day': 'date'});
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText('Sep 5, 2021')).toBeInTheDocument();
  });

  it('can render error.handled values', function () {
    const renderer = getFieldRenderer('error.handled', {'error.handled': 'boolean'});

    function validate(value: any, expectText: any) {
      const {unmount} = render(
        renderer(
          {'error.handled': value},
          {location, organization, theme}
        ) as React.ReactElement<any, any>
      );
      expect(screen.getByText(expectText)).toBeInTheDocument();
      unmount();
    }

    // Should render the same as the filter.
    // ie. all 1 or null
    validate([0, 1], 'false');
    validate([1, 0], 'false');
    validate([null, 0], 'false');
    validate([0, null], 'false');
    validate([null, 1], 'true');
    validate([1, null], 'true');

    // null = true for error.handled data.
    validate([null], 'true');

    // Default events won't have error.handled and will return an empty list.
    validate([], '(no value)');

    // Transactions will have null for error.handled as the 'tag' won't be set.
    validate(null, '(no value)');
  });

  it('can render user fields with aliased user', function () {
    const renderer = getFieldRenderer('user', {user: 'string'});

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByTestId('letter_avatar-avatar')).toBeInTheDocument();
    expect(screen.getByText('text@example.com')).toBeInTheDocument();
  });

  it('can render null user fields', function () {
    const renderer = getFieldRenderer('user', {user: 'string'});

    delete data.user;
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.queryByTestId('letter_avatar-avatar')).not.toBeInTheDocument();
    expect(screen.getByText('(no value)')).toBeInTheDocument();
  });

  it('can render null release fields', function () {
    const renderer = getFieldRenderer('release', {release: 'string'});

    delete data.release;
    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.getByText('(no value)')).toBeInTheDocument();
  });

  it('renders release version with hyperlink', function () {
    const renderer = getFieldRenderer('release', {release: 'string'});

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.queryByRole('link')).toHaveAttribute(
      'href',
      '/mock-pathname/?rd=show&rdRelease=F2520C43515BD1F0E8A6BD46233324641A370BF6&rdSource=release-version-link'
    );
    expect(screen.getByText('F2520C43515B')).toBeInTheDocument();
  });

  it('renders issue hyperlink', function () {
    const renderer = getFieldRenderer('issue', {issue: 'string'});

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.queryByRole('link')).toHaveAttribute(
      'href',
      `/organizations/org-slug/issues/123214/`
    );
    expect(screen.getByText('SENTRY-T6P')).toBeInTheDocument();
  });

  it('can render project as an avatar', function () {
    const renderer = getFieldRenderer('project', {project: 'string'});

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.queryByTestId('letter_avatar-avatar')).not.toBeInTheDocument();
    expect(screen.getByText(project.slug)).toBeInTheDocument();
  });

  it('can render project id as an avatar', function () {
    const renderer = getFieldRenderer('project', {project: 'number'});

    data = {...data, project: parseInt(project.id, 10)};

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    expect(screen.queryByTestId('letter_avatar-avatar')).not.toBeInTheDocument();
    expect(screen.getByText(project.slug)).toBeInTheDocument();
  });

  it('can render team key transaction as a star with the dropdown', async function () {
    const renderer = getFieldRenderer('team_key_transaction', {
      team_key_transaction: 'boolean',
    });

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    const star = screen.getByRole('button', {name: 'Toggle star for team'});

    // Enabled, can't open the menu in the test without setting up the
    // TeamKeyTransactionManager
    await waitFor(() => expect(star).toBeEnabled());
  });

  it('can render team key transaction as a star without the dropdown', function () {
    const renderer = getFieldRenderer('team_key_transaction', {
      team_key_transaction: 'boolean',
    });
    delete data.project;

    render(
      renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
    );

    const star = screen.getByRole('button', {name: 'Toggle star for team'});

    // Not enabled without a project
    expect(star).toBeDisabled();
  });

  describe('ops breakdown', () => {
    const getWidths = () =>
      Array.from(screen.getByTestId('relative-ops-breakdown').children).map(
        node => (node as HTMLElement).style.width
      );

    it('can render operation breakdowns', function () {
      const renderer = getFieldRenderer(SPAN_OP_RELATIVE_BREAKDOWN_FIELD, {
        [SPAN_OP_RELATIVE_BREAKDOWN_FIELD]: 'string',
      });

      render(
        renderer(data, {location, organization, theme}) as React.ReactElement<any, any>
      );

      expect(getWidths()).toEqual(['13.333%', '40%', '20%', '26.667%', '0%']);
    });

    it('renders operation breakdowns in sorted order when a sort field is provided', function () {
      const renderer = getFieldRenderer(SPAN_OP_RELATIVE_BREAKDOWN_FIELD, {
        [SPAN_OP_RELATIVE_BREAKDOWN_FIELD]: 'string',
      });

      render(
        renderer(data, {
          location,
          organization,
          theme,
          eventView: new EventView({
            sorts: [{field: 'spans.db', kind: 'desc'}],
            createdBy: UserFixture(),
            display: undefined,
            end: undefined,
            start: undefined,
            id: undefined,
            name: undefined,
            project: [],
            query: '',
            statsPeriod: undefined,
            environment: [],
            fields: [{field: 'spans.db'}],
            team: [],
            topEvents: undefined,
          }),
        }) as React.ReactElement<any, any>
      );

      expect(getWidths()).toEqual(['40%', '13.333%', '20%', '26.667%', '0%']);
    });
  });
});
