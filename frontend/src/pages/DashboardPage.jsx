import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import MetricCard from "@/components/MetricCard";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";

export default function DashboardPage() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const { data } = await apiClient.get("/sessions");
      setSessions(data);
    } catch {
      toast.error("Could not load sessions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  return (
    <div className="space-y-8" data-testid="dashboard-page-root">
      <section className="grid md:grid-cols-3 gap-5" data-testid="dashboard-metrics-grid">
        <MetricCard label="Total Sessions" value={sessions.length} testId="metric-total-sessions" />
        <MetricCard
          label="Gemini Sessions"
          value={sessions.filter((s) => s.ai_provider === "gemini").length}
          testId="metric-gemini-sessions"
        />
        <MetricCard
          label="Local LLM Sessions"
          value={sessions.filter((s) => s.ai_provider === "local").length}
          testId="metric-local-sessions"
        />
      </section>

      <section className="border-2 border-stone-300 bg-card p-6" data-testid="sessions-table-section">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-stone-500" data-testid="sessions-list-kicker">
              Grading Sessions
            </p>
            <h2 className="font-heading text-3xl font-extrabold" data-testid="sessions-list-title">
              Your Assignment Pipelines
            </h2>
          </div>
          <Button asChild className="rounded-none border-2 border-black" data-testid="create-session-cta-button">
            <Link to="/sessions/new">Create New Session</Link>
          </Button>
        </div>

        {loading ? (
          <p className="font-mono" data-testid="sessions-loading-text">Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <div className="border-2 border-dashed border-stone-300 p-8 text-center" data-testid="sessions-empty-state">
            <p className="text-lg">No session yet</p>
            <p className="text-sm text-stone-500">Create your first grading workflow to begin.</p>
          </div>
        ) : (
          <div className="overflow-x-auto" data-testid="sessions-list-wrapper">
            <table className="w-full min-w-[700px]" data-testid="sessions-table">
              <thead>
                <tr className="border-b-2 border-stone-300 text-left">
                  <th className="py-3" data-testid="sessions-header-title">Title</th>
                  <th className="py-3" data-testid="sessions-header-model">Model</th>
                  <th className="py-3" data-testid="sessions-header-updated">Updated</th>
                  <th className="py-3" data-testid="sessions-header-action">Action</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr key={session.id} className="border-b border-stone-200" data-testid={`session-row-${session.id}`}>
                    <td className="py-3 font-medium" data-testid={`session-title-${session.id}`}>{session.title}</td>
                    <td className="py-3 font-mono" data-testid={`session-model-${session.id}`}>{session.ai_provider}</td>
                    <td className="py-3" data-testid={`session-updated-${session.id}`}>
                      {new Date(session.updated_at).toLocaleString()}
                    </td>
                    <td className="py-3">
                      <Button asChild variant="outline" className="rounded-none" data-testid={`session-open-button-${session.id}`}>
                        <Link to={`/sessions/${session.id}`}>Open</Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
