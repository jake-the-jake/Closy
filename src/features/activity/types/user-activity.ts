export const USER_ACTIVITY_TYPES = ["follow", "like", "comment"] as const;

export type UserActivityType = (typeof USER_ACTIVITY_TYPES)[number];

export function isUserActivityType(value: string): value is UserActivityType {
  return (USER_ACTIVITY_TYPES as readonly string[]).includes(value);
}

/** Row as returned from Supabase (`user_activity`). */
export type UserActivityRow = {
  id: string;
  recipientUserId: string;
  actorUserId: string;
  activityType: UserActivityType;
  publishedOutfitId: string | null;
  commentId: string | null;
  createdAt: string;
  /** Null = unread for the signed-in recipient. */
  readAt: string | null;
};

/** Hydrated for the activity list UI. */
export type UserActivityListItem = UserActivityRow & {
  actorDisplayName: string;
  actorAvatarUrl: string | null;
  publishedOutfitName: string | null;
};
