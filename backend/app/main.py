"""Keep the historical ASGI import path on the authenticated Django application.

The old FastAPI routers are retained as migration reference only. Mounting them
would bypass Django's session, staff and child-ownership permission checks.
"""

from config.asgi import application as app  # noqa: F401
