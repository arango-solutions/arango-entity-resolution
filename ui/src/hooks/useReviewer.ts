import { useCallback, useEffect, useState } from "react";
import { REVIEWER_STORAGE_KEY } from "../api/client";

/**
 * Tracks the current reviewer's display name (attribution, not auth).
 * Persisted to localStorage and sent as the `X-Reviewer` header on API calls.
 */
export function useReviewer() {
  const [reviewer, setReviewerState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(REVIEWER_STORAGE_KEY);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      if (reviewer) {
        localStorage.setItem(REVIEWER_STORAGE_KEY, reviewer);
      } else {
        localStorage.removeItem(REVIEWER_STORAGE_KEY);
      }
    } catch {
      // localStorage unavailable — header simply won't be sent
    }
  }, [reviewer]);

  const setReviewer = useCallback((name: string | null) => {
    const trimmed = name?.trim();
    setReviewerState(trimmed ? trimmed : null);
  }, []);

  return { reviewer, setReviewer };
}
