# Shared Resources

This directory contains resources shared between `systemeval-py` (Python) and `systemeval-ts` (TypeScript) implementations.

## Contents

### Configuration Schemas
- Common configuration file schemas (YAML/JSON)
- Shared type definitions
- API contracts

### Test Fixtures
- Sample test data used by both implementations
- Mock responses
- Example configurations

### Documentation
- Architecture diagrams
- API documentation
- Cross-language design decisions

## Usage

Both Python and TypeScript packages may reference files in this directory for:
- Validating configuration files
- Sharing test fixtures
- Maintaining consistent type definitions across languages

## Structure

```
shared/
├── README.md (this file)
├── schemas/          # Configuration and data schemas
├── fixtures/         # Test data and mock responses
├── examples/         # Example configurations
└── docs/             # Shared documentation
```

## Adding New Shared Resources

When adding new resources to this directory:

1. **Schemas**: Add to `schemas/` with both TypeScript and Python type definitions
2. **Fixtures**: Add to `fixtures/` with clear naming conventions
3. **Examples**: Add to `examples/` with inline documentation
4. **Documentation**: Add to `docs/` following existing patterns

## Cross-Language Considerations

- Keep file formats language-agnostic (prefer JSON/YAML over language-specific formats)
- Document any language-specific nuances
- Maintain version compatibility between Python and TypeScript implementations
