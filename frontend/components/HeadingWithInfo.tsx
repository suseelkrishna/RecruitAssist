/**
 * A heading followed by its InfoTip. This is the one place explanations go: the heading
 * stays short, and anything that explains the data or the method behind it opens from the
 * (i) right after it. Without `info` it renders the heading alone.
 */

import type { ReactNode } from "react";
import { InfoTip } from "@/components/InfoTip";

export function HeadingWithInfo({ as: Tag = "h2", title, info, id, className }: {
  as?: "h1" | "h2" | "h3";
  title: string;
  info?: ReactNode;
  id?: string;
  className?: string;
}) {
  if (!info)
    return (
      <Tag id={id} className={className}>
        {title}
      </Tag>
    );
  return (
    <div className="heading-with-info">
      <Tag id={id} className={className}>
        {title}
      </Tag>
      <InfoTip title={title}>{info}</InfoTip>
    </div>
  );
}
