export type Difficulty = "facile" | "media" | "difficile";
export type JudgeMode = "voto" | "ai" | "entrambi";
export type PowerupKind = "extra" | "sabotage" | "reroll";
export type TimerMode = "libero" | "rigido" | "nessuno";

export interface Settings {
  rounds: number;
  judge: JudgeMode;
  theme: string;
  minutes: Record<Difficulty, number>;
  timer: TimerMode;
  rush: boolean;
  rush_after: number;
  rush_minutes: number;
  powerups: boolean;
  handicap: "off" | "leader" | "random";
  memory: boolean;
  colors: boolean;
}

export interface Player {
  seat: number;
  name: string;
  total: number;
  online: boolean;
  powerups: Partial<Record<PowerupKind, boolean>>;
}

export interface Attribution {
  title: string;
  creator: string;
  license: string;
  license_url: string;
  source_url: string;
  provider: string;
}

export interface AiResult {
  entries: Record<string, { score: number; comment: string }>;
  verdict: string;
}

export interface EntryState {
  seat: number;
  end_at: number | null;
  deadline: number | null;
  close_at: number | null;
  finished_at: number | null;
  delivered: boolean;
  photo: string | null;
  handicap: string | null;
  score: number | null;
  points: number | null;
  votes_received: number[] | null;
}

export interface RoundState {
  number: number;
  difficulty: Difficulty;
  multiplier: number;
  theme: string;
  subject: string | null;
  image: string | null;
  attribution: Attribution | null;
  memory: boolean;
  memory_hide_at: number | null;
  status: "sculpting" | "judging" | "done";
  starts_at: number;
  duration_s: number;
  timed: boolean;
  rush_end_at: number | null;
  entries: EntryState[];
  events: { by: number; kind: PowerupKind; target?: number; at: number }[];
  votes: {
    needed: boolean;
    voted: number[];
    closed: boolean;
    targets: number[];
    mine: Record<string, number> | null;
  };
  ai: { status: "none" | "pending" | "done" | "failed"; error: string | null; result: AiResult | null };
}

export interface MatchState {
  code: string;
  status: "lobby" | "ready" | "playing" | "finished";
  you: number | null;
  max_players: number;
  ai?: boolean;
  joinable?: boolean;
  server_now: number;
  created_at: number;
  finished_at: number | null;
  settings: Settings;
  grace_s: number;
  players: Player[];
  rounds: RoundState[];
  suggested_difficulty: Difficulty | null;
  winners: number[] | null;
  rematch_code: string | null;
}

export interface AppConfig {
  ai_available: boolean;
  themes: Record<string, string>;
  default_minutes: Record<Difficulty, number>;
  multipliers: Record<Difficulty, number>;
  defaults: Settings;
  max_players: number;
}

export interface GalleryMatch {
  code: string;
  finished_at: number;
  players: { seat: number; name: string; total: number }[];
  winners: number[];
  you: number | null;
  rounds: {
    subject: string;
    difficulty: Difficulty;
    image: string | null;
    photos: string[];
  }[];
}

export interface Gallery {
  matches: GalleryMatch[];
  head_to_head: { name: string; matches: number; wins: number; losses: number; draws: number }[];
  stats: { played: number; won: number };
}

export interface User {
  id: number;
  email: string;
  name: string | null;
}
