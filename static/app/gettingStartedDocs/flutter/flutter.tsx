import {Fragment} from 'react';

import {Alert} from 'sentry/components/core/alert';
import {ExternalLink} from 'sentry/components/core/link';
import List from 'sentry/components/list';
import ListItem from 'sentry/components/list/listItem';
import type {
  BasePlatformOptions,
  Docs,
  DocsParams,
  OnboardingConfig,
} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {
  getReplayMobileConfigureDescription,
  getReplayVerifyStep,
} from 'sentry/components/onboarding/gettingStartedDoc/utils/replayOnboarding';
import {feedbackOnboardingCrashApiDart} from 'sentry/gettingStartedDocs/dart/dart';
import {t, tct} from 'sentry/locale';
import {getPackageVersion} from 'sentry/utils/gettingStartedDocs/getPackageVersion';
import {getWizardInstallSnippet} from 'sentry/utils/gettingStartedDocs/mobileWizard';

export enum InstallationMode {
  AUTO = 'auto',
  MANUAL = 'manual',
}

const platformOptions = {
  installationMode: {
    label: t('Installation Mode'),
    items: [
      {
        label: t('Auto'),
        value: InstallationMode.AUTO,
      },
      {
        label: t('Manual'),
        value: InstallationMode.MANUAL,
      },
    ],
    defaultValue: InstallationMode.AUTO,
  },
} satisfies BasePlatformOptions;

type PlatformOptions = typeof platformOptions;
type Params = DocsParams<PlatformOptions>;

const isAutoInstall = (params: Params) =>
  params.platformOptions?.installationMode === InstallationMode.AUTO;

const getManualInstallSnippet = (params: Params) => {
  const version = getPackageVersion(params, 'sentry.dart.flutter', '8.13.2');
  return `dependencies:
  sentry_flutter: ^${version}`;
};

const getConfigureSnippet = (params: Params) => `
import 'package:sentry_flutter/sentry_flutter.dart';

Future<void> main() async {
  await SentryFlutter.init(
    (options) {
      options.dsn = '${params.dsn.public}';
      // Adds request headers and IP for users,
      // visit: https://docs.sentry.io/platforms/dart/data-management/data-collected/ for more info
      options.sendDefaultPii = true;${
        params.isPerformanceSelected
          ? `
      // Set tracesSampleRate to 1.0 to capture 100% of transactions for tracing.
      // We recommend adjusting this value in production.
      options.tracesSampleRate = 1.0;`
          : ''
      }${
        params.isProfilingSelected
          ? `
      // The sampling rate for profiling is relative to tracesSampleRate
      // Setting to 1.0 will profile 100% of sampled transactions:
      options.profilesSampleRate = 1.0;`
          : ''
      }${
        params.isReplaySelected
          ? `
      // Set sessionSampleRate to 0.1 to capture 10% of sessions and onErrorSampleRate to 1.0 to capture 100% of errors.
      options.replay.sessionSampleRate = 0.1;
      options.replay.onErrorSampleRate = 1.0;`
          : ''
      }${
        params.isLogsSelected
          ? `
      // Enable logs to be sent to Sentry
      options.enableLogs = true;`
          : ''
      }
    },
    appRunner: () => runApp(
      SentryWidget(
        child: MyApp(),
      ),
    ),
  );

  // or define SENTRY_DSN via Dart environment variable (--dart-define)
}`;

const configureAdditionalInfo = tct(
  'You can configure the [code: SENTRY_DSN], [code: SENTRY_RELEASE], [code: SENTRY_DIST], and [code: SENTRY_ENVIRONMENT] via the Dart environment variables passing the [code: --dart-define] flag to the compiler, as noted in the code sample.',
  {
    code: <code />,
  }
);

const getVerifySnippet = () => `
child: ElevatedButton(
  onPressed: () {
    throw StateError('This is test exception');
  },
  child: const Text('Verify Sentry Setup'),
)
`;

const getFeedbackConfigureSnippet = () => `
// The example uses the NavigatorState to present the widget. Adapt as needed to your navigation stack.
final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

...

await SentryFlutter.init((options) {
  options.beforeSend = (event, hint) async {
    // Filter here what kind of events you want users to give you feedback.

    final screenshot = await SentryFlutter.captureScreenshot();
    final context = navigatorKey.currentContext;
    if (context == null) return;
    if (context.mounted) {
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => SentryFeedbackWidget(
            associatedEventId: event.eventId,
            screenshot: screenshot,
          ),
          fullscreenDialog: true,
        ),
      );
    }
  };
});
`;

const getPerformanceSnippet = () => `
import 'package:sentry/sentry.dart';

void execute() async {
  final transaction = Sentry.startTransaction('processOrderBatch()', 'task');

  try {
    await processOrderBatch(transaction);
  } catch (exception) {
    transaction.throwable = exception;
    transaction.status = const SpanStatus.internalError();
  } finally {
    await transaction.finish();
  }
}

Future<void> processOrderBatch(ISentrySpan span) async {
  // span operation: task, span description: operation
  final innerSpan = span.startChild('task', description: 'operation');

  try {
    // omitted code
  } catch (exception) {
    innerSpan.throwable = exception;
    innerSpan.status = const SpanStatus.notFound();
  } finally {
    await innerSpan.finish();
  }
}`;

const getInstallReplaySnippet = () => `
await SentryFlutter.init(
  (options) {
    ...
    options.replay.sessionSampleRate = 1.0;
    options.replay.onErrorSampleRate = 1.0;
  },
  appRunner: () => runApp(
      SentryWidget(
        child: MyApp(),
      ),
    ),
);
`;

const getConfigureReplaySnippet = () => `
options.replay.maskAllText = true;
options.replay.maskAllImages = true;`;

const onboarding: OnboardingConfig<PlatformOptions> = {
  install: params =>
    isAutoInstall(params)
      ? [
          {
            type: StepType.INSTALL,
            description: tct(
              'Add Sentry automatically to your app with the [wizardLink:Sentry wizard] (call this inside your project directory).',
              {
                wizardLink: (
                  <ExternalLink href="https://docs.sentry.io/platforms/flutter/#install" />
                ),
              }
            ),
            configurations: [
              {
                code: getWizardInstallSnippet({
                  platform: 'flutter',
                  params,
                }),
              },
              {
                description: (
                  <Fragment>
                    <p>
                      {t(
                        'The Sentry wizard will automatically patch your project with the following:'
                      )}
                    </p>
                    <List symbol="bullet">
                      <ListItem>
                        {tct(
                          'Configure the SDK with your DSN and performance monitoring options in your [main:main.dart] file.',
                          {
                            main: <code />,
                          }
                        )}
                      </ListItem>
                      <ListItem>
                        {tct(
                          'Update your [pubspec:pubspec.yaml] with the Sentry package',
                          {
                            pubspec: <code />,
                          }
                        )}
                      </ListItem>
                      <ListItem>
                        {t('Add an example error to verify your setup')}
                      </ListItem>
                    </List>
                  </Fragment>
                ),
              },
            ],
          },
        ]
      : [
          {
            type: StepType.INSTALL,
            description: tct(
              'Sentry captures data by using an SDK within your application. Add the following to your [pubspec:pubspec.yaml]',
              {
                pubspec: <code />,
              }
            ),
            configurations: [
              {
                code: [
                  {
                    label: 'YAML',
                    value: 'yaml',
                    language: 'yaml',
                    filename: 'pubspec.yaml',
                    partialLoading: params.sourcePackageRegistries?.isLoading,
                    code: getManualInstallSnippet(params),
                  },
                ],
              },
            ],
          },
        ],
  configure: params =>
    isAutoInstall(params)
      ? []
      : [
          {
            type: StepType.CONFIGURE,
            description: tct(
              'Import [sentryFlutter: sentry_flutter] and initialize it in your [main:main.dart]',
              {
                sentryFlutter: <code />,
                main: <code />,
              }
            ),
            configurations: [
              ...(params.isProfilingSelected
                ? [
                    {
                      description: t(
                        'Flutter Profiling alpha is available for iOS and macOS since SDK version 7.12.0.'
                      ),
                    },
                  ]
                : []),
              {
                code: [
                  {
                    label: 'Dart',
                    value: 'dart',
                    language: 'dart',
                    filename: 'main.dart',
                    code: getConfigureSnippet(params),
                  },
                ],
                additionalInfo: params.isPerformanceSelected ? (
                  <Fragment>
                    <p>{configureAdditionalInfo}</p>
                    <Alert type="info" showIcon={false}>
                      {t(
                        'To monitor performance, you need to add extra instrumentation as described in the Tracing section below.'
                      )}
                    </Alert>
                  </Fragment>
                ) : (
                  configureAdditionalInfo
                ),
              },
            ],
          },
        ],
  verify: params =>
    isAutoInstall(params)
      ? []
      : [
          {
            type: StepType.VERIFY,
            description: t(
              'Create an intentional error, so you can test that everything is working. In the example below, pressing the button will throw an exception:'
            ),
            configurations: [
              {
                code: [
                  {
                    label: 'Dart',
                    value: 'dart',
                    language: 'dart',
                    code: getVerifySnippet(),
                  },
                ],
              },
            ],
          },
          ...(params.isPerformanceSelected
            ? [
                {
                  title: t('Tracing'),
                  description: t(
                    "You'll be able to monitor the performance of your app using the SDK. For example:"
                  ),
                  configurations: [
                    {
                      code: [
                        {
                          label: 'Dart',
                          value: 'dart',
                          language: 'dart',
                          code: getPerformanceSnippet(),
                        },
                      ],
                      additionalInfo: tct(
                        'To learn more about the API and automatic instrumentations, check out the [perfDocs: tracing documentation].',
                        {
                          perfDocs: (
                            <ExternalLink href="https://docs.sentry.io/platforms/flutter/tracing/instrumentation/" />
                          ),
                        }
                      ),
                    },
                  ],
                },
              ]
            : []),
        ],
  nextSteps: params => {
    const steps = [
      {
        name: t('Upload Debug Symbols'),
        description: t(
          'We offer a range of methods to provide Sentry with debug symbols so that you can see symbolicated stack traces and find the cause of your errors faster.'
        ),
        link: 'https://docs.sentry.io/platforms/flutter/upload-debug/',
      },
      {
        name: t('Distributed Tracing'),
        description: t(
          'Connect all your services by configuring your endpoints in the Sentry init.'
        ),
        link: 'https://docs.sentry.io/platforms/flutter/tracing/trace-propagation/limiting-trace-propagation/',
      },
      {
        name: t('Connect your Git Repo'),
        description: t(
          'Adding our Git integrations will allow us determine suspect commits, comment on PRs, and create links directly to your source code from Sentry issues.'
        ),
        link: 'https://docs.sentry.io/organization/integrations/source-code-mgmt/',
      },
    ];

    if (params.isLogsSelected) {
      steps.push({
        name: t('Structured Logs'),
        description: t(
          'Learn how to send structured logs to Sentry and view them alongside your errors.'
        ),
        link: 'https://docs.sentry.io/platforms/dart/guides/flutter/logs/',
      });
    }

    return steps;
  },
};

const replayOnboarding: OnboardingConfig<PlatformOptions> = {
  install: params => [
    {
      type: StepType.INSTALL,
      description: tct(
        'Make sure your Sentry Flutter SDK version is at least 8.9.0, which is required for Session Replay. You can update your [code:pubspec.yaml] to the matching version:',
        {code: <code />}
      ),
      configurations: [
        {
          code: [
            {
              label: 'YAML',
              value: 'yaml',
              language: 'yaml',
              code: getManualInstallSnippet(params),
            },
          ],
        },
        {
          description: t(
            'To set up the integration, add the following to your Sentry initialization:'
          ),
        },
        {
          code: [
            {
              label: 'Dart',
              value: 'dart',
              language: 'dart',
              code: getInstallReplaySnippet(),
            },
          ],
        },
      ],
    },
  ],
  configure: () => [
    {
      type: StepType.CONFIGURE,
      description: getReplayMobileConfigureDescription({
        link: 'https://docs.sentry.io/platforms/flutter/session-replay/#privacy',
      }),
      configurations: [
        {
          description: t(
            'The following code is the default configuration, which masks and blocks everything.'
          ),
          code: [
            {
              label: 'Dart',
              value: 'dart',
              language: 'dart',
              code: getConfigureReplaySnippet(),
            },
          ],
        },
      ],
    },
  ],
  verify: getReplayVerifyStep({
    replayOnErrorSampleRateName: 'options\u200b.replay\u200b.onErrorSampleRate',
    replaySessionSampleRateName: 'options\u200b.replay\u200b.sessionSampleRate',
  }),
  nextSteps: () => [],
};

const feedbackOnboarding: OnboardingConfig<PlatformOptions> = {
  install: () => [
    {
      type: StepType.INSTALL,
      description: tct(
        "Use the [code:SentryFeedbackWidget] to let users send feedback data to Sentry. [break] [break] The widget requests and collects the user's name, email address, and a description of what occurred. When an event identifier is provided, Sentry pairs the feedback with the original event, giving you additional insights into issues. Additionally, you can provide a screenshot that will be sent to Sentry. Learn more about how to enable screenshots in our [screenshotsDocs:screenshots documentation].",
        {
          screenshotsDocs: (
            <ExternalLink href="https://docs.sentry.io/platforms/dart/guides/flutter/enriching-events/screenshots/" />
          ),
          break: <br />,
          code: <code />,
        }
      ),
      configurations: [
        {
          description: tct(
            'One possible use for the [code:SentryFeedbackWidget] is to listen for specific Sentry events in the [code:beforeSend] callback and show the widget to users.',
            {
              code: <code />,
            }
          ),
          configurations: [
            {
              code: [
                {
                  label: 'Dart',
                  value: 'dart',
                  language: 'dart',
                  code: getFeedbackConfigureSnippet(),
                },
              ],
            },
          ],
        },
      ],
    },
  ],
  configure: () => [],
  verify: () => [],
  nextSteps: () => [],
};

const docs: Docs<PlatformOptions> = {
  onboarding,
  feedbackOnboardingNpm: feedbackOnboarding,
  crashReportOnboarding: feedbackOnboardingCrashApiDart,
  platformOptions,
  replayOnboarding,
};

export default docs;
