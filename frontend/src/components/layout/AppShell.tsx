import { Activity, BarChart3, Bell, LayoutDashboard, LogOut, Menu, Printer as PrinterIcon, X } from "lucide-react";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Skeleton } from "../ui";
import { PRINTER_STATUS } from "../../config/status";
import { usePrinters } from "../../context/PrintersContext";
import { useActiveAlertsCount } from "../../hooks/useActiveAlertsCount";
import { useAuth } from "../../hooks/useAuth";
import { useWebSocket } from "../../hooks/useWebSocket";

const DOT_COLORS = { neutral: "bg-faint", ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", accent: "bg-accent", info: "bg-info" };

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-accent">
        <Activity size={18} strokeWidth={2.5} />
      </span>
      <span className="text-base font-semibold tracking-tight text-fg">PrintWatch</span>
    </Link>
  );
}

function ConnectionStatus({ compact = false }: { compact?: boolean }) {
  const { connected } = useWebSocket();
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted" title="Conexión en vivo con el servidor">
      <span className={`h-2 w-2 rounded-full ${connected ? "bg-ok" : "animate-pulse bg-danger"}`} />
      {!compact && (connected ? "En vivo" : "Reconectando…")}
    </span>
  );
}

function NavItem({ to, icon, children, end, badge }: { to: string; icon: ReactNode; children: ReactNode; end?: boolean; badge?: number }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors ${
          isActive ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
        }`
      }
    >
      <span className="shrink-0">{icon}</span>
      <span className="flex-1 truncate">{children}</span>
      {badge ? (
        <span className="rounded-full bg-danger px-1.5 text-[11px] font-semibold tabular text-white">{badge}</span>
      ) : null}
    </NavLink>
  );
}

function SidebarContent({ alerts }: { alerts: number }) {
  const { printers } = usePrinters();
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="flex h-full w-full flex-col">
      <div className="px-4 py-4">
        <Logo />
      </div>
      <nav className="flex flex-col gap-0.5 px-2" aria-label="Principal">
        <NavItem to="/" end icon={<LayoutDashboard size={17} />}>
          Panel general
        </NavItem>
        <NavItem to="/analytics" icon={<BarChart3 size={17} />}>
          Analítica
        </NavItem>
        <NavItem to="/alerts" icon={<Bell size={17} />} badge={alerts}>
          Alertas
        </NavItem>
      </nav>

      <p className="mt-6 px-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-faint">Impresoras</p>
      <nav className="flex flex-col gap-0.5 overflow-y-auto px-2" aria-label="Impresoras">
        {printers.map((printer) => {
          const status = PRINTER_STATUS[printer.last_known_status];
          const active = location.pathname.startsWith(`/printers/${printer.id}/`);
          return (
            <Link
              key={printer.id}
              to={`/printers/${printer.id}/live`}
              className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                active ? "bg-surface-3 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
              }`}
            >
              <PrinterIcon size={17} className="shrink-0" />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{printer.name}</span>
                <span className="flex items-center gap-1.5 text-xs text-faint">
                  <span className={`h-1.5 w-1.5 rounded-full ${DOT_COLORS[status.tone]}`} />
                  {status.label}
                </span>
              </span>
            </Link>
          );
        })}
        {printers.length === 0 && <p className="px-2.5 py-2 text-xs text-faint">Sin impresoras registradas.</p>}
      </nav>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-line px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-fg">{user?.username}</p>
          <ConnectionStatus />
        </div>
        <button onClick={logout} title="Cerrar sesión" aria-label="Cerrar sesión" className="rounded-md p-2 text-muted hover:bg-surface-2 hover:text-fg">
          <LogOut size={17} />
        </button>
      </div>
    </div>
  );
}

/** Menu on the left on wide screens; on phones, a top bar with a drawer. */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();
  const alerts = useActiveAlertsCount();

  useEffect(() => setDrawerOpen(false), [location.pathname]);

  return (
    <div className="min-h-screen lg:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-line bg-surface lg:flex">
        <SidebarContent alerts={alerts} />
      </aside>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menú">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawerOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] border-r border-line bg-surface">
            <button
              onClick={() => setDrawerOpen(false)}
              aria-label="Cerrar menú"
              className="absolute right-2 top-3 rounded-md p-2 text-muted hover:text-fg"
            >
              <X size={18} />
            </button>
            <SidebarContent alerts={alerts} />
          </aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-canvas/90 px-4 backdrop-blur lg:hidden">
        <button onClick={() => setDrawerOpen(true)} aria-label="Abrir menú" className="-ml-1 rounded-md p-2 text-muted hover:text-fg">
          <Menu size={20} />
        </button>
        <Logo />
        <div className="ml-auto flex items-center gap-3">
          <ConnectionStatus compact />
          <Link to="/alerts" aria-label="Alertas" className="relative rounded-md p-2 text-muted hover:text-fg">
            <Bell size={19} />
            {alerts > 0 && (
              <span className="absolute -right-0.5 -top-0.5 rounded-full bg-danger px-1 text-[10px] font-semibold tabular text-white">
                {alerts}
              </span>
            )}
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] px-4 py-4 sm:px-6 sm:py-6">
        <Suspense fallback={<Skeleton className="h-96 w-full" />}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
