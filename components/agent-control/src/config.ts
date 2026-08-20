import { homedir } from 'node:os';
import { delimiter, join, resolve } from 'node:path';
import { z } from 'zod';

const environmentSchema = z.object({
  LAB_MODE: z.enum(['development', 'full']).default('full'),
  AGENT_CONTROL_PROJECT_PATH: z.string().trim().min(1),
  AGENT_CONTROL_DATA_DIR: z.string().trim().min(1).optional(),
  AGENT_CONTROL_LOG_DIR: z.string().trim().min(1).optional(),
  AGENT_CONTROL_LOCAL_BIN: z.string().trim().min(1).optional(),
  BMAD_LOOP_BIN: z.string().trim().min(1).default('bmad-loop'),
  BMAD_SPRINT_STATUS_PATH: z
    .string()
    .trim()
    .min(1)
    .default('_bmad-output/implementation-artifacts/sprint-status.yaml'),
  PRIME_AGENT_BIN: z.string().trim().min(1).default('prime-agent'),
  PRIME_WORKERS_DIR: z.string().trim().min(1).optional(),
  RESEARCH_PROVIDER: z.string().trim().min(1).default('opencode-go'),
  RESEARCH_MODEL: z.string().trim().min(1).default('deepseek-v4-pro'),
  RESEARCH_TOKEN_BUDGET: z.coerce
    .number()
    .int()
    .min(10_000)
    .max(500_000)
    .default(100_000),
});

export type DevelopmentConfig = {
  projectPath: string;
  bmadLoopBin: string;
  logDir: string;
  sprintStatusPath: string;
  path: string;
};

export type ResearchConfig = {
  primeAgentBin: string;
  rootDir: string;
  runsDir: string;
  primeWorkersDir: string;
  provider: string;
  model: string;
  defaultTokenBudget: number;
};

export type AgentControlConfig = {
  researchEnabled: boolean;
  development: DevelopmentConfig;
  research: ResearchConfig;
};

export function loadConfig(
  environment: NodeJS.ProcessEnv = process.env,
): AgentControlConfig {
  const parsed = environmentSchema.safeParse(environment);
  if (!parsed.success) {
    throw new Error(
      `Configuración inválida de agent-control: ${z.prettifyError(parsed.error)}`,
    );
  }

  const env = parsed.data;
  const dataDir = resolve(
    env.AGENT_CONTROL_DATA_DIR ?? join(homedir(), '.agent-control'),
  );
  const projectPath = resolve(env.AGENT_CONTROL_PROJECT_PATH);
  const researchRoot = join(dataDir, 'research');
  const executablePath = env.AGENT_CONTROL_LOCAL_BIN
    ? `${resolve(env.AGENT_CONTROL_LOCAL_BIN)}${delimiter}${environment.PATH ?? ''}`
    : (environment.PATH ?? '');

  return {
    researchEnabled: env.LAB_MODE === 'full',
    development: {
      projectPath,
      bmadLoopBin: env.BMAD_LOOP_BIN,
      logDir: resolve(env.AGENT_CONTROL_LOG_DIR ?? join(dataDir, 'logs')),
      sprintStatusPath: resolve(projectPath, env.BMAD_SPRINT_STATUS_PATH),
      path: executablePath,
    },
    research: {
      primeAgentBin: env.PRIME_AGENT_BIN,
      rootDir: researchRoot,
      runsDir: join(researchRoot, 'runs'),
      primeWorkersDir: resolve(
        env.PRIME_WORKERS_DIR ?? join(homedir(), '.prime', 'agent', 'daemon-workers'),
      ),
      provider: env.RESEARCH_PROVIDER,
      model: env.RESEARCH_MODEL,
      defaultTokenBudget: env.RESEARCH_TOKEN_BUDGET,
    },
  };
}
