/**
 * Layout de las rutas de auth (sign-in, sign-up).
 *
 * Sin sidebar ni navegación — pantalla centrada.
 */
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold tracking-tight">Praxis Asesor</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sistema operativo del despacho parlamentario
          </p>
        </div>
        {children}
      </div>
    </main>
  );
}
