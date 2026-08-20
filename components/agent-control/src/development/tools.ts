import type { McpServer } from '@modelcontextprotocol/server';
import { readFile } from 'node:fs/promises';
import { z } from 'zod';
import type { DevelopmentConfig } from '../config.ts';
import { errorDetails } from '../shared/errors.ts';
import type { TextResult } from '../shared/mcp.ts';
import { sleep } from '../shared/time.ts';
import { BmadClient } from './bmad-client.ts';
import { liveRuns } from './runs.ts';

type TextResponder = (data: unknown) => TextResult;

export function registerDevelopmentTools(
  server: McpServer,
  config: DevelopmentConfig,
  asText: TextResponder,
) {
  const client = new BmadClient(config);

  server.registerTool(
    'dev_runs',
    {
      description:
        'Lista las ejecuciones de desarrollo BMAD para seleccionar un run_id al consultar estado o logs, reanudar o detener.',
      inputSchema: { active_only: z.boolean().optional() },
    },
    async ({ active_only }) => {
      const runs = (await client.listRuns()).runs ?? [];
      const visibleRuns = active_only ? liveRuns(runs) : runs;

      return asText({
        runs: visibleRuns.map((run) => ({
          run_id: run.run_id,
          short_ref: run.short_ref ?? null,
          run_type: run.run_type ?? run.type ?? null,
          status: run.status,
          started_at: run.started_at ?? null,
          paused_stage: run.paused_stage ?? null,
        })),
      });
    },
  );

  server.registerTool(
    'dev_status',
    {
      description:
        'Devuelve el estado de desarrollo BMAD para un run_id, o el de la última ejecución si se omite.',
      inputSchema: { run_id: z.string().min(1).optional() },
    },
    async ({ run_id }) => {
      const run = await client.getStatus(run_id);
      const sprintStatus = await readFile(config.sprintStatusPath, 'utf8');
      const tasks = (run.tasks ?? []).map((task) => {
        const escaped = task.story_key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const match = sprintStatus.match(new RegExp(`^\\s*${escaped}:\\s*(\\S+)`, 'm'));
        return {
          story_key: task.story_key,
          run_phase: task.phase,
          board_status: match?.[1] ?? 'unknown',
          attempt: task.attempt,
          review_cycle: task.review_cycle,
          commit_sha: task.commit_sha,
        };
      });

      return asText({
        run_id: run.run_id,
        run_type: run.run_type,
        status: run.status,
        finished: run.finished,
        paused_stage: run.paused_stage,
        paused_reason: run.paused_reason,
        paused_story_key: run.paused_story_key,
        model: run.adapters?.dev?.model,
        tokens: run.tokens,
        tasks,
      });
    },
  );

  server.registerTool(
    'dev_log',
    {
      description:
        'Devuelve líneas del log de desarrollo o revisión para un run_id, o de la última ejecución si se omite.',
      inputSchema: {
        run_id: z.string().min(1).optional(),
        lines: z.number().int().min(1).max(500).optional(),
      },
    },
    async ({ run_id, lines }) => {
      const run = await client.getStatus(run_id);
      const currentTask = client.getCurrentTask(run);
      const currentLog = await client.findCurrentLog(run);
      if (!currentLog) {
        return asText({
          run_id: run.run_id,
          status: run.status,
          found: false,
          reason: 'no-run-log-found',
        });
      }

      const count = lines ?? 80;
      const tail = (await readFile(currentLog.path, 'utf8'))
        .split(/\r?\n/)
        .slice(-count)
        .join('\n');
      return asText({
        run_id: run.run_id,
        status: run.status,
        finished: run.finished,
        story: currentTask?.story_key ?? null,
        phase: currentTask?.phase ?? null,
        log: currentLog.path,
        lines: count,
        tail,
      });
    },
  );

  server.registerTool(
    'dev_start',
    {
      description: 'Inicia una story de BMAD en segundo plano.',
      inputSchema: { story: z.string().min(1) },
    },
    async ({ story }) =>
      asText(await client.startRun(['--story', story], { scope: 'story', story })),
  );

  server.registerTool(
    'dev_start_epic',
    {
      description: 'Inicia o completa todas las stories BMAD pendientes de una epic.',
      inputSchema: { epic: z.number().int().positive() },
    },
    async ({ epic }) =>
      asText(await client.startRun(['--epic', String(epic)], { scope: 'epic', epic })),
  );

  server.registerTool(
    'dev_start_project',
    {
      description:
        'Inicia el desarrollo BMAD autónomo de todas las stories pendientes del proyecto.',
    },
    async () => asText(await client.startRun([], { scope: 'project' })),
  );

  server.registerTool(
    'dev_resume',
    {
      description:
        'Reanuda una ejecución BMAD pausada después de que el usuario aprueba continuar.',
      inputSchema: { run_id: z.string().min(1) },
    },
    async ({ run_id }) => {
      const runs = await client.listRuns();
      const run = (runs.runs ?? []).find((item) => item.run_id === run_id);
      if (!run) return asText({ resumed: false, reason: 'run-not-found', run_id });
      if (run.status === 'finished') {
        return asText({ resumed: false, reason: 'run-already-finished', run_id });
      }
      if (['in-progress', 'running'].includes(run.status)) {
        return asText({ resumed: false, reason: 'run-already-running', run_id });
      }

      const child = await client.resumeRun(run_id);
      let observedStatus = run.status;
      for (let attempt = 0; attempt < 20; attempt += 1) {
        await sleep(500);
        const updated = (await client.listRuns()).runs?.find(
          (item) => item.run_id === run_id,
        );
        if (updated) {
          observedStatus = updated.status;
          if (updated.status !== run.status) break;
        }
      }

      return asText({
        resumed: true,
        run_id,
        pid: child.pid,
        previous_status: run.status,
        observed_status: observedStatus,
        engine_log: child.engineLogPath,
      });
    },
  );

  server.registerTool(
    'dev_confirm',
    {
      description:
        'Confirma las acciones humanas completadas para una story BMAD estacionada.',
      inputSchema: {
        story: z.string().min(1),
        reverify: z.boolean().optional(),
      },
    },
    async ({ story, reverify }) => {
      const args = ['confirm', story, '--yes'];
      if (reverify) args.push('--reverify');
      try {
        const { stdout, stderr } = await client.execute(args, 120_000);
        return asText({
          confirmed: true,
          story,
          reverified: Boolean(reverify),
          output: stdout.trim() || null,
          stderr: stderr.trim() || null,
        });
      } catch (error: unknown) {
        const details = errorDetails(error);
        return asText({
          confirmed: false,
          story,
          reason: 'confirm-failed',
          exit_code: details.code,
          stdout: details.stdout,
          stderr: details.stderr ?? details.message,
        });
      }
    },
  );

  server.registerTool(
    'dev_stop',
    {
      description: 'Detiene una ejecución BMAD de forma ordenada por defecto.',
      inputSchema: {
        run_id: z.string().min(1),
        graceful: z.boolean().optional(),
      },
    },
    async ({ run_id, graceful }) => {
      const runs = await client.listRuns();
      const run = (runs.runs ?? []).find((item) => item.run_id === run_id);
      if (!run) return asText({ stopped: false, reason: 'run-not-found', run_id });
      if (['finished', 'stopped', 'crashed'].includes(run.status)) {
        return asText({
          stopped: false,
          reason: 'run-not-running',
          run_id,
          status: run.status,
        });
      }

      const useGraceful = graceful !== false;
      const args = ['stop', run_id];
      if (useGraceful) args.push('--graceful');
      try {
        const { stdout, stderr } = await client.execute(args, 30_000);
        await sleep(500);
        const updated = (await client.listRuns()).runs?.find(
          (item) => item.run_id === run_id,
        );
        return asText({
          stopped: true,
          run_id,
          mode: useGraceful ? 'graceful' : 'hard',
          previous_status: run.status,
          observed_status: updated?.status ?? null,
          output: stdout.trim() || null,
          stderr: stderr.trim() || null,
        });
      } catch (error: unknown) {
        const details = errorDetails(error);
        return asText({
          stopped: false,
          reason: 'stop-failed',
          run_id,
          mode: useGraceful ? 'graceful' : 'hard',
          exit_code: details.code,
          stdout: details.stdout,
          stderr: details.stderr ?? details.message,
        });
      }
    },
  );
}
