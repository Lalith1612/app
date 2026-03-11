import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, register } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [loading, setLoading] = useState(false);

  const update = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      if (isRegister) {
        await register(form.name, form.email, form.password);
      } else {
        await login(form.email, form.password);
      }
      toast.success("Access granted. Welcome to ZenGrade.");
      navigate("/");
    } catch (error) {
      const message = error?.response?.data?.detail || "Authentication failed";
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-background" data-testid="login-page-root">
      <section
        className="hidden lg:flex flex-col justify-between p-10 border-r-2 border-stone-300"
        style={{ backgroundImage: "url('https://images.unsplash.com/photo-1761854149912-54ced79870ec?auto=format&fit=crop&w=1200&q=80')", backgroundSize: "cover" }}
        data-testid="login-hero-panel"
      >
        <p className="text-xs uppercase tracking-[0.25em] text-stone-700 bg-white/80 w-fit px-2 py-1" data-testid="login-hero-tag">
          Assignment Intelligence
        </p>
        <h2 className="font-heading text-5xl font-extrabold max-w-md text-stone-900" data-testid="login-hero-title">
          Grade in bulk. Review with clarity.
        </h2>
      </section>

      <section className="grid place-items-center p-6" data-testid="login-form-panel">
        <form
          onSubmit={submit}
          className="w-full max-w-md border-2 border-stone-300 bg-card p-8 space-y-5"
          data-testid="auth-form"
        >
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-stone-500" data-testid="auth-form-kicker">
              Instructor Access
            </p>
            <h1 className="font-heading text-4xl font-extrabold" data-testid="auth-form-title">
              {isRegister ? "Create account" : "Sign in"}
            </h1>
          </div>

          {isRegister && (
            <Input
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Full Name"
              required
              data-testid="register-name-input"
            />
          )}

          <Input
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            placeholder="Email"
            type="email"
            required
            data-testid="auth-email-input"
          />

          <Input
            value={form.password}
            onChange={(e) => update("password", e.target.value)}
            placeholder="Password"
            type="password"
            required
            data-testid="auth-password-input"
          />

          <Button
            disabled={loading}
            type="submit"
            className="w-full rounded-none border-2 border-black"
            data-testid="auth-submit-button"
          >
            {loading ? "Please wait..." : isRegister ? "Register" : "Login"}
          </Button>

          <button
            type="button"
            className="text-sm text-stone-700 underline"
            onClick={() => setIsRegister((prev) => !prev)}
            data-testid="auth-toggle-mode-button"
          >
            {isRegister ? "Already have an account? Login" : "No account yet? Register"}
          </button>
        </form>
      </section>
    </div>
  );
}
