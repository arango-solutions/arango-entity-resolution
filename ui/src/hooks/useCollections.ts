import { useQuery } from "@tanstack/react-query";
import { getCollections, getCollectionProfile } from "../api/collections";

export function useCollections() {
  return useQuery({
    queryKey: ["collections"],
    queryFn: getCollections,
  });
}

export function useCollectionProfile(name: string | null) {
  return useQuery({
    queryKey: ["collection-profile", name],
    queryFn: () => getCollectionProfile(name!),
    enabled: !!name,
  });
}
