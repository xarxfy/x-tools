import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { PageHead, SearchField } from "../components/ui";
import "./HelpPage.css";

interface Doc {
  id: string;
  title: string;
  body: ReactNode;
  text: string; // plain text for the search
  children?: Doc[];
}

function doc(id: string, title: string, body: ReactNode, text: string, children?: Doc[]): Doc {
  return { id, title, body, text, children };
}

const DOCS: Doc[] = [
  doc("start", "Getting started", <>
    <p>X-TOOLS keeps track of your servers, the services running on them, the sites you host for others and
      everything that needs attention.</p>
    <ol>
      <li>Add your <Link to="/services">services</Link> – name, ports, domains and folder are enough.</li>
      <li>Add <Link to="/customers">customers</Link> and assign their services; their websites are checked from outside.</li>
      <li>Set up <Link to="/settings">notifications</Link> so you hear about problems.</li>
      <li>Connect more servers with an <Link to="/settings?tab=agents">agent</Link>.</li>
    </ol>
  </>, "start first steps services customers notifications agent", [
    doc("start-overview", "Overview", <>
      <p>The overview lists everything that needs attention right now: ports that do not answer, stopped or
        unhealthy containers, outdated Docker data, full disks, silent agents and unreachable customer websites.
        Each entry links to the place where you can look into it.</p>
      <p>Containers you stopped yourself through X-TOOLS are shown separately and are not reported.</p>
    </>, "overview attention issues problems"),
  ]),
  doc("services", "Services", <>
    <p>A service is anything that runs somewhere: a compose project, a systemd unit, an LXC. Ports are checked
      every minute on the host X-TOOLS runs on (green = answers).</p>
  </>, "services ports domains folder type", [
    doc("services-credentials", "Credentials", <>
      <p>Each service can hold logins (label, address, username, password, note). They are encrypted with the
        secret key of this installation and only decrypted when you open them. Passwords stay hidden until you
        click the eye.</p>
      <p>Without the secret key the credentials cannot be read – include it in your backups.</p>
    </>, "credentials passwords logins encrypted secret key"),
    doc("services-domains", "Domains", <>
      <p>The domains page lists all domains of all services, grouped by root domain, with the customer they
        belong to.</p>
    </>, "domains"),
  ]),
  doc("customers", "Customers", <>
    <p>Customers bundle contact details, agreements and the services/sites you host for them. A service belongs
      to at most one customer.</p>
  </>, "customers contact agreements", [
    doc("customers-checks", "Website checks", <>
      <p>All domains of customer services are checked from outside every five minutes, the way visitors see them:
        DNS, HTTPS answer (redirects are not followed), response time and certificate. A certificate that expires
        within 14 days is a warning. “Check now” on the customer page runs the check immediately.</p>
      <p>Cloudflare error codes (502, 521–530) are explained in plain words, e.g. 530 = the tunnel is not reachable.</p>
    </>, "website checks dns https certificate cloudflare 502 530"),
  ]),
  doc("servers", "Servers & Docker", <>
    <p><em>This server</em> is the machine X-TOOLS runs on. Its Docker containers and host metrics come from the
      collector container <code>x-tools-collector</code>.</p>
  </>, "servers docker collector", [
    doc("servers-collector", "How the collector works", <>
      <p>The web container has no access to Docker. The collector runs in its own container without network, with
        the Docker socket and the compose folders mounted read-only. It writes a snapshot every minute and executes
        commands the web container drops into a shared “exchange” volume. It never sees the database or the secret key.</p>
      <p>Only start, stop, restart and logs are possible, only for known containers, and never for the protected
        ones (<code>XT_PROTECTED_CONTAINERS</code>, by default X-TOOLS itself).</p>
    </>, "collector exchange socket protected containers start stop restart"),
    doc("servers-files", "Compose files, Dockerfiles, git", <>
      <p>For each compose project you can open the compose files and Dockerfiles (up to three levels deep).
        Values of keys like PASSWORD, TOKEN or *_KEY and credentials in URLs are masked. <code>.env</code> files are
        never read. Only files below <code>XT_COMPOSE_ROOTS</code> are read.</p>
      <p>If the project folder is a git repository, branch, last commit and uncommitted changes are shown.</p>
      <p>“Add as service” creates a service from a compose project with its folder and ports.</p>
    </>, "compose dockerfile git masked env files add as service"),
    doc("servers-logs", "Logs", <>
      <p>The last 100–1000 lines of a container (stdout and stderr), in your time zone, with secrets masked.</p>
    </>, "logs"),
  ]),
  doc("agents", "Agents (more servers)", <>
    <p>An agent is X-TOOLS in agent mode on another machine, e.g. a server at home. It reports Docker, host
      metrics and optionally Proxmox every minute – outbound HTTPS only. It has no open ports and never receives
      commands, so containers on agent servers are shown read-only.</p>
  </>, "agents servers home outbound", [
    doc("agents-setup", "Set up an agent", <>
      <ol>
        <li>Settings → Agents → create an agent. The key is shown once; only its hash is stored.</li>
        <li>On the other server: clone the repository, go to <code>deploy/agent</code>, create <code>.env</code> from
          <code>.env.example</code> with the address and the key.</li>
        <li><code>docker compose up -d --build</code> – the server shows up within a minute.</li>
      </ol>
      <p>Agents of the predecessor Server-Info keep working after the import – just point their URL to X-TOOLS.</p>
    </>, "setup agent key env compose"),
    doc("agents-access", "Behind Cloudflare Access", <>
      <p>If X-TOOLS is protected by Cloudflare Access, the agent cannot log in interactively. Create a service token
        (Zero Trust → Access → Service Auth), add a policy with action “Service Auth” for the path
        <code>/api/agent/report</code> and put client ID and secret into the agent’s <code>.env</code>
        (<code>CF_ACCESS_CLIENT_ID</code>, <code>CF_ACCESS_CLIENT_SECRET</code>). A 403 or a login page in the agent
        log means the token or the path rule does not match.</p>
    </>, "cloudflare access service token 403"),
    doc("agents-proxmox", "Proxmox", <>
      <p>Create an API token with the role <code>PVEAuditor</code> (read-only), e.g. <code>xtools@pve!agent</code>,
        and set <code>PROXMOX_URL</code>, <code>PROXMOX_TOKEN_ID</code> and <code>PROXMOX_TOKEN_SECRET</code> in the
        agent’s <code>.env</code>. The server page then shows nodes, storage and all LXCs and VMs.</p>
    </>, "proxmox token pveauditor lxc vm"),
  ]),
  doc("notifications", "Notifications", <>
    <p>Every minute X-TOOLS compares the list of issues with the previous run. New problems are sent once they
      last longer than the delay; with “Back to normal” you also hear when they are solved. You can switch
      single kinds of events off.</p>
  </>, "notifications alerts delay recovery events", [
    doc("notifications-telegram", "Telegram", <>
      <ol>
        <li>Talk to <code>@BotFather</code>, <code>/newbot</code> – you get the bot token.</li>
        <li>Send your bot a message, then open <code>https://api.telegram.org/bot&lt;token&gt;/getUpdates</code> –
          <code>chat.id</code> is your chat ID.</li>
        <li>Enter both in Settings, save and send a test.</li>
      </ol>
    </>, "telegram bot token chat id botfather"),
    doc("notifications-ntfy", "ntfy", <>
      <p>Pick a hard-to-guess topic, subscribe to it in the ntfy app and enter server and topic. For a protected
        server, add an access token.</p>
    </>, "ntfy topic push"),
  ]),
  doc("security", "Security & backup", <>
    <ul>
      <li>Passwords are hashed with Argon2; sessions are stored hashed; all changes need a CSRF token; repeated
        wrong logins are slowed down.</li>
      <li>Credentials and notification tokens are encrypted with the secret key (<code>secret.key</code> in the data
        volume or <code>XT_SECRET_KEY</code>).</li>
      <li><strong>Back up the data volume</strong> including the secret key.</li>
      <li>Run X-TOOLS behind HTTPS (reverse proxy or tunnel) and ideally behind an additional login such as
        Cloudflare Access.</li>
    </ul>
  </>, "security backup secret key argon2 csrf https"),
];

function flatten(docs: Doc[], parents: string[] = []): { doc: Doc; path: string[] }[] {
  return docs.flatMap((d) => [{ doc: d, path: parents }, ...flatten(d.children ?? [], [...parents, d.title])]);
}

function Node({ d, open, toggle }: { d: Doc; open: Set<string>; toggle: (id: string) => void }) {
  const isOpen = open.has(d.id);
  return (
    <li className="doc-node" id={d.id}>
      <button type="button" className="doc-title" aria-expanded={isOpen} onClick={() => toggle(d.id)}>
        <span className={`doc-caret${isOpen ? " open" : ""}`} aria-hidden="true" />
        {d.title}
      </button>
      {isOpen && <div className="doc-body">{d.body}</div>}
      {d.children && (
        <ul className="doc-children">
          {d.children.map((c) => <Node key={c.id} d={c} open={open} toggle={toggle} />)}
        </ul>
      )}
    </li>
  );
}

export function HelpPage() {
  const [open, setOpen] = useState<Set<string>>(new Set(["start"]));
  const [query, setQuery] = useState("");
  const { hash } = useLocation();
  useEffect(() => {
    const id = hash.slice(1);
    if (id) setOpen((s) => new Set([...s, id]));
  }, [hash]);
  const toggle = (id: string) => setOpen((s) => {
    const n = new Set(s);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });
  const q = query.trim().toLowerCase();
  const hits = q ? flatten(DOCS).filter(({ doc: d }) => (d.title + " " + d.text).toLowerCase().includes(q)) : [];

  return (
    <>
      <PageHead title="Help" sub="How X-TOOLS works – click a topic to expand it.">
        <SearchField value={query} onChange={setQuery} />
      </PageHead>
      {q ? (
        hits.length ? (
          <div className="stack">
            {hits.map(({ doc: d, path }) => (
              <section key={d.id} className="card card-pad doc-hit">
                {path.length > 0 && <div className="muted doc-path">{path.join(" › ")}</div>}
                <h2>{d.title}</h2>
                {d.body}
              </section>
            ))}
          </div>
        ) : (
          <div className="card card-pad empty">Nothing found.</div>
        )
      ) : (
        <div className="card card-pad">
          <ul className="doc-tree">
            {DOCS.map((d) => <Node key={d.id} d={d} open={open} toggle={toggle} />)}
          </ul>
          <div className="doc-actions">
            <button type="button" className="btn btn-ghost btn-small"
                    onClick={() => setOpen(new Set(flatten(DOCS).map((x) => x.doc.id)))}>Expand all</button>
            <button type="button" className="btn btn-ghost btn-small" onClick={() => setOpen(new Set())}>Collapse all</button>
          </div>
        </div>
      )}
    </>
  );
}
