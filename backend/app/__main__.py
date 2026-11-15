"""Command line: ``x-tools serve`` (default), ``x-tools collect`` (Docker collector), ``x-tools agent``."""

import argparse
import os


def main() -> None:
    # Database, secret key and everything else X-TOOLS writes is readable by its own user only.
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog="x-tools", description="X-TOOLS server")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the web UI and API (default)")
    serve.add_argument("--host", default=os.environ.get("XT_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("XT_PORT", "8080")))
    reset = sub.add_parser("reset-admin", help="set a new password and switch off 2FA of an admin (run on the server)")
    reset.add_argument("username", nargs="?", help="needed when there are several admins")
    reset.add_argument("--generate", action="store_true", help="create a random password and print it")
    sub.add_parser("collect", help="run the Docker collector (needs the Docker socket)")
    sub.add_parser("deploy", help="run the deployer for customer websites (needs network and the Docker socket)")
    sub.add_parser("agent", help="report this server to an X-TOOLS instance (see deploy/agent)")
    args = parser.parse_args()

    if args.command == "agent":
        from app.collector.agent import run as run_agent

        run_agent()
        return
    if args.command == "reset-admin":
        from app.cli_admin import run as run_reset

        run_reset(args.username, args.generate)
        return
    if args.command == "deploy":
        from app.collector.deployer import run as run_deployer

        run_deployer()
        return
    if args.command == "collect":
        from app.collector.collector import run

        run()
        return

    if args.command in (None, "serve"):
        import uvicorn

        host = getattr(args, "host", os.environ.get("XT_HOST", "0.0.0.0"))
        port = getattr(args, "port", int(os.environ.get("XT_PORT", "8080")))
        uvicorn.run("app.main:app", host=host, port=port, proxy_headers=True, forwarded_allow_ips="*",
                    server_header=False)


if __name__ == "__main__":
    main()
