import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { createClient } from "./lib/api.ts";
import type { Client, Staff } from "./lib/api.ts";

const client: Client = createClient();

interface AuthState {
  staff: Staff | null;
  ready: boolean;
  api: Client;
  can: (permission: string) => boolean;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [staff, setStaff] = useState<Staff | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    client.onSessionLost(() => setStaff(null));
    client.restore().then((s) => {
      setStaff(s);
      setReady(true);
    });
  }, []);

  const login = useCallback(async (loginName: string, password: string) => {
    setStaff(await client.login(loginName, password));
  }, []);

  const logout = useCallback(async () => {
    await client.logout().catch(() => undefined);
    setStaff(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      staff,
      ready,
      api: client,
      can: (permission) => staff?.permissions.includes(permission) ?? false,
      login,
      logout,
    }),
    [staff, ready, login, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(Ctx);
  if (!value) throw new Error("AuthProvider отсутствует");
  return value;
}
