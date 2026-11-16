"""Permissions: what a role may do. Roles are free (see api/roles.py); these keys are fixed.

Areas group the permissions in the role editor. The built-in roles are presets: `viewer` can only look,
`operator` may do everything that is not administration, `admin` may do everything (and cannot be changed).
"""

PERMISSIONS: dict[str, str] = {
    # permission → area
    "services.edit": "services",
    "credentials.manage": "services",
    "customers.edit": "customers",
    "sites.deploy": "customers",
    "jobs.edit": "monitoring",
    "alerts.pause": "monitoring",
    "docker.control": "servers",
    "proxmox.control": "servers",
    "servers.control": "servers",
    "servers.manage": "servers",
    "servers.organize": "servers",
    "cloudflare.edit": "servers",
    "admin.users": "administration",
    "admin.roles": "administration",
    "admin.agents": "administration",
    "admin.settings": "administration",
    "admin.backup": "administration",
    "admin.audit": "administration",
}
AREAS = ("services", "customers", "monitoring", "servers", "administration")

ALL = frozenset(PERMISSIONS)
OPERATOR = frozenset(p for p, area in PERMISSIONS.items() if area != "administration" and p != "servers.manage")

# id → (name, permissions). `servers.manage` (updates, users and SSH keys, firewall on the servers) is an
# administrator right: it is not part of the operator preset.
BUILTIN: dict[str, tuple[str, frozenset[str]]] = {
    "viewer": ("Viewer", frozenset()),
    "operator": ("Operator", OPERATOR),
    "admin": ("Administrator", ALL),
}
