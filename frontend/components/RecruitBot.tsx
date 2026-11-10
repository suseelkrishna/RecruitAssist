/**
 * RecruitBot, the face of the assistant on the Ask page: a friendly robot head drawn as an
 * outline, with an antenna spark, side ears, round eyes, and a small smile. It uses the brand
 * kit's copper token so it follows the theme. It is decorative: the message beside it
 * already says who is speaking.
 */

export function RecruitBot({ size = 32 }: { size?: number }) {
  return (
    <svg
      className="recruitbot"
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      stroke="var(--ff-copper)"
      strokeWidth="2.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* Antenna with a spark on top. */}
      <path d="M24 13V8.5" />
      <path d="M24 3.5l1.2 2.3 2.3 1.2-2.3 1.2-1.2 2.3-1.2-2.3-2.3-1.2 2.3-1.2z" strokeWidth="1.6" />
      {/* Head. */}
      <rect x="9" y="13" width="30" height="27" rx="10" />
      {/* Ears. */}
      <path d="M5 23v8M43 23v8" />
      {/* Eyes and a small smile. */}
      <circle cx="18.5" cy="25" r="2.6" />
      <circle cx="29.5" cy="25" r="2.6" />
      <path d="M19.5 32.5q4.5 3 9 0" />
    </svg>
  );
}
