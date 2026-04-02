import type { ClothingItem } from "@/features/wardrobe/types/clothing-item";
import { mockPicsumImageUrl } from "@/lib/constants";

/**
 * Static seed data for UI development. Replace with repository/API calls later
 * without changing screen components if you keep `ClothingItem` in sync with the backend.
 */
export const MOCK_CLOTHING_ITEMS: ClothingItem[] = [
  {
    id: "item-oxford-white",
    name: "Classic Oxford shirt",
    category: "tops",
    colour: "White",
    brand: "Brooks Brothers",
    imageUrl: mockPicsumImageUrl("closy-oxford"),
    tags: ["work", "smart casual", "cotton"],
  },
  {
    id: "item-chino-navy",
    name: "Slim-fit chinos",
    category: "bottoms",
    colour: "Navy",
    brand: "Bonobos",
    imageUrl: mockPicsumImageUrl("closy-chino"),
    tags: ["work", "everyday", "spring"],
  },
  {
    id: "item-dress-linen",
    name: "Midi linen dress",
    category: "dresses",
    colour: "Sage",
    brand: "& Other Stories",
    imageUrl: mockPicsumImageUrl("closy-dress"),
    tags: ["summer", "event", "linen"],
  },
  {
    id: "item-peacoat-wool",
    name: "Double-breasted peacoat",
    category: "outerwear",
    colour: "Charcoal",
    brand: "J.Crew",
    imageUrl: mockPicsumImageUrl("closy-coat"),
    tags: ["winter", "work", "wool"],
  },
  {
    id: "item-sneakers-leather",
    name: "Low leather sneakers",
    category: "shoes",
    colour: "Ecru",
    brand: "Common Projects",
    imageUrl: mockPicsumImageUrl("closy-sneaker"),
    tags: ["everyday", "minimal", "leather"],
  },
  {
    id: "item-scarf-cashmere",
    name: "Ribbed cashmere scarf",
    category: "accessories",
    colour: "Camel",
    brand: "",
    imageUrl: mockPicsumImageUrl("closy-scarf"),
    tags: ["winter", "giftable", "cashmere"],
  },
  {
    id: "item-tee-merino",
    name: "Fine merino crewneck",
    category: "tops",
    colour: "Forest green",
    brand: "Uniqlo",
    imageUrl: mockPicsumImageUrl("closy-merino"),
    tags: ["layering", "travel", "merino"],
  },
  {
    id: "item-jeans-selvedge",
    name: "Slim selvedge jeans",
    category: "bottoms",
    colour: "Indigo",
    brand: "Levi's",
    imageUrl: mockPicsumImageUrl("closy-jeans"),
    tags: ["denim", "casual", "weekend"],
  },
  {
    id: "item-loafer-suede",
    name: "Penny loafers",
    category: "shoes",
    colour: "Chocolate",
    brand: "G.H. Bass",
    imageUrl: mockPicsumImageUrl("closy-loafer"),
    tags: ["work", "leather", "classic"],
  },
];
