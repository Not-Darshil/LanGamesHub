import type { RoomStatus } from "./types";

const STATUS_LABELS: Record<RoomStatus, string> = {
  CREATED: "awaiting host approval",
  WAITING_FOR_PLAYERS: "waiting for players",
  READY_TO_START: "ready — waiting for host to start",
  IN_PROGRESS: "in progress",
  COMPLETED: "finished",
  CANCELLED: "cancelled",
};

export function statusLabel(status: RoomStatus): string {
  return STATUS_LABELS[status];
}
