"""solarapi: read-only FastAPI dashboard backend for the solarmon collector.

This process NEVER touches the stick and NEVER writes to the database. It
opens SQLite read-only and serves decoded state, recent samples, settings,
and a Server-Sent Events live stream. Decoupled from the collector by design
(SPEC section 1): the split to a remote host is a config change, not a
rewrite.
"""

__version__ = "0.1.0"
