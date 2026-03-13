Project-Management State Files
==============================

This directory holds short-lived project state that should remain in the
consuming project's own repository rather than inside TheKnowledge.

Files
-----
- `pending-commit-changes.txt`: queue brief commit-ready summaries here while
  work is in flight. The standardized commit helper uses the nonblank contents
  as commit body text and clears the file after a successful local commit.
