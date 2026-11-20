import { t } from "./i18n";
import { useState, type FormEvent } from "react";
import { LockKeyhole, Mail } from "lucide-react";
import { Brand, BrandCredit } from "./Brand";
import { login } from "./services/api";

interface LoginPageProps {
  onLogin: (token: string) => void;
}

function LoginPage({ onLogin }: LoginPageProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await login(email, password);
      onLogin(response.access_token);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : t("Unable to sign in. Please try again."),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <Brand className="grans-login" />

        <div className="login-heading">
          <h1>{t("Welcome back")}</h1>
          <p>{t("Sign in to access your identity management workspace.")}</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="login-email">{t("Email address")}</label>
          <div className="login-input-wrap">
            <Mail size={18} />
            <input
              id="login-email"
              type="email"
              placeholder={t("name@company.com")}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </div>

          <label htmlFor="login-password">{t("Password")}</label>
          <div className="login-input-wrap">
            <LockKeyhole size={18} />
            <input
              id="login-password"
              type="password"
              placeholder={t("Enter your password")}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button
            className="login-submit"
            type="submit"
            disabled={loading}
          >
            {loading ? t("Signing in...") : t("Sign in")}
          </button>
        </form>

        <div className="login-footer">
          <BrandCredit />
        </div>
      </section>
    </main>
  );
}

export default LoginPage;
