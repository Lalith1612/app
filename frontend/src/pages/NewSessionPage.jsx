import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
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

export default function NewSessionPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [payload, setPayload] = useState({
    title: "",
    question_paper_text: "",
    answer_key_text: "",
    rubric_text: "",
    ai_provider: "gemini",
  });

  const update = (key, value) => setPayload((prev) => ({ ...prev, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      const { data } = await apiClient.post("/sessions", payload);
      toast.success("Grading session created");
      navigate(`/sessions/${data.id}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not create session");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form className="space-y-6" onSubmit={submit} data-testid="new-session-form">
      <div className="border-2 border-stone-300 bg-card p-6 space-y-4" data-testid="new-session-header-card">
        <p className="text-xs uppercase tracking-[0.2em] text-stone-500" data-testid="new-session-kicker">Setup</p>
        <h2 className="font-heading text-4xl font-extrabold" data-testid="new-session-title">Create Grading Session</h2>
        <p className="text-stone-600" data-testid="new-session-description">
          Add question paper, answer key, rubric, and default model. You can switch model later in session view.
        </p>
      </div>

      <div className="border-2 border-stone-300 bg-card p-6 space-y-5" data-testid="new-session-fields-card">
        <Input
          placeholder="Session title (e.g., Midterm - Physics A)"
          value={payload.title}
          onChange={(e) => update("title", e.target.value)}
          required
          data-testid="session-title-input"
        />

        <Select
          value={payload.ai_provider}
          onValueChange={(value) => update("ai_provider", value)}
          data-testid="session-model-select"
        >
          <SelectTrigger className="rounded-none border-2 border-stone-300" data-testid="session-model-select-trigger">
            <SelectValue placeholder="Select model" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="gemini" data-testid="session-model-option-gemini">Gemini 3 Flash</SelectItem>
            <SelectItem value="local" data-testid="session-model-option-local">
              Local LLM (qwen2.5:3b-instruct via Ollama)
            </SelectItem>
          </SelectContent>
        </Select>

        <Textarea
          placeholder="Question paper text"
          rows={8}
          value={payload.question_paper_text}
          onChange={(e) => update("question_paper_text", e.target.value)}
          required
          data-testid="session-question-paper-input"
        />

        <Textarea
          placeholder="Answer key text"
          rows={8}
          value={payload.answer_key_text}
          onChange={(e) => update("answer_key_text", e.target.value)}
          required
          data-testid="session-answer-key-input"
        />

        <Textarea
          placeholder="Rubric text (include marks like Q1: 5 marks)"
          rows={8}
          value={payload.rubric_text}
          onChange={(e) => update("rubric_text", e.target.value)}
          required
          data-testid="session-rubric-input"
        />

        <Button
          type="submit"
          disabled={loading}
          className="rounded-none border-2 border-black"
          data-testid="create-session-submit-button"
        >
          {loading ? "Creating..." : "Create Session"}
        </Button>
      </div>
    </form>
  );
}
