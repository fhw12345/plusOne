import Link from "next/link";

export default function HomePage() {
  return (
    <div className="shell" style={{ maxWidth: 820 }}>
      <p className="crest" style={{ marginTop: 18 }}>
        <span className="crest-dot" />
        PLUS &middot; ONE &middot; a travel planner
      </p>

      <section style={{ position: "relative", paddingTop: 60 }}>
        <span
          className="tape tape--mint"
          style={{ top: 28, left: 32, width: 130, height: 28, transform: "rotate(-6deg)" }}
        />
        <span
          className="tape tape--yellow"
          style={{ top: 36, right: 70, width: 86, height: 24, transform: "rotate(6deg)" }}
        />

        <h1 className="hand-xxl" style={{ marginBottom: 18 }}>
          plus one
        </h1>
        <p className="scrawl" style={{ fontSize: 19, maxWidth: 540, transform: "rotate(-.3deg)" }}>
          a quiet travel notebook. i ask around, cross-check, and write down the places worth your
          time &mdash; the ones the locals actually go to, not the ones with the queue.
        </p>

        <div style={{ marginTop: 56, display: "flex", alignItems: "center", gap: 22 }}>
          <Link href="/login" className="btn">
            let me in
          </Link>
          <span className="annot" style={{ fontSize: 16 }}>
            &uarr; one email, one link
          </span>
        </div>

        <p
          className="hand"
          style={{ marginTop: 64, fontSize: 22, maxWidth: 560, transform: "rotate(-.2deg)" }}
        >
          tell me where you&apos;re going. i&apos;ll dig through reddit, 小红书 and a couple of map
          databases, then write you a short list with sources you can verify.
        </p>

        <p className="scrawl" style={{ marginTop: 18, maxWidth: 540 }}>
          no algorithm slop, no &ldquo;top 10&rdquo;. just notes from someone who took the time.
        </p>
      </section>

      <footer
        style={{
          marginTop: 120,
          paddingTop: 18,
          borderTop: "1px dotted hsl(var(--kraft))",
        }}
      >
        <p className="type">
          PLUS &middot; ONE &middot; v0.1 &middot; tokyo &middot; taipei &middot; everywhere quiet
        </p>
      </footer>
    </div>
  );
}
