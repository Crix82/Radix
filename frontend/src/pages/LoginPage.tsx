import { type FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useCurrentUser, useLogin } from "../hooks/useAuth";
import { t } from "../i18n";

export function LoginPage() {
  const { data: user } = useCurrentUser();
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (user) {
    return <Navigate to="/search" replace />;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password });
  }

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.status === 429
        ? t.login.rateLimited
        : t.login.error
      : login.error
        ? t.login.genericError
        : null;

  return (
    <div className="flex h-screen items-center justify-center px-5">
      <div className="w-full max-w-[380px]">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-sm bg-gradient-to-br from-petrol to-petrol-mid text-lg font-bold text-white">
            R
          </div>
          <div>
            <div className="text-[17px] font-semibold">{t.app.name}</div>
            <div className="font-mono text-[10.5px] text-ink3">{t.app.tagline}</div>
          </div>
        </div>

        <form className="card px-6 py-6" onSubmit={onSubmit}>
          <h1 className="mb-1 text-[16px] font-semibold">{t.login.title}</h1>
          <p className="mb-4 text-[12.5px] text-ink2">{t.login.subtitle}</p>

          <div className="mb-[13px]">
            <label className="field-label" htmlFor="email">
              {t.login.email}
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="username"
              className="field-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="mb-4">
            <label className="field-label" htmlFor="password">
              {t.login.password}
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              className="field-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          {errorMessage && (
            <div className="mb-3 rounded-sm bg-err-tint px-3 py-2 text-[12.5px] font-semibold text-err">
              {errorMessage}
            </div>
          )}

          <button type="submit" className="btn-primary w-full justify-center" disabled={login.isPending}>
            {login.isPending ? t.common.loading : t.login.submit}
          </button>
        </form>

        <div className="mt-4 text-center font-mono text-[10.5px] text-ink3">
          {t.app.footPrivacy} · {t.app.footNoExternal}
        </div>
      </div>
    </div>
  );
}
