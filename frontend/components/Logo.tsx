/**
 * The RecruitAssist mark: an "RA" monogram on a copper tile, drawn with the brand kit's accent
 * tokens so it follows the theme. `withName` adds the product name beside it.
 */

export function Logo({ size = 32, withName = false }: { size?: number; withName?: boolean }) {
  return (
    <span className="logo">
      <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="RecruitAssist" focusable="false">
        <rect width="32" height="32" rx="8" fill="var(--ff-accent)" />
        <text
          x="16"
          y="21.5"
          textAnchor="middle"
          fontFamily="var(--ff-display)"
          fontWeight="700"
          fontSize="14"
          letterSpacing="-0.3"
          fill="var(--ff-on-accent)"
        >
          RA
        </text>
      </svg>
      {withName && <span className="logo-name">RecruitAssist</span>}
    </span>
  );
}
