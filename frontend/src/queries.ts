import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
export function useApi<T>(
  path: string | null,
  interval: number | false | ((data: T | undefined) => number | false) = false,
) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: ({ signal }) => api<T>(path!, {}, signal),
    enabled: path !== null,
    staleTime: path?.startsWith("/history") ? Infinity : 3000,
    refetchInterval: (q) =>
      typeof interval === "function" ? interval(q.state.data) : interval,
  });
}
