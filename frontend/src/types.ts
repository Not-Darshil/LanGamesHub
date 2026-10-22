export type SessionStatus = "PENDING" | "APPROVED" | "REJECTED" | "REVOKED" | "EXPIRED";
export type Screen = "VISIBLE" | "HIDDEN";
export type RoomStatus =
  | "CREATED"
  | "WAITING_FOR_PLAYERS"
  | "READY_TO_START"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED";

export interface SessionInfo {
  id: number;
  status: SessionStatus;
  nickname?: string | null;
  is_host?: boolean;
  screen: Screen;
}

export interface GameInfo {
  game_type: string;
  name: string;
  min_players: number;
  max_players: number;
  description: string;
}

export interface RoomSummary {
  id: number;
  name: string;
  game_type: string;
  game_name: string;
  status: RoomStatus;
  players: number;
  min_players: number | null;
  max_players: number;
  is_locked: boolean;
  creator: string;
  options?: Record<string, unknown>;
  options_label?: string | null;
}

export interface Member {
  session_id: number;
  nickname: string;
  seat: number;
  is_ready: boolean;
  online: boolean;
  is_host: boolean;
}

export interface MatchResultInfo {
  outcome: "WIN" | "DRAW" | "ABORTED" | "CANCELLED";
  winners: string[];
  reason: string;
}

export interface RoomDetail extends RoomSummary {
  members: Member[];
  status_reason: string | null;
  result: MatchResultInfo | null;
  awaiting: string[];
}

/** Common fields the server adds to every engine's game view. */
export interface GameViewBase {
  version: number;
  names: Record<string, string>;
  you: string;
  log?: string[];
}

export interface PlayerState {
  session: SessionInfo;
  lobby?: { games: GameInfo[]; rooms: RoomSummary[] };
  room?: RoomDetail | null;
  game?: (GameViewBase & Record<string, unknown>) | null;
}

export interface AdminPlayer extends SessionInfo {
  ip_address: string;
  user_agent: string;
  created_at: string;
  online: boolean;
  room: { id: number; name: string; status: RoomStatus } | null;
  prior_rejections?: number;
}

export interface AdminRoom extends RoomSummary {
  approved: boolean;
  members: Member[];
  status_reason: string | null;
  awaiting: string[];
  result: MatchResultInfo | null;
  created_at: string;
}

export interface HistoryEntry {
  id: number;
  room_name: string;
  game_type: string;
  outcome: string;
  winners: string[];
  reason: string;
  participants: string[];
  finished_at: string;
}

export interface AdminState {
  pending: AdminPlayer[];
  players: AdminPlayer[];
  rooms: AdminRoom[];
  games: GameInfo[];
  history: HistoryEntry[];
}
