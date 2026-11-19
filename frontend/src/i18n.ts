import { useEffect, useSyncExternalStore } from "react";
import { portuguese } from "./portuguese";

type Language = "en" | "pt-BR";
const key = "identityops.language";
function storedLanguage(): Language {
  try { return localStorage.getItem(key) === "pt-BR" ? "pt-BR" : "en"; }
  catch { return "en"; }
}

let language = storedLanguage();
const listeners = new Set<() => void>();
document.documentElement.lang = language;

export function setLanguage(next: Language) {
  language = next;
  document.documentElement.lang = next;
  try { localStorage.setItem(key, next); } catch { /* Remain usable when storage is unavailable. */ }
  listeners.forEach(listener => listener());
}

export function useLanguage() {
  return useSyncExternalStore(listener => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => language);
}

export function locale() { return language; }

export function t(message: string, values?: Record<string, string | number>) {
  const translated = language === "pt-BR" && Object.hasOwn(portuguese, message) ? portuguese[message] : message;
  return values ? translated.replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match)) : translated;
}

export function useLocalizedValidation() {
  useEffect(() => {
    function control(event: Event) {
      const target = event.target;
      return target instanceof HTMLInputElement || target instanceof HTMLSelectElement ||
        target instanceof HTMLTextAreaElement ? target : null;
    }
    function invalid(event: Event) {
      const field = control(event);
      if (!field) return;
      const validity = field.validity;
      field.setCustomValidity(t(validity.valueMissing ? "This field is required." :
        validity.typeMismatch ? "Check the format of this value." :
        validity.tooShort ? "The text is too short." :
        validity.tooLong ? "The text is too long." :
        validity.rangeOverflow || validity.rangeUnderflow ? "The value is outside the allowed range." :
        "Check this value and try again."));
    }
    function clear(event: Event) { control(event)?.setCustomValidity(""); }
    document.addEventListener("invalid", invalid, true);
    document.addEventListener("input", clear);
    document.addEventListener("change", clear);
    return () => {
      document.removeEventListener("invalid", invalid, true);
      document.removeEventListener("input", clear);
      document.removeEventListener("change", clear);
    };
  }, []);
}
