import * as ImagePicker from "expo-image-picker";

/**
 * Outcome of opening the device photo library for one wardrobe image.
 * Caller should ignore state updates on `canceled`; handle `permission_denied` in UI if needed.
 */
export type PickWardrobeImageResult =
  | { status: "picked"; uri: string }
  | { status: "canceled" }
  | { status: "permission_denied" }
  | { status: "error" };

const LIBRARY_OPTIONS: ImagePicker.ImagePickerOptions = {
  mediaTypes: ["images"],
  allowsEditing: false,
  quality: 0.85,
};

export async function pickWardrobeImageFromLibrary(): Promise<PickWardrobeImageResult> {
  try {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      return { status: "permission_denied" };
    }

    const result = await ImagePicker.launchImageLibraryAsync(LIBRARY_OPTIONS);

    if (result.canceled || !result.assets?.length) {
      return { status: "canceled" };
    }

    const uri = result.assets[0]?.uri;
    if (!uri?.trim()) {
      return { status: "canceled" };
    }

    return { status: "picked", uri: uri.trim() };
  } catch {
    return { status: "error" };
  }
}
