"""Test session setup: the suite runs against its own data store. Without this, tests that touch the store wrote into
the clone's data/ (a fresh clone's first test run left projects there). A store named by EDITVIDEO_DATA is kept: a
developer who points the suite at another drive on purpose still can."""
import os
import tempfile

if not os.environ.get("EDITVIDEO_DATA"):
    os.environ["EDITVIDEO_DATA"] = tempfile.mkdtemp(prefix="editvideo-test-store-")
