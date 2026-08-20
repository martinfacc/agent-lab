export type ResearchRun = {
  run_id: string;
  objective: string;
  provider: string;
  model: string;
  token_budget: number;
  created_at: string;
  updated_at: string;
  cwd: string;
  report_path: string;
  session_file: string;
  session_id: string;
  active_session_id: string;
  worker_pid: number | null;
  state: string;
  parent_run_id?: string | null;
};

export type GoalState = {
  status?: string;
  active?: boolean;
  goalId?: string;
  tokensUsed?: number;
  tokenBudget?: number;
  timeUsedSeconds?: number;
  continuationsUsed?: number;
  lastReason?: string;
  timestamp?: string | null;
};

export type PrimeWorkerDescriptor = {
  rootActiveSessionId?: string;
  pid?: string | number;
  descriptor_path: string;
};

export type PrimeHeartbeat = {
  activeSessionId: string;
  sessionFile: string;
  sessionId: string;
};

export type RpcResponse = {
  type: 'response';
  id: string;
  success: boolean;
  error?: string;
  data?: {
    heartbeat?: PrimeHeartbeat;
  };
};
