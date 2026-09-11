"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: unknown;
  reload: () => void;
}

/**
 * Minimal fetch-on-mount hook with retry.
 *
 * A data-fetching library would be overkill for six endpoints; this keeps the
 * loading/error/empty contract explicit at every call site, which is what the UX
 * requirements actually turn on.
 *
 * `loading` is derived rather than stored: state is only ever written from a
 * settled promise, so the effect never calls setState synchronously and there is
 * no cascading render. The request function is held in a ref refreshed by its own
 * effect, because callers pass an inline closure that would otherwise change
 * identity every render.
 */
export function useApi<T>(
  fn: () => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<{
    key: number;
    data: T | null;
    error: unknown;
  }>({ key: -1, data: null, error: null });

  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  useEffect(() => {
    let cancelled = false;
    fnRef
      .current()
      .then((data) => {
        if (!cancelled) setResult({ key: tick, data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setResult({ key: tick, data: null, error });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  return {
    data: result.data,
    error: result.error,
    loading: result.key !== tick,
    reload,
  };
}
