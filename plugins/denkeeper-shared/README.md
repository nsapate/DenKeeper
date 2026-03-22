# Denkeeper Shared

This directory is reserved for plugin-safe shared utilities that are truly cross-skill.

Current state: no shared runtime helpers are required yet; expense logic stays in the expense skill package.

Rules for shared code:

- only infrastructure-level helpers belong here
- no expense-specific logic
- no immigration-specific logic
- no chat-flow assumptions

If a helper is only used by one skill, keep it in that skill package instead of promoting it here.
