# Contributing to DealerScope

Thank you for your interest in contributing to DealerScope! This document provides guidelines and information for contributors.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style and Standards](#code-style-and-standards)
- [Testing Requirements](#testing-requirements)
- [Pull Request Process](#pull-request-process)
- [Security Considerations](#security-considerations)
- [Release Process](#release-process)

## Code of Conduct

This project adheres to a code of conduct that we expect all contributors to follow. Please be respectful and professional in all interactions.

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Node.js 18+** and npm
- **Python 3.11+** with pip
- **Git** for version control
- **Docker** and Docker Compose (for local development)
- **Supabase Account** (free tier works for development)

### Development Setup

1. **Fork and clone the repository:**
   ```bash
   git clone https://github.com/your-username/dealscan-insight.git
   cd dealscan-insight
   ```

2. **Install dependencies:**
   ```bash
   # Install Node.js dependencies
   npm install
   
   # Install Python dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Environment configuration:**
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Edit with your configuration
   nano .env
   ```

4. **Required environment variables:**
   ```bash
   VITE_SUPABASE_URL=your-supabase-url
   VITE_SUPABASE_ANON_KEY=your-anon-key
   ```

5. **Start development environment:**
   ```bash
   # Using Docker (recommended)
   docker-compose up --build
   
   # Or run individually
   npm run dev  # Frontend
   ```

## Code Style and Standards

### TypeScript/JavaScript

- **ESLint configuration**: Follow the existing `.eslintrc` rules
- **Formatting**: Use Prettier for consistent code formatting
- **Type safety**: Prefer explicit types, avoid `any` when possible
- **Naming conventions**:
  - Use camelCase for variables and functions
  - Use PascalCase for components and classes
  - Use SCREAMING_SNAKE_CASE for constants

### Python

- **PEP 8**: Follow Python style guidelines
- **Type hints**: Use type hints for all function parameters and return values
- **Documentation**: Use docstrings for all functions and classes
- **Tools**: Code is validated with `black`, `flake8`, `mypy`, and `bandit`

### Git Commit Messages

Follow conventional commit format:
```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
- `feat(dashboard): add real-time deal notifications`
- `fix(auth): resolve JWT token expiration handling`
- `docs(api): update authentication endpoint documentation`

## Testing Requirements

### Frontend Tests

- **Unit tests**: Use Vitest with React Testing Library
- **Coverage**: Maintain minimum 70% code coverage
- **Test files**: Place tests in `src/__tests__/` or alongside components as `.test.ts`

```bash
# Run tests
npm test

# Run with coverage
npm run test:coverage
```

### Backend Tests

- **Framework**: pytest for all Python tests
- **Types**: Unit, integration, and performance tests
- **Coverage**: Maintain minimum 80% code coverage

```bash
# Run Python tests
pytest tests/

# With coverage
pytest --cov=src tests/
```

### End-to-End Tests

- **Framework**: Playwright for E2E testing
- **Browser testing**: Chrome, Firefox, Safari
- **CI Integration**: Automated in pull requests

```bash
# Run E2E tests
npx playwright test
```

## Pull Request Process

### Before Submitting

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Run quality checks:**
   ```bash
   # Lint and format code
   npm run lint
   npm run lint:fix
   
   # Run tests
   npm test
   pytest tests/
   
   # Security scanning
   npm audit
   bandit -r src/
   ```

3. **Validate production readiness:**
   ```bash
   # Run production validation
   node scripts/validate-codex-sync.js
   ./scripts/sync-github-for-codex.sh
   ```

### PR Requirements

- [ ] **Description**: Clear description of changes and motivation
- [ ] **Tests**: All tests pass and new functionality is tested
- [ ] **Documentation**: Update relevant documentation
- [ ] **Security**: No new security vulnerabilities introduced
- [ ] **Performance**: No significant performance regressions
- [ ] **Breaking changes**: Clearly documented if any

### PR Template

```markdown
## Description
Brief description of the changes and their purpose.

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] E2E tests pass
- [ ] Manual testing completed

## Security
- [ ] No new security vulnerabilities
- [ ] Security scan passed
- [ ] Sensitive data properly handled

## Performance
- [ ] No performance regressions
- [ ] Bundle size impact assessed
- [ ] Database queries optimized (if applicable)
```

### Review Process

1. **Automated checks**: All CI/CD pipelines must pass
2. **Code review**: At least one maintainer review required
3. **Security review**: Required for security-related changes
4. **Performance review**: Required for performance-critical changes

## Security Considerations

### Security-First Development

- **Input validation**: Validate all user inputs
- **Authentication**: Use secure authentication mechanisms
- **Authorization**: Implement proper access controls
- **Data protection**: Encrypt sensitive data
- **Dependencies**: Keep dependencies updated and secure

### Security Testing

```bash
# Security scans
npm audit --audit-level=moderate
bandit -r src/
safety check -r requirements.txt

# Dependency vulnerability scanning
./scripts/security-hardening.sh
```

### Reporting Security Issues

**Do not** create public issues for security vulnerabilities. Instead:

1. Email security concerns to the maintainers
2. Provide detailed information about the vulnerability
3. Allow time for the issue to be addressed before public disclosure

## Release Process

### Version Management

- **Semantic versioning**: Follow SemVer (MAJOR.MINOR.PATCH)
- **Release branches**: Use `release/vX.Y.Z` branches
- **Tags**: Create signed tags for releases

### Pre-Release Checklist

- [ ] All tests pass
- [ ] Security scan clean
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Migration scripts tested
- [ ] Rollback plan prepared

### Deployment

- **Staging**: All changes go through staging first
- **Production**: Blue-green deployment with health checks
- **Monitoring**: Comprehensive monitoring and alerting
- **Rollback**: Automated rollback on failure

## Development Tools

### Recommended IDE Setup

- **VS Code** with extensions:
  - ESLint
  - Prettier
  - TypeScript
  - Python
  - GitLens

### Debugging

- **Frontend**: Browser dev tools, React DevTools
- **Backend**: Python debugger, logging
- **Database**: Supabase dashboard, SQL debugging

### Monitoring

- **Local**: Docker logs, console output
- **Production**: Structured logging, metrics, alerts

## Getting Help

### Resources

- **Documentation**: Check `/docs` directory
- **Examples**: See `/examples` for code samples
- **Scripts**: Use validation scripts in `/scripts`

### Communication

- **Issues**: Create GitHub issues for bugs and features
- **Discussions**: Use GitHub Discussions for questions
- **Reviews**: Engage constructively in code reviews

## Recognition

Contributors are recognized in our release notes and contributor lists. Thank you for helping make DealerScope better!

---

**Note**: This is a production-ready application with high standards for code quality, security, and performance. Please take time to understand these requirements before contributing.