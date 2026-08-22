import type { BmadRun } from './types.ts';

const liveStatuses = new Set(['running', 'in-progress']);

export function statusArguments(runId?: string): string[] {
  return runId ? ['status', runId, '--json'] : ['status', '--json'];
}

export function liveRuns(runs: BmadRun[]): BmadRun[] {
  return runs.filter((run) => liveStatuses.has(run.status));
}

export function recoverableRuns(runs: BmadRun[], story?: string): BmadRun[] {
  return runs.filter((run) => {
    if (!['stopped', 'interrupted'].includes(run.status)) return false;
    return (run.tasks ?? []).some(
      (task) => task.phase.endsWith('running') && (!story || task.story_key === story),
    );
  });
}

export function findNewRun(
  previousRuns: BmadRun[],
  currentRuns: BmadRun[],
): BmadRun | undefined {
  const previousIds = new Set(previousRuns.map((run) => run.run_id));
  return currentRuns.find((run) => !previousIds.has(run.run_id));
}
