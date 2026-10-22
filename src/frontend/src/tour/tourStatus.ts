/**
 * Whether an account has finished or skipped a tour, so each tour only
 * starts by itself the first time. Saved in the account's Supabase user
 * metadata, so it follows the student or instructor across computers.
 */
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabaseClient";

export type TourName = "student" | "instructor";
type TourStatus = "completed" | "skipped";

const metadataKey = (tour: TourName) => `${tour}_tour_status`;

// True once this account has finished or skipped the tour. With no login
// there is no account to save to, so the tour doesn't start by itself.
export const hasSeenTour = (
  session: Session | null,
  tour: TourName,
): boolean => {
  if (!session) return true;
  const status = session.user.user_metadata?.[metadataKey(tour)];
  return status === "completed" || status === "skipped";
};

// Saves the result to the account. Other metadata (e.g. the role) is kept,
// since Supabase merges these fields into what is already there.
export const saveTourStatus = async (tour: TourName, status: TourStatus) => {
  const { error } = await supabase.auth.updateUser({
    data: { [metadataKey(tour)]: status },
  });
  if (error) console.warn("Could not save tour status:", error.message);
};
