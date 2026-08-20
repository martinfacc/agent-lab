export type BmadTask = {
  story_key: string;
  phase: string;
  attempt?: number;
  review_cycle?: number;
  commit_sha?: string | null;
};

export type BmadRun = {
  run_id: string;
  short_ref?: string;
  type?: string;
  started_at?: string;
  run_type?: string;
  status: string;
  finished?: boolean;
  paused_stage?: string | null;
  paused_reason?: string | null;
  paused_story_key?: string | null;
  adapters?: { dev?: { model?: string } };
  tokens?: unknown;
  tasks?: BmadTask[];
};

export type BmadRunList = { runs?: BmadRun[] };

export type DevelopmentScope =
  | { scope: 'project' }
  | { scope: 'epic'; epic: number }
  | { scope: 'story'; story: string };
