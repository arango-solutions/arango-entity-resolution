import { EntityResolver } from "../components/resolve";

export function ResolvePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">Resolve Entity</h1>
        <p className="mt-1 text-sm text-gray-500">
          Submit a record for matching against a collection. Test single-record
          resolution without running a full pipeline.
        </p>
      </div>
      <EntityResolver />
    </div>
  );
}
