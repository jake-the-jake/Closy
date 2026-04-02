import type { ClothingCategory } from "@/features/wardrobe/types/clothing-item";

const labels: Record<ClothingCategory, string> = {
  tops: "Tops",
  bottoms: "Bottoms",
  dresses: "Dresses",
  outerwear: "Outerwear",
  shoes: "Shoes",
  accessories: "Accessories",
};

export function formatCategoryLabel(category: ClothingCategory): string {
  return labels[category];
}
