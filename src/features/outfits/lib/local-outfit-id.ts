/**
 * Client-generated outfit id until a backend assigns one.
 */
export function createLocalOutfitId(): string {
  return `outfit-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}
