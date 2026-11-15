import i18n from "../i18n";

/**
 * Problem texts are written by the server in English. In another language the common ones are translated here
 * (pattern → translation key); anything unknown is shown as it is.
 */
const AGO = /(\d+) (min|h|days?) ago|just now/g;

function agoText(text: string): string {
  return text.replace(AGO, (m, n, unit) => {
    if (m === "just now") return i18n.t("format.justNow");
    const key = unit === "min" ? "format.minAgo" : unit === "h" ? "format.hAgo" : "format.daysAgo";
    return i18n.t(key, { count: Number(n) });
  });
}

const PREFIX = (p: string) => (p === "This server: " ? `${i18n.t("issue.thisServer")}: ` : p);
const STATE = (s: string) => i18n.t(`docker.state.${s}`, { defaultValue: s });

function siteLabel(label: string): string {
  return label
    .replace(/certificate expires in (\d+) days/i, (_m, n) => i18n.t("issue.certDays", { count: Number(n) }))
    .replace(/^DNS: domain not found/, i18n.t("issue.dnsNotFound"))
    .replace(/^not reachable/, i18n.t("issue.notReachable"))
    .replace(/^reachable · protected by Cloudflare Access/, i18n.t("issue.protected"))
    .replace(/^reachable/, i18n.t("issue.reachable"))
    .replace(/access denied/, i18n.t("issue.accessDenied"))
    .replace(/server error/, i18n.t("issue.serverError"))
    .replace(/^Invalid certificate/, i18n.t("issue.invalidCert"));
}

type Rule = [RegExp, (m: RegExpMatchArray) => string];

const RULES: Rule[] = [
  [/^(.+): port (\d+)( \(.+?\))?( on .+?)? does not answer$/,
    (m) => i18n.t("issue.port", { name: m[1], port: m[2], label: m[3] ?? "", where: m[4] ? ` ${i18n.t("issue.on")} ${m[4].slice(4)}` : "" })],
  [/^(.*)disk (\d+) % full$/, (m) => i18n.t("issue.disk", { prefix: PREFIX(m[1]), pct: m[2] })],
  [/^(.*)memory (\d+) % used$/, (m) => i18n.t("issue.mem", { prefix: PREFIX(m[1]), pct: m[2] })],
  [/^No Docker data yet – is x-tools-collector running\?$/, () => i18n.t("issue.dockerNone")],
  [/^Docker data is outdated \(last update (.+)\)$/, (m) => i18n.t("issue.dockerStale", { when: agoText(m[1]) })],
  [/^Container (.+): stopped by you$/, (m) => i18n.t("issue.containerManual", { name: m[1] })],
  [/^Container (.+): (running|unhealthy|starting|restarting|paused|created|stopped)$/,
    (m) => i18n.t("issue.container", { name: m[1], state: STATE(m[2]) })],
  [/^(.+): container (.+): (running|unhealthy|starting|restarting|paused|created|stopped)$/,
    (m) => i18n.t("issue.hostContainer", { host: m[1], name: m[2], state: STATE(m[3]) })],
  [/^Server '(.+)' has never reported$/, (m) => i18n.t("issue.neverReported", { name: m[1] })],
  [/^Server '(.+)' does not report \(last (.+)\)$/, (m) => i18n.t("issue.silent", { name: m[1], when: agoText(m[2]) })],
  [/^(.+): service (.+) failed$/, (m) => i18n.t("issue.serviceFailed", { host: m[1], name: m[2] })],
  [/^Job '(.+)' reported a failure$/, (m) => i18n.t("issue.jobFailed", { name: m[1] })],
  [/^Job '(.+)' did not report \((?:last success (.+)|never reported), expected every (.+)\)$/,
    (m) => i18n.t(m[2] ? "issue.jobLate" : "issue.jobNever", { name: m[1], when: m[2] ? agoText(m[2]) : "", every: m[3].replace(/ h$/, " Std.") })],
  [/^Automatic backup failed \((.*)\)$/, (m) => i18n.t("issue.backupFailed", { why: m[1] })],
  [/^No automatic backup has run for a long time$/, () => i18n.t("issue.backupOld")],
  [/^Cloudflare Tunnel “(.+)” is (.+)$/, (m) => i18n.t("issue.tunnel", { name: m[1], status: i18n.t(`cloudflare.status.${m[2]}`, { defaultValue: m[2] }) })],
  [/^(.+?) \((.+?)\): (.+)$/, (m) => `${m[1]} (${m[2]}): ${siteLabel(m[3])}`],
];

export function issueText(text: string): string {
  if (!i18n.language.startsWith("de")) return text;
  for (const [pattern, fn] of RULES) {
    const m = text.match(pattern);
    if (m) return fn(m);
  }
  return agoText(text);
}
