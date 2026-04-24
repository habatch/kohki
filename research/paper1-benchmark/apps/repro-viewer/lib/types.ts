export type Stats = {
  mean: number; stdev: number; min: number; max: number; n: number;
} | null;

export type ReproSummary = {
  schema: string;
  experiment: string;
  n_trials: number;
  n_valid: number;
  n_parse_failures: number;
  model: string;
  temperature: number;
  seed_base: number | null;
  prompt_sha256: string;
  wall_seconds_total: number;
  wall_seconds_per_trial_mean: number;
  unique_response_count: number;
  unique_param_set_count: number;
  fully_reproducible_response: boolean;
  fully_reproducible_params: boolean;
  param_distributions: Record<string, Record<string, number>>;
  response_hash_counts: Record<string, number>;
  param_set_hash_counts: Record<string, number>;
  stats: {
    ecutwfc_Ry: Stats;
    ecutrho_Ry: Stats;
    degauss_Ry: Stats;
    conv_thr_Ry: Stats;
    mixing_beta: Stats;
  };
};

export type Trial = {
  trial_index: number;
  model: string;
  temperature: number;
  seed: number | null;
  prompt_sha256: string;
  response_text: string;
  response_sha256: string;
  parsed_json: Record<string, unknown> | null;
  params: Record<string, unknown> | null;
  params_valid: boolean;
  wall_seconds: number;
  ollama_eval_count: number;
  ollama_eval_duration_s: number;
  timestamp_utc: string;
};

export type ExperimentMeta = {
  id: string;
  source: 'filesystem' | 'imported';
  summary: ReproSummary;
};
