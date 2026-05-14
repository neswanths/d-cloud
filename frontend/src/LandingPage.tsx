import { useState, useEffect, useRef } from "react";

const LIBERTY = "#0e1531";
const LAVENDER = "#7B3FF2";
const LAVENDER_BRIGHT = "#9D5FFF";
const LAVENDER_GLOW = "rgba(123,63,242,0.35)";

function useInView(threshold = 0.15) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVisible(true); }, { threshold });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, visible] as const;
}

function FadeUp({ children, delay = 0, className = "" }: { children: React.ReactNode, delay?: number, className?: string }) {
  const [ref, visible] = useInView();
  return (
    <div ref={ref} className={className} style={{
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(40px)",
      transition: `opacity 0.8s ease ${delay}s, transform 0.8s ease ${delay}s`,
    }}>{children}</div>
  );
}

function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let animId: number;
    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener("resize", resize);

    const nodes = Array.from({ length: 55 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 2.5 + 1,
    }));

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      nodes.forEach(n => {
        n.x += n.vx; n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(157,95,255,0.6)";
        ctx.fill();
      });
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 130) {
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.strokeStyle = `rgba(123,63,242,${0.18 * (1 - dist / 130)})`;
            ctx.lineWidth = 1;
            ctx.stroke();
          }
        }
      }
      animId = requestAnimationFrame(draw);
    };
    draw();
    return () => { cancelAnimationFrame(animId); window.removeEventListener("resize", resize); };
  }, []);
  return <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, zIndex: 0, opacity: 0.7 }} />;
}

function PulsingNode({ label, status = "online", delay = "0s" }: { label: string, status?: "online" | "offline", delay?: string }) {
  const color = status === "online" ? LAVENDER_BRIGHT : "#ff4466";
  const label2 = status === "online" ? "● LIVE" : "✕ DOWN";
  return (
    <div style={{
      background: "rgba(14,21,49,0.8)", border: `1px solid ${status === "online" ? "rgba(123,63,242,0.4)" : "rgba(255,68,102,0.3)"}`,
      borderRadius: 12, padding: "16px 20px", textAlign: "center", position: "relative", overflow: "hidden",
    }}>
      <div style={{
        width: 10, height: 10, borderRadius: "50%", background: color,
        margin: "0 auto 10px",
        boxShadow: status === "online" ? `0 0 12px ${LAVENDER_GLOW}` : "none",
        animation: status === "online" ? `nodePulse 2s infinite ${delay}` : "none",
      }} />
      <div style={{ fontSize: 11, fontWeight: 700, fontFamily: "'Space Mono', monospace", color: "#c4b5fd", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 10, color: status === "online" ? LAVENDER_BRIGHT : "#ff4466", letterSpacing: "0.08em" }}>{label2}</div>
    </div>
  );
}

const steps = [
  { num: "01", title: "Chunk & Hash", desc: "File is split into content-addressed chunks. Each chunk receives a SHA-256 hash — its permanent tamper-proof identity.", tag: "Content Addressing" },
  { num: "02", title: "Sign & Distribute", desc: "Each node signs the chunks it stores. No central authority — just cryptographic proof that lives on the node itself.", tag: "P2P Distribution" },
  { num: "03", title: "Validate Locally", desc: "Retrieval triggers local validation on the serving node. Hash mismatches and bad signatures are rejected before data leaves the node.", tag: "Local Verification" },
  { num: "04", title: "Reassemble", desc: "Surviving chunks are gathered from available nodes and reconstructed. Zero data loss — even with multiple nodes offline.", tag: "Fault Tolerance" },
];

const concepts = [
  { icon: "⬡", title: "Agent-Centric Identity", body: "Every node generates its own cryptographic keypair at startup. Identity is self-sovereign — there's no central registry to breach, revoke, or compromise.", tag: "Identity" },
  { icon: "🛡", title: "Local Validation, Shared Rules", body: "Nodes validate operations independently using shared rule sets — not a global ledger. No consensus bottleneck, no waiting for network-wide agreement.", tag: "Consensus-Free" },
  { icon: "🌐", title: "DHT-Based Storage", body: "A distributed hash table routes data across nodes by content address. The network knows where every chunk lives without any master index server.", tag: "Storage" },
  { icon: "⚡", title: "Sub-Blockchain Latency", body: "By eliminating global consensus, D-Cloud achieves cloud-native response times. The performance cost of decentralization drops to near zero.", tag: "Performance" },
  { icon: "🔄", title: "Failure Isolation", body: "Node failures are strictly local. When Node 1 dies, Nodes 2 and 3 keep serving. No cascading failures — the network heals automatically.", tag: "Resilience" },
  { icon: "🔐", title: "Cryptographic Data Integrity", body: "Every chunk carry a hash and signature. Tampered or corrupted data is detected and refused on retrieval — before it reaches your application.", tag: "Integrity" },
];

export function LandingPage({ onLaunchApp }: { onLaunchApp: () => void }) {
  const [navScrolled, setNavScrolled] = useState(false);
  const [activeChunk, setActiveChunk] = useState<number | null>(null);

  useEffect(() => {
    const onScroll = () => setNavScrolled(window.scrollY > 40);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const chunks = [0, 1, 2, 3, 4, 5, 6, 7, 8];
    let i = 0;
    const interval = setInterval(() => { setActiveChunk(chunks[i % chunks.length]); i++; }, 500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ background: LIBERTY, color: "#e8e4ff", fontFamily: "'DM Sans', sans-serif", overflowX: "hidden" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&family=Space+Mono:wght@400;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: ${LIBERTY}; } ::-webkit-scrollbar-thumb { background: ${LAVENDER}; border-radius: 3px; }
        @keyframes nodePulse { 0%,100% { box-shadow: 0 0 8px rgba(157,95,255,0.5); } 50% { box-shadow: 0 0 20px rgba(157,95,255,0.9); } }
        @keyframes float { 0%,100% { transform: translateY(0px); } 50% { transform: translateY(-12px); } }
        @keyframes rotateGlow { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        @keyframes shimmer { 0% { background-position: -200% center; } 100% { background-position: 200% center; } }
        @keyframes chunkPop { 0% { transform: scale(1); } 50% { transform: scale(1.15); } 100% { transform: scale(1); } }
        .glow-text {
          background: linear-gradient(135deg, #fff 0%, #c4b5fd 40%, ${LAVENDER_BRIGHT} 100%);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .lavender-text { color: ${LAVENDER_BRIGHT}; }
        .card-hover { transition: all 0.3s ease; cursor: default; }
        .card-hover:hover { transform: translateY(-4px); border-color: rgba(123,63,242,0.5) !important; background: rgba(123,63,242,0.08) !important; }
        .nav-link { color: rgba(196,181,253,0.7); text-decoration: none; font-size: 14px; transition: color 0.2s; }
        .nav-link:hover { color: #fff; }
        .btn-main { background: ${LAVENDER}; color: #fff; border: none; padding: 14px 32px; border-radius: 10px; font-family: 'DM Sans'; font-size: 15px; font-weight: 500; cursor: pointer; transition: all 0.25s; letter-spacing: -0.01em; }
        .btn-main:hover { background: ${LAVENDER_BRIGHT}; box-shadow: 0 8px 32px rgba(123,63,242,0.4); transform: translateY(-2px); }
        .btn-outline { background: transparent; color: #c4b5fd; border: 1px solid rgba(123,63,242,0.4); padding: 14px 32px; border-radius: 10px; font-family: 'DM Sans'; font-size: 15px; cursor: pointer; transition: all 0.25s; }
        .btn-outline:hover { border-color: ${LAVENDER_BRIGHT}; background: rgba(123,63,242,0.1); }
        .step-card { background: rgba(123,63,242,0.06); border: 1px solid rgba(123,63,242,0.2); border-radius: 16px; padding: 36px 30px; transition: all 0.3s; }
        .step-card:hover { background: rgba(123,63,242,0.12); border-color: rgba(123,63,242,0.45); transform: translateY(-4px); }
      `}</style>

      {/* NAV */}
      <nav style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "18px 52px",
        background: navScrolled ? "rgba(14,21,49,0.92)" : "transparent",
        backdropFilter: navScrolled ? "blur(20px)" : "none",
        borderBottom: navScrolled ? "1px solid rgba(123,63,242,0.2)" : "1px solid transparent",
        transition: "all 0.4s ease",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: `linear-gradient(135deg, ${LAVENDER}, ${LAVENDER_BRIGHT})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 800, fontFamily: "'Syne'" }}>D</div>
          <span style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: 18, letterSpacing: "-0.02em" }}>D<span style={{ color: LAVENDER_BRIGHT }}>-</span>Cloud</span>
        </div>
        <div style={{ display: "flex", gap: 36, alignItems: "center" }}>
          {["Architecture", "How It Works", "Security", "Docs"].map(l => <a key={l} href="#" className="nav-link">{l}</a>)}
        </div>
        <button className="btn-main" style={{ padding: "10px 22px", fontSize: 13 }} onClick={onLaunchApp}>Launch Dashboard</button>
      </nav>

      {/* HERO */}
      <section style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", position: "relative", overflow: "hidden", padding: "140px 24px 100px", textAlign: "center" }}>
        <ParticleField />
        <div style={{ position: "absolute", top: "30%", left: "50%", transform: "translate(-50%,-50%)", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(123,63,242,0.18) 0%, transparent 70%)", pointerEvents: "none", zIndex: 0 }} />
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "rgba(123,63,242,0.15)", border: "1px solid rgba(123,63,242,0.35)", borderRadius: 100, padding: "6px 18px", marginBottom: 32 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: LAVENDER_BRIGHT, display: "inline-block" }} />
            <span style={{ fontSize: 12, color: "#c4b5fd", letterSpacing: "0.12em", textTransform: "uppercase", fontWeight: 500 }}>Decentralized Cloud Infrastructure</span>
          </div>
          <h1 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(3rem, 8vw, 6rem)", lineHeight: 1.0, letterSpacing: "-0.04em", marginBottom: 28, maxWidth: 820, margin: "0 auto 28px" }}>
            <span className="glow-text">Cloud without</span>
            <br />
            <span style={{ color: LAVENDER_BRIGHT }}>a single point</span>
            <br />
            <span className="glow-text">of failure</span>
          </h1>
          <p style={{ color: "rgba(196,181,253,0.75)", fontSize: 18, maxWidth: 560, margin: "0 auto 48px", lineHeight: 1.7, fontWeight: 300 }}>
            D-Cloud distributes trust across independently verifiable nodes — no centralized control plane, no vendor lock-in, no global ledger overhead.
          </p>
          <div style={{ display: "flex", gap: 16, justifyContent: "center", flexWrap: "wrap" }}>
            <button className="btn-main" onClick={onLaunchApp}>Launch Dashboard</button>
            <button className="btn-outline">View Architecture →</button>
          </div>
          <div style={{ display: "flex", gap: 48, justifyContent: "center", marginTop: 72, flexWrap: "wrap" }}>
            {[["0", "Single Points of Failure"], ["∞", "Node Scalability"], ["100%", "Data Sovereignty"], ["<ms", "Local Validation"]].map(([num, label]) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: 32, color: LAVENDER_BRIGHT, letterSpacing: "-0.04em" }}>{num}</div>
                <div style={{ fontSize: 12, color: "rgba(196,181,253,0.55)", marginTop: 4, letterSpacing: "0.05em" }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* TRUSTED BAR */}
      <div style={{ borderTop: "1px solid rgba(123,63,242,0.2)", borderBottom: "1px solid rgba(123,63,242,0.2)", padding: "22px 52px", display: "flex", alignItems: "center", justifyContent: "center", gap: 64, flexWrap: "wrap", background: "rgba(123,63,242,0.04)" }}>
        <span style={{ fontSize: 11, color: "rgba(196,181,253,0.4)", letterSpacing: "0.15em", textTransform: "uppercase" }}>Built for</span>
        {["Zero Downtime", "Data Sovereignty", "Cryptographic Trust", "Vendor Freedom", "Agent-Centric Design"].map(t => (
          <span key={t} style={{ fontFamily: "'Syne'", fontWeight: 700, fontSize: 13, color: "rgba(196,181,253,0.55)", letterSpacing: "0.05em" }}>{t}</span>
        ))}
      </div>

      {/* CORE CONCEPTS */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "110px 48px" }}>
        <FadeUp>
          <div style={{ marginBottom: 16, fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500 }}>Core Architecture</div>
          <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(2rem, 4vw, 3.2rem)", letterSpacing: "-0.03em", marginBottom: 16, maxWidth: 640, lineHeight: 1.1 }}>
            Distributed trust for<br /><span style={{ color: LAVENDER_BRIGHT }}>modern cloud workloads</span>
          </h2>
          <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 16, maxWidth: 520, lineHeight: 1.75, marginBottom: 64, fontWeight: 300 }}>
            Every concept in D-Cloud eliminates a specific failure mode of centralized systems — from identity to storage to consensus.
          </p>
        </FadeUp>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          {concepts.map((c, i) => (
            <FadeUp key={c.title} delay={i * 0.08}>
              <div className="card-hover" style={{ background: "rgba(123,63,242,0.05)", border: "1px solid rgba(123,63,242,0.18)", borderRadius: 16, padding: "36px 30px", height: "100%" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
                  <div style={{ width: 48, height: 48, borderRadius: 12, background: "rgba(123,63,242,0.15)", border: "1px solid rgba(123,63,242,0.3)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>{c.icon}</div>
                  <span style={{ fontSize: 10, color: LAVENDER_BRIGHT, border: `1px solid rgba(123,63,242,0.3)`, borderRadius: 100, padding: "3px 10px", letterSpacing: "0.1em", textTransform: "uppercase" }}>{c.tag}</span>
                </div>
                <h3 style={{ fontFamily: "'Syne'", fontWeight: 700, fontSize: 17, letterSpacing: "-0.02em", marginBottom: 12, color: "#fff" }}>{c.title}</h3>
                <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 14, lineHeight: 1.7 }}>{c.body}</p>
              </div>
            </FadeUp>
          ))}
        </div>
      </section>

      {/* HOW IT WORKS */}
      <div style={{ background: "rgba(123,63,242,0.04)", borderTop: "1px solid rgba(123,63,242,0.12)", borderBottom: "1px solid rgba(123,63,242,0.12)", padding: "110px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 48px" }}>
          <FadeUp>
            <div style={{ marginBottom: 16, fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500 }}>How It Works</div>
            <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(2rem, 4vw, 3rem)", letterSpacing: "-0.03em", marginBottom: 16, lineHeight: 1.1 }}>
              From upload to retrieval<br /><span style={{ color: LAVENDER_BRIGHT }}>without a control plane</span>
            </h2>
            <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 16, maxWidth: 480, lineHeight: 1.75, marginBottom: 64, fontWeight: 300 }}>
              D-Cloud's agent-centric model makes every operation self-contained, verifiable, and survivable.
            </p>
          </FadeUp>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
            {steps.map((s, i) => (
              <FadeUp key={s.num} delay={i * 0.1}>
                <div className="step-card">
                  <div style={{ fontFamily: "'Syne'", fontSize: 52, fontWeight: 800, color: "rgba(123,63,242,0.25)", lineHeight: 1, marginBottom: 28, letterSpacing: "-0.05em" }}>{s.num}</div>
                  <div style={{ width: 2, height: 32, background: `linear-gradient(to bottom, ${LAVENDER_BRIGHT}, transparent)`, marginBottom: 20, borderRadius: 2 }} />
                  <h4 style={{ fontFamily: "'Syne'", fontWeight: 700, fontSize: 16, marginBottom: 12, color: "#fff" }}>{s.title}</h4>
                  <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 13.5, lineHeight: 1.65 }}>{s.desc}</p>
                  <div style={{ marginTop: 24, fontSize: 10, color: LAVENDER_BRIGHT, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 600 }}>{s.tag}</div>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </div>

      {/* LIVE DEMO VISUAL */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "110px 48px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "center" }}>
          <FadeUp>
            <div style={{ fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500, marginBottom: 16 }}>Fault Tolerance</div>
            <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(1.8rem, 3vw, 2.8rem)", letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: 20 }}>
              Watch data survive<br /><span style={{ color: LAVENDER_BRIGHT }}>node failures live</span>
            </h2>
            <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 15, lineHeight: 1.75, marginBottom: 36, fontWeight: 300 }}>
              The live dashboard visualizes chunk distribution and node health. Kill Node 1 — data survives. Kill Node 2 — still alive. Judges go "oh."
            </p>
            {["Real-time node health monitoring with instant failure detection", "Automatic rerouting when a node becomes unreachable", "Visual chunk distribution map showing where each piece lives"].map(t => (
              <div key={t} style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
                <div style={{ width: 20, height: 20, borderRadius: "50%", background: "rgba(123,63,242,0.2)", border: `1px solid ${LAVENDER}`, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 2 }}>
                  <span style={{ color: LAVENDER_BRIGHT, fontSize: 10 }}>✓</span>
                </div>
                <span style={{ color: "rgba(196,181,253,0.65)", fontSize: 14, lineHeight: 1.6 }}>{t}</span>
              </div>
            ))}
          </FadeUp>
          <FadeUp delay={0.2}>
            <div style={{ background: "rgba(14,21,49,0.8)", border: "1px solid rgba(123,63,242,0.25)", borderRadius: 20, padding: 32, position: "relative" }}>
              <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle, rgba(123,63,242,0.1) 0%, transparent 70%)", pointerEvents: "none" }} />
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
                <span style={{ fontFamily: "'Space Mono'", fontSize: 11, color: "rgba(196,181,253,0.5)", letterSpacing: "0.08em" }}>// CHUNK DISTRIBUTION</span>
                <span style={{ fontSize: 10, color: "#4afa9a", background: "rgba(74,250,154,0.1)", border: "1px solid rgba(74,250,154,0.2)", padding: "2px 10px", borderRadius: 100 }}>LIVE</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 24 }}>
                {Array.from({ length: 9 }, (_, i) => (
                  <div key={i} style={{
                    height: 28, borderRadius: 6,
                    background: activeChunk === i ? LAVENDER : "rgba(123,63,242,0.15)",
                    border: `1px solid ${activeChunk === i ? LAVENDER_BRIGHT : "rgba(123,63,242,0.25)"}`,
                    transition: "all 0.3s ease",
                    boxShadow: activeChunk === i ? `0 0 12px ${LAVENDER_GLOW}` : "none",
                    animation: activeChunk === i ? "chunkPop 0.3s ease" : "none",
                  }} />
                ))}
              </div>
              <div style={{ fontSize: 10, color: "rgba(196,181,253,0.4)", fontFamily: "'Space Mono'", marginBottom: 20, textAlign: "center" }}>distributing 9 chunks across 3 nodes...</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 10, marginBottom: 20 }}>
                <PulsingNode label="Node — 1" status="online" delay="0s" />
                <PulsingNode label="Node — 2" status="offline" />
                <PulsingNode label="Node — 3" status="online" delay="0.5s" />
              </div>
              <div style={{ background: "rgba(74,250,154,0.07)", border: "1px solid rgba(74,250,154,0.2)", borderRadius: 10, padding: "12px 16px", textAlign: "center" }}>
                <span style={{ fontSize: 13, color: "#4afa9a", fontFamily: "'Space Mono'", letterSpacing: "0.05em" }}>✓ File retrieved from Node 3 — zero loss</span>
              </div>
            </div>
          </FadeUp>
        </div>
      </section>

      {/* SECURITY SHOWCASE */}
      <div style={{ background: "rgba(123,63,242,0.04)", borderTop: "1px solid rgba(123,63,242,0.12)", borderBottom: "1px solid rgba(123,63,242,0.12)", padding: "110px 0" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 48px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "center" }}>
          <FadeUp>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { icon: "🔑", label: "Node Keypair Generated", sub: "pub: 0x4af0...b830 · priv: sealed", status: "VERIFIED", ok: true },
                { icon: "📦", label: "Chunk Signed on Store", sub: "sig: 0x9f2e...a451 · node-1", status: "VERIFIED", ok: true },
                { icon: "🔍", label: "Retrieval Hash Check", sub: "SHA256 match confirmed", status: "VALID", ok: true },
                { icon: "⚠️", label: "Tampered Chunk Detected", sub: "hash mismatch → rejected at node level", status: "BLOCKED", ok: false },
              ].map((row, i) => (
                <FadeUp key={row.label} delay={i * 0.1}>
                  <div style={{ display: "flex", alignItems: "center", gap: 16, background: row.ok ? "rgba(14,21,49,0.8)" : "rgba(255,68,102,0.04)", border: `1px solid ${row.ok ? "rgba(123,63,242,0.2)" : "rgba(255,68,102,0.2)"}`, borderRadius: 12, padding: "16px 20px" }}>
                    <span style={{ fontSize: 20 }}>{row.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "#fff", marginBottom: 3 }}>{row.label}</div>
                      <div style={{ fontSize: 11, color: "rgba(196,181,253,0.45)", fontFamily: "'Space Mono'" }}>{row.sub}</div>
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: row.ok ? "#4afa9a" : "#ff4466", background: row.ok ? "rgba(74,250,154,0.1)" : "rgba(255,68,102,0.1)", border: `1px solid ${row.ok ? "rgba(74,250,154,0.2)" : "rgba(255,68,102,0.2)"}`, padding: "4px 10px", borderRadius: 100 }}>{row.status}</span>
                  </div>
                </FadeUp>
              ))}
            </div>
          </FadeUp>
          <FadeUp delay={0.2}>
            <div style={{ fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500, marginBottom: 16 }}>Security Model</div>
            <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(1.8rem, 3vw, 2.8rem)", letterSpacing: "-0.03em", lineHeight: 1.1, marginBottom: 20 }}>
              Cryptographic trust<br /><span style={{ color: LAVENDER_BRIGHT }}>without a third party</span>
            </h2>
            <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 15, lineHeight: 1.75, marginBottom: 36, fontWeight: 300 }}>
              No central certificate authority. No master key. No single secret that compromises everything when stolen. Each node's keypair makes it independently trustworthy.
            </p>
            {["Node-signed storage proofs — every stored chunk has a cryptographic receipt", "Data access policies enforced locally — no API gateway to bypass", "Breach isolation — one compromised node reveals zero about others"].map(t => (
              <div key={t} style={{ display: "flex", gap: 12, marginBottom: 14, alignItems: "flex-start" }}>
                <span style={{ color: LAVENDER_BRIGHT, fontSize: 14, marginTop: 2 }}>◆</span>
                <span style={{ color: "rgba(196,181,253,0.65)", fontSize: 14, lineHeight: 1.6 }}>{t}</span>
              </div>
            ))}
          </FadeUp>
        </div>
      </div>

      {/* ARTICLES */}
      <section style={{ maxWidth: 1200, margin: "0 auto", padding: "110px 48px" }}>
        <FadeUp>
          <div style={{ fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500, marginBottom: 16 }}>Learn More</div>
          <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(2rem, 4vw, 3rem)", letterSpacing: "-0.03em", marginBottom: 16, lineHeight: 1.1 }}>
            Understand the <span style={{ color: LAVENDER_BRIGHT }}>architecture</span>
          </h2>
          <p style={{ color: "rgba(196,181,253,0.6)", fontSize: 16, maxWidth: 480, lineHeight: 1.75, marginBottom: 60, fontWeight: 300 }}>Deep-dives into the concepts powering D-Cloud.</p>
        </FadeUp>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20 }}>
          {[
            { num: "01", tag: "Architecture", title: "Why Agent-Centric Design Beats Centralized Control Planes", meta: "6 min read", bg: "linear-gradient(135deg, #0f0d1f 0%, #1a1040 100%)" },
            { num: "02", tag: "Security", title: "Cryptographic Identity Without a Certificate Authority", meta: "8 min read", bg: "linear-gradient(135deg, #0d0f1f 0%, #0a1830 100%)" },
            { num: "03", tag: "Performance", title: "Eliminating Global Consensus: How D-Cloud Scales", meta: "5 min read", bg: "linear-gradient(135deg, #120d20 0%, #1a0d3a 100%)" },
          ].map((a, i) => (
            <FadeUp key={a.num} delay={i * 0.1}>
              <div className="card-hover" style={{ background: "rgba(123,63,242,0.05)", border: "1px solid rgba(123,63,242,0.18)", borderRadius: 16, overflow: "hidden" }}>
                <div style={{ height: 160, background: a.bg, display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
                  <span style={{ fontFamily: "'Syne'", fontSize: 72, fontWeight: 800, color: "rgba(123,63,242,0.2)", letterSpacing: "-0.06em" }}>{a.num}</span>
                  <div style={{ position: "absolute", bottom: 16, left: 20, width: 32, height: 32, borderRadius: "50%", background: LAVENDER, opacity: 0.3 }} />
                </div>
                <div style={{ padding: 24 }}>
                  <div style={{ fontSize: 10, color: LAVENDER_BRIGHT, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 10 }}>{a.tag}</div>
                  <div style={{ fontFamily: "'Syne'", fontWeight: 600, fontSize: 15, lineHeight: 1.45, marginBottom: 14, color: "#e8e4ff" }}>{a.title}</div>
                  <div style={{ fontSize: 12, color: "rgba(196,181,253,0.4)" }}>{a.meta} · Engineering</div>
                </div>
              </div>
            </FadeUp>
          ))}
        </div>
      </section>

      {/* CTA */}
      <div style={{ textAlign: "center", padding: "120px 48px", position: "relative", overflow: "hidden", background: "rgba(123,63,242,0.04)", borderTop: "1px solid rgba(123,63,242,0.12)" }}>
        <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: 600, height: 400, borderRadius: "50%", background: "radial-gradient(ellipse, rgba(123,63,242,0.15) 0%, transparent 70%)", pointerEvents: "none" }} />
        <FadeUp>
          <div style={{ fontSize: 12, color: LAVENDER_BRIGHT, letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500, marginBottom: 20, position: "relative" }}>Get Started</div>
          <h2 style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: "clamp(2.2rem, 5vw, 4rem)", letterSpacing: "-0.03em", lineHeight: 1.05, marginBottom: 24, maxWidth: 700, margin: "0 auto 24px", position: "relative" }}>
            <span className="glow-text">Decentralize your cloud.</span>
            <br /><span style={{ color: LAVENDER_BRIGHT }}>Own your data.</span>
          </h2>
          <p style={{ color: "rgba(196,181,253,0.6)", maxWidth: 480, margin: "0 auto 48px", lineHeight: 1.75, fontWeight: 300, position: "relative" }}>
            Join teams building on infrastructure that doesn't have a single point of failure — or a single point of trust.
          </p>
          <div style={{ display: "flex", gap: 16, justifyContent: "center", position: "relative" }}>
            <button className="btn-main" style={{ fontSize: 16, padding: "16px 40px" }} onClick={onLaunchApp}>Launch Dashboard</button>
            <button className="btn-outline" style={{ fontSize: 16, padding: "16px 36px" }}>Read the Docs →</button>
          </div>
        </FadeUp>
      </div>

      {/* FOOTER */}
      <footer style={{ borderTop: "1px solid rgba(123,63,242,0.15)", padding: "52px 52px 32px", background: LIBERTY }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 40, marginBottom: 52 }}>
            <div>
              <div style={{ fontFamily: "'Syne'", fontWeight: 800, fontSize: 20, marginBottom: 12, letterSpacing: "-0.02em" }}>D<span style={{ color: LAVENDER_BRIGHT }}>-</span>Cloud</div>
              <div style={{ fontSize: 13, color: "rgba(196,181,253,0.45)", maxWidth: 200, lineHeight: 1.6 }}>Decentralized cloud infrastructure without the blockchain overhead.</div>
            </div>
            {[["Product", ["Architecture", "Node Dashboard", "File Storage", "Security Model"]], ["Resources", ["Documentation", "Whitepaper", "GitHub", "Blog"]], ["Company", ["About", "Contact", "Privacy"]]].map(([col, links]) => (
              <div key={col as string}>
                <div style={{ fontFamily: "'Syne'", fontWeight: 600, fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "#c4b5fd", marginBottom: 18 }}>{col}</div>
                {(links as string[]).map(l => <a key={l} href="#" style={{ display: "block", fontSize: 13, color: "rgba(196,181,253,0.5)", textDecoration: "none", marginBottom: 12, transition: "color 0.2s" }} onMouseEnter={e => e.currentTarget.style.color = "#fff"} onMouseLeave={e => e.currentTarget.style.color = "rgba(196,181,253,0.5)"}>{l}</a>)}
              </div>
            ))}
          </div>
          <div style={{ borderTop: "1px solid rgba(123,63,242,0.12)", paddingTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <span style={{ fontSize: 12, color: "rgba(196,181,253,0.3)" }}>© 2026 D-Cloud. Decentralized by design.</span>
            <span style={{ fontFamily: "'Space Mono'", fontSize: 10, color: "rgba(196,181,253,0.2)", letterSpacing: "0.1em" }}>TRUST DISTRIBUTED. DATA OWNED.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
