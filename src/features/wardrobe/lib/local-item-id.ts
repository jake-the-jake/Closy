/**
 * Client-generated id until a server assigns persistent ids. Prefix avoids clashes
 * with imported seed data shapes while staying a plain string for `ClothingItem.id`.
 */
export function createLocalWardrobeItemId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}
