import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createClient } from "./api.ts";
import { changedFields, errorText, money, percent } from "./format.ts";
import { manageableRoles } from "./permissions.ts";

const staff = { id: 1, login: "a", display_name: "A", role: "owner", is_active: true, last_login_at: null, created_at: "", permissions: [] };
const json = (status: number, body?: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status });
const tokenBody = (token: string) => ({ access_token: token, expires_in: 900, staff });

test("login stores token and sends it in Authorization", async () => {
  const seen: (string | null)[] = [];
  const client = createClient(async (url, init) => {
    seen.push(new Headers(init?.headers).get("Authorization"));
    return url.endsWith("/login") ? json(200, tokenBody("t1")) : json(200, { ok: true });
  });
  await client.login("a", "b");
  await client.request("GET", "/admin/v1/players");
  assert.deepEqual(seen, [null, "Bearer t1"]);
});

test("login error becomes ApiError with code and extras", async () => {
  const client = createClient(async () => json(401, { detail: { code: "invalid_credentials" } }));
  await assert.rejects(client.login("a", "x"), (e: unknown) => e instanceof ApiError && e.code === "invalid_credentials" && e.status === 401);
});

test("401 triggers a single refresh and the request is retried", async () => {
  let calls = 0;
  const client = createClient(async (url, init) => {
    if (url.endsWith("/login")) return json(200, tokenBody("old"));
    if (url.endsWith("/refresh")) return json(200, tokenBody("new"));
    calls += 1;
    const auth = new Headers(init?.headers).get("Authorization");
    return auth === "Bearer new" ? json(200, { n: calls }) : json(401, { detail: { code: "invalid_credentials" } });
  });
  await client.login("a", "b");
  const result = await client.request<{ n: number }>("GET", "/admin/v1/x");
  assert.equal(result.n, 2);
});

test("parallel 401s share one refresh (refresh token is single-use)", async () => {
  let refreshes = 0;
  const client = createClient(async (url, init) => {
    if (url.endsWith("/login")) return json(200, tokenBody("old"));
    if (url.endsWith("/refresh")) {
      refreshes += 1;
      return json(200, tokenBody("new"));
    }
    return new Headers(init?.headers).get("Authorization") === "Bearer new" ? json(200, {}) : json(401, {});
  });
  await client.login("a", "b");
  await Promise.all([client.request("GET", "/a"), client.request("GET", "/b"), client.request("GET", "/c")]);
  assert.equal(refreshes, 1);
});

test("failed refresh reports session loss", async () => {
  let lost = 0;
  const client = createClient(async (url) => {
    if (url.endsWith("/login")) return json(200, tokenBody("old"));
    return json(401, { detail: { code: "invalid_refresh" } });
  });
  client.onSessionLost(() => (lost += 1));
  await client.login("a", "b");
  await assert.rejects(client.request("GET", "/admin/v1/x"));
  assert.equal(lost, 1);
});

test("restore returns null without a valid cookie and 204 gives undefined", async () => {
  const client = createClient(async (url) => (url.endsWith("/refresh") ? json(401, {}) : json(204)));
  assert.equal(await client.restore(), null);
});

test("formatting helpers", () => {
  assert.equal(money(1234567).replace(/\s/g, " "), "1 234 567 ₸");
  assert.equal(percent("3"), "+3%");
  assert.equal(percent("-2.5"), "-2.5%");
  assert.equal(errorText("request_not_found"), "Заявка не найдена.");
  assert.equal(errorText("http_502"), "Ошибка сервера. Попробуйте позже.");
  assert.equal(errorText("weird"), "Ошибка: weird");
});

test("changedFields sends only edited values and converts integers", () => {
  const diff = changedFields(
    { deposit_min_amount: "1000", deposit_commission_percent: "0" },
    { deposit_min_amount: " 2000 ", deposit_commission_percent: "0" },
    ["deposit_min_amount"],
  );
  assert.deepEqual(diff, { deposit_min_amount: 2000 });
});

test("admins cannot manage owners", () => {
  assert.deepEqual(manageableRoles("admin"), ["operator", "finance"]);
  assert.deepEqual(manageableRoles("operator"), []);
});
