import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export const COLORS = ["gray", "blue", "green", "orange", "red", "purple", "pink", "teal"] as const;
export type Color = (typeof COLORS)[number];

export interface Tag {
  id: string;
  name: string;
  color: Color;
  servers: number;
  customers: number;
}

export const useTags = () => useQuery({ queryKey: ["tags"], queryFn: () => api<Tag[]>("/tags"), staleTime: 30_000 });

/** Class names for a coloured tag/badge: tagClass("web") → "colored c-blue" (grey when the tag is unknown). */
export function useTagClass() {
  const colors = new Map((useTags().data ?? []).map((t) => [t.name.toLowerCase(), t.color]));
  return (name: string) => `colored c-${colors.get(name.toLowerCase()) ?? "gray"}`;
}

export const colorClass = (color?: string) => `colored c-${color || "gray"}`;

export function useTagActions() {
  const qc = useQueryClient();
  const done = () => {
    for (const key of ["tags", "agents", "customers", "server-groups", "categories"]) qc.invalidateQueries({ queryKey: [key] });
  };
  const add = useMutation({
    mutationFn: (b: { name: string; color: Color }) => api<Tag>("/tags", { method: "POST", body: b }),
    onSuccess: done,
  });
  const update = useMutation({
    mutationFn: ({ id, ...b }: { id: string; name: string; color: Color }) => api<Tag>(`/tags/${id}`, { method: "PUT", body: b }),
    onSuccess: done,
  });
  const merge = useMutation({
    mutationFn: ({ id, into }: { id: string; into: string }) => api<Tag>(`/tags/${id}/merge`, { method: "POST", body: { into } }),
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: (id: string) => api<void>(`/tags/${id}`, { method: "DELETE" }), onSuccess: done });
  return { add, update, merge, remove };
}
