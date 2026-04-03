import type { User } from "@supabase/supabase-js";

import { supabase } from "@/lib/supabase/client";

export async function getAuthedUserId(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.user.id ?? null;
}

export async function getAuthedUser(): Promise<User | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.user ?? null;
}
