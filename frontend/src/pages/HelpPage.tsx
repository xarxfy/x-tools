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
      <li>Optional: switch on <Link to="/settings">customers</Link> if you host sites for others; their websites are
        checked from outside.</li>
      <li>Set up <Link to="/admin?tab=notifications">notifications</Link> so you hear about problems.</li>
      <li>Connect more servers with an <Link to="/servers">agent</Link>.</li>
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
    doc("services-assistant", "Assistant for new services", <>
      <p><Link to="/services/new">Services → Assistant</Link> walks you through a new service: pick a template (web app,
        Node.js, static site, WordPress, PostgreSQL or only a proxy config), name, host, folder and a free port (ports
        already used on that host are detected), then how it is published – Cloudflare Tunnel, Caddy, nginx, Traefik or
        only in the LAN.</p>
      <p>It generates <code>docker-compose.yml</code>, a <code>.env</code> with random passwords (optionally saved as
        credentials), the reverse proxy or tunnel configuration and the commands – to copy or download. The service
        is created with a checklist of the remaining steps, which you tick off in the service dialog. For existing
        services, <em>Configs</em> in the service dialog generates the proxy configuration.</p>
    </>, "assistant wizard template compose caddy nginx traefik tunnel checklist config"),
    doc("services-host", "Host", <>
      <p>By default ports are checked on the machine X-TOOLS runs on. For a service on another machine (e.g. an LXC
        at home) enter its IP address or host name under <em>Host</em> – the ports are then checked there.</p>
    </>, "host ip port check lxc homelab"),
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
  doc("how", "How X-TOOLS works", <>
    <p>A <strong>web part</strong> (this page) shows and watches everything; a <strong>collector</strong> reads Docker
      on this server; <strong>agents</strong> on other servers report in (outbound only, no open ports); an optional
      <strong> deployer</strong> rolls out customer websites. Full guide, including what to do behind Cloudflare
      Access or a Tunnel: <code>docs/guide.md</code> in the repository.</p>
    <p>Note: X-TOOLS is entirely “vibe coded” (written with an AI assistant) and has had no independent security
      audit – keep backups and be careful what you give it control over.</p>
  </>, "how works parts guide cloudflare access tunnel vibe coded ai audit"),
  doc("search", "Search, notes and group actions", <>
    <p><strong>Search:</strong> press <kbd>Ctrl</kbd>+<kbd>K</kbd> (<kbd>⌘K</kbd> on a Mac) or <kbd>/</kbd> anywhere, or use
      the search button in the sidebar. It finds servers, containers, Proxmox guests, services (also by port, domain
      or a word in their notes), domains, customers, websites, jobs and tags. Arrow keys and Enter open a result.</p>
    <p><strong>Notes:</strong> every server has a free-text note on its page (what is it for, who is responsible,
      links become clickable); services and customers have notes, too. Notes are searchable.</p>
    <p><strong>Group actions</strong> (<Link to="/servers">Servers</Link>, for people who may manage servers): the
      button <em>Group actions</em> runs one action on several servers – choose them by group, tag or one by one,
      review, run, and see the result per server: install updates, add or remove an SSH key, add a firewall rule,
      restart a service. The tab <em>SSH keys</em> shows which key has access to which server and user and removes
      an old key everywhere with one click.</p>
  </>, "search find ctrl k notes group actions bulk ssh keys everywhere"),
  doc("jobs", "Jobs and maintenance", <>
    <p>The <Link to="/monitoring">Monitoring → Jobs</Link> page monitors things that should happen regularly (backups, cron jobs).
      Each job has a secret address; the job calls it when it has run
      (<code>curl -fsS https://…/api/heartbeat/&lt;token&gt;</code>, add <code>/fail</code> to report a failure).
      If the call stays away longer than the expected interval plus tolerance, you get an alert.</p>
    <p>Before maintenance, <em>Pause alerts</em> on the overview silences a part of the system (or everything) for a
      while. Problems stay visible but nothing is sent, and no “back to normal” follows.</p>
  </>, "jobs heartbeat cron backup monitor maintenance pause silence alerts"),
  doc("customers", "Customers", <>
    <p>Customers bundle contact details, agreements and the services/sites you host for them. A service belongs
      to at most one customer.</p>
    <p>The area is optional: switch it on or off under <Link to="/settings">Settings → General</Link>. When it is
      off, the menu entry and the website checks disappear; stored customers are kept.</p>
  </>, "customers contact agreements", [
    doc("customers-deploy", "Deploying websites", <>
      <p>On a customer page, <em>Websites → Add website</em> rolls out a website from a git repository: X-TOOLS
        clones it, writes the variables you entered to <code>.env</code> and starts it with docker compose (or serves
        a static folder with nginx when you enter a port). <em>Redeploy</em> pulls the latest commit.</p>
      <p>This needs the optional deployer container: <code>COMPOSE_PROFILES=deploy</code> in
        <code>deploy/.env</code>, then <code>sudo sh setup.sh</code>. Tokens and variables are stored encrypted.</p>
    </>, "deploy website git repository compose static nginx deployer"),
    doc("customers-checks", "Website checks", <>
      <p>All domains of customer services are checked from outside every five minutes, the way visitors see them:
        DNS, HTTPS answer (redirects are not followed), response time and certificate. A certificate that expires
        within 14 days is a warning. “Check now” on the customer page runs the check immediately.</p>
      <p>Cloudflare error codes (502, 521–530) are explained in plain words, e.g. 530 = the tunnel is not reachable.</p>
    </>, "website checks dns https certificate cloudflare 502 530"),
  ]),
  doc("servers", "Docker & Proxmox", <>
    <p>The <Link to="/docker">Docker</Link> page shows <em>This server</em> (the machine X-TOOLS runs on – its data
      comes from the collector container <code>x-tools-collector</code>) and every Docker host with an agent; the
      <Link to="/proxmox">Proxmox</Link> page every Proxmox host. Each host shows load, memory and disk and a chart of
      the last 30 days. Without a host, the pages explain how to set up an agent.</p>
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
        <li>Open the page of the kind – <Link to="/servers">Servers</Link> (any Linux server, VM or LXC: services, ports,
          disks, updates), <Link to="/proxmox">Proxmox</Link> (enter the API token) or <Link to="/docker">Docker</Link>
          (a server, LXC or VM with Docker) – and press <em>Add … server/host</em>.
          Docker containers are only visible to an agent on the same machine, so install one on the Proxmox host and
          one on every LXC/VM with Docker.</li>
        <li>Copy the install command and run it as root on the other server. It installs a small service
          (<code>x-tools-agent</code>, Python standard library only, no Docker needed).</li>
        <li>The server shows up within a minute.</li>
      </ol>
      <p>The command works once and for one hour. Lost it, or want to add Proxmox later? <em>Install command</em> on
        the agent creates a new one (and a new key). Prefer Docker? Use <code>deploy/agent</code> from the repository.</p>
      <p>Agents of the predecessor Server-Info keep working after the import – just point their URL to X-TOOLS.</p>
    </>, "setup agent key env compose"),
    doc("agents-remove", "Remove an agent", <>
      <p>Delete the agent on its own page (the trash icon next to its name) – X-TOOLS then rejects its
        reports – and run this as root on that server (works for the systemd service and the Docker variant):</p>
      <pre className="code command">{"systemctl disable --now x-tools-agent 2>/dev/null; rm -rf /opt/x-tools-agent " +
        "/etc/x-tools-agent /etc/systemd/system/x-tools-agent.service; systemctl daemon-reload 2>/dev/null; " +
        "docker rm -f x-tools-agent 2>/dev/null; echo 'X-TOOLS agent removed'"}</pre>
    </>, "remove uninstall delete agent"),
    doc("agents-control", "Control (start/stop)", <>
      <p>With <em>Allow control from X-TOOLS</em> (when adding the server or with a new install command), operators and
        admins can start, stop and restart containers and read logs on Docker hosts, start, stop and restart systemd
        services, read their journal and reboot Linux servers, and start, shut down, stop and
        reboot LXCs/VMs on Proxmox hosts, change their CPU cores, memory, swap, start at boot and tags, and
        grow disks (detail page of a guest). The agent still opens no port – it asks X-TOOLS for commands and only runs
        this fixed list. Control must be switched on on the agent itself (<code>XT_AGENT_CONTROL=1</code>). Proxmox needs
        a token with the matching privileges – see docs/agents.md for a ready <code>pveum</code> command. Every action is
        in the audit log.</p>
    </>, "control start stop restart reboot shutdown operator agent proxmox docker"),
    doc("agents-proxmox-details", "Proxmox details", <>
      <p>Click an LXC/VM on the <em>Proxmox</em> page: resources and disks, network cards with bridge, VLAN, MAC and the
        current IP addresses (VMs need the QEMU guest agent), snapshots, backups (with a warning when the last one is
        older than 3 days), OS, start at boot, features, tags and the .conf file of the guest. Node cards show the Proxmox version, kernel
        and available updates; the host network (bridges, bonds, VLANs) is listed below. Details are refreshed every
        10 minutes and right after a change.</p>
    </>, "proxmox details config lxc vm ip snapshot backup network bridge version updates"),
    doc("agents-access", "Behind Cloudflare Access", <>
      <p>If X-TOOLS is protected by Cloudflare Access, the agent cannot log in interactively. Create a service token
        (Zero Trust → Access → Service Auth), add a policy with action “Service Auth” for the path
        <code>/api/agent/</code> and enter client ID and secret when you create the agent (they go into the install
        command and the agent’s configuration). A 403 or a login page in the agent
        log means the token or the path rule does not match.</p>
    </>, "cloudflare access service token 403"),
    doc("agents-proxmox", "Proxmox", <>
      <p>In the Proxmox web UI: Datacenter → Permissions → API Tokens → <em>Add</em> (e.g. user <code>root@pam</code>,
        token ID <code>xtools</code>, <em>Privilege Separation</em> on). Then Permissions → <em>Add → API Token
        Permission</em>: path <code>/</code>, the token, role <code>PVEAuditor</code> (read-only). Enter token ID
        (<code>root@pam!xtools</code>) and secret when creating the agent. They are stored encrypted, so a new
        install command for the same agent is filled in – the secret is never shown again; leave the field empty to
        keep it.</p>
    </>, "proxmox token pveauditor lxc vm"),
  ]),
  doc("cloudflare", "Cloudflare", <>
    <p>Read-only: under <Link to="/admin?tab=cloudflare">Administration → Cloudflare</Link> you store an API token with read
      permissions (Zone, DNS, Cloudflare Tunnel, Access: Apps and Policies). The <em>Cloudflare</em> page then shows
      per hostname the chain DNS record → tunnel → route → Access app and the service using it, and marks problems:
      no DNS record, a tunnel without route for the hostname, a route to a different port than the service uses,
      DNS not pointing to the tunnel. Unhealthy tunnels appear on the overview. Data is refreshed every 10 minutes.</p>
    <p>Read-only by default. With <em>Allow changes</em> (admins, token with DNS Edit and Cloudflare Tunnel Edit)
      operators can add, edit and delete DNS records and tunnel routes – or fix a hostname with <em>Create route</em>.
      Every change is in the audit log.</p>
  </>, "cloudflare dns tunnel route access token"),
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
  doc("users", "Users, roles & permissions", <>
    <p>Under <Link to="/admin?tab=users">Administration</Link> (visible only to people with administration permissions)
      admins add users and give each a <strong>role</strong>. A role is a set of permissions that you choose yourself
      under <Link to="/admin?tab=roles">Roles &amp; permissions</Link>, for example &ldquo;Support&rdquo; may restart
      containers but not see credentials. Three roles are built in:</p>
    <ul>
      <li><strong>Viewer</strong> – sees everything, changes nothing (preset without permissions).</li>
      <li><strong>Operator</strong> – maintains services, customers, credentials, containers and servers (preset).</li>
      <li><strong>Administrator</strong> – everything, including users, roles, agents, settings, backups and the audit
        log. Cannot be changed.</li>
    </ul>
    <p>Nobody can give a role (or a user) more permissions than they have themselves. Disabling a user or resetting
      the password logs them out everywhere. There is always at least one active user who can manage users. Users change
      their own password and two-factor login under Settings → Account.</p>
  </>, "users roles permissions rights viewer operator admin administration", [
    doc("users-audit", "Audit log", <>
      <p><Link to="/admin?tab=audit">Administration → Audit log</Link> shows who did what and when, with IP address:
        logins (also failed ones), viewed and changed credentials, container actions, changes to services,
        customers, users, agents and settings, backups. Entries are kept for one year. Passwords never appear in it.</p>
    </>, "audit log who what when"),
  ]),
  doc("history", "History", <>
    <p>Every problem from the overview is recorded with start and end. The overview shows recent events, services show
      their uptime of the last 7 days, and server pages show load, memory and disk for up to 30 days (one sample every
      5 minutes). Metrics are kept for 30 days, solved events for 90 days.</p>
  </>, "history events uptime metrics chart"),
  doc("security", "Security & backup", <>
    <ul>
      <li>Passwords are hashed with Argon2; sessions are stored hashed; all changes need a CSRF token; repeated
        wrong logins are slowed down.</li>
      <li>Credentials and notification tokens are encrypted with the secret key (<code>secret.key</code> in the data
        volume or <code>XT_SECRET_KEY</code>).</li>
      <li><strong>Back up regularly:</strong> <Link to="/admin?tab=backup">Administration → Backup</Link> downloads an
        encrypted file with database and secret key; the same page restores it.</li>
      <li>Turn on two-factor login under <Link to="/settings?tab=account">Settings → Account</Link>. Keep the recovery
        codes – each one replaces a code once if you lose your phone.</li>
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
