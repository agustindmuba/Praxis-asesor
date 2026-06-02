/**
 * /dev-login — atajo SOLO para desarrollo local sin Clerk.
 *
 * Renderiza un form que dispara una Server Action setting cookies
 * (`praxis_dev_token` + `praxis_despacho_id`). Después el usuario navega
 * normal y el backend acepta el token fake porque corre en `ENV=dev`.
 *
 * En producción (`NODE_ENV=production`), esta página tira 404.
 *
 * Diseño feat/33: marca Praxis aplicada. Fondo crema, brand strip
 * superior, placa blanca con borde fino, tipografía display Space
 * Grotesk en el titular.
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
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md space-y-7">
        {/* Brand strip */}
        <div className="space-y-1 text-center">
          <p className="font-display text-3xl font-bold tracking-tight text-[var(--color-praxis-azul)]">
            Praxis
            <span className="text-[var(--color-praxis-salmon)]">.</span>
          </p>
          <p className="text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
            Decisiones estratégicas basadas en datos
          </p>
        </div>

        <Card className="space-y-5 border-border bg-card p-7 shadow-none">
          <div>
            <h2 className="font-display text-lg font-semibold text-[var(--color-praxis-azul)]">
              Entrar al despacho
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Atajo de desarrollo local. Setea cookies que el backend acepta
              porque corre con <code className="text-foreground">ENV=dev</code>.
            </p>
          </div>

          <form action={devLoginAction} className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="clerkId"
                className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                Usuario (auth_provider_id)
              </label>
              <Input
                id="clerkId"
                name="clerkId"
                defaultValue={presetClerk}
                required
                autoComplete="off"
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="despachoId"
                className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                Despacho (UUID)
              </label>
              <Input
                id="despachoId"
                name="despachoId"
                defaultValue={presetDespacho}
                placeholder="0a8cf4c0-3b95-44bf-93c5-c8aebff97306"
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
          <code className="rounded bg-secondary px-1.5 py-0.5 text-[10.5px]">
            uv run python -m scripts.seed_inicial
          </code>{" "}
          en el backend.
        </p>
      </div>
    </main>
  );
}
