import { useMemo } from "react";
import { ShieldCheck } from "lucide-react";
import { Button } from "./components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./components/ui/card";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";

function getTokenFromPath() {
  const path = window.location.pathname;
  const parts = path.split("/auth/");
  if (parts.length < 2) return "";
  return parts[1].split("/")[0];
}

export default function App() {
  const token = useMemo(() => getTokenFromPath(), []);
  const action = token ? `/auth/${token}` : window.location.pathname;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl items-center justify-center px-6 py-12">
      <div className="w-full space-y-6">
        <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/40 px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Telegram Login
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Вхід в акаунт</CardTitle>
            <CardDescription>
              Введіть код, який прийшов у Telegram або SMS. Якщо увімкнено 2FA — додайте пароль.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form method="post" action={action} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="code">Код з Telegram/SMS</Label>
                <Input id="code" name="code" inputMode="numeric" autoComplete="one-time-code" placeholder="12345" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Пароль 2FA (якщо увімкнено)</Label>
                <Input id="password" name="password" type="password" autoComplete="current-password" placeholder="••••••••" />
              </div>
              <div className="space-y-3">
                <Button type="submit" className="w-full">Підтвердити вхід</Button>
                <p className="text-xs text-muted-foreground">
                  Після відправки поверніться в бот і натисніть «Перевірити вхід».
                </p>
              </div>
            </form>
            <div className="mt-6 h-px w-full bg-gradient-to-r from-transparent via-border/60 to-transparent" />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <span>Безпека: код діє обмежений час</span>
              <span>Підтримка: напишіть у бот</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
