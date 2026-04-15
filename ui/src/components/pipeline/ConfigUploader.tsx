import { useState, useRef, type ChangeEvent } from "react";
import { Upload, FileText, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { validateConfig, type ValidationResult } from "../../api/config";

interface ConfigUploaderProps {
  onConfigLoaded: (config: Record<string, unknown>) => void;
}

export function ConfigUploader({ onConfigLoaded }: ConfigUploaderProps) {
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [pasteValue, setPasteValue] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [configSummary, setConfigSummary] = useState<Record<string, unknown> | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function parseAndLoad(text: string, source: string) {
    setParseError(null);
    setValidation(null);
    setConfigSummary(null);
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      setConfigSummary(parsed);
      setFileName(source);
      onConfigLoaded(parsed);
    } catch {
      setParseError("Invalid JSON. Please check the format and try again.");
    }
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        parseAndLoad(reader.result, file.name);
      }
    };
    reader.readAsText(file);
  }

  function handlePasteApply() {
    if (!pasteValue.trim()) return;
    parseAndLoad(pasteValue, "pasted config");
  }

  async function handleValidate() {
    if (!configSummary) return;
    setIsValidating(true);
    try {
      const result = await validateConfig(configSummary);
      setValidation(result);
    } catch (err) {
      setValidation({
        valid: false,
        errors: [err instanceof Error ? err.message : "Validation request failed"],
        warnings: [],
      });
    } finally {
      setIsValidating(false);
    }
  }

  const entityType: string | null =
    configSummary && typeof configSummary["entity_type"] === "string"
      ? (configSummary["entity_type"] as string)
      : null;
  const configCollection: string | null =
    configSummary && typeof configSummary["collection"] === "string"
      ? (configSummary["collection"] as string)
      : null;
  const blocking =
    configSummary && typeof configSummary["blocking"] === "object" && configSummary["blocking"]
      ? (configSummary["blocking"] as Record<string, unknown>)
      : null;
  const blockingStrategy: string | null =
    blocking && typeof blocking["strategy"] === "string"
      ? (blocking["strategy"] as string)
      : null;

  return (
    <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-gray-500" />
        <h3 className="text-sm font-medium text-gray-900">Pipeline Config</h3>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setMode("file")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium ${
            mode === "file"
              ? "bg-indigo-100 text-indigo-700"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Upload File
        </button>
        <button
          onClick={() => setMode("paste")}
          className={`rounded-md px-3 py-1.5 text-xs font-medium ${
            mode === "paste"
              ? "bg-indigo-100 text-indigo-700"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Paste Config
        </button>
      </div>

      {mode === "file" ? (
        <div>
          <input
            ref={fileRef}
            type="file"
            accept=".json,.yaml,.yml"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileRef.current?.click()}
            className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500 transition hover:border-indigo-400 hover:text-indigo-600"
          >
            <Upload className="h-5 w-5" />
            {fileName ? fileName : "Choose .json or .yaml file"}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={pasteValue}
            onChange={(e) => setPasteValue(e.target.value)}
            placeholder='Paste JSON config here...\n{\n  "entity_type": "company",\n  "collection": "companies",\n  ...\n}'
            rows={6}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs text-gray-800 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            onClick={handlePasteApply}
            disabled={!pasteValue.trim()}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Parse Config
          </button>
        </div>
      )}

      {parseError && (
        <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
          {parseError}
        </div>
      )}

      {configSummary && (
        <div className="space-y-3">
          <div className="rounded-md bg-gray-50 p-3 text-xs text-gray-700">
            <div className="grid grid-cols-2 gap-2">
              {entityType && (
                <>
                  <span className="font-medium">Entity Type:</span>
                  <span>{entityType}</span>
                </>
              )}
              {configCollection && (
                <>
                  <span className="font-medium">Collection:</span>
                  <span>{configCollection}</span>
                </>
              )}
              {blockingStrategy && (
                <>
                  <span className="font-medium">Blocking:</span>
                  <span>{blockingStrategy}</span>
                </>
              )}
            </div>
          </div>

          <button
            onClick={handleValidate}
            disabled={isValidating}
            className="rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
          >
            {isValidating ? "Validating..." : "Validate Config"}
          </button>

          {validation && (
            <div
              className={`rounded-md p-3 text-xs ${
                validation.valid
                  ? "bg-green-50 text-green-700"
                  : "bg-red-50 text-red-700"
              }`}
            >
              <div className="flex items-center gap-1.5 font-medium">
                {validation.valid ? (
                  <>
                    <CheckCircle className="h-3.5 w-3.5" /> Config is valid
                  </>
                ) : (
                  <>
                    <XCircle className="h-3.5 w-3.5" /> Config has errors
                  </>
                )}
              </div>
              {validation.errors.length > 0 && (
                <ul className="mt-2 list-inside list-disc space-y-1">
                  {validation.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
              {validation.warnings.length > 0 && (
                <div className="mt-2 space-y-1 text-amber-700">
                  {validation.warnings.map((warn, i) => (
                    <p key={i} className="flex items-start gap-1">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                      {warn}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
