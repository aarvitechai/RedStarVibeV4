import { type Browser, type Page, expect, test } from "@playwright/test";

const run = () => `${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
const SHOTS = process.env.E2E_SCREENSHOTS; // folder for review screenshots (optional)

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${test.info().project.name}-${name}.png`, fullPage: true });
}

async function signup(browser: Browser, username: string, name: string) {
  const ctx = await browser.newContext({ ...test.info().project.use });
  const page = await ctx.newPage();
  await page.goto("/signup");
  await page.getByLabel("Name", { exact: true }).fill(name);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Email", { exact: true }).fill(`${username}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("E2e-Passw0rd-123");
  await page.getByLabel("I am 18 or older").check();
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", { name: `Hi, ${name}` })).toBeVisible();
  return page;
}

test("no horizontal scroll and core pages render", async ({ page }) => {
  for (const path of ["/", "/signup", "/login", "/help", "/plans", "/search?q=fan"]) {
    await page.goto(path);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(1);
  }
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "RedStarVibe" })).toBeVisible();
  await shot(page, "home");
});

test("owner creates a page, customer books, owner confirms", async ({ browser }) => {
  const id = run();
  const owner = await signup(browser, `own${id}`, "Ramesh Sharma");
  await owner.goto("/dashboard");
  await expect(owner.getByLabel("Business name")).toBeVisible();
  expect(await owner.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await owner.getByLabel("Business name").fill("Sharma Electricals");
  await owner.getByLabel("Page address").fill(`sharma-${id}`);
  await owner.getByLabel("Tagline").fill("Wiring, fans and repairs");
  await owner.getByRole("button", { name: "Create page" }).click();
  await expect(owner.getByRole("heading", { name: "Sharma Electricals" })).toBeVisible();
  await owner.getByLabel("Service name").fill("Fan installation");
  await owner.getByLabel("Service price (₹)").fill("499");
  await owner.getByRole("button", { name: "Add service" }).click();
  await expect(owner.getByText("₹499 · 60 min")).toBeVisible();
  await shot(owner, "dashboard");

  const customer = await signup(browser, `cus${id}`, "Priya Verma");
  await customer.goto(`/business/sharma-${id}`);
  await expect(customer.getByRole("heading", { name: "Sharma Electricals" })).toBeVisible();
  // Tomorrow is always open (Mon-Sat default hours) unless it is Sunday; pick the first day with free times.
  const days = customer.getByRole("group", { name: "Day" }).getByRole("button");
  for (let i = 1; i < 7; i++) {
    await days.nth(i).click();
    if (await customer.getByRole("group", { name: "Available times" }).isVisible().catch(() => false)) break;
  }
  await customer.getByRole("group", { name: "Available times" }).getByRole("button").first().click();
  await shot(customer, "business-page");
  await expect(customer.getByRole("button", { name: /^Book .*₹499$/ })).toBeVisible();
  await customer.getByRole("button", { name: /^Book / }).click();
  await expect(customer.getByText(/Booking requested/)).toBeVisible();
  await customer.goto("/bookings");
  await expect(customer.getByText("pending")).toBeVisible();

  await owner.reload();
  for (let i = 0; i < 7 && !(await owner.getByRole("button", { name: "Confirm" }).isVisible()); i++) {
    await owner.getByRole("group", { name: "Day" }).getByRole("button").nth(i).click();
    await owner.waitForTimeout(500);
  }
  await owner.getByRole("button", { name: "Confirm" }).click();
  await expect(owner.getByText("confirmed")).toBeVisible();
  await customer.reload();
  await expect(customer.getByText("confirmed")).toBeVisible();
  await expect(async () => {  // delivered by the worker via the outbox, so poll with reloads
    await customer.goto("/notifications");
    await expect(customer.getByText(/Booking confirmed: Fan installation/)).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
});

test("post to the feed, follower sees it, likes it", async ({ browser }) => {
  const id = run();
  const asha = await signup(browser, `asha${id}`, "Asha Mehndi");
  const ravi = await signup(browser, `ravi${id}`, "Ravi Kumar");
  await ravi.goto(`/asha${id}`);
  await ravi.getByRole("button", { name: "Follow" }).click();
  await expect(ravi.getByRole("button", { name: "Following" })).toBeVisible();

  await asha.goto("/feed");
  await asha.getByLabel("Caption").fill(`Bridal mehndi booking open #mehndi ${id}`);
  await asha.getByRole("button", { name: "Post", exact: true }).click();
  await expect(asha.getByText(`Bridal mehndi booking open`)).toBeVisible();

  await expect(async () => {
    await ravi.goto("/feed");
    await expect(ravi.getByText(`Bridal mehndi booking open`)).toBeVisible({ timeout: 2000 });
  }).toPass({ timeout: 30_000 });
  await ravi.getByRole("button", { name: /♥ 0/ }).click();
  await expect(ravi.getByRole("button", { name: /♥ 1/ })).toBeVisible();
  await shot(ravi, "feed");
});

test("live chat delivers without reload", async ({ browser }) => {
  const id = run();
  const asha = await signup(browser, `cha${id}`, "Asha Chat");
  const ravi = await signup(browser, `chr${id}`, "Ravi Chat");
  await ravi.goto(`/cha${id}`);
  await ravi.getByRole("button", { name: "Message" }).click();
  await expect(ravi).toHaveURL(/\/messages\?c=/);
  const url = ravi.url();
  await asha.goto(url.replace(/^https?:\/\/[^/]+/, ""));
  await expect(asha.getByText("live")).toBeVisible();
  await expect(ravi.getByText("live")).toBeVisible();
  await ravi.getByLabel("Message", { exact: true }).fill(`Namaste ${id}`);
  await ravi.getByRole("button", { name: "Send" }).click();
  await expect(asha.getByText(`Namaste ${id}`)).toBeVisible({ timeout: 10_000 }); // pushed over WebSocket
  await shot(asha, "messages");
});
