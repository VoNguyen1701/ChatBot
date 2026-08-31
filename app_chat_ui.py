"""Compatibility shim.

The active Flask application lives in app.py.
This file intentionally avoids re-registering routes or bootstrapping the
retrieval system to prevent duplicate endpoints and startup conflicts.
"""

from app import app


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
