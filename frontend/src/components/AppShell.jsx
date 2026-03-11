import { BarChart3, FilePlus2, Home, LogOut, Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const navLinkClass = ({ isActive }) =>
  `border-2 px-4 py-2 text-sm font-bold uppercase tracking-wider transition-all ${
    isActive ? "bg-primary text-primary-foreground border-black" : "bg-white text-stone-700 border-stone-300"
  }`;

export default function AppShell({ children }) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="app-shell-root">
      <header className="border-b-2 border-stone-300 bg-card" data-testid="main-header">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 flex flex-wrap gap-4 items-center justify-between">
          <div className="space-y-1" data-testid="brand-block">
            <p className="text-xs uppercase tracking-[0.2em] text-stone-500">AI Assignment Grading</p>
            <h1 className="font-heading text-3xl font-extrabold tracking-tight" data-testid="app-main-title">
              ZenGrade Control Room
            </h1>
          </div>
          <div className="text-right" data-testid="header-user-info">
            <p className="text-sm text-stone-500">Instructor</p>
            <p className="font-mono text-sm" data-testid="header-user-email">{user?.email}</p>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 grid lg:grid-cols-[280px_1fr] gap-8">
        <aside className="border-2 border-stone-300 bg-card p-5 h-fit" data-testid="sidebar-navigation">
          <nav className="space-y-3">
            <NavLink to="/" className={navLinkClass} data-testid="nav-dashboard-link">
              <Home className="inline mr-2 h-4 w-4" /> Dashboard
            </NavLink>
            <NavLink to="/sessions/new" className={navLinkClass} data-testid="nav-new-session-link">
              <FilePlus2 className="inline mr-2 h-4 w-4" /> New Session
            </NavLink>
            <div className="border-2 border-dashed border-stone-300 p-3 text-sm text-stone-600" data-testid="nav-tip-card">
              <Sparkles className="inline h-4 w-4 mr-2" />
              Choose Gemini or local model directly from each grading session.
            </div>
            <div className="border-2 border-dashed border-stone-300 p-3 text-sm text-stone-600" data-testid="nav-analytics-card">
              <BarChart3 className="inline h-4 w-4 mr-2" />
              Real-time grading, plagiarism checks, and export in one place.
            </div>
            <Button
              onClick={logout}
              className="w-full rounded-none border-2 border-black"
              variant="outline"
              data-testid="logout-button"
            >
              <LogOut className="mr-2 h-4 w-4" /> Logout
            </Button>
          </nav>
        </aside>
        <main data-testid="app-main-content">{children}</main>
      </div>
    </div>
  );
}
