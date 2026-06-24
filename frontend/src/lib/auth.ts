/**
 * Helpers para manejar el JWT en el browser.
 *
 * Guardamos en localStorage por simplicidad de MVP.
 * En producción es mejor HttpOnly cookie (más seguro contra XSS),
 * pero para dev en localhost localStorage va bien.
 *
 * Todas estas funciones tienen que chequear `typeof window` porque
 * Next.js renderiza componentes en el SERVER también (donde no hay
 * localStorage). Si no chequeamos, explota durante el build.
 */

const TOKEN_KEY = "anoven_token";

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}
