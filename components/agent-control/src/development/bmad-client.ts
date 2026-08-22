import { execFile, spawn } from 'node:child_process';
import { mkdir, open, readdir, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { promisify } from 'node:util';
import type { DevelopmentConfig } from '../config.ts';
import { sleep } from '../shared/time.ts';
import { findNewRun, liveRuns, recoverableRuns, statusArguments } from './runs.ts';
import type { BmadRun, BmadRunList, BmadTask, DevelopmentScope } from './types.ts';

const execFileAsync = promisify(execFile);

export class BmadClient {
  private launchQueue: Promise<void> = Promise.resolve();

  constructor(private readonly config: DevelopmentConfig) {}

  async listRuns(): Promise<BmadRunList> {
    const { stdout } = await execFileAsync(
      this.config.bmadLoopBin,
      ['list', '--json'],
      {
        cwd: this.config.projectPath,
        timeout: 15_000,
      },
    );
    return JSON.parse(stdout) as BmadRunList;
  }

  async getStatus(runId?: string): Promise<BmadRun> {
    const { stdout } = await execFileAsync(
      this.config.bmadLoopBin,
      statusArguments(runId),
      { cwd: this.config.projectPath, timeout: 15_000 },
    );
    return JSON.parse(stdout) as BmadRun;
  }

  getCurrentTask(run: BmadRun): BmadTask | null {
    const tasks = run.tasks ?? [];
    return (
      tasks.find((task) =>
        ['dev-running', 'review-running', 'triage-running'].includes(task.phase),
      ) ??
      tasks.find((task) => !['done', 'deferred'].includes(task.phase)) ??
      [...tasks].reverse().find((task) => task.phase === 'done') ??
      tasks.at(-1) ??
      null
    );
  }

  async findCurrentLog(run: BmadRun) {
    const logsDir = join(
      this.config.projectPath,
      '.bmad-loop',
      'runs',
      run.run_id,
      'logs',
    );
    let files: string[];
    try {
      files = (await readdir(logsDir)).filter((name) => name.endsWith('.log'));
    } catch {
      return null;
    }
    if (files.length === 0) return null;

    const task = this.getCurrentTask(run);
    let candidates = files;
    if (task?.story_key) {
      const matching = candidates.filter((name) =>
        name.startsWith(`${task.story_key}-`),
      );
      if (matching.length > 0) candidates = matching;
    }

    const preferredStage = task?.phase.startsWith('review')
      ? 'review'
      : task?.phase.startsWith('dev')
        ? 'dev'
        : null;
    if (preferredStage) {
      const matching = candidates.filter((name) =>
        name.includes(`-${preferredStage}-`),
      );
      if (matching.length > 0) candidates = matching;
    }

    const entries = await Promise.all(
      candidates.map(async (name) => {
        const path = join(logsDir, name);
        return { name, path, mtimeMs: (await stat(path)).mtimeMs };
      }),
    );
    entries.sort((left, right) => right.mtimeMs - left.mtimeMs);
    return entries[0] ?? null;
  }

  async startRun(args: string[], scope: DevelopmentScope) {
    return this.withLaunchLock(async () => {
      const before = await this.listRuns();
      const activeRuns = liveRuns(before.runs ?? []);
      const recoverable = recoverableRuns(
        before.runs ?? [],
        scope.scope === 'story' ? scope.story : undefined,
      );
      if (recoverable.length > 0) {
        return {
          started: false,
          reason: 'recoverable-run-exists',
          ...scope,
          recoverable_runs: recoverable.map((run) => run.run_id),
        };
      }
      const child = await this.spawnDetached(
        ['run', ...args],
        `bmad-${this.timestamp()}.log`,
      );
      let detectedRun: BmadRun | undefined;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await sleep(500);
        const current = await this.listRuns();
        detectedRun = findNewRun(before.runs ?? [], current.runs ?? []);
        if (detectedRun) break;
      }

      return {
        started: true,
        ...scope,
        pid: child.pid,
        run_id: detectedRun?.run_id ?? null,
        run_id_pending: !detectedRun,
        engine_log: child.engineLogPath,
        parallel_with: activeRuns.map((run) => run.run_id),
      };
    });
  }

  resumeRun(runId: string) {
    return this.spawnDetached(['resume', runId], `bmad-resume-${this.timestamp()}.log`);
  }

  execute(args: string[], timeout: number) {
    return execFileAsync(this.config.bmadLoopBin, args, {
      cwd: this.config.projectPath,
      timeout,
    });
  }

  private async spawnDetached(args: string[], logName: string) {
    await mkdir(this.config.logDir, { recursive: true });
    const engineLogPath = join(this.config.logDir, logName);
    const engineLog = await open(engineLogPath, 'a');
    const child = spawn(this.config.bmadLoopBin, args, {
      cwd: this.config.projectPath,
      detached: true,
      stdio: ['ignore', engineLog.fd, engineLog.fd],
      env: { ...process.env, PATH: this.config.path },
    });
    child.unref();
    await engineLog.close();
    return { pid: child.pid, engineLogPath };
  }

  private timestamp() {
    return new Date().toISOString().replace(/[:.]/g, '-');
  }

  private async withLaunchLock<T>(operation: () => Promise<T>): Promise<T> {
    const previous = this.launchQueue;
    let release!: () => void;
    this.launchQueue = new Promise<void>((resolve) => {
      release = resolve;
    });

    await previous;
    try {
      return await operation();
    } finally {
      release();
    }
  }
}
