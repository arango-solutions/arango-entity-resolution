import { ConfigBuilder } from "../components/config";

export function ConfigPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">
          Pipeline Config Builder
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          A guided, visual alternative to writing YAML. Configure blocking
          strategies, similarity weights, clustering backends, and LLM curation
          settings.
        </p>
      </div>
      <ConfigBuilder />
    </div>
  );
}
