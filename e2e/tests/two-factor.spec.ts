import { createHmac } from "node:crypto";
import { expect, test } from "@playwright/test";

/** RFC 6238 TOTP, same parameters as the server (SHA-1, 30 s, 6 digits). */
function totp(secretB32: string, offsetSteps = 0): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secretB32.replace(/=+$/, "")) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((b) => parseInt(b, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000) + offsetSteps));
  const h = createHmac("sha1", key).update(counter).digest();
  const o = h[h.length - 1]! & 0x0f;
  return String((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

test("turn on two-factor login and sign in with a code", async ({ page }) => {
  const id = `${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
  await page.goto("/signup");
  await page.getByLabel("Name", { exact: true }).fill("Secure Sana");
  await page.getByLabel("Username").fill(`sana${id}`);
  await page.getByLabel("Email", { exact: true }).fill(`sana${id}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("E2e-Passw0rd-123");
  await page.getByLabel("I am 18 or older").check();
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page).toHaveURL(/\/account$/);

  await page.getByRole("button", { name: "Set up two-factor login" }).click();
  await expect(page.getByAltText(/QR code to add RedStarVibe/)).toBeVisible();
  const secret = (await page.locator("code").first().textContent())!.trim();
  await page.getByLabel("6-digit code").fill(totp(secret));
  await page.getByRole("button", { name: "Turn on" }).click();
  await expect(page.getByText(/^On\. You will be asked for a code/)).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(`sana${id}@example.com`);
  await page.getByLabel("Password").fill("E2e-Passw0rd-123");
  await page.getByRole("button", { name: "Log in" }).click();
  await page.getByLabel("Code from your authenticator app").fill("000000");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText(/That code is not right/)).toBeVisible();
  await page.getByLabel("Code from your authenticator app").fill(totp(secret, 1)); // next step: the current one was used to confirm
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/account$/);
  await expect(page.getByRole("heading", { name: "Hi, Secure Sana" })).toBeVisible();
});
