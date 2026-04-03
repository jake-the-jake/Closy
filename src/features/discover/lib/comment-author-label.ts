/** Display name for a comment row when `profiles.display_name` is empty. */
export function commentAuthorDisplayLabel(
  profileDisplayName: string,
  authorUserId: string,
): string {
  const t = profileDisplayName.trim();
  if (t.length > 0) return t;
  const compact = authorUserId.replace(/-/g, "");
  return `Member ${compact.slice(0, 8)}`;
}
