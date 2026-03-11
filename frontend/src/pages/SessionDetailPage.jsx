import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api";

const acceptedFormats = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "text/plain": [".txt"],
  "application/zip": [".zip"],
};

export default function SessionDetailPage() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [modelSaving, setModelSaving] = useState(false);
  const [reviewDrafts, setReviewDrafts] = useState({});

  const loadAll = useCallback(async () => {
    try {
      setLoading(true);
      const [sessionRes, submissionsRes, analyticsRes] = await Promise.all([
        apiClient.get(`/sessions/${sessionId}`),
        apiClient.get(`/sessions/${sessionId}/submissions`),
        apiClient.get(`/sessions/${sessionId}/analytics`),
      ]);
      setSession(sessionRes.data);
      setSubmissions(submissionsRes.data);
      setAnalytics(analyticsRes.data);

      const drafts = {};
      submissionsRes.data.forEach((submission) => {
        drafts[submission.id] = {
          review_note: submission.review_note || "",
          grading: submission.grading.reduce((acc, line) => {
            acc[line.question_id] = { score: line.score, max_marks: line.max_marks, reason: line.reason };
            return acc;
          }, {}),
        };
      });
      setReviewDrafts(drafts);
    } catch {
      toast.error("Failed to load session details");
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!job || job.status === "completed") return undefined;
    const timer = setInterval(async () => {
      try {
        const { data } = await apiClient.get(`/jobs/${job.id}`);
        setJob(data);
        if (data.status === "completed") {
          toast.success(data.message);
          await loadAll();
        }
      } catch {
        toast.error("Could not fetch job progress");
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [job, loadAll]);

  const onDrop = async (files) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    try {
      const { data } = await apiClient.post(`/sessions/${sessionId}/bulk-upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setJob(data);
      toast.success("Bulk upload queued");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Upload failed");
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptedFormats,
  });

  const triggerGrading = async () => {
    try {
      const { data } = await apiClient.post(`/sessions/${sessionId}/grade`, { ai_provider: session.ai_provider });
      setJob(data);
      toast.success("Grading job started");
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not start grading");
    }
  };

  const updateModel = async (aiProvider) => {
    try {
      setModelSaving(true);
      const { data } = await apiClient.put(`/sessions/${sessionId}/model`, { ai_provider: aiProvider });
      setSession(data);
      toast.success(`Model switched to ${aiProvider}`);
    } catch {
      toast.error("Could not update model");
    } finally {
      setModelSaving(false);
    }
  };

  const updateDraftScore = (submissionId, questionId, key, value) => {
    setReviewDrafts((prev) => ({
      ...prev,
      [submissionId]: {
        ...prev[submissionId],
        grading: {
          ...prev[submissionId]?.grading,
          [questionId]: {
            ...(prev[submissionId]?.grading?.[questionId] || {}),
            [key]: key === "score" || key === "max_marks" ? Number(value) : value,
          },
        },
      },
    }));
  };

  const updateDraftNote = (submissionId, value) => {
    setReviewDrafts((prev) => ({
      ...prev,
      [submissionId]: { ...prev[submissionId], review_note: value },
    }));
  };

  const saveReview = async (submission, approved) => {
    const draft = reviewDrafts[submission.id];
    if (!draft?.grading || Object.keys(draft.grading).length === 0) {
      toast.error("No grading lines available for review");
      return;
    }
    const payload = {
      grading: Object.entries(draft.grading).map(([question_id, line]) => ({
        question_id,
        score: Number(line.score || 0),
        max_marks: Number(line.max_marks || 0),
        reason: String(line.reason || ""),
      })),
      approved,
      review_note: draft.review_note,
    };
    try {
      await apiClient.put(`/submissions/${submission.id}/manual-review`, payload);
      toast.success(approved ? "Submission approved" : "Manual review saved");
      await loadAll();
    } catch {
      toast.error("Failed to save review");
    }
  };

  const downloadExcel = async () => {
    try {
      const { data } = await apiClient.get(`/sessions/${sessionId}/export`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `${session?.title || "grades"}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Excel exported");
    } catch {
      toast.error("Export failed");
    }
  };

  const summary = useMemo(() => {
    const total = submissions.length;
    const graded = submissions.filter((item) => ["graded", "reviewed", "approved"].includes(item.status)).length;
    const flagged = submissions.filter((item) => item.plagiarism_flag).length;
    return { total, graded, flagged };
  }, [submissions]);

  if (loading || !session) {
    return <p data-testid="session-loading-text">Loading session...</p>;
  }

  return (
    <div className="space-y-8" data-testid="session-detail-page-root">
      <section className="border-2 border-stone-300 bg-card p-6 space-y-5" data-testid="session-header-card">
        <div className="flex flex-wrap gap-4 items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-stone-500" data-testid="session-header-kicker">
              Session Workspace
            </p>
            <h2 className="font-heading text-4xl font-extrabold" data-testid="session-header-title">{session.title}</h2>
            <p className="text-sm text-stone-600" data-testid="session-header-subtitle">
              Upload assignments, run AI grading, review marks, and export grade sheet.
            </p>
          </div>

          <div className="grid sm:grid-cols-3 gap-3" data-testid="session-summary-grid">
            <div className="border-2 border-stone-200 px-4 py-2" data-testid="session-summary-total">
              <p className="text-xs">Submissions</p>
              <p className="font-mono text-xl" data-testid="session-summary-total-value">{summary.total}</p>
            </div>
            <div className="border-2 border-stone-200 px-4 py-2" data-testid="session-summary-graded">
              <p className="text-xs">Graded</p>
              <p className="font-mono text-xl" data-testid="session-summary-graded-value">{summary.graded}</p>
            </div>
            <div className="border-2 border-stone-200 px-4 py-2" data-testid="session-summary-flagged">
              <p className="text-xs">Plagiarism Flags</p>
              <p className="font-mono text-xl" data-testid="session-summary-flagged-value">{summary.flagged}</p>
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-[1fr_260px] gap-4" data-testid="model-controls-row">
          <Select
            value={session.ai_provider}
            onValueChange={updateModel}
            disabled={modelSaving}
            data-testid="session-model-switch-select"
          >
            <SelectTrigger className="rounded-none border-2 border-stone-300" data-testid="session-model-switch-trigger">
              <SelectValue placeholder="Choose model" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="gemini" data-testid="session-model-switch-gemini">Gemini 3 Flash</SelectItem>
              <SelectItem value="local" data-testid="session-model-switch-local">Local LLM (qwen2.5:3b-instruct)</SelectItem>
            </SelectContent>
          </Select>
          <div className="grid grid-cols-2 gap-2">
            <Button onClick={triggerGrading} className="rounded-none border-2 border-black" data-testid="start-grading-button">
              Run Grading
            </Button>
            <Button variant="outline" onClick={downloadExcel} className="rounded-none" data-testid="export-excel-button">
              Export Excel
            </Button>
          </div>
        </div>

        <div
          {...getRootProps()}
          className={`border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
            isDragActive ? "border-primary bg-accent/40" : "border-stone-300"
          }`}
          data-testid="submission-dropzone"
        >
          <input {...getInputProps()} data-testid="submission-dropzone-input" />
          <p className="font-medium" data-testid="submission-dropzone-title">
            {isDragActive ? "Drop the files now" : "Drag & drop PDF/DOCX/TXT/ZIP files here"}
          </p>
          <p className="text-sm text-stone-500" data-testid="submission-dropzone-helper">Bulk upload supported</p>
        </div>

        {job && (
          <div className="border-2 border-stone-200 p-3" data-testid="job-progress-card">
            <p className="text-sm" data-testid="job-progress-message">{job.message}</p>
            <p className="font-mono" data-testid="job-progress-percent">{job.progress_percent}%</p>
            <p className="text-xs text-stone-500" data-testid="job-progress-meta">
              Processed: {job.processed_items}/{job.total_items} | Failed: {job.failed_items}
            </p>
          </div>
        )}
      </section>

      <section className="grid lg:grid-cols-2 gap-6" data-testid="analytics-section">
        <div className="border-2 border-stone-300 bg-card p-5" data-testid="score-distribution-card">
          <h3 className="font-heading text-2xl font-bold mb-4" data-testid="score-distribution-title">Score Distribution</h3>
          <div className="h-[260px]" data-testid="score-distribution-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics?.distribution || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="range" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#F97316" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="border-2 border-stone-300 bg-card p-5" data-testid="difficulty-chart-card">
          <h3 className="font-heading text-2xl font-bold mb-4" data-testid="difficulty-chart-title">Question Difficulty</h3>
          <div className="h-[260px]" data-testid="difficulty-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={analytics?.question_difficulty || []}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="question" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="difficulty" fill="#44403C" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      <section className="border-2 border-stone-300 bg-card p-5 space-y-6" data-testid="manual-review-section">
        <h3 className="font-heading text-3xl font-bold" data-testid="manual-review-title">Manual Review Dashboard</h3>

        {submissions.length === 0 ? (
          <p data-testid="manual-review-empty">No submissions uploaded yet.</p>
        ) : (
          submissions.map((submission) => {
            const draft = reviewDrafts[submission.id] || { grading: {}, review_note: "" };
            const gradeKeys = Object.keys(draft.grading);
            return (
              <div className="border-2 border-stone-200 p-4 space-y-4" key={submission.id} data-testid={`submission-card-${submission.id}`}>
                <div className="flex flex-wrap justify-between gap-4">
                  <div>
                    <p className="font-semibold" data-testid={`submission-student-${submission.id}`}>
                      {submission.student_name} ({submission.roll_number})
                    </p>
                    <p className="text-sm text-stone-500" data-testid={`submission-file-${submission.id}`}>
                      {submission.filename}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-mono" data-testid={`submission-total-${submission.id}`}>Total: {submission.total_score}</p>
                    <p className="text-sm" data-testid={`submission-status-${submission.id}`}>Status: {submission.status}</p>
                    <p className="text-sm" data-testid={`submission-plagiarism-${submission.id}`}>
                      Plagiarism: {(submission.plagiarism_score * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>

                {submission.extraction_flags?.length > 0 && (
                  <div className="border-2 border-amber-300 bg-amber-50 p-2" data-testid={`submission-extraction-flags-${submission.id}`}>
                    <p className="text-sm font-medium">Extraction Flags: {submission.extraction_flags.join(", ")}</p>
                  </div>
                )}

                <details className="border-2 border-stone-200 p-3" data-testid={`submission-answers-${submission.id}`}>
                  <summary className="cursor-pointer font-medium">View extracted answers</summary>
                  <div className="mt-3 space-y-3">
                    {Object.entries(submission.answers || {}).map(([questionId, answer]) => (
                      <div key={questionId} className="border border-stone-200 p-2" data-testid={`submission-answer-${submission.id}-${questionId}`}>
                        <p className="font-mono text-sm">{questionId}</p>
                        <p className="text-sm whitespace-pre-wrap">{answer}</p>
                      </div>
                    ))}
                  </div>
                </details>

                {gradeKeys.length === 0 ? (
                  <p className="text-sm text-stone-500" data-testid={`submission-no-grades-${submission.id}`}>
                    No AI grade yet. Run grading first.
                  </p>
                ) : (
                  <div className="space-y-3" data-testid={`submission-grading-editor-${submission.id}`}>
                    {gradeKeys.map((questionId) => (
                      <div key={questionId} className="grid md:grid-cols-[120px_120px_1fr] gap-3 items-start">
                        <Input value={questionId} disabled data-testid={`review-question-${submission.id}-${questionId}`} />
                        <Input
                          type="number"
                          value={draft.grading[questionId]?.score ?? 0}
                          onChange={(e) => updateDraftScore(submission.id, questionId, "score", e.target.value)}
                          data-testid={`review-score-${submission.id}-${questionId}`}
                        />
                        <Input
                          value={draft.grading[questionId]?.reason ?? ""}
                          onChange={(e) => updateDraftScore(submission.id, questionId, "reason", e.target.value)}
                          data-testid={`review-reason-${submission.id}-${questionId}`}
                        />
                      </div>
                    ))}
                    <Textarea
                      rows={2}
                      value={draft.review_note}
                      onChange={(e) => updateDraftNote(submission.id, e.target.value)}
                      placeholder="Instructor note"
                      data-testid={`review-note-${submission.id}`}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        className="rounded-none"
                        onClick={() => saveReview(submission, false)}
                        data-testid={`save-review-${submission.id}`}
                      >
                        Save Review
                      </Button>
                      <Button
                        className="rounded-none border-2 border-black"
                        onClick={() => saveReview(submission, true)}
                        data-testid={`approve-review-${submission.id}`}
                      >
                        Approve Score
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}
