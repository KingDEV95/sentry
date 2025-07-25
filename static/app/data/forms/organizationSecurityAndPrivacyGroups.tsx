import type {JsonFormObject} from 'sentry/components/forms/types';
import {t} from 'sentry/locale';
import {convertMultilineFieldValue, extractMultilineFields} from 'sentry/utils';
import {
  formatStoreCrashReports,
  getStoreCrashReportsValues,
  SettingScope,
} from 'sentry/utils/crashReports';

// Export route to make these forms searchable by label/help
export const route = '/settings/:orgId/security-and-privacy/';
const formGroups: JsonFormObject[] = [
  {
    title: t('Security & Privacy'),
    fields: [
      {
        name: 'require2FA',
        type: 'boolean',
        label: t('Require Two-Factor Authentication'),
        help: t('Require and enforce two-factor authentication for all members'),
        'aria-label': t(
          'Enable to require and enforce two-factor authentication for all members'
        ),
        confirm: {
          isDangerous: true,
          true: t(
            'This will remove all members without two-factor authentication from your organization. It will also send them an email to setup 2FA and reinstate their access and settings. Do you want to continue?'
          ),
          false: t(
            'Are you sure you want to allow users to access your organization without having two-factor authentication enabled?'
          ),
        },
      },
      {
        name: 'allowSharedIssues',
        type: 'boolean',

        label: t('Allow Shared Issues'),
        help: t('Enable sharing of limited details on issues to anonymous users'),
        confirm: {
          isDangerous: true,
          true: t('Are you sure you want to allow sharing issues to anonymous users?'),
        },
      },
      {
        name: 'enhancedPrivacy',
        type: 'boolean',

        label: t('Enhanced Privacy'),
        help: t(
          'Enable enhanced privacy controls to limit personally identifiable information (PII) as well as source code in things like notifications'
        ),
        confirm: {
          isDangerous: true,
          false: t(
            'Disabling this can have privacy implications for ALL projects, are you sure you want to continue?'
          ),
        },
      },
      {
        name: 'scrapeJavaScript',
        type: 'boolean',
        confirm: {
          isDangerous: true,
          false: t(
            "Are you sure you want to disable sourcecode fetching for JavaScript events? This will affect Sentry's ability to aggregate issues if you're not already uploading sourcemaps as artifacts."
          ),
        },
        label: t('Allow JavaScript Source Fetching'),
        help: t('Allow Sentry to scrape missing JavaScript source context when possible'),
      },
      {
        name: 'storeCrashReports',
        type: 'select',
        label: t('Store Minidumps As Attachments'),
        help: t(
          'Store minidumps as attachments for improved processing and download in issue details.'
        ),
        visible: ({features}) => features.has('event-attachments'),
        // HACK: some organization can have limit of stored crash reports a number that's not in the options (legacy reasons),
        // we therefore display it in a placeholder
        placeholder: ({value}) => formatStoreCrashReports(value),
        choices: () =>
          getStoreCrashReportsValues(SettingScope.ORGANIZATION).map(value => [
            value,
            formatStoreCrashReports(value),
          ]),
      },
      {
        name: 'allowJoinRequests',
        type: 'boolean',

        label: t('Allow Join Requests'),
        help: t('Allow users to request to join your organization'),
        'aria-label': t('Enable to allow users to request to join your organization'),
        confirm: {
          isDangerous: true,
          true: t(
            'Are you sure you want to allow users to request to join your organization?'
          ),
        },
        visible: ({hasSsoEnabled}) => !hasSsoEnabled,
      },
    ],
  },
  {
    title: t('Data Scrubbing'),
    fields: [
      {
        name: 'dataScrubber',
        type: 'boolean',
        label: t('Require Data Scrubber'),
        help: t('Require server-side data scrubbing be enabled for all projects'),
        'aria-label': t('Enable server-side data scrubbing'),
        confirm: {
          isDangerous: true,
          false: t(
            'Disabling this can have privacy implications for ALL projects, are you sure you want to continue?'
          ),
        },
      },
      {
        name: 'dataScrubberDefaults',
        type: 'boolean',
        label: t('Require Using Default Scrubbers'),
        help: t(
          'Require the default scrubbers be applied to prevent things like passwords and credit cards from being stored for all projects'
        ),
        'aria-label': t(
          'Enable to apply default scrubbers to prevent things like passwords and credit cards from being stored'
        ),
        confirm: {
          isDangerous: true,
          false: t(
            'Disabling this can have privacy implications for ALL projects, are you sure you want to continue?'
          ),
        },
      },
      {
        name: 'sensitiveFields',
        type: 'string',
        multiline: true,
        autosize: true,
        maxRows: 10,
        rows: 1,
        placeholder: 'e.g. email',
        label: t('Global Sensitive Fields'),
        help: t(
          'Additional field names to match against when scrubbing data for all projects. Separate multiple entries with a newline.'
        ),
        'aria-label': t(
          'Enter additional field names to match against when scrubbing data for all projects. Separate multiple entries with a newline.'
        ),
        extraHelp: t(
          'Note: These fields will be used in addition to project specific fields.'
        ),
        saveOnBlur: false,
        saveMessage: t(
          'Changes to your scrubbing configuration will apply to all new events.'
        ),
        getValue: val => extractMultilineFields(val),
        setValue: val => convertMultilineFieldValue(val),
      },
      {
        name: 'safeFields',
        type: 'string',
        multiline: true,
        autosize: true,
        maxRows: 10,
        rows: 1,
        placeholder: t('e.g. business-email'),
        label: t('Global Safe Fields'),
        help: t(
          'Field names which data scrubbers should ignore. Separate multiple entries with a newline.'
        ),
        'aria-label': t(
          'Enter field names which data scrubbers should ignore. Separate multiple entries with a newline.'
        ),
        extraHelp: t(
          'Note: These fields will be used in addition to project specific fields'
        ),
        saveOnBlur: false,
        saveMessage: t(
          'Changes to your scrubbing configuration will apply to all new events.'
        ),
        getValue: val => extractMultilineFields(val),
        setValue: val => convertMultilineFieldValue(val),
      },
      {
        name: 'scrubIPAddresses',
        type: 'boolean',
        label: t('Prevent Storing of IP Addresses'),
        help: t(
          'Preventing IP addresses from being stored for new events on all projects'
        ),
        'aria-label': t(
          'Enable to prevent IP addresses from being stored for new events'
        ),
        confirm: {
          isDangerous: true,
          false: t(
            'Disabling this can have privacy implications for ALL projects, are you sure you want to continue?'
          ),
        },
      },
    ],
  },
];

export default formGroups;
