# @debugg-ai/cli (SystemEval for TypeScript)

[![npm version](https://img.shields.io/npm/v/@debugg-ai/cli)](https://www.npmjs.com/package/@debugg-ai/cli)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen)](https://nodejs.org)

The TypeScript/Node.js implementation of [SystemEval](https://debugg.ai/docs/systemeval) - a unified evaluation framework providing objective, deterministic, and traceable test execution.

**Homepage**: [debugg.ai](https://debugg.ai) | **Docs**: [debugg.ai/docs/systemeval](https://debugg.ai/docs/systemeval)

## Philosophy

Test results should be **facts, not opinions**.

Traditional test runners produce ambiguous output that requires human interpretation. Did the build pass? Sort of. Are we ready to deploy? Probably. SystemEval eliminates this ambiguity.

### Core Principles

1. **One Verdict**: `PASS`, `FAIL`, or `ERROR` - nothing else
2. **Non-Fungible Runs**: Every execution has UUID, timestamp, exit code
3. **Deterministic**: Same inputs always produce same verdict
4. **Machine-First**: JSON for automation, human output secondary
5. **No Retry-Until-Green**: Flaky tests fail, period

### The Agent Loop

```
Agent writes code
    ↓
systemeval test --json  (or: npx @debugg-ai/cli test)
    ↓
Structured result (pass/fail/error + metrics)
    ↓
Agent reads result, fixes failures
    ↓
Repeat until PASS
```

## Installation

```bash
# Global CLI installation
npm install -g @debugg-ai/cli

# Project dependency (for programmatic usage)
npm install @debugg-ai/cli
```

## Quick Start

### CLI Usage

```bash
# Set your API key
export DEBUGGAI_API_KEY=your_api_key_here

# Run tests on current git changes
debugg-ai test

# Test last 3 commits
debugg-ai test --last 3

# Test all commits in a PR individually
debugg-ai test --pr-sequence

# Wait for local development server
debugg-ai test --wait-for-server
```

### Programmatic Usage (TypeScript)

```typescript
import { runDebuggAITests } from '@debugg-ai/cli';

const result = await runDebuggAITests({
  apiKey: process.env.DEBUGGAI_API_KEY!,
  repoPath: process.cwd(),
  waitForServer: true,
  serverPort: 3000,
});

// Deterministic verdict
if (result.success) {
  process.exit(0);  // PASS
} else {
  process.exit(1);  // FAIL
}
```

## Exit Codes

| Code | Verdict | Meaning |
|------|---------|---------|
| 0 | PASS | All tests passed |
| 1 | FAIL | One or more tests failed |

These exit codes are deterministic and machine-parseable. No interpretation required.

## GitHub Actions

### Basic Setup
```yaml
- name: Run SystemEval Tests
  env:
    DEBUGGAI_API_KEY: ${{ secrets.DEBUGGAI_API_KEY }}
  run: npx @debugg-ai/cli test
```

### PR Testing - GitHub App Integration
```yaml
- name: Test PR via GitHub App
  env:
    DEBUGGAI_API_KEY: ${{ secrets.DEBUGGAI_API_KEY }}
  run: npx @debugg-ai/cli test --pr ${{ github.event.pull_request.number }}
```

### PR Testing - Per-Commit Analysis
```yaml
- name: Test PR Commits Sequentially
  env:
    DEBUGGAI_API_KEY: ${{ secrets.DEBUGGAI_API_KEY }}
  run: npx @debugg-ai/cli test --pr-sequence
```

### Full Workflow Example
```yaml
name: E2E Tests with SystemEval

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for git analysis

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install dependencies
        run: npm ci

      - name: Start dev server
        run: npm run dev &

      - name: Run SystemEval Tests
        env:
          DEBUGGAI_API_KEY: ${{ secrets.DEBUGGAI_API_KEY }}
        run: npx @debugg-ai/cli test --wait-for-server --server-port 3000

      - name: Upload test artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: systemeval-tests
          path: tests/debugg-ai/
```

## CLI Commands

### `debugg-ai test`

Generate and run E2E tests from git changes.

**Authentication:**
- `--api-key, -k` - Your DebuggAI API key (or use DEBUGGAI_API_KEY env var)

**Git Analysis Options:**
- `--last <number>` - Analyze last N commits
- `--since <date>` - Analyze commits since date/time
- `--commit <hash>` - Test a specific commit
- `--commit-range <range>` - Test a commit range

**PR Testing Options:**
- `--pr <number>` - PR number for GitHub App testing
- `--pr-sequence` - Test each commit in a PR individually
- `--base-branch <branch>` - Base branch for PR
- `--head-branch <branch>` - Head branch for PR

**Local Development:**
- `--wait-for-server` - Wait for local dev server to start
- `--server-port <port>` - Port to wait for (default: 3000)
- `--server-timeout <ms>` - Timeout for server (default: 60000)
- `--max-test-time <ms>` - Maximum test wait time (default: 600000)

**Output Options:**
- `--output-dir, -o` - Where to save test files (default: tests/debugg-ai)
- `--download-artifacts` - Download test artifacts
- `--verbose, -v` - Enable verbose logging
- `--dev` - Enable development mode
- `--no-color` - Disable colored output

### `debugg-ai status`

Check test suite status.

```bash
debugg-ai status --suite-id <uuid>
```

### `debugg-ai list`

List your test suites.

```bash
debugg-ai list --repo my-app --branch main --limit 10
```

## TypeScript API

### Main Entry Point

```typescript
import {
  // Quick start function
  runDebuggAITests,

  // Core classes
  CLIBackendClient,
  GitAnalyzer,
  E2EManager,
  ServerManager,

  // Configuration
  DEFAULT_CONFIG,
  ENV_VARS,

  // Types
  type CLIClientConfig,
  type WorkingChange,
  type CommitInfo,
  type BranchInfo,
  type WorkingChanges,
  type GitAnalyzerOptions,
  type PRCommitInfo,
  type PRCommitSequence,
  type E2EManagerOptions,
  type E2EResult,
  type PRSequenceResult,
  type ServerConfig,
  type ServerStatus,
  type ServerManagerOptions,
  type Chunk,
} from '@debugg-ai/cli';
```

### runDebuggAITests()

The simplest way to run tests programmatically:

```typescript
import { runDebuggAITests } from '@debugg-ai/cli';

const result = await runDebuggAITests({
  // Required
  apiKey: string;

  // Optional - repository
  repoPath?: string;           // Default: process.cwd()
  baseUrl?: string;            // Default: 'https://api.debugg.ai'

  // Optional - server
  waitForServer?: boolean;     // Wait for local server
  serverPort?: number;         // Default: 3000

  // Optional - output
  testOutputDir?: string;      // Default: 'tests/debugg-ai'
  downloadArtifacts?: boolean; // Download test files
  maxTestWaitTime?: number;    // Default: 600000 (10 min)

  // Optional - PR testing
  prSequence?: boolean;        // Test each commit individually
  baseBranch?: string;         // PR base branch
  headBranch?: string;         // PR head branch
});

// Result type - deterministic verdict
interface RunDebuggAITestsResult {
  success: boolean;        // true = PASS, false = FAIL
  suiteUuid?: string;      // Non-fungible run identifier
  testFiles?: string[];    // Generated test artifacts
  error?: string;          // Error message if failed
}
```

### GitAnalyzer

Analyze git repositories for changes:

```typescript
import { GitAnalyzer } from '@debugg-ai/cli';

const analyzer = new GitAnalyzer({
  repoPath: '/path/to/repo',
});

// Get working directory changes (uncommitted)
const workingChanges = await analyzer.getWorkingChanges();

// Get changes for a specific commit
const commitChanges = await analyzer.getCommitChanges('abc123');

// Analyze PR commit sequence
const prSequence = await analyzer.analyzePRCommitSequence({
  baseBranch: 'main',
  headBranch: 'feature-branch',
});

// Get enhanced context with branch info
const context = await analyzer.getEnhancedContext();
```

#### GitAnalyzer Types

```typescript
interface WorkingChange {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed' | 'copied';
  staged: boolean;
  chunks?: Chunk[];
  oldPath?: string;
}

interface CommitInfo {
  hash: string;
  message: string;
  author: string;
  date: string;
  changes: WorkingChange[];
}

interface BranchInfo {
  name: string;
  tracking?: string;
  ahead: number;
  behind: number;
}

interface PRCommitSequence {
  baseBranch: string;
  headBranch: string;
  commits: PRCommitInfo[];
  totalCommits: number;
}

interface Chunk {
  startLine: number;
  endLine: number;
  contents: string;
  filePath?: string;
}
```

### E2EManager

Full E2E test lifecycle management:

```typescript
import { E2EManager } from '@debugg-ai/cli';

const manager = new E2EManager({
  apiKey: 'your-api-key',
  repoPath: process.cwd(),
  baseUrl: 'https://api.debugg.ai',
  testOutputDir: 'tests/debugg-ai',
  serverPort: 3000,
  serverTimeout: 60000,
  maxTestWaitTime: 600000,
  downloadArtifacts: true,

  // Commit options
  commit: 'abc123',
  commitRange: 'main..HEAD',
  since: '2 days ago',
  last: 5,

  // PR options
  prSequence: true,
  baseBranch: 'main',
  headBranch: 'feature-branch',
});

// Wait for server to be ready
const serverReady = await manager.waitForServer(3000, 60000);

// Run tests - returns deterministic result
const result = await manager.runCommitTests();

// Cleanup resources
await manager.cleanup();
```

### ServerManager

Manage local development servers:

```typescript
import { ServerManager } from '@debugg-ai/cli';

const serverManager = new ServerManager({
  port: 3000,
  command: 'npm',
  args: ['run', 'dev'],
  cwd: process.cwd(),
  env: { NODE_ENV: 'development' },
  startupTimeout: 30000,
});

await serverManager.startServer();
const ready = await serverManager.waitForServerHealth(30000);
const status = serverManager.checkServerHealth();
await serverManager.stopServer();
```

### CLIBackendClient

Direct API communication:

```typescript
import { CLIBackendClient } from '@debugg-ai/cli';

const client = new CLIBackendClient({
  apiKey: 'your-api-key',
  baseUrl: 'https://api.debugg.ai',
  repoPath: process.cwd(),
  timeout: 30000,
});

// Create a test suite from commit changes
const suite = await client.createCommitTestSuite({
  changes: workingChanges.changes,
  commitHash: 'abc123',
  branchName: 'main',
});

// Check suite status
const status = await client.getCommitTestSuiteStatus(suite.uuid);

// List test suites
const suites = await client.listTestSuites({
  repoName: 'my-app',
  branchName: 'main',
  limit: 20,
  page: 1,
});
```

### Constants

```typescript
import { DEFAULT_CONFIG, ENV_VARS } from '@debugg-ai/cli';

// Default configuration values
DEFAULT_CONFIG.BASE_URL;            // 'https://api.debugg.ai'
DEFAULT_CONFIG.TEST_OUTPUT_DIR;     // 'tests/debugg-ai'
DEFAULT_CONFIG.SERVER_TIMEOUT;      // 30000
DEFAULT_CONFIG.MAX_TEST_WAIT_TIME;  // 600000
DEFAULT_CONFIG.POLL_INTERVAL;       // 5000
DEFAULT_CONFIG.DEFAULT_SERVER_PORT; // 3000

// Environment variable names
ENV_VARS.API_KEY;           // 'DEBUGGAI_API_KEY'
ENV_VARS.BASE_URL;          // 'DEBUGGAI_BASE_URL'
ENV_VARS.GITHUB_SHA;        // 'GITHUB_SHA'
ENV_VARS.GITHUB_REF_NAME;   // 'GITHUB_REF_NAME'
ENV_VARS.GITHUB_HEAD_REF;   // 'GITHUB_HEAD_REF'
ENV_VARS.NGROK_AUTH_TOKEN;  // 'NGROK_AUTH_TOKEN'
```

## How It Works

1. **Git Analysis**: Analyzes your git changes (working directory, commits, PR)
2. **Test Generation**: Sends changes to DebuggAI API to generate contextual E2E tests
3. **Tunnel Creation**: Creates ngrok tunnel to expose local server for cloud testing
4. **Execution**: Tests run in cloud environment with real browser automation
5. **Results**: Downloads test files, recordings, and structured results

## Comparison: Python vs TypeScript

| Feature | systemeval (Python) | @debugg-ai/cli (TypeScript) |
|---------|---------------------|----------------------------|
| Installation | `pip install systemeval` | `npm install @debugg-ai/cli` |
| CLI Command | `systemeval test` | `debugg-ai test` |
| Config File | `systemeval.yaml` | Environment variables |
| Exit Codes | 0/1/2 (PASS/FAIL/ERROR) | 0/1 (PASS/FAIL) |
| Adapters | pytest, jest, playwright | DebuggAI cloud E2E |
| Primary Use | Local test orchestration | CI/CD E2E generation |

Both implementations share the same philosophy: **objective, deterministic, traceable test results**.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DEBUGGAI_API_KEY` | Your API key (required) |
| `DEBUGGAI_BASE_URL` | Custom API endpoint |
| `NGROK_AUTH_TOKEN` | Ngrok authentication token |
| `GITHUB_SHA` | Auto-detected in GitHub Actions |
| `GITHUB_REF_NAME` | Auto-detected in GitHub Actions |
| `GITHUB_HEAD_REF` | Auto-detected in GitHub Actions |

## Output Files

When `--download-artifacts` is enabled:

- **Test Scripts**: Playwright files (`.spec.js`)
- **Recordings**: Test execution GIFs (`.gif`)
- **Results**: Detailed test data (`.json`)

Files are saved to `tests/debugg-ai/` by default.

## Troubleshooting

**Authentication issues?** Check your API key is set correctly.

**Server not starting?** Verify the port with `curl http://localhost:3000`.

**No changes detected?** Make sure you have git changes to analyze.

**Tunnel issues?** Check your `NGROK_AUTH_TOKEN` is set.

## Requirements

- Node.js >= 18.0.0
- Git repository with changes to analyze
- DebuggAI API key

## Links

- **Homepage**: [debugg.ai](https://debugg.ai)
- **Documentation**: [debugg.ai/docs/systemeval](https://debugg.ai/docs/systemeval)
- **Python SystemEval**: [pypi.org/project/systemeval](https://pypi.org/project/systemeval/)
- **npm Package**: [npmjs.com/package/@debugg-ai/cli](https://www.npmjs.com/package/@debugg-ai/cli)

## License

MIT
