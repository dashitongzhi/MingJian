# Contributing to 明鉴 (MingJian)

Thank you for your interest in contributing to 明鉴! This document provides guidelines and information for contributors.

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
   cd mingjian
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

### Suggesting Enhancements

- Open a GitHub discussion first
- Describe the problem you're trying to solve
- Explain why this enhancement would be useful

### Code Contributions

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make your changes**:
   - Follow the coding standards
   - Add tests for new functionality
   - Update documentation as needed

3. **Run the test suite**:
   ```bash
   pytest
   ```

4. **Commit your changes**:
   ```bash
   git commit -m "feat: add amazing feature"
   ```

5. **Push to the branch**:
   ```bash
   git push origin feature/amazing-feature
   ```

6. **Open a Pull Request**

## 📋 Coding Standards

### Python

- Follow PEP 8
- Use type hints
- Write docstrings for public functions
- Keep functions focused and small

### TypeScript/React

- Use TypeScript for all new code
- Follow the existing code style
- Use functional components with hooks
- Write meaningful component names

### Commit Messages

Use conventional commits:

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `style:` for formatting changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `chore:` for maintenance tasks

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=planagent

# Run specific test file
pytest tests/test_debate.py

# Run with verbose output
pytest -v
```

### Writing Tests

- Write tests for all new functionality
- Use descriptive test names
- Test both success and failure cases
- Mock external dependencies

## 📚 Documentation

- Update README.md if needed
- Add docstrings to new functions
- Update API documentation
- Include examples for new features

## 🤝 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow the project's coding standards

## 📞 Getting Help

- 📧 Email: [Your Email]
- 🐛 Issues: github.com/dashitongzhi/planagent/issues
- 💬 Discussions: github.com/dashitongzhi/planagent/discussions

## 🙏 Acknowledgments

Thank you for contributing to 明鉴! Your contributions help make this project better for everyone.

---

**明鉴** — *明察秋毫，鉴往知来*

**明鉴** — *See Clearly, Judge Wisely*
