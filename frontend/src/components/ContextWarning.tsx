"use client";

type ContextWarningProps = {
  state: "warning" | "compacted" | null;
  droppedCount?: number;
  onDismiss: () => void;
};

export function ContextWarning({ state, droppedCount, onDismiss }: ContextWarningProps) {
  if (!state) return null;

  const isCompacted = state === "compacted";

  return (
    <div
      role={isCompacted ? "alert" : "status"}
      className="border-t border-leaf-border bg-leaf-soft px-6 py-2.5"
    >
      <div className="mx-auto flex w-full max-w-3xl items-center justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          <span
            className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-leaf"
            aria-hidden="true"
          />
          <div className="min-w-0">
            {isCompacted ? (
              <>
                <p className="font-serif text-[15px] italic leading-snug text-ink">
                  Resumimos {droppedCount ?? 0} mensajes antiguos para seguir conversando.
                </p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-ink-soft">
                  Tus mensajes en el historial siguen completos.
                </p>
              </>
            ) : (
              <>
                <p className="font-serif text-[15px] italic leading-snug text-ink">
                  Esta conversación se está extendiendo.
                </p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-ink-soft">
                  Pronto vamos a resumir lo más antiguo para mantener la conversación fluida.
                </p>
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Cerrar aviso"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-ink-soft transition-colors hover:bg-leaf-border hover:text-ink"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            <path d="M1 1l10 10M11 1L1 11" />
          </svg>
        </button>
      </div>
    </div>
  );
}
