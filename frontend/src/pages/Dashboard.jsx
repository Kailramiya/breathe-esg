import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api";
import { StatusBadge } from "../components/Badge";

function StatCard({ label, value, sub, color = "emerald" }) {
  const colors = {
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    orange:  "bg-orange-50 border-orange-200 text-orange-700",
    blue:    "bg-blue-50 border-blue-200 text-blue-700",
    purple:  "bg-purple-50 border-purple-200 text-purple-700",
    red:     "bg-red-50 border-red-200 text-red-700",
    yellow:  "bg-yellow-50 border-yellow-200 text-yellow-700",
  };
  return (
    <div className={`rounded-xl border p-5 ${colors[color]}`}>
      <p className="text-sm font-medium opacity-70">{label}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
      {sub && <p className="text-xs opacity-60 mt-1">{sub}</p>}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/dashboard/").then((r) => setData(r.data)).finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500 mt-8 text-center">Loading…</p>;
  if (!data)   return <p className="text-red-500 mt-8 text-center">Failed to load dashboard.</p>;

  const fmt = (n) => n?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? "—";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-0.5">Carbon data overview — ACME Manufacturing Ltd</p>
      </div>

      {/* Total + Scope breakdown */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label="Total CO₂e"
          value={`${fmt(data.total_co2e_kg / 1000)} t`}
          sub="tonnes CO₂ equivalent"
          color="emerald"
        />
        <StatCard
          label="Scope 1"
          value={`${fmt(data.scope_totals?.scope_1 / 1000)} t`}
          sub="Direct combustion"
          color="orange"
        />
        <StatCard
          label="Scope 2"
          value={`${fmt(data.scope_totals?.scope_2 / 1000)} t`}
          sub="Purchased electricity"
          color="blue"
        />
        <StatCard
          label="Scope 3"
          value={`${fmt(data.scope_totals?.scope_3 / 1000)} t`}
          sub="Business travel"
          color="purple"
        />
      </div>

      {/* Review status */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pending Review"   value={data.pending_review} color="yellow" />
        <StatCard label="Flagged"          value={data.flagged}        color="red"    />
        <StatCard label="Suspicious"       value={data.suspicious}     color="red"    />
        <StatCard label="Approved"         value={data.approved}       color="emerald"/>
      </div>

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link
          to="/review?status=pending"
          className="bg-emerald-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-700"
        >
          Review pending ({data.pending_review})
        </Link>
        <Link
          to="/ingest"
          className="border border-emerald-600 text-emerald-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-emerald-50"
        >
          Upload new data
        </Link>
      </div>

      {/* Recent jobs */}
      <div>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Recent ingestion jobs</h2>
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {data.recent_jobs.length === 0 ? (
            <p className="text-center text-gray-400 py-8">No jobs yet — upload your first file.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  {["File", "Source", "Status", "Rows OK", "Errors", "Date"].map((h) => (
                    <th key={h} className="px-4 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.recent_jobs.map((job) => (
                  <tr key={job.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5 font-medium text-gray-900 max-w-xs truncate">{job.original_filename}</td>
                    <td className="px-4 py-2.5 text-gray-600">{job.source_type_display}</td>
                    <td className="px-4 py-2.5"><StatusBadge status={job.status} /></td>
                    <td className="px-4 py-2.5 text-gray-700">{job.row_count_ok}</td>
                    <td className="px-4 py-2.5 text-red-600 font-medium">{job.row_count_error || "—"}</td>
                    <td className="px-4 py-2.5 text-gray-500">{new Date(job.ingested_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
