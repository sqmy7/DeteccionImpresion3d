import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../services/apiClient";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (update: T | null | ((current: T | null) => T | null)) => void;
}

/** Loads data with the session token whenever `deps` change; stale answers from an earlier call
 * are dropped. `fetcher` returning null skips the call (e.g. while an id is unknown). */
export function useApi<T>(fetcher: (token: string) => Promise<T> | null, deps: DependencyList): ApiState<T> {
  const { token } = useAuth();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const callId = useRef(0);

  useEffect(() => {
    if (!token) return;
    const promise = fetcher(token);
    if (promise === null) {
      setLoading(false);
      return;
    }
    const id = ++callId.current;
    setLoading(true);
    promise
      .then((result) => {
        if (id !== callId.current) return;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (id !== callId.current) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar la información.");
      })
      .finally(() => {
        if (id === callId.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, version, ...deps]);

  const reload = useCallback(() => setVersion((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}
