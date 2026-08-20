import { execFile, spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { promisify } from 'node:util';
import type { ResearchConfig } from '../config.ts';
import { errorDetails, hasErrorCode } from '../shared/errors.ts';
import { sleep } from '../shared/time.ts';
import type {
  GoalState,
  PrimeHeartbeat,
  PrimeWorkerDescriptor,
  ResearchRun,
  RpcResponse,
} from './types.ts';

const execFileAsync = promisify(execFile);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isRpcResponse(value: unknown): value is RpcResponse {
  return (
    isRecord(value) &&
    value.type === 'response' &&
    typeof value.id === 'string' &&
    typeof value.success === 'boolean'
  );
}

function isResearchRun(value: unknown): value is ResearchRun {
  return (
    isRecord(value) &&
    typeof value.run_id === 'string' &&
    typeof value.objective === 'string' &&
    typeof value.provider === 'string' &&
    typeof value.model === 'string' &&
    typeof value.token_budget === 'number' &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string' &&
    typeof value.cwd === 'string' &&
    typeof value.report_path === 'string' &&
    typeof value.session_file === 'string' &&
    typeof value.session_id === 'string' &&
    typeof value.active_session_id === 'string' &&
    (typeof value.worker_pid === 'number' || value.worker_pid === null) &&
    typeof value.state === 'string'
  );
}

function metadataPath(config: ResearchConfig, runId: string) {
  return `${config.runsDir}/${runId}/run.json`;
}

export async function saveRun(config: ResearchConfig, run: ResearchRun) {
  run.updated_at = new Date().toISOString();

  await writeFile(
    metadataPath(config, run.run_id),
    JSON.stringify(run, null, 2) + '\n',
    'utf8',
  );
}

export async function loadRun(
  config: ResearchConfig,
  runId: string,
): Promise<ResearchRun | null> {
  try {
    const parsed: unknown = JSON.parse(
      await readFile(metadataPath(config, runId), 'utf8'),
    );
    return isResearchRun(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function findWorkerDescriptor(
  config: ResearchConfig,
  activeSessionId: string,
): Promise<PrimeWorkerDescriptor | null> {
  let dirs: string[];

  try {
    dirs = await readdir(config.primeWorkersDir);
  } catch {
    return null;
  }

  for (const dir of dirs) {
    const path = `${config.primeWorkersDir}/${dir}`;

    let files: string[];

    try {
      files = await readdir(path);
    } catch {
      continue;
    }

    for (const file of files) {
      if (!file.endsWith('.json')) {
        continue;
      }

      try {
        const descriptor: unknown = JSON.parse(
          await readFile(`${path}/${file}`, 'utf8'),
        );

        if (
          isRecord(descriptor) &&
          descriptor.rootActiveSessionId === activeSessionId
        ) {
          return {
            rootActiveSessionId: activeSessionId,
            pid:
              typeof descriptor.pid === 'string' || typeof descriptor.pid === 'number'
                ? descriptor.pid
                : undefined,
            descriptor_path: `${path}/${file}`,
          };
        }
      } catch {
        // Ignore stale or partially-written descriptors.
      }
    }
  }

  return null;
}

async function waitForWorkerPid(config: ResearchConfig, activeSessionId: string) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const descriptor = await findWorkerDescriptor(config, activeSessionId);

    if (descriptor?.pid) {
      return Number(descriptor.pid);
    }

    await sleep(100);
  }

  return null;
}

function latestGoalState(sessionText: string): GoalState | null {
  const lines = sessionText.split(/\r?\n/).filter(Boolean).reverse();

  for (const line of lines) {
    try {
      const item: unknown = JSON.parse(line);

      if (
        isRecord(item) &&
        item.type === 'custom' &&
        item.customType === 'thread_goal_state' &&
        isRecord(item.data)
      ) {
        return {
          ...item.data,
          timestamp: typeof item.timestamp === 'string' ? item.timestamp : null,
        };
      }
    } catch {
      // Ignore malformed/incomplete lines.
    }
  }

  return null;
}

export async function getGoalState(run: ResearchRun) {
  try {
    const text = await readFile(run.session_file, 'utf8');
    return latestGoalState(text);
  } catch {
    return null;
  }
}

export async function stopPrimeWorker(
  config: ResearchConfig,
  activeSessionId: string,
  workerPid: number | null,
) {
  let officialStop: boolean;
  let stdout: string;
  let stderr: string;

  try {
    const result = await execFileAsync(
      config.primeAgentBin,
      ['stop', activeSessionId, '--json'],
      {
        timeout: 15_000,
      },
    );

    stdout = result.stdout;
    stderr = result.stderr;

    try {
      const parsed: unknown = JSON.parse(stdout);

      officialStop =
        isRecord(parsed) && parsed.success === true && parsed.command === 'kill';
    } catch {
      officialStop = stdout.includes('"success": true');
    }
  } catch (error: unknown) {
    const details = errorDetails(error);
    stdout = details.stdout ?? '';
    stderr = details.stderr ?? details.message;

    // Prime 0.7.3 can emit EPIPE while the daemon still
    // successfully completes the kill.
    officialStop =
      stdout.includes('"command": "kill"') && stdout.includes('"success": true');
  }

  if (workerPid) {
    try {
      process.kill(-workerPid, 'SIGTERM');
    } catch (error: unknown) {
      if (!hasErrorCode(error, 'ESRCH')) {
        throw error;
      }
    }

    await sleep(300);

    try {
      process.kill(-workerPid, 0);
      process.kill(-workerPid, 'SIGKILL');
    } catch (error: unknown) {
      if (!hasErrorCode(error, 'ESRCH')) {
        throw error;
      }
    }
  }

  return {
    official_stop: officialStop,
    stdout: stdout.trim() || null,
    stderr: stderr.trim() || null,
  };
}

export async function cleanupTerminalWorker(config: ResearchConfig, run: ResearchRun) {
  const descriptor = await findWorkerDescriptor(config, run.active_session_id);

  if (!descriptor) {
    return {
      cleaned: false,
      reason: 'worker-not-running',
    };
  }

  const workerPid = Number(descriptor.pid) || run.worker_pid || null;

  const result = await stopPrimeWorker(config, run.active_session_id, workerPid);

  return {
    cleaned: true,
    worker_pid: workerPid,
    ...result,
  };
}

export async function startRpcResearch(
  config: ResearchConfig,
  objective: string,
  tokenBudget: number,
  parentRunId?: string,
) {
  const runId = randomUUID();
  const cwd = `${config.runsDir}/${runId}`;
  const reportPath = `${cwd}/report.md`;

  await mkdir(cwd, { recursive: true });

  const goal = [
    'Complete the following deep research objective:',
    '',
    objective,
    '',
    'Requirements:',
    '- Research the objective thoroughly and verify important claims.',
    '- Prefer primary and authoritative sources when available.',
    '- Preserve URLs or source references needed to audit the findings.',
    `- Write the final complete report to "${reportPath}".`,
    '- Verify the report file exists and is complete before finishing.',
    '- Call goal.complete() only after the report has been written and verified.',
  ].join('\n');

  const child = spawn(
    config.primeAgentBin,
    [
      '--mode',
      'rpc',
      '--cwd',
      cwd,
      '--provider',
      config.provider,
      '--model',
      config.model,
      '--goal',
      goal,
      '--goal-token-budget',
      String(tokenBudget),
    ],
    {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: process.env,
    },
  );

  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');

  let stdoutBuffer = '';
  let stderrBuffer = '';
  const pending = new Map<
    string,
    {
      resolve: (value: RpcResponse) => void;
      reject: (error: Error) => void;
    }
  >();

  child.stderr.on('data', (chunk) => {
    stderrBuffer += chunk;
  });

  child.stdout.on('data', (chunk) => {
    stdoutBuffer += chunk;

    while (true) {
      const newline = stdoutBuffer.indexOf('\n');

      if (newline === -1) {
        break;
      }

      const line = stdoutBuffer.slice(0, newline);
      stdoutBuffer = stdoutBuffer.slice(newline + 1);

      if (!line.trim()) {
        continue;
      }

      try {
        const message: unknown = JSON.parse(line);

        if (isRpcResponse(message) && pending.has(message.id)) {
          const waiter = pending.get(message.id)!;
          pending.delete(message.id);

          if (message.success) {
            waiter.resolve(message);
          } else {
            waiter.reject(
              new Error(message?.error ?? `RPC command failed: ${message.id}`),
            );
          }
        }
      } catch {
        // Ignore non-JSON diagnostic output.
      }
    }
  });

  const request = (message: Record<string, unknown> & { id: string }) =>
    new Promise<RpcResponse>((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(message.id);

        reject(new Error(`RPC timeout waiting for ${message.id}. ${stderrBuffer}`));
      }, 15_000);

      pending.set(message.id, {
        resolve: (value) => {
          clearTimeout(timeout);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timeout);
          reject(error);
        },
      });

      child.stdin.write(JSON.stringify(message) + '\n', (error) => {
        if (error) {
          clearTimeout(timeout);
          pending.delete(message.id);
          reject(error);
        }
      });
    });

  let heartbeat: PrimeHeartbeat;

  try {
    const heartbeatResponse = await request({
      id: 'bootstrap-heartbeat',
      type: 'set_heartbeat',
      schedule: 'every 1 hour',
      prompt: 'research residency bootstrap',
    });

    const receivedHeartbeat = heartbeatResponse.data?.heartbeat;
    if (!receivedHeartbeat) {
      throw new Error(
        'La respuesta heartbeat de Prime RPC no incluyó datos del heartbeat.',
      );
    }
    heartbeat = receivedHeartbeat;

    await request({
      id: 'bootstrap-clear',
      type: 'update_heartbeat',
      action: 'clear',
    });

    await request({
      id: 'research-start',
      type: 'prompt',
      message: 'Execute the research goal completely.',
    });
  } catch (error) {
    child.kill('SIGTERM');
    throw error;
  }

  const activeSessionId = heartbeat.activeSessionId;

  const workerPid = await waitForWorkerPid(config, activeSessionId);

  const run: ResearchRun = {
    run_id: runId,
    objective,
    provider: config.provider,
    model: config.model,
    token_budget: tokenBudget,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    cwd,
    report_path: reportPath,
    session_file: heartbeat.sessionFile,
    session_id: heartbeat.sessionId,
    active_session_id: activeSessionId,
    worker_pid: workerPid,
    state: 'active',
    parent_run_id: parentRunId ?? null,
  };

  await saveRun(config, run);

  // The session is already promoted to a resident daemon worker,
  // so terminating only the invocation-local RPC client is safe.
  child.kill('SIGTERM');

  return run;
}
