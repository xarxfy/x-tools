"""Docker collector.

Runs as its own process (``x-tools collect``), ideally in a separate container
without network that has the Docker socket and the compose roots (read-only).
The web process never talks to Docker itself: the collector writes a snapshot
to the exchange directory, and the web process drops command files there
(start/stop/restart/logs) which the collector validates and executes.
"""
