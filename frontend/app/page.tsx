import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-4xl font-bold tracking-tight">Plus One</h1>
      <p className="text-muted-foreground text-center text-lg">
        AI travel planner — local gems vs tourist traps, with sources you can verify.
      </p>
      <p className="text-muted-foreground text-sm">🚧 Phase α — under construction</p>
      <Link href="/login" className="text-foreground underline underline-offset-4">
        Sign in
      </Link>
    </main>
  );
}
