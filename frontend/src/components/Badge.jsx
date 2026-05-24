const SCOPE_COLORS = {
  "1": "bg-orange-100 text-orange-800",
  "2": "bg-blue-100 text-blue-800",
  "3": "bg-purple-100 text-purple-800",
};

const STATUS_COLORS = {
  pending:  "bg-yellow-100 text-yellow-800",
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  flagged:  "bg-orange-100 text-orange-800",
  completed:"bg-green-100 text-green-800",
  failed:   "bg-red-100 text-red-800",
  processing:"bg-blue-100 text-blue-800",
};

export function ScopeBadge({ scope }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${SCOPE_COLORS[scope] || "bg-gray-100 text-gray-700"}`}>
      Scope {scope}
    </span>
  );
}

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${STATUS_COLORS[status] || "bg-gray-100 text-gray-700"}`}>
      {status?.replace("_", " ")}
    </span>
  );
}

export function SuspiciousBadge() {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
      ⚠ Suspicious
    </span>
  );
}
