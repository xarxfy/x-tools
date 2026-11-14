"""Command line: ``x-tools serve`` (default), later also ``collect`` and ``agent``."""

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="x-tools", description="X-TOOLS server")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="run the web UI and API (default)")
    serve.add_argument("--host", default=os.environ.get("XT_HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("XT_PORT", "8080")))
    args = parser.parse_args()

    if args.command in (None, "serve"):
        import uvicorn

        host = getattr(args, "host", os.environ.get("XT_HOST", "0.0.0.0"))
        port = getattr(args, "port", int(os.environ.get("XT_PORT", "8080")))
        uvicorn.run("app.main:app", host=host, port=port, proxy_headers=True, forwarded_allow_ips="*",
                    server_header=False)


if __name__ == "__main__":
    main()
