// How long ago a timestamp was, e.g. "2 hours ago" or "1 week ago".
const units: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60],
  ["month", 30 * 24 * 60 * 60],
  ["week", 7 * 24 * 60 * 60],
  ["day", 24 * 60 * 60],
  ["hour", 60 * 60],
  ["minute", 60],
];

const format = new Intl.RelativeTimeFormat("en", { numeric: "always" });

export function timeAgo(
  timestamp: string | Date,
  now: Date = new Date(),
): string {
  const seconds = Math.max(
    0,
    (now.getTime() - new Date(timestamp).getTime()) / 1000,
  );
  for (const [unit, size] of units) {
    if (seconds >= size)
      return format.format(-Math.floor(seconds / size), unit);
  }
  return "just now";
}
