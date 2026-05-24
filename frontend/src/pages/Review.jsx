import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../api";
import { ScopeBadge, StatusBadge, SuspiciousBadge } from "../components/Badge";

function RecordModal({ record, onClose, onAction }) {
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState([]);
  const [editQty, setEditQty] = useState(record.quantity_normalized);

  useEffect(() => {
    api.get(`/records/${record.id}/audit_trail/`).then((r) => setAudit(r.data));
  }, [record.id]);

  async function doAction(action) {
    setLoading(true);
    try {
      await api.post(`/records/${record.id}/${action}/`, { note });
      onAction();
      onClose();
    } finally {
      setLoading(false);
    }
  }

  async function saveEdit() {
    setLoading(true);
    try {
      await api.patch(`/records/${record.id}/`, { quantity_normalized: editQty, note });
      onAction();
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="p-5 border-b border-gray-200 flex items-start justify-between">
          <div>
            <h2 className="font-semibold text-gray-900">{record.description}</h2>
            <div className="flex gap-2 mt-1">
              <ScopeBadge scope={record.scope} />
              <StatusBadge status={record.review_status} />
              {record.is_suspicious && <SuspiciousBadge />}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
        </div>

        <div className="p-5 space-y-4">
          {/* Key fields */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ["Category",    record.category],
              ["Date",        record.activity_date],
              ["Location",    record.location_resolved || record.location_raw],
              ["Source type", record.source_type_display],
              ["Original qty", `${record.quantity_original} ${record.unit_original}`],
              ["Normalised",  `${record.quantity_normalized} ${record.unit_normalized}`],
              ["Factor",      `${record.emission_factor} kgCO₂e/${record.unit_normalized} (${record.emission_factor_source})`],
              ["CO₂e",        `${Number(record.co2e_kg).toLocaleString()} kgCO₂e`],
            ].map(([k, v]) => (
              <div key={k} className="bg-gray-50 rounded p-2">
                <p className="text-xs text-gray-500">{k}</p>
                <p className="font-medium text-gray-900 break-words">{v}</p>
              </div>
            ))}
          </div>

          {/* Suspicion reasons */}
          {record.suspicion_reasons?.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded p-3">
              <p className="text-xs font-semibold text-red-700 mb-1">Suspicion flags</p>
              <ul className="text-xs text-red-600 space-y-0.5">
                {record.suspicion_reasons.map((r, i) => <li key={i}>• {r}</li>)}
              </ul>
            </div>
          )}

          {/* Raw source data */}
          {record.raw_data && (
            <details className="text-xs">
              <summary className="cursor-pointer text-gray-500 font-medium">Raw source row</summary>
              <pre className="bg-gray-50 rounded p-3 mt-2 overflow-x-auto text-gray-700">
                {JSON.stringify(record.raw_data, null, 2)}
              </pre>
            </details>
          )}

          {/* Edit quantity (only for unlocked records) */}
          {!record.is_locked && (
            <div className="border-t border-gray-100 pt-4">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Correct normalised quantity
              </label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={editQty}
                  onChange={(e) => setEditQty(e.target.value)}
                  className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm"
                />
                <button
                  onClick={saveEdit}
                  disabled={loading || String(editQty) === String(record.quantity_normalized)}
                  className="bg-gray-800 text-white text-xs px-3 py-1.5 rounded disabled:opacity-40"
                >
                  Save edit
                </button>
              </div>
            </div>
          )}

          {/* Note */}
          <textarea
            placeholder="Add a review note…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm resize-none"
          />

          {/* Actions */}
          {!record.is_locked && (
            <div className="flex gap-2">
              <button
                onClick={() => doAction("approve")}
                disabled={loading}
                className="flex-1 bg-emerald-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                onClick={() => doAction("flag")}
                disabled={loading}
                className="flex-1 bg-orange-500 text-white py-2 rounded-lg text-sm font-medium hover:bg-orange-600 disabled:opacity-50"
              >
                Flag
              </button>
              <button
                onClick={() => doAction("reject")}
                disabled={loading}
                className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}

          {record.is_locked && (
            <p className="text-sm text-gray-400 text-center bg-gray-50 rounded p-2">
              This record is locked for audit.
            </p>
          )}

          {/* Audit trail */}
          {audit.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-600 mb-2">Audit trail</p>
              <div className="space-y-1.5">
                {audit.map((log) => (
                  <div key={log.id} className="flex gap-2 text-xs text-gray-600">
                    <span className="text-gray-400 shrink-0">{new Date(log.timestamp).toLocaleString()}</span>
                    <span className="font-medium">{log.actor_username}</span>
                    <span className="capitalize">{log.action_display}</span>
                    {log.note && <span className="text-gray-400">— {log.note}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Review() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  const filters = {
    status:      searchParams.get("status") || "",
    scope:       searchParams.get("scope") || "",
    source_type: searchParams.get("source_type") || "",
    suspicious:  searchParams.get("suspicious") || "",
  };

  const load = useCallback(() => {
    setLoading(true);
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
    api.get("/records/", { params }).then((r) => setRecords(r.data.results ?? r.data)).finally(() => setLoading(false));
  }, [searchParams]);

  useEffect(() => { load(); }, [load]);

  function setFilter(key, value) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value); else next.delete(key);
    setSearchParams(next);
    setSelectedIds(new Set());
  }

  function toggleSelect(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function bulkApprove() {
    setBulkLoading(true);
    await api.post("/records/bulk_approve/", { ids: Array.from(selectedIds) });
    setSelectedIds(new Set());
    load();
    setBulkLoading(false);
  }

  const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });

  return (
    <div className="space-y-5">
      {selected && (
        <RecordModal record={selected} onClose={() => setSelected(null)} onAction={load} />
      )}

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <p className="text-sm text-gray-500 mt-0.5">Approve, reject, or flag records before they are locked for audit.</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        {[
          { key: "status", label: "Status", opts: ["pending", "approved", "rejected", "flagged"] },
          { key: "scope",  label: "Scope",  opts: ["1", "2", "3"] },
        ].map(({ key, label, opts }) => (
          <select
            key={key}
            value={filters[key]}
            onChange={(e) => setFilter(key, e.target.value)}
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm bg-white"
          >
            <option value="">All {label}s</option>
            {opts.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        ))}
        <label className="flex items-center gap-1.5 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={filters.suspicious === "true"}
            onChange={(e) => setFilter("suspicious", e.target.checked ? "true" : "")}
            className="accent-emerald-600"
          />
          Suspicious only
        </label>
        {selectedIds.size > 0 && (
          <button
            onClick={bulkApprove}
            disabled={bulkLoading}
            className="ml-auto bg-emerald-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {bulkLoading ? "Approving…" : `Approve ${selectedIds.size} selected`}
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <p className="text-center text-gray-400 py-10">Loading…</p>
        ) : records.length === 0 ? (
          <p className="text-center text-gray-400 py-10">No records match these filters.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="w-8 px-3 py-2.5"></th>
                {["Source", "Date", "Location", "Description", "CO₂e (kg)", "Status", ""].map((h) => (
                  <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {records.map((rec) => (
                <tr
                  key={rec.id}
                  className={`hover:bg-gray-50 cursor-pointer ${rec.is_suspicious ? "bg-red-50 hover:bg-red-100" : ""}`}
                  onClick={() => setSelected(rec)}
                >
                  <td className="px-3 py-2.5" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(rec.id)}
                      onChange={() => toggleSelect(rec.id)}
                      className="accent-emerald-600"
                      disabled={rec.is_locked || rec.review_status === "approved"}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <ScopeBadge scope={rec.scope} />
                  </td>
                  <td className="px-3 py-2.5 text-gray-700">{rec.activity_date}</td>
                  <td className="px-3 py-2.5 text-gray-700 max-w-[140px] truncate">{rec.location_resolved || rec.location_raw}</td>
                  <td className="px-3 py-2.5 text-gray-900 max-w-[180px] truncate">{rec.description}</td>
                  <td className="px-3 py-2.5 font-medium text-gray-900">{fmt(rec.co2e_kg)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      <StatusBadge status={rec.review_status} />
                      {rec.is_suspicious && <SuspiciousBadge />}
                      {rec.is_locked && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">Locked</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <button className="text-emerald-600 hover:text-emerald-800 text-xs font-medium">Review →</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
