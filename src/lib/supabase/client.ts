/**
 * TypeScript resolves `client` here. Metro bundles `client.web.ts` on web and
 * `client.native.ts` on iOS/Android when those files exist — this file is not
 * used in platform bundles in that case.
 */
export { requireSupabase, supabase } from "./client.native";
