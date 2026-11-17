// k6 baseline (Blueprint 14 / 27.2): run before each phase exit and on every release candidate (staging).
//   docker run --rm -i --network rsv4_public -e BASE=http://gateway:8080 grafana/k6:1.3.0 run - < infra/scripts/load/baseline.js
// Thresholds: reads p95 < 200 ms, booking create p95 < 300 ms, no 5xx. Slot clashes (409) are expected and not errors.
import http from "k6/http";
import { check } from "k6";
import { Counter } from "k6/metrics";

const BASE = __ENV.BASE || "http://localhost:8080";
const CUSTOMERS = Number(__ENV.CUSTOMERS || 40);
const RATE = Number(__ENV.RATE || 1); // multiplies all arrival rates
const r = (base) => Math.max(1, Math.round(base * RATE)); // k6 needs whole requests per second
const DURATION = __ENV.DURATION || "2m";
const run = `${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;
const clashes = new Counter("booking_slot_taken");

export const options = {
  setupTimeout: "5m",
  scenarios: {
    business_page: { executor: "constant-arrival-rate", rate: r(20), timeUnit: "1s", duration: DURATION, preAllocatedVUs: 20, maxVUs: 200, exec: "businessPage" },
    slots: { executor: "constant-arrival-rate", rate: r(10), timeUnit: "1s", duration: DURATION, preAllocatedVUs: 10, maxVUs: 100, exec: "slots" },
    feed: { executor: "constant-arrival-rate", rate: r(20), timeUnit: "1s", duration: DURATION, preAllocatedVUs: 20, maxVUs: 200, exec: "feed" },
    search: { executor: "constant-arrival-rate", rate: r(5), timeUnit: "1s", duration: DURATION, preAllocatedVUs: 5, maxVUs: 50, exec: "search" },
    booking_create: { executor: "constant-arrival-rate", rate: r(2), timeUnit: "1s", duration: DURATION, preAllocatedVUs: 5, maxVUs: 50, exec: "book" },
  },
  thresholds: {
    "http_req_duration{kind:read}": ["p(95)<200"],
    "http_req_duration{kind:booking}": ["p(95)<300"],
    "http_req_failed{kind:read}": ["rate<0.01"],
    checks: ["rate>0.99"],
  },
};

function session(username) {
  const jar = http.cookieJar();
  const csrf = http.get(`${BASE}/api/v1/auth/csrf`).json("csrf_token");
  const body = JSON.stringify({ username, email: `${username}@example.com`, password: "Load-Passw0rd-123",
    display_name: username, is_18_or_older: true });
  const r = http.post(`${BASE}/api/v1/auth/signup`, body, { headers: { "content-type": "application/json", "x-csrf-token": csrf } });
  if (r.status !== 201) throw new Error(`signup failed ${r.status} ${r.body}`);
  const cookies = jar.cookiesForURL(BASE);
  return { csrf, at: cookies.rsv_at[0], rt: cookies.rsv_rt[0] };
}

function authed(s) {
  return { headers: { "content-type": "application/json", "x-csrf-token": s.csrf, cookie: `rsv_at=${s.at}; rsv_csrf=${s.csrf}` } };
}

export function setup() {
  const owner = session(`ldown${run}`);
  const biz = http.post(`${BASE}/api/v1/businesses`, JSON.stringify({ slug: `load-${run}`, name: "Load Test Electricals",
    category: "electrician", tagline: "Fans, wiring and repairs", lat: 26.91, lng: 75.78 }), authed(owner)).json();
  http.put(`${BASE}/api/v1/businesses/${biz.id}/hours`, JSON.stringify([0, 1, 2, 3, 4, 5, 6].map((d) => ({ weekday: d, opens: "08:00", closes: "20:00" }))), authed(owner));
  for (let i = 0; i < 4; i++) http.post(`${BASE}/api/v1/businesses/${biz.id}/resources`, JSON.stringify({ name: `Helper ${i}` }), authed(owner));
  const service = http.post(`${BASE}/api/v1/businesses/${biz.id}/services`, JSON.stringify({ name: "Fan installation", price_paise: 49900, duration_min: 30 }), authed(owner)).json();
  for (let i = 0; i < 20; i++) http.post(`${BASE}/api/v1/posts`, JSON.stringify({ caption: `Ceiling fan offer number ${i} #fans #jaipur` }), authed(owner));
  const customers = [];
  for (let i = 0; i < CUSTOMERS; i++) {
    const c = session(`ldc${i}${run}`);
    http.post(`${BASE}/api/v1/profiles/ldown${run}/follow`, null, authed(c));
    customers.push(c);
  }
  const days = [];
  for (let d = 1; d <= 14; d++) days.push(new Date(Date.now() + d * 86400000).toISOString().slice(0, 10));
  return { slug: biz.slug, bizId: biz.id, serviceId: service.id, customers, days };
}

const pick = (a) => a[Math.floor(Math.random() * a.length)];

export function businessPage(d) {
  const r = http.get(`${BASE}/api/v1/businesses/by-slug/${d.slug}`, { tags: { kind: "read", name: "business_page" } });
  check(r, { "business 200": (x) => x.status === 200 });
}

export function slots(d) {
  const r = http.get(`${BASE}/api/v1/businesses/${d.bizId}/slots?service_id=${d.serviceId}&date=${pick(d.days)}`, { tags: { kind: "read", name: "slots" } });
  check(r, { "slots 200": (x) => x.status === 200 });
}

export function feed(d) {
  const r = http.get(`${BASE}/api/v1/feed`, { ...authed(pick(d.customers)), tags: { kind: "read", name: "feed" } });
  check(r, { "feed 200": (x) => x.status === 200 });
}

export function search() {
  const r = http.get(`${BASE}/api/v1/search?q=${pick(["fan", "wiring", "jaipur", "repairs"])}`, { tags: { kind: "read", name: "search" } });
  check(r, { "search 200": (x) => x.status === 200 });
}

export function book(d) {
  const c = pick(d.customers);
  const day = pick(d.days);
  const hour = 8 + Math.floor(Math.random() * 12);
  const startsAt = `${day}T${String(hour).padStart(2, "0")}:${pick(["00", "30"])}:00+05:30`;
  const r = http.post(`${BASE}/api/v1/bookings`, JSON.stringify({ business_id: d.bizId, service_id: d.serviceId, starts_at: startsAt }),
    { headers: { ...authed(c).headers, "Idempotency-Key": `${run}-${__VU}-${__ITER}` }, tags: { kind: "booking", name: "booking_create" },
      responseCallback: http.expectedStatuses(201, 409, 429) });
  if (r.status === 409) clashes.add(1);
  check(r, { "booking 201/409/429 (no 5xx)": (x) => [201, 409, 429].includes(x.status) });
}
