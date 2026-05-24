import { useState, useRef } from "react";
import api from "../api";
import { StatusBadge } from "../components/Badge";

const SOURCES = [
  {
    key: "sap",
    label: "SAP Fuel & Procurement",
    scope: "Scope 1",
    scopeColor: "text-orange-600",
    description:
      "MB51 Material Document List flat file — semicolon-delimited, German locale. Handles diesel, petrol, natural gas, LPG. Expects movement types 201/261 (consumption) and 262 (reversal).",
    accept: ".csv,.txt,.dat",
  },
  {
    key: "utility",
    label: "Utility Electricity",
    scope: "Scope 2",
    scopeColor: "text-blue-600",
    description:
      "Portal CSV export from utility provider (EDF, British Gas, E.ON). Handles kWh and MWh. Billing periods do not need to align with calendar months.",
    accept: ".csv",
  },
  {
    key: "travel",
    label: "Corporate Travel (Concur)",
    scope: "Scope 3",
    scopeColor: "text-purple-600",
    description:
      "Concur Expense Report Extract CSV. Handles flights (calculates distance from IATA codes if not provided), hotels (room-nights), and ground transport (taxi, car rental).",
    accept: ".csv",
  },
];

function UploadCard({ source }) {
  const [file, setFile]     = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]   = useState("");
  const inputRef = useRef();

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post(`/ingest/${source.key}/`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch (e) {
      setError(e.response?.data?.error || "Upload failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
      <div>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">{source.label}</h3>
          <span className={`text-xs font-medium ${source.scopeColor}`}>{source.scope}</span>
        </div>
        <p className="text-xs text-gray-500 mt-1">{source.description}</p>
      </div>

      <div
        onClick={() => inputRef.current?.click()}
        className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:border-emerald-400 hover:bg-emerald-50 transition-colors"
      >
        <input
          ref={inputRef}
          type="file"
          accept={source.accept}
          className="hidden"
          onChange={(e) => { setFile(e.target.files[0]); setResult(null); setError(""); }}
        />
        {file ? (
          <p className="text-sm text-emerald-700 font-medium">{file.name}</p>
        ) : (
          <p className="text-sm text-gray-400">Click to select file ({source.accept})</p>
        )}
      </div>

      {file && (
        <button
          onClick={handleUpload}
          disabled={loading}
          className="w-full bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium py-2 rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? "Processing…" : "Upload & Ingest"}
        </button>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-800">Ingestion complete</span>
            <StatusBadge status={result.status} />
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="bg-green-100 rounded p-2">
              <div className="font-bold text-green-700 text-lg">{result.row_count_ok}</div>
              <div className="text-green-600">Imported</div>
            </div>
            <div className="bg-yellow-100 rounded p-2">
              <div className="font-bold text-yellow-700 text-lg">{result.row_count_warning}</div>
              <div className="text-yellow-600">Warnings</div>
            </div>
            <div className="bg-red-100 rounded p-2">
              <div className="font-bold text-red-700 text-lg">{result.row_count_error}</div>
              <div className="text-red-600">Errors</div>
            </div>
          </div>
          {result.error_summary?.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-red-600 font-medium">
                {result.error_summary.length} parse error(s)
              </summary>
              <ul className="mt-1 space-y-1 text-gray-600">
                {result.error_summary.slice(0, 10).map((e, i) => (
                  <li key={i} className="bg-red-50 rounded px-2 py-1">
                    Row {e.row}: {e.errors?.join("; ")}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default function Ingest() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Ingest Data</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Upload source files for parsing and normalization. Each file is stored verbatim for audit purposes.
        </p>
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        {SOURCES.map((s) => <UploadCard key={s.key} source={s} />)}
      </div>
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
        <strong>Sample files</strong> are included in <code>sample_data/</code> — download and upload them to try the platform.
      </div>
    </div>
  );
}
