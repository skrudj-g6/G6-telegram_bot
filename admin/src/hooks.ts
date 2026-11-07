import { useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "./auth.tsx";
import { ApiError } from "./lib/api.ts";
import { errorText } from "./lib/format.ts";

export function messageOf(error: unknown): string {
  return errorText(error instanceof ApiError ? error.code : "network_error");
}

/** Загрузка данных с перезагрузкой при смене зависимостей; устаревшие ответы отбрасываются. */
export function useLoad<T>(path: string | null) {
  const { api } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const seq = useRef(0);

  useEffect(() => {
    if (path === null) return;
    const mine = ++seq.current;
    setLoading(true);
    api
      .request<T>("GET", path)
      .then((result) => {
        if (mine === seq.current) {
          setData(result);
          setError(null);
        }
      })
      .catch((e) => mine === seq.current && setError(messageOf(e)))
      .finally(() => mine === seq.current && setLoading(false));
  }, [api, path, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}

/** Запуск действия с блокировкой кнопок и показом ошибки. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async <R,>(fn: () => Promise<R>): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(messageOf(e));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, run, clear: () => setError(null) };
}
