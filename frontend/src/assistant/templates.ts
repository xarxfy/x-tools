/** Service templates and config generators for the assistant. Everything runs in the browser. */

export type Expose = "tunnel" | "caddy" | "nginx" | "traefik" | "lan";

export interface Ctx {
  name: string;
  slug: string;
  host: string; // where it runs (empty = this server)
  folder: string;
  port: number; // port on the host
  domain: string;
  expose: Expose;
  image: string;
  timezone: string;
  secrets: Record<string, string>;
}

export interface GeneratedFile {
  name: string; // file name, e.g. docker-compose.yml
  lang: string;
  content: string;
  note?: string;
}

export interface Template {
  id: string;
  type: string; // service type stored in X-TOOLS
  internalPort: number;
  image: string;
  http: boolean; // can be published under a domain
  secrets: string[]; // generated into .env
  compose?: (c: Ctx) => string; // undefined = no compose (custom)
  extraFiles?: (c: Ctx) => GeneratedFile[];
}

export function randomSecret(length = 32): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}

export function slugify(name: string): string {
  return name.toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-").slice(0, 40) || "app";
}

function bind(c: Ctx): string {
  return c.expose === "lan" ? "" : "127.0.0.1:";
}

function portsBlock(c: Ctx, internal: number): string {
  if (c.expose === "traefik") return "";
  return `    ports:\n      - "${bind(c)}${c.port}:${internal}"\n`;
}

function traefik(c: Ctx, internal: number): string {
  if (c.expose !== "traefik") return "";
  const r = c.slug;
  return `    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.${r}.rule=Host(\`${c.domain || "app.example.com"}\`)"
      - "traefik.http.routers.${r}.entrypoints=websecure"
      - "traefik.http.routers.${r}.tls.certresolver=letsencrypt"
      - "traefik.http.services.${r}.loadbalancer.server.port=${internal}"
    networks:
      - proxy
`;
}

function networks(c: Ctx): string {
  return c.expose === "traefik" ? `\nnetworks:\n  proxy:\n    external: true\n` : "";
}

const header = (c: Ctx) => `# ${c.name} – created with the X-TOOLS assistant\n`;

export const TEMPLATES: Template[] = [
  {
    id: "webapp", type: "Docker Compose", internalPort: 3000, image: "ghcr.io/owner/app:latest", http: true, secrets: [],
    compose: (c) => `${header(c)}services:
  app:
    image: ${c.image}
    container_name: ${c.slug}
    restart: unless-stopped
    env_file: .env
    environment:
      TZ: ${c.timezone}
${portsBlock(c, 3000)}${traefik(c, 3000)}${networks(c)}`,
  },
  {
    id: "node", type: "Docker Compose", internalPort: 3000, image: "node:22-alpine", http: true, secrets: [],
    compose: (c) => `${header(c)}services:
  app:
    build: .
    container_name: ${c.slug}
    restart: unless-stopped
    env_file: .env
    environment:
      NODE_ENV: production
      PORT: "3000"
      TZ: ${c.timezone}
${portsBlock(c, 3000)}${traefik(c, 3000)}${networks(c)}`,
    extraFiles: () => [{
      name: "Dockerfile", lang: "dockerfile", note: "Builds your app from the folder (package.json, npm start).",
      content: `FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
USER node
EXPOSE 3000
CMD ["npm", "start"]
`,
    }],
  },
  {
    id: "static", type: "Docker Compose", internalPort: 80, image: "nginx:alpine", http: true, secrets: [],
    compose: (c) => `${header(c)}services:
  web:
    image: ${c.image}
    container_name: ${c.slug}
    restart: unless-stopped
    volumes:
      - ./site:/usr/share/nginx/html:ro
${portsBlock(c, 80)}${traefik(c, 80)}${networks(c)}`,
  },
  {
    id: "wordpress", type: "Docker Compose", internalPort: 80, image: "wordpress:6", http: true,
    secrets: ["DB_PASSWORD", "DB_ROOT_PASSWORD"],
    compose: (c) => `${header(c)}services:
  wordpress:
    image: ${c.image}
    container_name: ${c.slug}
    restart: unless-stopped
    depends_on:
      - db
    environment:
      WORDPRESS_DB_HOST: db
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: \${DB_PASSWORD}
      WORDPRESS_DB_NAME: wordpress
    volumes:
      - wp-data:/var/www/html
${portsBlock(c, 80)}${traefik(c, 80)}
  db:
    image: mariadb:11
    container_name: ${c.slug}-db
    restart: unless-stopped
    environment:
      MARIADB_DATABASE: wordpress
      MARIADB_USER: wordpress
      MARIADB_PASSWORD: \${DB_PASSWORD}
      MARIADB_ROOT_PASSWORD: \${DB_ROOT_PASSWORD}
    volumes:
      - db-data:/var/lib/mysql
${c.expose === "traefik" ? "    networks:\n      - default\n" : ""}
volumes:
  wp-data:
  db-data:
${c.expose === "traefik" ? "\nnetworks:\n  proxy:\n    external: true\n  default:\n" : ""}`,
  },
  {
    id: "postgres", type: "Docker Compose", internalPort: 5432, image: "postgres:17-alpine", http: false,
    secrets: ["POSTGRES_PASSWORD"],
    compose: (c) => `${header(c)}services:
  db:
    image: ${c.image}
    container_name: ${c.slug}
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${c.slug.replace(/-/g, "_")}
      POSTGRES_PASSWORD: \${POSTGRES_PASSWORD}
      POSTGRES_DB: ${c.slug.replace(/-/g, "_")}
      TZ: ${c.timezone}
    volumes:
      - db-data:/var/lib/postgresql/data
    ports:
      - "${c.expose === "lan" ? "" : "127.0.0.1:"}${c.port}:5432"

volumes:
  db-data:
`,
  },
  { id: "custom", type: "", internalPort: 8080, image: "", http: true, secrets: [] },
];

export function envFile(t: Template, c: Ctx): string {
  const lines = ["# Secrets for " + c.name + " – keep this file private, never commit it"];
  for (const key of t.secrets) lines.push(`${key}=${c.secrets[key] ?? ""}`);
  if (!t.secrets.length) lines.push("# Add environment variables of your app here, e.g. API_KEY=…");
  return lines.join("\n") + "\n";
}

/** Reverse proxy / tunnel configuration for publishing the service under its domain. */
export function proxyFiles(c: Ctx): GeneratedFile[] {
  const domain = c.domain || "app.example.com";
  const target = `${c.host && c.host !== "localhost" ? c.host : "127.0.0.1"}:${c.port}`;
  switch (c.expose) {
    case "tunnel":
      return [{
        name: "cloudflared (config.yml)", lang: "yaml",
        note: `With a dashboard-managed tunnel instead: Zero Trust → Networks → Tunnels → your tunnel → Public hostname → ${domain} → HTTP → localhost:${c.port}.`,
        content: `# Add to the ingress list of your tunnel, above the final "- service: http_status:404"
ingress:
  - hostname: ${domain}
    service: http://localhost:${c.port}
`,
      }];
    case "caddy":
      return [{
        name: "Caddyfile", lang: "caddy", note: "Then: sudo systemctl reload caddy – Caddy gets the certificate by itself.",
        content: `${domain} {
    encode zstd gzip
    reverse_proxy ${target}
}
`,
      }];
    case "nginx":
      return [{
        name: `nginx (/etc/nginx/sites-available/${c.slug})`, lang: "nginx",
        note: `Then: sudo ln -s /etc/nginx/sites-available/${c.slug} /etc/nginx/sites-enabled/ && sudo certbot --nginx -d ${domain}`,
        content: `server {
    listen 80;
    server_name ${domain};

    location / {
        proxy_pass http://${target};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
`,
      }];
    default:
      return [];
  }
}

export function setupCommands(t: Template, c: Ctx): string {
  if (!t.compose) return "";
  const files = ["docker-compose.yml", ".env", ...(t.extraFiles?.(c).map((f) => f.name) ?? [])];
  return `mkdir -p ${c.folder} && cd ${c.folder}
# put ${files.join(", ")} here (copy from above)
chmod 600 .env
docker compose up -d
docker compose ps
`;
}

export function checklist(t: Template, c: Ctx): string[] {
  const steps: string[] = [];
  if (t.compose) {
    steps.push(`Create ${c.folder} with the generated files`);
    steps.push("Start it: docker compose up -d");
  } else {
    steps.push(`Make the service listen on port ${c.port}`);
  }
  const domain = c.domain || "the domain";
  if (t.http && c.expose === "tunnel") {
    steps.push(`Add the public hostname ${domain} → http://localhost:${c.port} to the Cloudflare Tunnel`);
    steps.push(`Optional: protect ${domain} with a Cloudflare Access application`);
  }
  if (t.http && (c.expose === "caddy" || c.expose === "nginx" || c.expose === "traefik")) {
    steps.push(`DNS: point ${domain} to the server (A/AAAA record)`);
    if (c.expose === "caddy") steps.push("Add the block to the Caddyfile and reload Caddy");
    if (c.expose === "nginx") steps.push("Enable the nginx site and get a certificate with certbot");
    if (c.expose === "traefik") steps.push("Make sure the external Docker network \"proxy\" of Traefik exists");
  }
  if (t.http && c.expose !== "lan" && c.domain) steps.push(`Open https://${c.domain} and check it works`);
  if (c.expose === "lan") steps.push(`Open http://${c.host || "<server-ip>"}:${c.port} in your network`);
  if (t.secrets.length) steps.push("Keep the .env file private (the passwords are also saved as credentials)");
  return steps;
}
