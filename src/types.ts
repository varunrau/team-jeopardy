// Shared types matching the Python Pydantic event models in models/events.py

export interface BoardClue {
  id: string;
  dollar_value: number;
  is_answered: boolean;
  is_daily_double: boolean;
  category: string;
  answer?: string;
  clue_text?: string;
}

export interface BoardUpdate {
  type: "BOARD_UPDATE";
  board: Record<string, BoardClue[]>;
  scores: Record<string, number>;
  team_names: Record<string, string>;
}

export interface ClueSelected {
  type: "CLUE_SELECTED";
  clue_text: string;
  clue_image_url: string | null;
  category: string;
  dollar_value: number;
  is_daily_double: boolean;
}

export interface BuzzOpen {
  type: "BUZZ_OPEN";
}

export interface BuzzLocked {
  type: "BUZZ_LOCKED";
  team_name: string;
}

export interface BuzzWinner {
  type: "BUZZ_WINNER";
  team_id: string;
  team_name: string;
}

export interface BuzzTimeout {
  type: "BUZZ_TIMEOUT";
}

export interface JudgeResult {
  type: "JUDGE_RESULT";
  correct: boolean;
  team_id: string;
  team_name: string;
  score_delta: number;
  new_score: number;
}

export interface ScoreUpdate {
  type: "SCORE_UPDATE";
  scores: Record<string, number>;
  team_names: Record<string, string>;
}

export interface GameStatusChange {
  type: "GAME_STATUS";
  status: "lobby" | "in_progress" | "final_jeopardy" | "finished";
}

export interface FinalJeopardyClue {
  type: "FINAL_JEOPARDY_CLUE";
  category: string;
  clue_text: string;
}

export interface FinalJeopardyReveal {
  type: "FINAL_REVEAL";
  results: FinalResult[];
}

export interface FinalResult {
  team_id: string;
  team_name: string;
  wager: number | null;
  answer: string | null;
  score: number;
}

export interface AnswerReveal {
  type: "ANSWER_REVEAL";
  answer: string;
}

export interface DailyDouble {
  type: "DAILY_DOUBLE";
  team_id: string;
  team_name: string;
  category: string;
  dollar_value: number;
}

export interface TeamJoined {
  type: "TEAM_JOINED";
  team_id: string;
  team_name: string;
}

export interface ClueComplete {
  type: "CLUE_COMPLETE";
}

// Union of all server -> host events
export type HostEvent =
  | BoardUpdate
  | ClueSelected
  | BuzzWinner
  | BuzzTimeout
  | JudgeResult
  | ScoreUpdate
  | AnswerReveal
  | GameStatusChange
  | FinalJeopardyClue
  | FinalJeopardyReveal
  | TeamJoined
  | ClueComplete
  | DailyDouble;

// Union of all server -> team events
export type TeamEvent =
  | BuzzOpen
  | BuzzLocked
  | BuzzTimeout
  | ClueSelected
  | ScoreUpdate
  | JudgeResult
  | GameStatusChange
  | FinalJeopardyClue
  | ClueComplete
  | DailyDouble;

// Client -> server
export interface BuzzIn {
  type: "BUZZ";
}

// API response types
export interface GameTeam {
  team_id: string;
  name: string;
  score: number;
}

export interface GameStateResponse {
  game_id: string;
  status: string;
  teams: GameTeam[];
  board: Record<string, BoardClue[]>;
  current_clue: { clue_text: string; category: string; dollar_value: number } | null;
  buzz_window_open: boolean;
}
