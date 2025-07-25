import type {Location} from 'history';
import {LocationFixture} from 'sentry-fixture/locationFixture';
import {OrganizationFixture} from 'sentry-fixture/organization';

import {render, screen} from 'sentry-test/reactTestingLibrary';
import {resetMockDate, setMockDate} from 'sentry-test/utils';

import EventView from 'sentry/utils/discover/eventView';

import {FieldRenderer} from './fieldRenderer';

const mockedEventData = {
  id: 'spanId',
  timestamp: '2024-10-03T10:15:00',
  trace: 'traceId',
  'span.op': 'test_op',
  'transaction.id': 'transactionId',
  'transaction.span_id': 'transactionSpanId',
};

describe('FieldRenderer tests', function () {
  const organization = OrganizationFixture();

  const location: Location = LocationFixture({
    query: {
      id: '42',
      name: 'best query',
      field: ['id', 'timestamp', 'trace', 'span.op', 'transaction.id'],
    },
  });

  const eventView = EventView.fromLocation(location);

  beforeAll(() => {
    const mockTimestamp = new Date('2024-10-06T00:00:00').getTime();
    setMockDate(mockTimestamp);
  });

  afterAll(() => {
    jest.restoreAllMocks();
    resetMockDate();
  });

  it('renders span.op', function () {
    render(
      <FieldRenderer
        column={eventView.getColumns()[3]}
        data={mockedEventData}
        meta={{}}
      />,
      {organization}
    );

    expect(screen.getByText('test_op')).toBeInTheDocument();
  });

  it('renders span id link to traceview', function () {
    render(
      <FieldRenderer
        column={eventView.getColumns()[0]}
        data={mockedEventData}
        meta={{}}
      />,
      {organization}
    );

    expect(screen.getByText('spanId')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      `/organizations/org-slug/traces/trace/traceId/?node=span-spanId&node=txn-transactionSpanId&source=traces&statsPeriod=14d&targetId=transactionSpanId&timestamp=1727964900`
    );
  });

  it('renders transaction id link to traceview', function () {
    render(
      <FieldRenderer
        column={eventView.getColumns()[4]}
        data={mockedEventData}
        meta={{}}
      />,
      {organization}
    );

    expect(screen.getByText('transactionId')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      `/organizations/org-slug/traces/trace/traceId/?source=traces&statsPeriod=14d&targetId=transactionSpanId&timestamp=1727964900`
    );
  });

  it('renders trace id link to traceview', function () {
    render(
      <FieldRenderer
        column={eventView.getColumns()[2]}
        data={mockedEventData}
        meta={{}}
      />,
      {organization}
    );

    expect(screen.getByText('traceId')).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      `/organizations/org-slug/traces/trace/traceId/?source=traces&statsPeriod=14d&timestamp=1727964900`
    );
  });

  it('renders timestamp', function () {
    render(
      <FieldRenderer
        column={eventView.getColumns()[1]}
        data={mockedEventData}
        meta={{}}
      />,
      {organization}
    );

    expect(screen.getByRole('time')).toBeInTheDocument();
    expect(screen.getByText('3d ago')).toBeInTheDocument();
  });
});
