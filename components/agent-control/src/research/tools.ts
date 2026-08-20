import type { McpServer } from '@modelcontextprotocol/server';
import { readFile } from 'node:fs/promises';
import { z } from 'zod';
import type { ResearchConfig } from '../config.ts';
import { errorDetails } from '../shared/errors.ts';
import type { TextResult } from '../shared/mcp.ts';
import {
  cleanupTerminalWorker,
  findWorkerDescriptor,
  getGoalState,
  loadRun,
  saveRun,
  startRpcResearch,
  stopPrimeWorker,
} from './prime-client.ts';

export function registerResearchTools(
  server: McpServer,
  config: ResearchConfig,
  asText: (data: unknown) => TextResult,
) {
  server.registerTool(
    'research_start',
    {
      description:
        'Inicia una investigación profunda y persistente con Prime en segundo plano. Devuelve de inmediato un run_id consultable con research_status.',
      inputSchema: {
        objective: z.string().min(1),
        token_budget: z.number().int().min(10_000).max(500_000).optional(),
        parent_run_id: z.string().min(1).optional(),
      },
    },
    async ({
      objective,
      token_budget,
      parent_run_id,
    }: {
      objective: string;
      token_budget?: number;
      parent_run_id?: string;
    }) => {
      try {
        const run = await startRpcResearch(
          config,
          objective,
          token_budget ?? config.defaultTokenBudget,
          parent_run_id,
        );

        return asText({
          started: true,
          run_id: run.run_id,
          state: run.state,
          provider: run.provider,
          model: run.model,
          token_budget: run.token_budget,
          active_session_id: run.active_session_id,
          session_id: run.session_id,
          session_file: run.session_file,
          worker_pid: run.worker_pid,
          report_path: run.report_path,
        });
      } catch (error: unknown) {
        const details = errorDetails(error);
        return asText({
          started: false,
          reason: 'research-start-failed',
          error: details.message,
        });
      }
    },
  );

  server.registerTool(
    'research_status',
    {
      description:
        'Devuelve el estado autoritativo del objetivo persistente de una investigación Prime. Las ejecuciones finalizadas se limpian conservando su informe y transcripción.',
      inputSchema: {
        run_id: z.string().min(1),
      },
    },
    async ({ run_id }: { run_id: string }) => {
      const run = await loadRun(config, run_id);

      if (!run) {
        return asText({
          found: false,
          run_id,
          reason: 'run-not-found',
        });
      }

      if (run.state === 'stopped') {
        return asText({
          found: true,
          run_id,
          status: 'stopped',
          active: false,
          report_path: run.report_path,
        });
      }

      const goal = await getGoalState(run);

      if (!goal) {
        const descriptor = await findWorkerDescriptor(config, run.active_session_id);

        return asText({
          found: true,
          run_id,
          status: descriptor ? 'starting' : 'unknown',
          active: Boolean(descriptor),
          report_path: run.report_path,
          session_file: run.session_file,
        });
      }

      const status = goal.status ?? 'active';
      const terminal = ['complete', 'budget_limited', 'error'].includes(status);

      let cleanup = null;

      if (terminal) {
        cleanup = await cleanupTerminalWorker(config, run);
        run.state = status;
        await saveRun(config, run);
      } else {
        run.state = status;
        await saveRun(config, run);
      }

      return asText({
        found: true,
        run_id,
        status: goal.status,
        active: goal.active,
        goal_id: goal.goalId,
        objective: run.objective,
        tokens_used: goal.tokensUsed,
        token_budget: goal.tokenBudget,
        time_used_seconds: goal.timeUsedSeconds,
        continuations_used: goal.continuationsUsed,
        last_reason: goal.lastReason,
        goal_updated_at: goal.timestamp,
        report_path: run.report_path,
        session_file: run.session_file,
        cleanup,
      });
    },
  );

  server.registerTool(
    'research_result',
    {
      description:
        'Devuelve el informe Markdown persistido de una investigación. El informe terminado sigue disponible después de limpiar el worker de Prime.',
      inputSchema: {
        run_id: z.string().min(1),
      },
    },
    async ({ run_id }: { run_id: string }) => {
      const run = await loadRun(config, run_id);

      if (!run) {
        return asText({
          found: false,
          run_id,
          reason: 'run-not-found',
        });
      }

      const goal = await getGoalState(run);

      let report: string;

      try {
        report = await readFile(run.report_path, 'utf8');
      } catch {
        return asText({
          found: true,
          ready: false,
          run_id,
          status: run.state === 'stopped' ? 'stopped' : (goal?.status ?? run.state),
          reason: 'report-not-found',
          report_path: run.report_path,
        });
      }

      return asText({
        found: true,
        ready: true,
        run_id,
        status: run.state === 'stopped' ? 'stopped' : (goal?.status ?? run.state),
        report_path: run.report_path,
        report,
      });
    },
  );

  server.registerTool(
    'research_stop',
    {
      description:
        'Detiene una sesión de investigación Prime y limpia los procesos residuales de herramientas del grupo del worker.',
      inputSchema: {
        run_id: z.string().min(1),
      },
    },
    async ({ run_id }: { run_id: string }) => {
      const run = await loadRun(config, run_id);

      if (!run) {
        return asText({
          stopped: false,
          run_id,
          reason: 'run-not-found',
        });
      }

      if (run.state === 'stopped') {
        return asText({
          stopped: false,
          run_id,
          reason: 'already-stopped',
        });
      }

      const goal = await getGoalState(run);

      if (goal?.status === 'complete') {
        const cleanup = await cleanupTerminalWorker(config, run);

        run.state = 'complete';
        await saveRun(config, run);

        return asText({
          stopped: false,
          run_id,
          reason: 'already-complete',
          status: 'complete',
          cleanup,
          report_path: run.report_path,
        });
      }

      const descriptor = await findWorkerDescriptor(config, run.active_session_id);

      const workerPid = Number(descriptor?.pid) || run.worker_pid || null;

      const result = await stopPrimeWorker(config, run.active_session_id, workerPid);

      run.state = 'stopped';
      await saveRun(config, run);

      return asText({
        stopped: true,
        run_id,
        status: 'stopped',
        active_session_id: run.active_session_id,
        worker_pid: workerPid,
        ...result,
      });
    },
  );
}
