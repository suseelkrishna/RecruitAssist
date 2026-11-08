/**
 * A tiny bar per stage showing active candidates in it, for the jobs table. The bar heights
 * are drawn from the API's counts; the counts are also read out for screen readers.
 */

const MAX_HEIGHT = 28;

export function MiniFunnel({ stages }: { stages: { stage: string; count: number }[] }) {
  const tallest = Math.max(1, ...stages.map((s) => s.count));
  const label = stages.map((s) => `${s.stage} ${s.count}`).join(", ");
  return (
    <span className="mini-funnel" role="img" aria-label={`Active candidates by stage: ${label}`} title={label}>
      {stages.map((s) => (
        <span key={s.stage} style={{ height: Math.max(2, (s.count / tallest) * MAX_HEIGHT) }} />
      ))}
    </span>
  );
}
