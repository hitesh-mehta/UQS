# Contributing to Universal Query Solver (UQS)

Thank you for your interest in contributing!

## Developer Certificate of Origin (DCO)

This project uses the **Developer Certificate of Origin (DCO)**. By submitting a pull request,
you certify that your contribution is your original work and you have the right to submit it
under the Apache 2.0 license.

**All commits must be signed off:**

```bash
git commit -s -m "feat: describe your change"
```

The `-s` flag appends a `Signed-off-by` line to your commit message:

```
Signed-off-by: Your Name <your-email@example.com>
```

This email must match your GitHub account email.

## Code Style

- **Python**: PEP 8, type hints required, docstrings on public functions
- **TypeScript**: strict mode, component-level comments for non-obvious logic
- **Naming**: snake_case for Python, camelCase for TypeScript/JS
- **No sensitive data**: never commit API keys, tokens, or real credentials

## Pull Request Guidelines

1. Fork the repo and create a feature branch: `git checkout -b feat/my-feature`
2. Write clean, commented code
3. Add tests in `backend/tests/` for new backend logic
4. Sign all commits with `-s`
5. Open a PR with a clear description of what changed and why

## License

Apache 2.0 — all contributions are licensed under Apache 2.0 upon submission.
