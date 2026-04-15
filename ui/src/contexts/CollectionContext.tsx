import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";

interface CollectionContextValue {
  selectedCollection: string | null;
  setSelectedCollection: (collection: string | null) => void;
}

const CollectionContext = createContext<CollectionContextValue | null>(null);

const STORAGE_KEY = "er-ui-selected-collection";

export function CollectionProvider({ children }: { children: ReactNode }) {
  const [selectedCollection, setSelectedCollection] = useState<string | null>(
    () => {
      try {
        return localStorage.getItem(STORAGE_KEY);
      } catch {
        return null;
      }
    },
  );

  useEffect(() => {
    try {
      if (selectedCollection) {
        localStorage.setItem(STORAGE_KEY, selectedCollection);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // localStorage unavailable
    }
  }, [selectedCollection]);

  return (
    <CollectionContext.Provider
      value={{ selectedCollection, setSelectedCollection }}
    >
      {children}
    </CollectionContext.Provider>
  );
}

export function useSelectedCollection() {
  const ctx = useContext(CollectionContext);
  if (!ctx) {
    throw new Error(
      "useSelectedCollection must be used within a CollectionProvider",
    );
  }
  return ctx;
}
