/**
 * Tipos del User que viajan del backend al frontend.
 * Tienen que coincidir con `app/schemas/user.py` del backend.
 */

export type User = {
  id: number;
  email: string;
  nombre: string;
  role: "user" | "admin";
  onboarding_state: "pending" | "in_progress" | "passed" | "failed_quality";
  onboarding_score: number | null;
  onboarding_attempts: number;
  active_project_id: number | null;
  research_opt_in: boolean;
  created_at: string;
};

export type UseCase = {
  id: number;
  project_id: number;
  slug: string;
  name: string;
  description: string | null;
  is_default: boolean;
  created_at: string;
};

export type Project = {
  id: number;
  user_id: number;
  slug: string;
  name: string;
  description: string | null;
  is_default: boolean;
  created_at: string;
  use_cases: UseCase[];
};
