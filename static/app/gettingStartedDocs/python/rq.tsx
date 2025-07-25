import {Fragment} from 'react';

import {ExternalLink} from 'sentry/components/core/link';
import type {
  Docs,
  DocsParams,
  OnboardingConfig,
} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/types';
import {
  agentMonitoringOnboarding,
  AlternativeConfiguration,
  crashReportOnboardingPython,
} from 'sentry/gettingStartedDocs/python/python';
import {t, tct} from 'sentry/locale';
import {
  getPythonInstallConfig,
  getPythonProfilingOnboarding,
} from 'sentry/utils/gettingStartedDocs/python';

type Params = DocsParams;

const getInitCallSnippet = (params: Params) => `
sentry_sdk.init(
  dsn="${params.dsn.public}",
  # Add data like request headers and IP for users,
  # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
  send_default_pii=True,${
    params.isPerformanceSelected
      ? `
  # Set traces_sample_rate to 1.0 to capture 100%
  # of transactions for tracing.
  traces_sample_rate=1.0,`
      : ''
  }${
    params.isProfilingSelected &&
    params.profilingOptions?.defaultProfilingMode !== 'continuous'
      ? `
  # Set profiles_sample_rate to 1.0 to profile 100%
  # of sampled transactions.
  # We recommend adjusting this value in production.
  profiles_sample_rate=1.0,`
      : params.isProfilingSelected &&
          params.profilingOptions?.defaultProfilingMode === 'continuous'
        ? `
  # Set profile_session_sample_rate to 1.0 to profile 100%
  # of profile sessions.
  profile_session_sample_rate=1.0,
  # Set profile_lifecycle to "trace" to automatically
  # run the profiler on when there is an active transaction
  profile_lifecycle="trace",`
        : ''
  }
)
`;

const getSdkSetupSnippet = (params: Params) => `
import sentry_sdk

${getInitCallSnippet(params)}`;

const getStartWorkerSnippet = () => `
rq worker \
-c mysettings \  # module name of mysettings.py
--sentry-dsn="..."  # only necessary for RQ < 1.0`;

const getJobDefinitionSnippet = () => `
def hello(name):
    1/0  # raises an error
    return "Hello %s!" % name`;

const getWorkerSetupSnippet = (params: Params) => `
import sentry_sdk

# Sentry configuration for RQ worker processes
${getInitCallSnippet(params)}`;

const getMainPythonScriptSetupSnippet = (params: Params) => `
from redis import Redis
from rq import Queue

from jobs import hello

import sentry_sdk

#import { get } from 'lodash';
Sentry configuration for main.py process (same as above)
${getInitCallSnippet(params)}

q = Queue(connection=Redis())
with sentry_sdk.start_transaction(name="testing_sentry"):
    result = q.enqueue(hello, "World")`;

const onboarding: OnboardingConfig = {
  introduction: () =>
    tct('The RQ integration adds support for the [link:RQ Job Queue System].', {
      link: <ExternalLink href="https://python-rq.org/" />,
    }),
  install: () => [
    {
      type: StepType.INSTALL,
      description: tct('Install [code:sentry-sdk] from PyPI with the [code:rq] extra:', {
        code: <code />,
      }),
      configurations: getPythonInstallConfig({packageName: 'sentry-sdk[rq]'}),
    },
  ],
  configure: (params: Params) => [
    {
      type: StepType.CONFIGURE,
      description: (
        <Fragment>
          <p>
            {tct(
              'If you have the [codeRq:rq] package in your dependencies, the RQ integration will be enabled automatically when you initialize the Sentry SDK.',
              {
                codeRq: <code />,
              }
            )}
          </p>
          <p>
            {tct(
              'Create a file called [code:mysettings.py] with the following content:',
              {
                code: <code />,
              }
            )}
          </p>
        </Fragment>
      ),
      configurations: [
        {
          code: [
            {
              label: 'mysettings.py',
              value: 'mysettings.py',
              language: 'python',
              code: getSdkSetupSnippet(params),
            },
          ],
        },
        {
          description: t('Start your worker with:'),
          language: 'shell',
          code: getStartWorkerSnippet(),
        },
      ],
      additionalInfo: (
        <Fragment>
          {tct(
            'Generally, make sure that the call to [code:init] is loaded on worker startup, and not only in the module where your jobs are defined. Otherwise, the initialization happens too late and events might end up not being reported.',
            {code: <code />}
          )}
          {params.isProfilingSelected &&
            params.profilingOptions?.defaultProfilingMode === 'continuous' && (
              <Fragment>
                <br />
                <AlternativeConfiguration />
              </Fragment>
            )}
        </Fragment>
      ),
    },
  ],
  verify: params => [
    {
      type: StepType.VERIFY,
      description: tct(
        'To verify, create a simple job and a [code:main.py] script that enqueues the job in RQ, then start an RQ worker to run the job:',
        {
          code: <code />,
        }
      ),
      configurations: [
        {
          description: <h5>{t('Job definition')}</h5>,
          code: [
            {
              language: 'python',
              label: 'jobs.py',
              value: 'jobs.py',
              code: getJobDefinitionSnippet(),
            },
          ],
        },
        {
          description: <h5>{t('Settings for worker')}</h5>,
          code: [
            {
              label: 'mysettings.py',
              value: 'mysettings.py',
              language: 'python',
              code: getWorkerSetupSnippet(params),
            },
          ],
        },
        {
          description: <h5>{t('Main Python Script')}</h5>,
          code: [
            {
              label: 'main.py',
              value: 'main.py',
              language: 'python',
              code: getMainPythonScriptSetupSnippet(params),
            },
          ],
        },
      ],
      additionalInfo: (
        <div>
          <p>
            {tct(
              'When you run [code:python main.py] a transaction named [code:testing_sentry] in the Performance section of Sentry will be created.',
              {
                code: <code />,
              }
            )}
          </p>
          <p>
            {tct(
              'If you run the RQ worker with [code:rq worker -c mysettings] a transaction for the execution of [code:hello()] will be created. Additionally, an error event will be sent to Sentry and will be connected to the transaction.',
              {
                code: <code />,
              }
            )}
          </p>
          <p>{t('It takes a couple of moments for the data to appear in Sentry.')}</p>
        </div>
      ),
    },
  ],
};

const docs: Docs = {
  onboarding,
  profilingOnboarding: getPythonProfilingOnboarding({basePackage: 'sentry-sdk[rq]'}),
  crashReportOnboarding: crashReportOnboardingPython,
  agentMonitoringOnboarding,
};

export default docs;
