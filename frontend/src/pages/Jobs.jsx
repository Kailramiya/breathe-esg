import { useEffect, useState } from "react";
import api from "../api";
import { StatusBadge } from "../components/Badge";

export default function Jobs() {
  const [jobs, setJobs]     = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    api.get("/jobs/").then((r) => setJobs(r.data.results ?? r.data)).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Job History</h1>
        <p className="text-sm text-gray-500 mt-0.5">All ingestion jobs for this tenant. Original files are preserved for audit.</p>
      </div>

      {loading ? (
        <p className="text-center text-gray-400 py-10">Loading…</p>
      ) : jobs.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg font-medium">No jobs yet</p>
          <p className="text-sm mt-1">Upload your first data file on the Ingest page.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <div key={job.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div
                className="flex items-center gap-4 px-5 py-3.5 cursor-pointer hover:bg-gray-50"
                onClick={() => setExpanded(expanded === job.id ? null : job.id)}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 truncate">{job.original_filename}</p>
                  <p className="text-xs text-gray-500">{job.source_type_display}</p>
                </div>
                <StatusBadge status={job.status} />
                <div className="flex gap-4 text-sm text-center">
                  <div>
                    <p className="font-bold text-green-600">{job.row_count_ok}</p>
                    <p className="text-xs text-gray-400">OK</p>
                  </div>
                  <div>
                    <p className="font-bold text-yellow-600">{job.row_count_warning}</p>
                    <p className="text-xs text-gray-400">Warn</p>
                  </div>
                  <div>
                    <p className="font-bold text-red-600">{job.row_count_error}</p>
                    <p className="text-xs text-gray-400">Error</p>
                  </div>
                </div>
                <p className="text-xs text-gray-400 w-32 text-right">
                  {new Date(job.ingested_at).toLocaleString()}
                </p>
                <span className="text-gray-400 text-sm">{expanded === job.id ? "▲" : "▼"}</span>
              </div>

              {expanded === job.id && job.error_summary?.length > 0 && (
                <div className="border-t border-gray-100 px-5 py-4 bg-red-50">
                  <p className="text-sm font-medium text-red-700 mb-2">Parse errors ({job.error_summary.length})</p>
                  <div className="space-y-1 max-h-48 overflow-y-auto">
                    {job.error_summary.map((e, i) => (
                      <div key={i} className="text-xs bg-white rounded px-3 py-1.5 border border-red-100">
                        <span className="font-medium text-gray-700">Row {e.row}:</span>{" "}
                        <span className="text-red-600">{e.errors?.join("; ")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {expanded === job.id && (!job.error_summary || job.error_summary.length === 0) && (
                <div className="border-t border-gray-100 px-5 py-3 text-sm text-gray-500 bg-green-50">
                  All rows parsed successfully.
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
