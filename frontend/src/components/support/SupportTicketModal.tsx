/**
 * SupportTicketModal — modal para crear tickets de soporte.
 *
 * Flujo de 2 pasos:
 *   1. POST /api/tickets → obtiene ticket_id
 *   2. POST /api/tickets/{id}/attachments (multipart) por cada adjunto
 *
 * Validación cliente: 1–3 archivos, ≤5 MB c/u, solo PNG/JPEG/WebP.
 * Copy: tuteo limeño culto (NO voseo).
 * D3.1: solo paleta accent (terracotta). D3.2: LIGHT MODE only.
 * A2.1: "use client" justificado — form state + paste handler + fetch.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL } from "@/lib/config";
import { clearToken, getToken } from "@/lib/auth";

type TicketType = "bug" | "mejora" | "pregunta" | "otro";

const TYPE_LABEL: Record<TicketType, string> = {
  bug: "Bug",
  mejora: "Mejora",
  pregunta: "Pregunta",
  otro: "Otro",
};

const ALLOWED_MIMES = ["image/png", "image/jpeg", "image/webp"];
const MAX_FILES = 3;
const MAX_SIZE_BYTES = 5 * 1024 * 1024; // 5 MB

interface SupportTicketModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId?: number;
  mentorSlug?: string;
}

interface AttachmentFile {
  file: File;
  preview: string; // object URL
}

export function SupportTicketModal({
  isOpen,
  onClose,
  conversationId,
  mentorSlug,
}: SupportTicketModalProps) {
  const router = useRouter();

  const [ticketType, setTicketType] = useState<TicketType>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<AttachmentFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [successTicketId, setSuccessTicketId] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropzoneRef = useRef<HTMLDivElement>(null);

  // Revoke object URLs on unmount to avoid memory leaks
  useEffect(() => {
    return () => {
      attachments.forEach((a) => URL.revokeObjectURL(a.preview));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Paste handler
  useEffect(() => {
    if (!isOpen) return;

    function handlePaste(e: ClipboardEvent) {
      const items = e.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of Array.from(items)) {
        if (item.kind === "file") {
          const f = item.getAsFile();
          if (f) files.push(f);
        }
      }
      if (files.length > 0) addFiles(files);
    }

    window.addEventListener("paste", handlePaste);
    return () => window.removeEventListener("paste", handlePaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, attachments]);

  function validateFile(file: File): string | null {
    if (!ALLOWED_MIMES.includes(file.type)) {
      return "Solo aceptamos imágenes PNG, JPEG o WebP.";
    }
    if (file.size > MAX_SIZE_BYTES) {
      return "La imagen supera los 5 MB. Intenta con una más liviana.";
    }
    return null;
  }

  function addFiles(files: File[]) {
    setFieldErrors((prev) => ({ ...prev, attachments: "" }));
    const remaining = MAX_FILES - attachments.length;
    if (remaining <= 0) {
      setFieldErrors((prev) => ({
        ...prev,
        attachments: "Sube hasta 3 imágenes.",
      }));
      return;
    }

    const toAdd: AttachmentFile[] = [];
    let firstError: string | null = null;

    for (const file of files.slice(0, remaining)) {
      const err = validateFile(file);
      if (err) {
        if (!firstError) firstError = err;
        continue;
      }
      toAdd.push({ file, preview: URL.createObjectURL(file) });
    }

    if (firstError) {
      setFieldErrors((prev) => ({ ...prev, attachments: firstError! }));
    }

    if (toAdd.length > 0) {
      setAttachments((prev) => [...prev, ...toAdd]);
    }
  }

  function removeAttachment(index: number) {
    setAttachments((prev) => {
      URL.revokeObjectURL(prev[index].preview);
      return prev.filter((_, i) => i !== index);
    });
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) addFiles(files);
    // Reset input so same file can be re-selected after removal
    e.target.value = "";
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(true);
  }

  function handleDragLeave() {
    setDragActive(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) addFiles(files);
  }

  function validateForm(): boolean {
    const errs: Record<string, string> = {};
    if (title.trim().length < 1 || title.trim().length > 200) {
      errs.title = "El título debe tener entre 1 y 200 caracteres.";
    }
    if (description.trim().length < 1 || description.trim().length > 5000) {
      errs.description = "La descripción debe tener entre 1 y 5000 caracteres.";
    }
    if (attachments.length === 0) {
      errs.attachments = "Adjunta al menos una captura antes de enviar.";
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validateForm()) return;

    const token = getToken();
    if (!token) {
      clearToken();
      router.replace("/?error=session_expired");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      // Step 1: create ticket
      const body: Record<string, unknown> = {
        ticket_type: ticketType,
        title: title.trim(),
        description: description.trim(),
      };
      if (conversationId) body.conversation_id = conversationId;

      const createRes = await fetch(`${API_URL}/api/tickets`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });

      if (createRes.status === 401) {
        clearToken();
        router.replace("/?error=session_expired");
        return;
      }
      if (!createRes.ok) {
        const errData = await createRes.json().catch(() => ({}));
        throw new Error(errData.detail ?? `Error ${createRes.status}`);
      }

      const { id: ticketId } = await createRes.json();

      // Step 2: upload each attachment
      for (const att of attachments) {
        const formData = new FormData();
        formData.append("file", att.file, att.file.name);

        const uploadRes = await fetch(`${API_URL}/api/tickets/${ticketId}/attachments`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });

        if (!uploadRes.ok) {
          const errData = await uploadRes.json().catch(() => ({}));
          throw new Error(errData.detail ?? `Error subiendo imagen ${att.file.name}`);
        }
      }

      // Success
      setSuccessTicketId(ticketId);

    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido. Intenta de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleClose() {
    if (submitting) return;
    // Revoke previews before closing
    attachments.forEach((a) => URL.revokeObjectURL(a.preview));
    setAttachments([]);
    setTitle("");
    setDescription("");
    setTicketType("bug");
    setError(null);
    setFieldErrors({});
    setSuccessTicketId(null);
    onClose();
  }

  function handleGoToTicket() {
    if (successTicketId) {
      handleClose();
      router.push(`/mis-tickets/${successTicketId}`);
    }
  }

  if (!isOpen) return null;

  const canSubmit =
    !submitting &&
    title.trim().length >= 1 &&
    description.trim().length >= 1 &&
    attachments.length >= 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) handleClose();
      }}
    >
      <div className="relative w-full max-w-lg rounded-2xl border border-rule bg-paper shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <h2 className="font-serif text-xl font-medium tracking-tight text-ink">
            Reportar un problema o sugerencia
          </h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            aria-label="Cerrar"
            className="rounded-md p-1 text-ink-muted hover:text-ink disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {/* Success state */}
        {successTicketId !== null ? (
          <div className="px-6 py-8 text-center">
            <p className="font-serif text-2xl italic text-ink">
              Listo.
            </p>
            <p className="mt-2 text-sm text-ink-soft">
              Ticket #{successTicketId} enviado. Te respondemos pronto desde Anoven, sin correo.
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <button
                onClick={handleGoToTicket}
                className="rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:bg-accent-hover"
              >
                Ver ticket
              </button>
              <button
                onClick={handleClose}
                className="rounded-xl border border-rule px-5 py-2.5 text-sm text-ink-soft hover:bg-paper-dim"
              >
                Cerrar
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-6 py-5 space-y-4">
            {/* Global error */}
            {error && (
              <p className="rounded-lg border border-accent bg-accent-soft px-4 py-2 text-sm text-accent">
                {error}
              </p>
            )}

            {/* Type */}
            <div>
              <label className="block text-xs font-medium uppercase tracking-wide text-ink-muted mb-1">
                ¿De qué se trata?
              </label>
              <select
                value={ticketType}
                onChange={(e) => setTicketType(e.target.value as TicketType)}
                className="w-full rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none"
              >
                {(Object.keys(TYPE_LABEL) as TicketType[]).map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABEL[t]}
                  </option>
                ))}
              </select>
            </div>

            {/* Title */}
            <div>
              <label className="block text-xs font-medium uppercase tracking-wide text-ink-muted mb-1">
                Título
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder="Resúmelo en una línea"
                className={`w-full rounded-lg border bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:outline-none ${
                  fieldErrors.title ? "border-accent" : "border-rule focus:border-accent"
                }`}
              />
              {fieldErrors.title && (
                <p className="mt-1 text-xs text-accent">{fieldErrors.title}</p>
              )}
            </div>

            {/* Description */}
            <div>
              <label className="block text-xs font-medium uppercase tracking-wide text-ink-muted mb-1">
                Descripción
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={5000}
                rows={4}
                placeholder="Cuéntanos qué pasó y qué esperabas que pasara"
                className={`w-full resize-none rounded-lg border bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:outline-none ${
                  fieldErrors.description ? "border-accent" : "border-rule focus:border-accent"
                }`}
              />
              {fieldErrors.description && (
                <p className="mt-1 text-xs text-accent">{fieldErrors.description}</p>
              )}
            </div>

            {/* Attachments */}
            <div>
              <label className="block text-xs font-medium uppercase tracking-wide text-ink-muted mb-1">
                Capturas de pantalla
              </label>

              {/* Dropzone */}
              {attachments.length < MAX_FILES && (
                <div
                  ref={dropzoneRef}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors ${
                    dragActive
                      ? "border-accent bg-accent-soft"
                      : "border-rule bg-paper-dim hover:border-rule-strong hover:bg-paper"
                  }`}
                >
                  <p className="text-sm text-ink-soft">
                    Pega capturas (Cmd+V) o arrástralas aquí.
                  </p>
                  <p className="mt-1 text-xs text-ink-muted">
                    Mínimo 1, máximo 3. Solo PNG, JPEG o WebP. Máximo 5 MB por imagen.
                  </p>
                </div>
              )}

              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                className="hidden"
                onChange={handleFileInput}
              />

              {/* Previews */}
              {attachments.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {attachments.map((att, i) => (
                    <div key={att.preview} className="relative group">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={att.preview}
                        alt={att.file.name}
                        className="h-20 w-20 rounded-lg border border-rule object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => removeAttachment(i)}
                        className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] text-accent-ink opacity-0 group-hover:opacity-100"
                        aria-label="Eliminar imagen"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {fieldErrors.attachments && (
                <p className="mt-1 text-xs text-accent">{fieldErrors.attachments}</p>
              )}
            </div>

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="rounded-xl border border-rule px-4 py-2 text-sm text-ink-soft hover:bg-paper-dim disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={!canSubmit}
                className="rounded-xl bg-accent px-5 py-2 text-sm font-medium text-accent-ink hover:bg-accent-hover disabled:opacity-60"
              >
                {submitting ? "Enviando..." : "Enviar ticket"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
