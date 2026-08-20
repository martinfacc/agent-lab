import assert from 'node:assert/strict';
import { delimiter, isAbsolute, join, resolve } from 'node:path';
import test from 'node:test';
import { loadConfig } from '../src/config.ts';

void test('requiere la ruta del proyecto de desarrollo', () => {
  assert.throws(() => loadConfig({}), /AGENT_CONTROL_PROJECT_PATH/);
});

void test('crea valores portables sin rutas específicas de una VM', () => {
  const projectPath = join('fixtures', 'project');
  const config = loadConfig({
    AGENT_CONTROL_PROJECT_PATH: projectPath,
    PATH: 'existing-path',
  });

  assert.equal(config.development.projectPath, resolve(projectPath));
  assert.equal(config.researchEnabled, true);
  assert.equal(config.development.bmadLoopBin, 'bmad-loop');
  assert.equal(config.research.primeAgentBin, 'prime-agent');
  assert.equal(config.research.defaultTokenBudget, 100_000);
  assert.ok(isAbsolute(config.development.logDir));
  assert.ok(isAbsolute(config.research.runsDir));
});

void test('permite desactivar las herramientas de investigación', () => {
  const config = loadConfig({
    AGENT_CONTROL_PROJECT_PATH: 'project',
    LAB_MODE: 'development',
  });

  assert.equal(config.researchEnabled, false);
});

void test('acepta una ubicación personalizada para sprint-status', () => {
  const config = loadConfig({
    AGENT_CONTROL_PROJECT_PATH: 'project',
    BMAD_SPRINT_STATUS_PATH: 'docs/bmad/development/sprint-status.yaml',
  });

  assert.equal(
    config.development.sprintStatusPath,
    resolve('project', 'docs/bmad/development/sprint-status.yaml'),
  );
});

void test('acepta personalizar ejecutables, almacenamiento e investigación', () => {
  const config = loadConfig({
    AGENT_CONTROL_PROJECT_PATH: 'project',
    AGENT_CONTROL_DATA_DIR: 'runtime-data',
    AGENT_CONTROL_LOCAL_BIN: 'tools',
    BMAD_LOOP_BIN: 'custom-bmad',
    PRIME_AGENT_BIN: 'custom-prime',
    RESEARCH_PROVIDER: 'provider',
    RESEARCH_MODEL: 'model',
    RESEARCH_TOKEN_BUDGET: '25000',
    PATH: 'existing-path',
  });

  assert.equal(config.development.bmadLoopBin, 'custom-bmad');
  assert.equal(config.research.primeAgentBin, 'custom-prime');
  assert.equal(config.research.provider, 'provider');
  assert.equal(config.research.model, 'model');
  assert.equal(config.research.defaultTokenBudget, 25_000);
  assert.equal(config.development.path, `${resolve('tools')}${delimiter}existing-path`);
});
