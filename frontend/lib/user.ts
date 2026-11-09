/**
 * The current demo user, kept in the demo_user cookie. This is a demo feature, not sign-in:
 * the backend turns the ID into a role and a job scope on every request.
 */

const COOKIE = "demo_user";
const ONE_WEEK_SECONDS = 60 * 60 * 24 * 7;

/** The demo user ID from the cookie, or null when none has been picked. */
export function getDemoUser(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${COOKIE}=`));
  return match ? decodeURIComponent(match.slice(COOKIE.length + 1)) : null;
}

/** Remember the picked demo user for a week on this browser. */
export function setDemoUser(userId: string): void {
  document.cookie = `${COOKIE}=${encodeURIComponent(userId)}; path=/; max-age=${ONE_WEEK_SECONDS}; samesite=lax`;
}

/** Forget the demo user, so the landing page asks again. */
export function clearDemoUser(): void {
  document.cookie = `${COOKIE}=; path=/; max-age=0; samesite=lax`;
}
