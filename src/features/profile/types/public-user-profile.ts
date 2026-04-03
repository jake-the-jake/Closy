/**
 * Row shape from `public.profiles` (Supabase). Used for Discover attribution.
 */
export type PublicUserProfile = {
  userId: string;
  displayName: string;
  avatarUrl: string | null;
};
