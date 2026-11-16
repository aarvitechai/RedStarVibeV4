import { describe, expect, it } from "vitest";
import { dayLabel, rupees, timeIn } from "./format";

describe("format", () => {
  it("formats paise as rupees", () => {
    expect(rupees(49900)).toBe("₹499");
    expect(rupees(12345)).toBe("₹123.45");
    expect(rupees(10000000)).toBe("₹1,00,000");
  });

  it("shows times in the business time zone", () => {
    expect(timeIn("2027-01-04T04:30:00Z", "Asia/Kolkata").toLowerCase()).toContain("10:00");
  });

  it("labels a calendar date without shifting it", () => {
    expect(dayLabel("2027-01-04")).toContain("4");
  });
});
