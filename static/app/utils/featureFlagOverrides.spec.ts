import {OrganizationFixture} from 'sentry-fixture/organization';

import FeatureFlagOverrides from 'sentry/utils/featureFlagOverrides';
import localStorageWrapper from 'sentry/utils/localStorage';

const LOCALSTORAGE_KEY = 'feature-flag-overrides';

describe('FeatureFlagOverrides', () => {
  let organization: any;
  beforeEach(() => {
    localStorage.clear();

    organization = OrganizationFixture({
      features: ['enable-issues', 'enable-profiling', 'enable-replay'],
    });
  });

  describe('getFlagMap', () => {
    it('should convert `organization.features` into the shape of FlagMap', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":false,"enable-profiling":true}'
      );
      const inst = new FeatureFlagOverrides();

      expect(organization.features).toEqual([
        'enable-issues',
        'enable-profiling',
        'enable-replay',
      ]);

      expect(inst.getFlagMap(organization)).toEqual({
        'enable-issues': true,
        'enable-profiling': true,
        'enable-replay': true,
      });
    });
  });

  describe('getOverrides', () => {
    it('should return the FlapMap of everything that is manually overridden', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":false,"enable-profiling":true}'
      );
      const inst = new FeatureFlagOverrides();

      expect(inst.getStoredOverrides()).toEqual({
        'enable-issues': false,
        'enable-profiling': true,
      });
    });
  });

  describe('setStoredOverride', () => {
    it('should insert new flag names into localstorage', () => {
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBeNull();
      const inst = new FeatureFlagOverrides();

      inst.setStoredOverride('enable-issues', false);
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBe(
        '{"enable-issues":false}'
      );

      inst.setStoredOverride('enable-issues', true);
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBe(
        '{"enable-issues":true}'
      );
    });

    it('should preserve other flag overrides in localstorage', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":true,"enable-profiling":false}'
      );
      const inst = new FeatureFlagOverrides();

      inst.setStoredOverride('enable-replay', false);
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBe(
        '{"enable-issues":true,"enable-profiling":false,"enable-replay":false}'
      );

      inst.setStoredOverride('enable-replay', true);
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBe(
        '{"enable-issues":true,"enable-profiling":false,"enable-replay":true}'
      );
    });

    it('should set localstorage, even if the original value is malformed', () => {
      localStorageWrapper.setItem(LOCALSTORAGE_KEY, 'this is not an object {}');
      const inst = new FeatureFlagOverrides();

      inst.setStoredOverride('enable-issues', false);
      expect(localStorageWrapper.getItem(LOCALSTORAGE_KEY)).toBe(
        '{"enable-issues":false}'
      );
    });
  });

  describe('getEnabledFeatureFlagList', () => {
    it('should combine & remove features that are disabled locally', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":false,"enable-profiling":true}'
      );
      const inst = new FeatureFlagOverrides();

      // The original values
      expect(organization.features).toEqual([
        'enable-issues',
        'enable-profiling',
        'enable-replay',
      ]);

      // The overridden values
      expect(inst.getStoredOverrides()).toEqual({
        'enable-issues': false,
        'enable-profiling': true,
      });

      // The combined values
      expect(inst.getEnabledFeatureFlagList(organization)).toEqual([
        'enable-profiling',
        'enable-replay',
      ]);
    });

    it('should combine & add features that are listed locally, but not in the org', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":false,"secret-new-feature":true,"local-only-feature":false}'
      );
      const inst = new FeatureFlagOverrides();

      expect(inst.getEnabledFeatureFlagList(organization)).toEqual([
        'enable-profiling',
        'enable-replay',
        'secret-new-feature',
      ]);
    });
  });

  describe('loadOrg', () => {
    it('should override the features on an org with the combined list', () => {
      localStorageWrapper.setItem(
        LOCALSTORAGE_KEY,
        '{"enable-issues":false,"secret-new-feature":true,"local-only-feature":false}'
      );
      const inst = new FeatureFlagOverrides();

      expect(organization.features).toEqual([
        'enable-issues',
        'enable-profiling',
        'enable-replay',
      ]);

      inst.loadOrg(organization);

      expect(organization.features).toEqual([
        'enable-profiling',
        'enable-replay',
        'secret-new-feature',
      ]);
    });
  });
});
