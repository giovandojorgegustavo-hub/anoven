/**
 * Página `/auth/callback`.
 *
 * Recibe token del Google OAuth flow, lo guarda en localStorage, y redirige
 * según onboarding_state. Tiene que estar wrapped en <Suspense> para que
 * useSearchParams funcione en production build de Next.js.
 */

"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { API_URL } from "@/lib/config";
import { setToken } from "@/lib/auth";
import type { User } from "@/lib/user";


function AuthCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const token = searchParams.get("token");

    if (!token) {
      router.replace("/?error=no_token");
      return;
    }

    setToken(token);

    fetch(`${API_URL}/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const user: User = await res.json();
        if (user.onboarding_state === "passed") {
          router.replace("/dashboard");
        } else {
          router.replace("/onboarding");
        }
      })
      .catch(() => {
        router.replace("/?error=fetch_failed");
      });
  }, [searchParams, router]);

  return (
    <p className="font-serif text-lg italic text-ink-soft">
      Iniciando sesión...
    </p>
  );
}


export default function AuthCallbackPage() {
  return (
    <main className="flex flex-1 items-center justify-center">
      <Suspense fallback={
        <p className="font-serif text-lg italic text-ink-soft">
          Cargando...
        </p>
      }>
        <AuthCallbackInner />
      </Suspense>
    </main>
  );
}
