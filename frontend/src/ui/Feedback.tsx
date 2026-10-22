import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";
import { play } from "./sound";

/* ---------------- Toasts ---------------- */

type ToastKind = "error" | "success" | "info";
interface ToastItem { id: number; kind: ToastKind; message: string; leaving?: boolean }

interface Feedback {
  toast: (message: string, kind?: ToastKind) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

export interface ConfirmOptions {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

const FeedbackContext = createContext<Feedback | null>(null);

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [dialog, setDialog] = useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.map((t) => (t.id === id ? { ...t, leaving: true } : t)));
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 250);
  }, []);

  const toast = useCallback((message: string, kind: ToastKind = "info") => {
    const id = nextId.current++;
    if (kind === "error") play("error");
    setToasts((list) => [...list.filter((t) => t.message !== message).slice(-3), { id, kind, message }]);
    window.setTimeout(() => dismiss(id), kind === "error" ? 5000 : 3500);
  }, [dismiss]);

  const confirm = useCallback((options: ConfirmOptions) =>
    new Promise<boolean>((resolve) => setDialog({ ...options, resolve })), []);

  const close = (ok: boolean) => {
    dialog?.resolve(ok);
    setDialog(null);
  };

  return (
    <FeedbackContext.Provider value={{ toast, confirm }}>
      {children}
      {createPortal(
        <div className="toasts" role="status" aria-live="polite">
          {toasts.map((t) => (
            <div key={t.id} className={`toast ${t.kind}${t.leaving ? " leaving" : ""}`} onClick={() => dismiss(t.id)}>
              <span className="toast-icon">
                <Icon name={t.kind === "error" ? "alert" : t.kind === "success" ? "check" : "info"} size={13} strokeWidth={2.6} />
              </span>
              <span>{t.message}</span>
            </div>
          ))}
        </div>,
        document.body,
      )}
      {dialog && (
        <Modal onClose={() => close(false)} labelledBy="confirm-title">
          <h2 id="confirm-title">{dialog.title}</h2>
          {dialog.body && <div className="modal-body">{dialog.body}</div>}
          <div className="modal-actions">
            <button className="secondary" onClick={() => close(false)}>{dialog.cancelLabel ?? "Cancel"}</button>
            <button className={dialog.danger ? "danger" : ""} autoFocus onClick={() => close(true)}>
              {dialog.confirmLabel ?? "Confirm"}
            </button>
          </div>
        </Modal>
      )}
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): Feedback {
  const value = useContext(FeedbackContext);
  if (!value) throw new Error("useFeedback must be used inside FeedbackProvider");
  return value;
}

/* ---------------- Modal ---------------- */

export function Modal({ children, onClose, wide, labelledBy }: {
  children: ReactNode; onClose: () => void; wide?: boolean; labelledBy?: string;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
        {children}
      </div>
    </div>,
    document.body,
  );
}
