import {OrganizationFixture} from 'sentry-fixture/organization';

import {renderHook} from 'sentry-test/reactTestingLibrary';
import {setWindowLocation} from 'sentry-test/utils';

import {browserHistory} from 'sentry/utils/browserHistory';
import useActiveReplayTab, {TabKey} from 'sentry/utils/replays/hooks/useActiveReplayTab';
import {OrganizationContext} from 'sentry/views/organizationContext';

describe('useActiveReplayTab', () => {
  beforeEach(() => {
    setWindowLocation('http://localhost/');
  });

  describe('breadcrumbs tab is default', () => {
    it('should use Breadcrumbs as a default', () => {
      const {result} = renderHook(useActiveReplayTab, {
        initialProps: {},
        wrapper: ({children}) => (
          <OrganizationContext value={OrganizationFixture({features: []})}>
            {children}
          </OrganizationContext>
        ),
      });

      expect(result.current.getActiveTab()).toBe(TabKey.BREADCRUMBS);
    });

    it('should use Breadcrumbs as a default, when there is a click search in the url', () => {
      setWindowLocation('http://localhost/?query=click.tag:button');

      const {result} = renderHook(useActiveReplayTab, {
        initialProps: {},
        wrapper: ({children}) => (
          <OrganizationContext value={OrganizationFixture({features: []})}>
            {children}
          </OrganizationContext>
        ),
      });

      expect(result.current.getActiveTab()).toBe(TabKey.BREADCRUMBS);
    });

    it('should set the default tab if the name is invalid', () => {
      const {result} = renderHook(useActiveReplayTab, {
        initialProps: {},
        wrapper: ({children}) => (
          <OrganizationContext value={OrganizationFixture({features: []})}>
            {children}
          </OrganizationContext>
        ),
      });
      expect(result.current.getActiveTab()).toBe(TabKey.BREADCRUMBS);

      result.current.setActiveTab('foo bar');
      expect(browserHistory.push).toHaveBeenLastCalledWith({
        pathname: '/',
        query: {t_main: TabKey.BREADCRUMBS},
      });
    });

    it('should allow case-insensitive tab names', () => {
      const {result} = renderHook(useActiveReplayTab, {
        initialProps: {},
        wrapper: ({children}) => (
          <OrganizationContext value={OrganizationFixture({features: []})}>
            {children}
          </OrganizationContext>
        ),
      });
      expect(result.current.getActiveTab()).toBe(TabKey.BREADCRUMBS);

      result.current.setActiveTab('nEtWoRk');
      expect(browserHistory.push).toHaveBeenLastCalledWith({
        pathname: '/',
        state: undefined,
        query: {t_main: TabKey.NETWORK},
      });
    });
  });
});
