/**
 * Configuración del frontend.
 *
 * En dev: el backend FastAPI corre en localhost:8000.
 * En prod: vendrá de NEXT_PUBLIC_API_URL.
 */
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
