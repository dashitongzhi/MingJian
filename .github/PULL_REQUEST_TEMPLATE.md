## Description

<!-- Brief description of changes -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## Related Issues

<!-- Link related issues: Fixes #123, Closes #456 -->

## Screenshots (for frontend changes)

<!-- If your PR includes UI changes in frontend-v2, please add before/after screenshots or screen recordings.
     Drag & drop images into this area or paste from clipboard. -->

## Checklist

- [ ] My code follows the project's coding style
- [ ] I have added tests that prove my fix/feature works
- [ ] All new and existing tests pass (`python -m pytest tests/ -v`)
- [ ] Code is formatted (`ruff format src/ tests/`)
- [ ] Type-checks pass (`mypy src/planagent/`)
- [ ] I have updated documentation if needed
- [ ] I have checked that no existing functionality is broken
- [ ] Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (e.g. `feat:`, `fix:`, `docs:`)

## Local Verification

Before opening this PR, please confirm the following pass locally:

```bash
# Format check
ruff format --check src/ tests/

# Type check
mypy src/planagent/

# Unit tests
pytest tests/unit/
```

- [ ] I have run the above checks locally and they all pass

## Testing

<!-- Describe how you tested your changes -->
