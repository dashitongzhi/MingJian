# Contributing to PlanAgent

Thank you for your interest in contributing to PlanAgent! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- Git
- PostgreSQL (optional)
- Redis (optional)

### Development Setup

1. **Fork and clone** the repository:
   ```bash
   git clone https://github.com/your-username/planagent.git
   cd planagent
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

4. **Set up configuration**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

5. **Run tests**:
   ```bash
   pytest
   ```

## 🎯 How to Contribute

### Reporting Issues

- Use the GitHub issue tracker
- Include detailed reproduction steps
- Provide system information (OS, Python version, etc.)
- Include error logs and screenshots if applicable

### Suggesting Enhancements

- Open an issue with the "enhancement" label
- Describe the use case and expected behavior
- Include mockups or examples if possible

### Code Contributions

1. **Check existing issues** for something to work on
2. **Create a new branch** for your feature/fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Write tests** for your changes
4. **Follow the coding style** (see below)
5. **Update documentation** if needed
6. **Submit a pull request**

## 📝 Coding Style

### Python

- Follow PEP 8
- Use type hints for all function signatures
- Write docstrings for public functions and classes
- Keep functions focused and small
- Use meaningful variable names

### Git Commit Messages

- Use the present tense ("Add feature" not "Added feature")
- Use the imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters or less
- Reference issues and pull requests liberally after the first line

Example:
```
Add military scenario branching feature

- Implement baseline fork with state overrides
- Add KPI comparison output
- Include probability band validation

Fixes #123
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_simulation.py

# Run with coverage
pytest --cov=planagent

# Run with verbose output
pytest -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files as `test_*.py`
- Use descriptive test function names
- Test both success and failure cases
- Mock external dependencies

### Test Structure

```python
import pytest
from planagent.services.simulation import SimulationService

class TestSimulationService:
    """Tests for SimulationService."""
    
    def test_create_simulation_run(self, db_session):
        """Test creating a new simulation run."""
        # Arrange
        service = SimulationService(db_session)
        
        # Act
        run = service.create_run(...)
        
        # Assert
        assert run.id is not None
        assert run.status == "pending"
    
    def test_simulation_run_with_invalid_data(self, db_session):
        """Test simulation run with invalid data raises error."""
        service = SimulationService(db_session)
        
        with pytest.raises(ValueError):
            service.create_run(invalid_data)
```

## 📚 Documentation

### Building Documentation

```bash
# Install documentation dependencies
pip install -e ".[docs]"

# Build documentation
mkdocs build

# Serve documentation locally
mkdocs serve
```

### Documentation Guidelines

- Use Markdown for all documentation
- Include code examples where applicable
- Keep documentation up-to-date with code changes
- Use clear, concise language

## 🔧 Development Tools

### Code Formatting

```bash
# Format code with black
black planagent/ tests/

# Check formatting
black --check planagent/ tests/

# Sort imports
isort planagent/ tests/
```

### Linting

```bash
# Run linter
flake8 planagent/ tests/

# Type checking
mypy planagent/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run all hooks
pre-commit run --all-files
```

## 🏷️ Pull Request Process

1. **Update the README.md** with details of changes if applicable
2. **Update the CHANGELOG.md** with a note describing your changes
3. **The PR will be reviewed** by maintainers
4. **Address any feedback** from code review
5. **Once approved**, your PR will be merged

### PR Template

```markdown
## Description

Brief description of the changes.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Checklist

- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
```

## 🎉 Recognition

Contributors will be recognized in the following ways:

- Listed in the CONTRIBUTORS.md file
- Mentioned in release notes for significant contributions
- Invited to join the contributor team for sustained contributions

## 📞 Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Email**: [maintainer@example.com](mailto:maintainer@example.com)

## 📜 Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.

---

Thank you for contributing to PlanAgent! 🚀