# Development

Full contributor guide, including the issue-first workflow and PR process:
[docs/development/contributing.md](docs/development/contributing.md) (or the built site's
Development section).

## Quick start

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # install uv
just setup                                        # install dev environment + pre-commit hooks
just check                                        # before committing
just ci                                            # before pushing
```

Run `just --list` for every available command. `just` is optional; each recipe wraps a plain
`uv run ...` command, visible in the `justfile`.
