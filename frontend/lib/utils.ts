import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combina clases Tailwind con resolución de conflictos.
 * Estándar de shadcn/ui: `cn("p-2", isActive && "p-4")` produce "p-4".
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
