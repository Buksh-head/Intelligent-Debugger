/**
 * Theme shared by the student, session history and instructor pages, so a
 * choice made on one page carries over to the others.
 */

export const themeOptions = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
  { label: "Synthwave", value: "synthwave" },
  { label: "Forest", value: "forest" },
  { label: "Luxury", value: "luxury" },
] as const;

export type Theme = (typeof themeOptions)[number]["value"];
export const themeStorageKey = "debugging-assistant.theme";

// Use the saved theme if there is one, otherwise match the device's light/dark setting.
export const getInitialTheme = (): Theme => {
  const savedTheme = localStorage.getItem(themeStorageKey);
  const savedOption = themeOptions.find(
    (option) => option.value === savedTheme,
  );
  if (savedOption) return savedOption.value;

  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
};
