/**
 * /dev-login — atajo SOLO para desarrollo local sin Clerk.
 *
 * Renderiza un form que dispara una Server Action setting cookies
 * (`praxis_dev_token` + `praxis_despacho_id`). Después el usuario navega
 * normal y el backend acepta el token fake porque corre en `ENV=dev`.
 *
 * En producción (`NODE_ENV=production`), esta página tira 404.
 */
import { notFound } from "next/navigation";

import { devLoginAction } from "@/app/actions/despacho";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export const metadata = { title: "Dev login" };

export default function DevLoginPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | undefined>>;
}) {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <DevLoginForm searchParams={searchParams} />;
}

async function DevLoginForm({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | undefined>>;
}) {
  const params = (await searchParams) ?? {};
  const presetClerk = params.clerkId ?? "user_agustin";
  const presetDespacho = params.despachoId ?? "";

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold tracking-tight">Praxis Asesor</h1>
          <p className="mt-2 text-sm text-muted-foreground">Modo desarrollo</p>
        </div>

        <Card className="space-y-4 p-6">
          <div>
            <p className="text-sm font-medium">Entrar sin Clerk</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Este atajo solo funciona en desarrollo local. Setea cookies que el backend
              acepta porque está corriendo con <code>ENV=dev</code>.
            </p>
          </div>

          <form action={devLoginAction} className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="clerkId" className="text-xs font-medium uppercase text-muted-foreground">
                ID del usuario (auth_provider_id seedeado)
              </label>
              <Input
                id="clerkId"
                name="clerkId"
                defaultValue={presetClerk}
                required
                autoComplete="off"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="despachoId" className="text-xs font-medium uppercase text-muted-foreground">
                Despacho ID (UUID)
              </label>
              <Input
                id="despachoId"
                name="despachoId"
                defaultValue={presetDespacho}
                placeholder="UUID del despacho seedeado"
                required
                autoComplete="off"
                pattern="^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
              />
            </div>

            <Button type="submit" className="w-full">
              Entrar como {presetClerk}
            </Button>
          </form>
        </Card>

        <p className="text-center text-xs text-muted-foreground">
          ¿Necesitás IDs? Corré{" "}
          <code className="rounded bg-muted px-1 py-0.5 text-xs">
            uv run python -m scripts.seed_inicial --email tu@email --nombre Vos --clerk-id user_agustin
          </code>
        </p>
      </div>
    </main>
  );
}
