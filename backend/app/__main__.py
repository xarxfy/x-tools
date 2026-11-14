"""Command line: ``x-tools serve`` (default) and ``x-tools collect`` (Docker collector)."""

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
    sub.add_parser("collect", help="run the Docker collector (needs the Docker socket)")
    args = parser.parse_args()

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
