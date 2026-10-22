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

/** Colour tone for a room status pill. */
export function statusTone(status: RoomStatus): "ok" | "warn" | "accent" | "danger" | "" {
  switch (status) {
    case "READY_TO_START": return "ok";
    case "IN_PROGRESS": return "accent";
    case "CREATED": return "warn";
    case "CANCELLED": return "danger";
    default: return "";
  }
}
