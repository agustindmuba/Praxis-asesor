import { redirect } from "next/navigation";

/**
 * El root no tiene contenido propio — los usuarios autenticados van al
 * dashboard, los no autenticados van a sign-in (el middleware Clerk los
 * intercepta y redirige).
 */
export default function RootPage() {
  redirect("/dashboard");
}
