import type {EntryException} from 'sentry/types/event';
import {EntryType} from 'sentry/types/event';

/**
 * Exception group chained exceptions
 */
export function EventEntryExceptionGroupFixture(): EntryException {
  return {
    type: EntryType.EXCEPTION,
    data: {
      excOmitted: null,
      hasSystemFrames: false,
      values: [
        {
          type: 'ValueError',
          value: 'test',
          mechanism: {
            handled: true,
            type: '',
            exception_id: 4,
            is_exception_group: false,
            parent_id: 3,
            source: 'exceptions[2]',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func4',
                module: 'helpers',
                filename: 'file4.py',
                absPath: 'file4.py',
                lineNo: 50,
                colNo: null,
                context: [[50, 'raise ValueError("test")']],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          threadId: null,
          rawStacktrace: null,
        },
        {
          type: 'ExceptionGroup 2',
          value: 'child',
          mechanism: {
            handled: true,
            type: '',
            exception_id: 3,
            is_exception_group: true,
            parent_id: 1,
            source: 'exceptions[1]',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func3',
                module: 'helpers',
                filename: 'file3.py',
                absPath: 'file3.py',
                lineNo: 50,
                colNo: null,
                context: [],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          rawStacktrace: null,
          threadId: null,
        },
        {
          type: 'TypeError',
          value: 'nested',
          mechanism: {
            handled: true,
            type: '',
            exception_id: 2,
            is_exception_group: false,
            parent_id: 1,
            source: 'exceptions[0]',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func2',
                module: 'helpers',
                filename: 'file2.py',
                absPath: 'file2.py',
                lineNo: 50,
                colNo: null,
                context: [[50, 'raise TypeError("int")']],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          threadId: null,
          rawStacktrace: null,
        },
        {
          type: 'ExceptionGroup 1',
          value: 'parent',
          mechanism: {
            handled: true,
            type: '',
            exception_id: 1,
            is_exception_group: true,
            source: '__context__',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func1',
                module: 'helpers',
                filename: 'file1.py',
                absPath: 'file1.py',
                lineNo: 50,
                colNo: null,
                context: [[50, 'raise ExceptionGroup("parent")']],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          threadId: null,
          rawStacktrace: null,
        },
      ],
    },
  };
}

/**
 * Non-exception group chained exceptions
 */
export function EventEntryChainedExceptionFixture(): EntryException {
  return {
    type: EntryType.EXCEPTION,
    data: {
      excOmitted: null,
      hasSystemFrames: false,
      values: [
        {
          type: 'ValueError',
          value: 'test',
          mechanism: {
            handled: true,
            type: '',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func4',
                module: 'helpers',
                filename: 'file4.py',
                absPath: 'file4.py',
                lineNo: 50,
                colNo: null,
                context: [[50, 'raise ValueError("test")']],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          threadId: null,
          rawStacktrace: null,
        },
        {
          type: 'TypeError',
          value: 'nested',
          mechanism: {
            handled: true,
            type: '',
          },
          stacktrace: {
            framesOmitted: null,
            hasSystemFrames: false,
            registers: null,
            frames: [
              {
                function: 'func2',
                module: 'helpers',
                filename: 'file2.py',
                absPath: 'file2.py',
                lineNo: 50,
                colNo: null,
                context: [[50, 'raise TypeError("int")']],
                inApp: true,
                rawFunction: null,
                package: null,
                platform: null,
                instructionAddr: null,
                symbol: null,
                symbolAddr: null,
                trust: null,
                vars: null,
              },
            ],
          },
          module: 'helpers',
          threadId: null,
          rawStacktrace: null,
        },
      ],
    },
  };
}
