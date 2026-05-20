import Link from "next/link";

// Hit when `getSharedTrip` rejects (404 or transport error). Stays
// intentionally generic so we never confirm whether the token ever
// existed.
export default function SharedTripNotFound() {
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-bold tracking-tight">Link expired or revoked.</h1>
      <p className="text-muted-foreground text-sm">
        This share link is no longer active. Ask the person who sent it for a new one.
      </p>
      <Link href="/" className="text-sm underline underline-offset-4">
        Go to Plus One
      </Link>
    </main>
  );
}
