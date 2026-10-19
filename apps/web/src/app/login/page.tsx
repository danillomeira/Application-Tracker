"use client";

import { useQuery } from "@tanstack/react-query";
import { LogIn, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { Button, Card, EASE } from "@/components/ui";

export default function LoginPage() {
  const config = useQuery({
    queryKey: ["auth-config"],
    queryFn: async () => (await fetch("/api/v1/auth/config")).json() as Promise<{ google: boolean; dev_login: boolean }>,
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(900px_500px_at_20%_0%,color-mix(in_oklab,var(--primary)_18%,transparent),transparent),radial-gradient(800px_500px_at_100%_100%,color-mix(in_oklab,#8b5cf6_14%,transparent),transparent)] p-4">
      <motion.div className="w-full max-w-sm" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: EASE }}>
        <Card className="p-8 shadow-[var(--shadow-lift)]">
          <motion.div
            className="mb-5 grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-primary to-violet-500 text-white shadow-lg shadow-primary/30"
            initial={{ scale: 0.6, rotate: -12 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 16, delay: 0.1 }}
          >
            <Sparkles size={22} />
          </motion.div>
          <h1 className="text-xl font-semibold tracking-tight">Application Tracker</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">Sua busca de emprego organizada: vagas avaliadas, currículos sob medida e acompanhamento.</p>
          <div className="flex flex-col gap-2">
            {config.data?.dev_login && (
              <form action="/api/v1/auth/dev-login" method="post">
                <Button className="w-full" size="lg" type="submit">
                  <LogIn size={16} /> Entrar
                </Button>
              </form>
            )}
            <a href="/api/v1/auth/google/login" aria-disabled={!config.data?.google}>
              <Button className="w-full" variant={config.data?.dev_login ? "outline" : "default"} size="lg" disabled={!config.data?.google}>
                Entrar com Google
              </Button>
            </a>
            {config.data && !config.data.google && (
              <p className="text-xs text-muted-foreground">
                {config.data.dev_login
                  ? "Rodando no seu computador, “Entrar” basta. O login Google só é necessário se você expuser o app na internet."
                  : "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env para usar o login Google."}
              </p>
            )}
          </div>
        </Card>
      </motion.div>
    </div>
  );
}
