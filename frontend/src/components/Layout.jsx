import { Outlet, NavLink, useNavigate } from "react-router-dom";

const nav = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/ingest",    label: "Ingest Data" },
  { to: "/review",    label: "Review Queue" },
  { to: "/jobs",      label: "Job History" },
];

export default function Layout() {
  const navigate = useNavigate();

  function logout() {
    localStorage.clear();
    navigate("/login");
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-emerald-700 text-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-bold text-xl tracking-tight">Breathe ESG</span>
            <span className="text-emerald-200 text-sm">Data Review Platform</span>
          </div>
          <nav className="flex items-center gap-1">
            {nav.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-white text-emerald-800"
                      : "text-emerald-100 hover:bg-emerald-600"
                  }`
                }
              >
                {n.label}
              </NavLink>
            ))}
            <button
              onClick={logout}
              className="ml-4 px-3 py-1.5 rounded text-sm text-emerald-200 hover:text-white hover:bg-emerald-600"
            >
              Sign out
            </button>
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
