import {ExternalLink} from 'sentry/components/core/link';
import type {
  Docs,
  DocsParams,
  OnboardingConfig,
} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {CrashReportWebApiOnboarding} from 'sentry/components/onboarding/gettingStartedDoc/utils/feedbackOnboarding';
import {t, tct} from 'sentry/locale';

type Params = DocsParams;

export const getRubyProfilingOnboarding = ({
  frameworkPackage,
}: {frameworkPackage?: string} = {}) => ({
  install: () => [
    {
      type: StepType.INSTALL,
      description: tct(
        'We use the [code:stackprof] [stackprofLink:gem] to collect profiles for Ruby.',
        {
          code: <code />,
          stackprofLink: <ExternalLink href="https://github.com/tmm1/stackprof" />,
        }
      ),
      configurations: [
        {
          description: tct(
            'First add [code:stackprof] to your [code:Gemfile] and make sure it is loaded before the Sentry SDK.',
            {
              code: <code />,
            }
          ),
          language: 'ruby',
          code: `
gem 'stackprof'
gem 'sentry-ruby'${
            frameworkPackage
              ? `
gem '${frameworkPackage}'`
              : ''
          }`,
        },
      ],
    },
  ],
  configure: (params: Params) => [
    {
      type: StepType.CONFIGURE,
      description: tct(
        'Then, make sure both [code:traces_sample_rate] and [code:profiles_sample_rate] are set and non-zero in your Sentry initializer.',
        {
          code: <code />,
        }
      ),
      configurations: [
        {
          code: [
            {
              label: 'Ruby',
              value: 'ruby',
              filename: 'config/initializers/sentry.rb',
              language: 'ruby',
              code: `
Sentry.init do |config|
  config.dsn = "${params.dsn.public}"
  config.traces_sample_rate = 1.0
  config.profiles_sample_rate = 1.0
end
                   `,
            },
          ],
        },
      ],
    },
  ],
  verify: () => [],
});

const getInstallSnippet = (params: Params) =>
  `${params.isProfilingSelected ? 'gem "stackprof"\n' : ''}gem "sentry-ruby"`;

const getConfigureSnippet = (params: Params) => `
require 'sentry-ruby'

Sentry.init do |config|
  config.dsn = '${params.dsn.public}'

  # Add data like request headers and IP for users,
  # see https://docs.sentry.io/platforms/ruby/data-management/data-collected/ for more info
  config.send_default_pii = true${
    params.isLogsSelected
      ? `

  # Enable sending logs to Sentry
  config.enable_logs = true
  # Patch Ruby logger to forward logs
  config.enabled_patches = [:logger]`
      : ''
  }${
    params.isPerformanceSelected
      ? `

  # Set traces_sample_rate to 1.0 to capture 100%
  # of transactions for tracing.
  # We recommend adjusting this value in production.
  config.traces_sample_rate = 1.0
  # or
  config.traces_sampler = lambda do |context|
    true
  end`
      : ''
  }${
    params.isProfilingSelected
      ? `
  # Set profiles_sample_rate to profile 100%
  # of sampled transactions.
  # We recommend adjusting this value in production.
  config.profiles_sample_rate = 1.0`
      : ''
  }
end`;

const getVerifySnippet = () => `
begin
  1 / 0
rescue ZeroDivisionError => exception
  Sentry.capture_exception(exception)
end

Sentry.capture_message("test message")`;

const onboarding: OnboardingConfig = {
  install: (params: Params) => [
    {
      type: StepType.INSTALL,
      description: tct(
        'The Sentry SDK for Ruby comes as a gem that should be added to your [gemfileCode:Gemfile]:',
        {
          gemfileCode: <code />,
        }
      ),
      configurations: [
        {
          description: params.isProfilingSelected
            ? tct(
                'Ruby Profiling beta is available since SDK version 5.9.0. We use the [stackprofLink:stackprof gem] to collect profiles for Ruby. Make sure [code:stackprof] is loaded before [code:sentry-ruby].',
                {
                  stackprofLink: (
                    <ExternalLink href="https://github.com/tmm1/stackprof" />
                  ),
                  code: <code />,
                }
              )
            : undefined,
          language: 'ruby',
          code: getInstallSnippet(params),
        },
        {
          description: t('After adding the gems, run the following to install the SDK:'),
          language: 'ruby',
          code: 'bundle install',
        },
      ],
    },
  ],
  configure: params => [
    {
      type: StepType.CONFIGURE,
      description: tct(
        'To use Sentry Ruby all you need is your DSN. Like most Sentry libraries it will honor the [code:SENTRY_DSN] environment variable. You can find it on the project settings page under API Keys. You can either export it as environment variable or manually configure it with [code:Sentry.init]:',
        {code: <code />}
      ),
      configurations: [
        {
          language: 'ruby',
          code: getConfigureSnippet(params),
        },
      ],
    },
  ],
  verify: () => [
    {
      type: StepType.VERIFY,
      description: t(
        "This snippet contains a deliberate error and message sent to Sentry and can be used as a test to make sure that everything's working as expected."
      ),
      configurations: [
        {
          language: 'ruby',
          code: getVerifySnippet(),
        },
      ],
    },
  ],
};

const docs: Docs = {
  onboarding,
  crashReportOnboarding: CrashReportWebApiOnboarding,
  profilingOnboarding: getRubyProfilingOnboarding(),
};

export default docs;
