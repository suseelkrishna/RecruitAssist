"use client";

/** The loading, error, and empty states every page shows, built on the brand kit. */

import { Alert, Button, Card, EmptyState, Skeleton, Stack } from "@suseelkrishna/fieryfusion-react";
import type { ReactNode } from "react";

/** Placeholder blocks shaped like the page, shown while its data loads. */
export function LoadingSkeleton({ blocks = 3, label = "Loading" }: { blocks?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      <Stack gap={16}>
        <Skeleton width="40%" height={28} />
        <div className="grid grid-2">
          {Array.from({ length: blocks }, (_, i) => (
            <Card key={i}>
              <Stack gap={10}>
                <Skeleton width="50%" height={18} />
                <Skeleton height={120} />
              </Stack>
            </Card>
          ))}
        </div>
      </Stack>
    </div>
  );
}

/** A friendly error with a retry button and an optional extra action. */
export function ErrorState({ message, onRetry, action }: { message: string; onRetry?: () => void; action?: ReactNode }) {
  return (
    <Stack gap={12}>
      <Alert tone="danger" title="This could not be loaded">
        {message}
      </Alert>
      <div className="card-actions">
        {onRetry && (
          <Button variant="secondary" onClick={onRetry}>
            Try again
          </Button>
        )}
        {action}
      </div>
    </Stack>
  );
}

/** Shown when a page or section has nothing to list. */
export function Empty({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <EmptyState title={title} description={description} action={action} />;
}
