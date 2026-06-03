/**
 * Layout de las rutas de auth (sign-in, sign-up).
 *
 * Sin sidebar ni navegación — pantalla centrada. La marca aparece como
 * logo PNG (no como texto) — consistente con sidebar y dev-login.
 */
import Image from "next/image";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <Image
            src="/logo-praxis-asesor.png"
            alt="Praxis Asesor"
            width={800}
            height={208}
            priority
            className="mx-auto h-24 w-auto"
          />
          <p className="mt-3 text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
            Decisiones estratégicas basadas en datos
          </p>
        </div>
        {children}
      </div>
    </main>
  );
}
