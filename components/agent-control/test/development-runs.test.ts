import assert from 'node:assert/strict';
import test from 'node:test';
import { findNewRun, liveRuns, statusArguments } from '../src/development/runs.ts';
import type { BmadRun } from '../src/development/types.ts';

const run = (runId: string, status: string): BmadRun => ({
  run_id: runId,
  status,
});

void test('consulta una ejecución específica al solicitar estado', () => {
  assert.deepEqual(statusArguments(), ['status', '--json']);
  assert.deepEqual(statusArguments('run-b'), ['status', 'run-b', '--json']);
});

void test('reconoce nombres actuales y heredados de estados activos', () => {
  const runs = [
    run('current', 'running'),
    run('legacy', 'in-progress'),
    run('paused', 'paused'),
    run('finished', 'finished'),
  ];

  assert.deepEqual(
    liveRuns(runs).map((item) => item.run_id),
    ['current', 'legacy'],
  );
});

void test('identifica la ejecución creada por un inicio serializado', () => {
  const previous = [run('run-a', 'running')];
  const current = [...previous, run('run-b', 'running')];

  assert.equal(findNewRun(previous, current)?.run_id, 'run-b');
});
