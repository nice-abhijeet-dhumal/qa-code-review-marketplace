# qa-code-review-test (marketplace)

A minimal **test marketplace** for dry-running the [`qa-code-review`](plugin/qa-code-review/)
plugin via [unagi](https://github.com/NiCE-AI-Marketplace/agentic-platform/tree/master/utils/unagi)
before it is merged into the official NiCE Agentic Platform marketplace.

It contains a single plugin entry so you can validate discovery + installation
end-to-end without touching the shared marketplace.

## Install with unagi

```bash
# Point unagi at this marketplace (uses this repo's default branch)
unagi --repo https://github.com/nice-abhijeet-dhumal/qa-code-review-marketplace
```

Then in the TUI: switch to the **NOT INSTALLED** panel, select **qa-code-review**,
mark it (`x`), press `Enter`, choose the target assistant, and install.

Or register it persistently:

```bash
unagi config add-marketplace nice-abhijeet-dhumal/qa-code-review-marketplace
```

## Note

This is a throwaway test marketplace. The plugin's canonical home is
`plugin/qa-code-review/` in `NiCE-AI-Marketplace/agentic-platform` (contribution
PR pending).
