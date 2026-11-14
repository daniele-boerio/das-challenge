export type Role = "host" | "guest";
export type Difficulty = "facile" | "media" | "difficile";
export type JudgeMode = "voto" | "ai" | "entrambi";
export type PowerupKind = "extra" | "sabotage" | "reroll";

export interface Settings {
  rounds: number;
  judge: JudgeMode;
  theme: string;
  minutes: Record<Difficulty, number>;
  powerups: boolean;
  handicap: "off" | "leader" | "random";
  memory: boolean;
}

export interface Player {
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
  host: { score: number; comment: string };
  guest: { score: number; comment: string };
  verdict: string;
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
  end_at: Record<Role, number>;
  finished_at: Record<Role, number | null>;
  delivered: Record<Role, boolean>;
  photos: Record<Role, string | null>;
  handicaps: Record<Role, string | null>;
  events: { by: Role; kind: PowerupKind; at: number }[];
  votes: {
    needed: boolean;
    host_voted: boolean;
    guest_voted: boolean;
    host?: number | null;
    guest?: number | null;
    mine?: number | null;
  };
  ai: { status: "none" | "pending" | "done" | "failed"; error: string | null; result: AiResult | null };
  scores: Record<Role, number> | null;
  points: Record<Role, number> | null;
}

export interface MatchState {
  code: string;
  status: "lobby" | "ready" | "playing" | "finished";
  you: Role | null;
  server_now: number;
  created_at: number;
  finished_at: number | null;
  settings: Settings;
  players: { host: Player; guest: Player | null };
  rounds: RoundState[];
  suggested_difficulty: Difficulty | null;
  winner: Role | "pari" | null;
  rematch_code: string | null;
}

export interface AppConfig {
  access_required: boolean;
  ai_available: boolean;
  themes: Record<string, string>;
  default_minutes: Record<Difficulty, number>;
  multipliers: Record<Difficulty, number>;
  defaults: Settings;
}

export interface GalleryMatch {
  code: string;
  finished_at: number;
  host: { name: string; total: number };
  guest: { name: string; total: number };
  winner: Role | "pari" | null;
  rounds: {
    subject: string;
    difficulty: Difficulty;
    image: string | null;
    host_photo: string | null;
    guest_photo: string | null;
  }[];
}

export interface Gallery {
  matches: GalleryMatch[];
  head_to_head: { players: string[]; wins: Record<string, number>; draws: number; matches: number }[];
}
