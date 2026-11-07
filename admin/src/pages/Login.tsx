import { useState } from "react";
import type { FormEvent } from "react";

import { useAuth } from "../auth.tsx";
import { useAction } from "../hooks.ts";
import { ErrorNote } from "../components/ui.tsx";

export function LoginPage() {
  const { login } = useAuth();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const action = useAction();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void action.run(() => login(name.trim(), password));
  };

  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>Altyn Crown</h1>
        <p className="muted">Вход для сотрудников</p>
        <input placeholder="Логин" autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <input placeholder="Пароль" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <ErrorNote text={action.error} />
        <button className="primary" disabled={action.busy || !name || !password}>Войти</button>
      </form>
    </div>
  );
}
