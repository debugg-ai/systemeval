#!/usr/bin/env node

import { Command } from 'commander';
import * as path from 'path';
import * as fs from 'fs-extra';
import { config } from 'dotenv';
import { CLIBackendClient } from './backend/cli/client';
import { loadCliConfig, saveCliConfig, getConfigFilePath } from './config';
import { E2EManager } from './lib/e2e-manager';
import { systemLogger } from './util/system-logger';
import { telemetry } from './services/telemetry';

// Load environment variables
config();

// Read version from package.json
const packageJsonPath = path.join(__dirname, '..', 'package.json');
const packageJson = fs.readJsonSync(packageJsonPath);
const version = packageJson.version;

const program = new Command();

program
  .name('@debugg-ai/cli')
  .description('CLI tool for running DebuggAI tests in CI/CD environments')
  .version(version);

const DEFAULT_BASE_URL = 'https://api.debugg.ai';

type TokenType = 'token' | 'bearer';

interface AuthInputs {
  apiKey?: string;
  token?: string;
  jwtToken?: string;
  tokenType?: string;
  baseUrl?: string;
}

interface AuthDetails {
  token: string;
  tokenType: TokenType;
  baseUrl: string;
}

const normalizeTokenType = (value?: string): TokenType => {
  if (!value) return 'token';
  return value.toLowerCase() === 'bearer' ? 'bearer' : 'token';
};

async function resolveAuth(inputs: AuthInputs): Promise<AuthDetails> {
  const storedConfig = await loadCliConfig();
  const envToken = process.env.DEBUGGAI_API_TOKEN || process.env.DEBUGGAI_JWT_TOKEN || process.env.DEBUGGAI_API_KEY;
  const token = inputs.jwtToken ?? inputs.token ?? inputs.apiKey ?? storedConfig.token ?? envToken;
  if (!token) {
    throw new Error(
      'API token is required. Provide one via --api-key/--token, login with credentials, or DEBUGGAI_API_KEY/DEBUGGAI_API_TOKEN.'
    );
  }

  let tokenType: TokenType = 'token';
  if (inputs.jwtToken) {
    tokenType = 'bearer';
  } else if (inputs.tokenType) {
    tokenType = normalizeTokenType(inputs.tokenType);
  } else if (storedConfig.tokenType) {
    tokenType = normalizeTokenType(storedConfig.tokenType);
  } else if (process.env.DEBUGGAI_TOKEN_TYPE) {
    tokenType = normalizeTokenType(process.env.DEBUGGAI_TOKEN_TYPE);
  }

  const baseUrl = inputs.baseUrl || storedConfig.baseUrl || process.env.DEBUGGAI_BASE_URL || DEFAULT_BASE_URL;
  return { token, tokenType, baseUrl };
}

function addAuthOptions(cmd: Command): Command {
  return cmd
    .option('-k, --api-key <key>', 'DebuggAI API key (can also be stored via login or DEBUGGAI_API_KEY)')
    .option('-t, --token <token>', 'Alias for --api-key (use when referencing saved credentials)')
    .option('--jwt-token <token>', 'Use a JWT token (switches Authorization header to Bearer)')
    .option('--token-type <type>', 'Token type for the Authorization header (token|bearer)')
    .option('-u, --base-url <url>', 'API base URL (default from config or https://api.debugg.ai)');
}

function maskToken(token: string): string {
  if (token.length <= 10) return token;
  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

function enableDevMode(dev?: boolean): void {
  if (dev) {
    process.env.DEBUGGAI_LOG_LEVEL = 'DEBUG';
    process.env.DEBUGGAI_DEV_MODE = 'true';
    systemLogger.debug('Development mode enabled');
  }
}

program
  .command('login')
  .description('Store API credentials locally for repeated use')
  .requiredOption('-t, --token <token>', 'API or JWT token')
  .option('--token-type <type>', 'Token type for Authorization header (token|bearer)')
  .option('-u, --base-url <url>', 'API base URL to store (default: https://api.debugg.ai)')
  .action(async (options) => {
    try {
      const tokenType = normalizeTokenType(options.tokenType);
      const existingConfig = await loadCliConfig();
      const nextConfig = {
        ...existingConfig,
        token: options.token,
        tokenType,
        baseUrl: options.baseUrl || existingConfig.baseUrl || DEFAULT_BASE_URL,
      };
      await saveCliConfig(nextConfig);
      systemLogger.success(`Credentials saved to ${getConfigFilePath()}`);
    } catch (error) {
      systemLogger.error('Failed to save credentials: ' + (error instanceof Error ? error.message : String(error)));
      process.exit(1);
    }
  });

const testCommand = program
  .command('test')
  .description('Run E2E tests based on git changes');
addAuthOptions(testCommand);
testCommand
  .option('-r, --repo-path <path>', 'Repository path (default: current directory)')
  .option('-o, --output-dir <dir>', 'Test output directory (default: tests/debugg-ai)')
  .option('-c, --commit <hash>', 'Specific commit hash to analyze (instead of working changes)')
  .option('--commit-range <range>', 'Commit range to analyze (e.g., HEAD~3..HEAD, main..feature-branch)')
  .option('--since <date>', 'Analyze commits since date/time (e.g., "2024-01-01", "2 days ago")')
  .option('--last <number>', 'Analyze last N commits (e.g., --last 3)')
  .option('--pr <number>', 'PR number for GitHub App-based testing (requires GitHub App integration)')
  .option('--pr-sequence', 'Enable PR commit sequence testing (sends individual test requests for each commit in PR)')
  .option('--base-branch <branch>', 'Base branch for PR testing (auto-detected from GitHub env if not provided)')
  .option('--head-branch <branch>', 'Head branch for PR testing (auto-detected from GitHub env if not provided)')
  .option('--wait-for-server', 'Wait for local development server to be ready')
  .option('--server-port <port>', 'Local server port to test', '3000')
  .option('--server-timeout <ms>', 'Server wait timeout in milliseconds (default: 60000)', '60000')
  .option('--max-test-time <ms>', 'Maximum test wait time in milliseconds (default: 600000)', '600000')
  .option('--download-artifacts', 'Download test artifacts (scripts, recordings, JSON results) to local filesystem')
  .option('-v, --verbose', 'Enable verbose logging for debugging')
  .option('--dev', 'Enable development logging (shows all technical details, tunnel info, API calls, git details, timing)')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      // Track command start
      telemetry.trackCommandStart('test', options);
      
      // Set up logging mode based on flags
      if (options.dev) {
        systemLogger.setDevMode(true);
        systemLogger.debug('Development mode enabled - showing all technical details');
      } else if (options.verbose) {
        systemLogger.setDevMode(true);
        systemLogger.debug('Verbose logging enabled');
      }
      
      // Disable colors if requested (logger handles this now)
      if (options.noColor) {
        // Color handling is now managed by the logger system
      }

      systemLogger.info('DebuggAI Test Runner');
      if (!systemLogger.getDevMode()) {
        console.log('='.repeat(50));
      }

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const repoPath = options.repoPath ? path.resolve(options.repoPath) : process.cwd();
      
      if (!await fs.pathExists(repoPath)) {
        systemLogger.error(`Repository path does not exist: ${repoPath}`);
        process.exit(1);
      }

      const gitDir = path.join(repoPath, '.git');
      if (!await fs.pathExists(gitDir)) {
        systemLogger.error(`Not a git repository: ${repoPath}`);
        process.exit(1);
      }

      const serverPort = parseInt(options.serverPort || '3000');

      systemLogger.debug('CLI configuration', {
        category: 'cli',
        details: {
          repoPath,
          token: maskToken(auth.token),
          tokenType: auth.tokenType,
          baseUrl: auth.baseUrl,
          serverPort,
          waitForServer: options.waitForServer || false
        }
      } as any);

      systemLogger.info(`Server port: ${serverPort}`);
      if (options.waitForServer) {
        systemLogger.info(`Will wait for server on port ${serverPort} before creating tunnel`);
      }
      systemLogger.info(`Tunnel will forward port ${serverPort} to ngrok`);

      const e2eManager = new E2EManager({
        apiKey: auth.token,
        repoPath,
        baseUrl: auth.baseUrl,
        tokenType: auth.tokenType,
        ...(options.outputDir && { testOutputDir: options.outputDir }),
        serverTimeout: parseInt(options.serverTimeout) || 60000,
        maxTestWaitTime: parseInt(options.maxTestTime) || 600000,
        downloadArtifacts: options.downloadArtifacts || false,
        serverPort,
        commit: options.commit,
        commitRange: options.commitRange,
        since: options.since,
        ...(options.last && { last: parseInt(options.last) }),
        prSequence: options.prSequence || false,
        baseBranch: options.baseBranch,
        headBranch: options.headBranch,
        ...(options.pr && { pr: parseInt(options.pr) })
      });

      if (options.waitForServer) {
        const serverTimeout = parseInt(options.serverTimeout) || 60000;
        
        systemLogger.debug('Waiting for development server', { 
          category: 'server',
          details: { port: serverPort, timeout: serverTimeout } 
        } as any);
        
        if (systemLogger.getDevMode()) {
          systemLogger.debug(`Waiting for development server on port ${serverPort}`, { category: 'server' } as any);
        } else {
          (systemLogger.progress as any).start(`Waiting for development server on port ${serverPort}`);
        }
        
        const serverReady = await e2eManager.waitForServer(serverPort, serverTimeout);
        if (!serverReady) {
          systemLogger.error(`Server on port ${serverPort} did not start within ${serverTimeout}ms`);
          process.exit(1);
        }
      }

      if (systemLogger.getDevMode()) {
        systemLogger.debug('Starting test analysis and generation', { category: 'test' } as any);
      } else {
        (systemLogger.progress as any).start('Starting test analysis and generation');
      }
      const result = await e2eManager.runCommitTests();

      if (result.success) {
        systemLogger.success('Tests completed successfully!');
        
        if (result.testFiles && result.testFiles.length > 0) {
          systemLogger.displayFileList(result.testFiles, repoPath);
        }

        systemLogger.info(`Test suite ID: ${result.suiteUuid}`);

        if (process.exitCode === 1) {
          systemLogger.error('Some tests failed - see results above.');
          process.exit(1);
        } else {
          systemLogger.success('All tests completed successfully!');
          process.exit(0);
        }
      } else {
        systemLogger.error(`Tests failed: ${result.error}`);
        process.exit(1);
      }

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }
      
      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Unexpected error: ' + errorMsg);
      
      if (process.env.DEBUG) {
        systemLogger.error('Stack trace: ' + (error as any)?.stack);
      }
      
      telemetry.trackCommandComplete('test', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const statusCommand = program
  .command('status')
  .description('Check the status of a test suite')
  .requiredOption('-s, --suite-id <id>', 'Test suite UUID');
addAuthOptions(statusCommand);
statusCommand
  .option('--dev', 'Enable development logging (shows all technical details)')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      telemetry.trackCommandStart('status', options);
      if (options.dev) {
        enableDevMode(true);
      }
      
      if (options.noColor) {
        // Color handling delegated to logger
      }

      systemLogger.info('DebuggAI Test Status');
      console.log('='.repeat(50));

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const e2eManager = new E2EManager({
        apiKey: auth.token,
        repoPath: process.cwd(),
        baseUrl: auth.baseUrl,
        tokenType: auth.tokenType
      });

      const suite = await (e2eManager as any).client.getCommitTestSuiteStatus(options.suiteId);
      if (!suite) {
        systemLogger.error(`Test suite not found: ${options.suiteId}`);
        process.exit(1);
      }

      systemLogger.info(`Suite ID: ${suite.uuid}`);
      systemLogger.info(`Name: ${suite.name || 'Unnamed'}`);
      systemLogger.info(`Status: ${getStatusColor(suite.status || 'unknown')}`);
      systemLogger.info(`Tests: ${suite.tests?.length || 0}`);

      if (suite.tests && suite.tests.length > 0) {
        systemLogger.info('\nTest Details:');
        for (const test of suite.tests) {
          const status = test.curRun?.status || 'unknown';
          console.log(`  • ${test.name || test.uuid}: ${getStatusColor(status)}`);
        }
      }

      telemetry.trackCommandComplete('status', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }

      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error checking status: ' + errorMsg);
      telemetry.trackCommandComplete('status', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const listCommand = program
  .command('list')
  .description('List test suites for a repository');
addAuthOptions(listCommand);
listCommand
  .option('-r, --repo <name>', 'Repository name filter')
  .option('-b, --branch <name>', 'Branch name filter')
  .option('-l, --limit <number>', 'Limit number of results (default: 20)', '20')
  .option('-p, --page <number>', 'Page number (default: 1)', '1')
  .option('--dev', 'Enable development logging (shows all technical details)')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      telemetry.trackCommandStart('list', options);
      if (options.dev) {
        enableDevMode(true);
      }
      
      if (options.noColor) {
        // Color handling delegated to logger
      }

      systemLogger.info('DebuggAI Test Suites');
      console.log('='.repeat(50));

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const e2eManager = new E2EManager({
        apiKey: auth.token,
        repoPath: process.cwd(),
        baseUrl: auth.baseUrl,
        tokenType: auth.tokenType
      });

      const result = await (e2eManager as any).client.listTestSuites({
        repoName: options.repo,
        branchName: options.branch,
        limit: parseInt(options.limit),
        page: parseInt(options.page)
      });

      if (!result?.suites?.length) {
        systemLogger.warn('No test suites found.');
        telemetry.trackCommandComplete('list', true);
        await telemetry.shutdown();
        return;
      }

      systemLogger.info(`Found ${result.total} test suites (showing ${result.suites.length}):`); console.log('');

      for (const suite of result.suites) {
        console.log(`${suite.name || suite.uuid}`);
        console.log(`  Status: ${getStatusColor(suite.status || 'unknown')}`);
        console.log(`  Tests: ${suite.tests?.length || 0}`);
        console.log(`  UUID: ${suite.uuid}`);
        console.log('');
      }
      
      telemetry.trackCommandComplete('list', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }
      
      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error listing test suites: ' + errorMsg);
      telemetry.trackCommandComplete('list', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const e2eGroup = program
  .command('e2e')
  .description('Interact with the E2E tests API');

const e2eListCommand = e2eGroup
  .command('list')
  .description('List available E2E tests');
addAuthOptions(e2eListCommand);
e2eListCommand
  .option('--status <status>', 'Filter tests by status')
  .option('--project <uuid>', 'Filter by project UUID')
  .option('--branch <name>', 'Filter by branch name')
  .option('--page <number>', 'Page to fetch (default: 1)', '1')
  .option('--limit <number>', 'Number of items per page (default: 20)', '20')
  .option('--json', 'Print raw JSON response')
  .option('--dev', 'Enable development logging')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      telemetry.trackCommandStart('e2e:list', options);
      if (options.dev) {
        enableDevMode(true);
      }

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const client = new CLIBackendClient({
        apiKey: auth.token,
        baseUrl: auth.baseUrl,
        repoPath: process.cwd(),
        tokenType: auth.tokenType
      });
      await client.initialize();

      const response = await client.e2es.listE2eTests({
        status: options.status,
        project: options.project,
        branchName: options.branch,
        page: parseInt(options.page),
        limit: parseInt(options.limit)
      });

      if (options.json) {
        console.log(JSON.stringify(response, null, 2));
        telemetry.trackCommandComplete('e2e:list', true);
        await telemetry.shutdown();
        return;
      }

      const tests = Array.isArray(response?.results) ? response?.results : [];
      if (!tests.length) {
        systemLogger.warn('No E2E tests found.');
        telemetry.trackCommandComplete('e2e:list', true);
        await telemetry.shutdown();
        return;
      }

      tests.forEach((test) => {
        const status = test.curRun?.status || 'unknown';
        console.log(`${test.uuid} (${test.name || 'Unnamed'})`);
        console.log(`  Status: ${getStatusColor(status)}`);
        if (test.description) {
          console.log(`  Description: ${test.description}`);
        }
        if (test.projectName) {
          console.log(`  Project: ${test.projectName}`);
        }
        console.log('');
      });

      telemetry.trackCommandComplete('e2e:list', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }

      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error listing E2E tests: ' + errorMsg);
      telemetry.trackCommandComplete('e2e:list', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const e2eCreateCommand = e2eGroup
  .command('create')
  .description('Create a new E2E test via the API');
addAuthOptions(e2eCreateCommand);
e2eCreateCommand
  .requiredOption('-d, --description <text>', 'Test description')
  .requiredOption('-p, --project <uuid>', 'Project UUID to associate with the test')
  .option('-b, --branch <name>', 'Branch name')
  .option('--file-path <path>', 'Path to the file under test')
  .option('--local-port <port>', 'Application port (used for local runs)', '3000')
  .option('--repo-path <path>', 'Repository path for localized context (default: current directory)')
  .option('--url <url>', 'Target URL for the test')
  .option('--test-type <type>', 'Test type (e.g., functional, regression)')
  .option('--json', 'Print raw JSON response')
  .option('--dev', 'Enable development logging')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      telemetry.trackCommandStart('e2e:create', options);
      if (options.dev) {
        enableDevMode(true);
      }

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const client = new CLIBackendClient({
        apiKey: auth.token,
        baseUrl: auth.baseUrl,
        repoPath: process.cwd(),
        tokenType: auth.tokenType
      });
      await client.initialize();

      const payload: Record<string, any> = {
        project: options.project,
        branchName: options.branch,
        filePath: options.filePath,
        localPort: parseInt(options.localPort),
        repoPath: options.repoPath || process.cwd(),
        url: options.url,
        testType: options.testType
      };

      const created = await client.e2es.createE2eTest(options.description, payload);
      if (!created) {
        throw new Error('Failed to create E2E test');
      }

      if (options.json) {
        console.log(JSON.stringify(created, null, 2));
      } else {
        systemLogger.info(`Created E2E test: ${created.uuid}`);
        systemLogger.info(`Status: ${created.curRun?.status || 'pending'}`);
      }

      telemetry.trackCommandComplete('e2e:create', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }

      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error creating E2E test: ' + errorMsg);
      telemetry.trackCommandComplete('e2e:create', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const e2eStatusCommand = e2eGroup
  .command('status <testId>')
  .description('Get the status of a specific E2E test');
addAuthOptions(e2eStatusCommand);
e2eStatusCommand
  .option('--json', 'Print raw JSON response')
  .option('--dev', 'Enable development logging')
  .option('--no-color', 'Disable colored output')
  .action(async (testId, options) => {
    try {
      telemetry.trackCommandStart('e2e:status', options);
      if (options.dev) {
        enableDevMode(true);
      }

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const client = new CLIBackendClient({
        apiKey: auth.token,
        baseUrl: auth.baseUrl,
        repoPath: process.cwd(),
        tokenType: auth.tokenType
      });
      await client.initialize();

      const transport = client.getTransport();
      const response = await transport.get(`api/v1/e2e-tests/${testId}/status/`);
      if (options.json) {
        console.log(JSON.stringify(response, null, 2));
        telemetry.trackCommandComplete('e2e:status', true);
        await telemetry.shutdown();
        return;
      }

      const data = response?.data ?? response;
      systemLogger.info(`Test ID: ${data?.id || testId}`);
      systemLogger.info(`Status: ${data?.status ?? 'unknown'}`);
      if (data?.currentStep) {
        systemLogger.info(`Current step: ${data.currentStep}`);
      }
      if (data?.progress !== undefined) {
        systemLogger.info(`Progress: ${data.progress}%`);
      }
      if (data?.screenshots?.length) {
        systemLogger.info('Screenshots:');
        data.screenshots.forEach((url: string) => systemLogger.info(`  - ${url}`));
      }

      telemetry.trackCommandComplete('e2e:status', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }

      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error fetching E2E test status: ' + errorMsg);
      telemetry.trackCommandComplete('e2e:status', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

const crawlGroup = program
  .command('crawl')
  .description('Inspect crawl session metadata');

const crawlListCommand = crawlGroup
  .command('list')
  .description('List crawl sessions recorded by the platform');
addAuthOptions(crawlListCommand);
crawlListCommand
  .option('--graph <uuid>', 'Filter sessions by knowledge graph UUID')
  .option('--project <uuid>', 'Filter sessions by project UUID')
  .option('--crawler <uuid>', 'Filter sessions by crawler UUID')
  .option('--completed <true|false>', 'Show only completed or incomplete sessions')
  .option('--page <number>', 'Page number for pagination (default: 1)', '1')
  .option('--limit <number>', 'Page size (default: 20)', '20')
  .option('--json', 'Print raw JSON response')
  .option('--dev', 'Enable development logging')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      telemetry.trackCommandStart('crawl:list', options);
      if (options.dev) {
        enableDevMode(true);
      }

      const auth = await resolveAuth({
        apiKey: options.apiKey,
        token: options.token,
        jwtToken: options.jwtToken,
        tokenType: options.tokenType,
        baseUrl: options.baseUrl
      });

      const client = new CLIBackendClient({
        apiKey: auth.token,
        baseUrl: auth.baseUrl,
        repoPath: process.cwd(),
        tokenType: auth.tokenType
      });
      await client.initialize();

      const params: Record<string, any> = {
        graph: options.graph,
        project: options.project,
        crawler: options.crawler,
        completed: typeof options.completed === 'string'
          ? options.completed.toLowerCase() === 'true'
          : undefined,
        page: parseInt(options.page),
        limit: parseInt(options.limit)
      };

      const response = await client.getTransport().get('api/v1/graphs/crawl-sessions/', params);
      if (options.json) {
        console.log(JSON.stringify(response, null, 2));
        telemetry.trackCommandComplete('crawl:list', true);
        await telemetry.shutdown();
        return;
      }

      const sessions = Array.isArray(response)
        ? response
        : Array.isArray(response?.results)
          ? response.results
          : [];

      if (!sessions.length) {
        systemLogger.warn('No crawl sessions found.');
        telemetry.trackCommandComplete('crawl:list', true);
        await telemetry.shutdown();
        return;
      }

      sessions.forEach((session: any) => {
        const graphLabel = session.graph?.uuid ?? session.graph ?? 'N/A';
        const crawlerLabel = session.crawler?.uuid ?? session.crawler ?? 'N/A';
        const completed = session.completedSuccessfully ?? session.completed ?? false;

        console.log(`${session.uuid} | Graph: ${graphLabel} | Crawler: ${crawlerLabel} | Completed: ${completed}`);
        console.log(`  Strategy: ${session.strategy || 'N/A'} | States: ${session.statesDiscovered ?? 0} | Edges: ${session.edgesDiscovered ?? 0}`);
        if (session.startState?.uuid) {
          console.log(`  Start state: ${session.startState.uuid}`);
        }
        if (session.errorMessage) {
          console.log(`  Error: ${session.errorMessage}`);
        }
        console.log('');
      });

      telemetry.trackCommandComplete('crawl:list', true);
      await telemetry.shutdown();

    } catch (error) {
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }

      const errorMsg = error instanceof Error ? error.message : String(error);
      systemLogger.error('Error listing crawl sessions: ' + errorMsg);
      telemetry.trackCommandComplete('crawl:list', false, errorMsg);
      await telemetry.shutdown();
      process.exit(1);
    }
  });

// Workflow command - temporarily disabled during refactoring
// TODO: Re-implement workflow command with new architecture
/*
program
  .command('workflow')
  .description('Run complete E2E testing workflow with server management and tunnel setup')
  .option('-k, --api-key <key>', 'DebuggAI API key (can also use DEBUGGAI_API_KEY env var)')
  .option('-u, --base-url <url>', 'API base URL (default: https://api.debugg.ai)')
  .option('-r, --repo-path <path>', 'Repository path (default: current directory)')
  .option('-o, --output-dir <dir>', 'Test output directory (default: tests/debugg-ai)')
  .option('-p, --port <port>', 'Server port (default: 3000)', '3000')
  .option('-c, --command <cmd>', 'Server start command (default: npm start)', 'npm start')
  .option('--server-args <args>', 'Server command arguments (comma-separated)')
  .option('--server-cwd <path>', 'Server working directory')
  .option('--server-env <env>', 'Server environment variables (KEY=value,KEY2=value2)')
  .option('--ngrok-token <token>', 'Ngrok auth token (can also use NGROK_AUTH_TOKEN env var)')
  .option('--ngrok-subdomain <subdomain>', 'Custom ngrok subdomain')
  .option('--ngrok-domain <domain>', 'Custom ngrok domain')
  .option('--base-domain <domain>', 'Base domain for tunnels (default: ngrok.debugg.ai)')
  .option('--max-test-time <ms>', 'Maximum test wait time in milliseconds (default: 600000)', '600000')
  .option('--server-timeout <ms>', 'Server startup timeout in milliseconds (default: 60000)', '60000')
  .option('--cleanup-on-success', 'Cleanup resources after successful completion (default: true)', true)
  .option('--cleanup-on-error', 'Cleanup resources after errors (default: true)', true)
  .option('--download-artifacts', 'Download test artifacts (scripts, recordings, JSON results) to local filesystem')
  .option('--pr-sequence', 'Enable PR commit sequence testing (sends individual test requests for each commit in PR)')
  .option('--base-branch <branch>', 'Base branch for PR testing (auto-detected from GitHub env if not provided)')
  .option('--head-branch <branch>', 'Head branch for PR testing (auto-detected from GitHub env if not provided)')
  .option('--verbose', 'Verbose logging')
  .option('--dev', 'Enable development logging (shows all technical details, server logs, tunnel info)')
  .option('--no-color', 'Disable colored output')
  .action(async (options) => {
    try {
      // Set up development mode
      if (options.dev) {
        process.env.DEBUGGAI_LOG_LEVEL = 'DEBUG';
        process.env.DEBUGGAI_DEV_MODE = 'true';
        systemLogger.debug('Development mode enabled');
      }
      
      // Disable colors if requested (now handled by loggers)
      if (options.noColor) {
        // Color handling is now managed by the logger system
      }

      systemLogger.info('DebuggAI Workflow Runner');
      console.log('='.repeat(50));

      // Get API key
      const apiKey = options.apiKey || process.env.DEBUGGAI_API_KEY;
      if (!apiKey) {
        systemLogger.error('API key is required. Provide it via --api-key or DEBUGGAI_API_KEY environment variable.');
        process.exit(1);
      }

      // Get repository path
      const repoPath = options.repoPath ? path.resolve(options.repoPath) : process.cwd();
      
      // Validate repository path exists
      if (!await fs.pathExists(repoPath)) {
        systemLogger.error(`Repository path does not exist: ${repoPath}`);
        process.exit(1);
      }

      // Validate it's a git repository
      const gitDir = path.join(repoPath, '.git');
      if (!await fs.pathExists(gitDir)) {
        systemLogger.error(`Not a git repository: ${repoPath}`);
        process.exit(1);
      }

      systemLogger.debug('Workflow configuration', { 
        category: 'workflow',
        details: { repoPath, apiKey: `${apiKey.substring(0, 8)}...` } 
      } as any);

      // Parse server command and args
      const [command, ...defaultArgs] = options.command.split(' ');
      const serverArgs = options.serverArgs 
        ? options.serverArgs.split(',').map((arg: string) => arg.trim())
        : defaultArgs;

      // Parse environment variables
      const serverEnv: Record<string, string> = {};
      if (options.serverEnv) {
        options.serverEnv.split(',').forEach((pair: string) => {
          const [key, value] = pair.trim().split('=');
          if (key && value) {
            serverEnv[key] = value;
          }
        });
      }

      // Generate a tunnel key for backend to create tunnel endpoints
      const tunnelKey = randomUUID();
      systemLogger.debug('Generated tunnel key for workflow', { 
        category: 'tunnel',
        details: { key: tunnelKey.substring(0, 8) + '...' } 
      } as any);

      // Initialize workflow orchestrator
      const orchestrator = new WorkflowOrchestrator({
        ngrokAuthToken: options.ngrokToken || process.env.NGROK_AUTH_TOKEN,
        baseDomain: options.baseDomain,
        verbose: options.verbose || options.dev,  // Dev mode implies verbose
        devMode: options.dev
      });

      // Configure workflow
      const workflowConfig = {
        server: {
          command,
          args: serverArgs,
          port: parseInt(options.port),
          cwd: options.serverCwd || repoPath,
          env: serverEnv,
          startupTimeout: parseInt(options.serverTimeout)
        },
        tunnel: {
          port: parseInt(options.port),
          subdomain: options.ngrokSubdomain,
          customDomain: options.ngrokDomain,
          authtoken: options.ngrokToken || process.env.NGROK_AUTH_TOKEN
        },
        test: {
          apiKey,
          baseUrl: options.baseUrl,
          repoPath,
          testOutputDir: options.outputDir,
          maxTestWaitTime: parseInt(options.maxTestTime),
          downloadArtifacts: options.downloadArtifacts || false,
          tunnelKey, // Add the generated tunnel key
          createTunnel: true, // Enable tunnel creation
          tunnelPort: parseInt(options.port) || 3000, // Use server port for tunnel
          // PR sequence options
          prSequence: options.prSequence || false,
          baseBranch: options.baseBranch,
          headBranch: options.headBranch,
          // GitHub App PR testing
          ...(options.pr && { pr: parseInt(options.pr) })
        },
        cleanup: {
          onSuccess: options.cleanupOnSuccess,
          onError: options.cleanupOnError
        }
      };

      systemLogger.debug('Starting workflow orchestrator');
      (systemLogger.progress as any).start('Starting complete testing workflow');
      const result = await orchestrator.executeWorkflow(workflowConfig);

      if (result.success) {
        systemLogger.success('Workflow completed successfully!');
        
        if (result.tunnelInfo) {
          systemLogger.info(`Tunnel URL: ${result.tunnelInfo.url}`);
        }
        
        if (result.serverUrl) {
          systemLogger.info(`Local Server: ${result.serverUrl}`);
        }

        if (result.testResult?.testFiles && result.testResult.testFiles.length > 0) {
          systemLogger.displayFileList(result.testResult.testFiles, repoPath);
        }

        if (result.testResult?.suiteUuid) {
          systemLogger.info(`Test suite ID: ${result.testResult.suiteUuid}`);
        }
        
        // Check if any tests failed (process.exitCode may have been set by reportResults)
        if (process.exitCode === 1) {
          systemLogger.error('Some tests failed - see results above');
          process.exit(1);
        } else {
          process.exit(0);
        }
      } else {
        systemLogger.error(`Workflow failed: ${result.error}`);
        process.exit(1);
      }

    } catch (error) {
      // Re-throw test exit errors to prevent them from being handled
      if (error instanceof Error && (error as any).isSuccessExit) {
        throw error;
      }
      
      systemLogger.error('Unexpected workflow error: ' + (error instanceof Error ? error.message : String(error)));
      
      if (process.env.DEBUG) {
        systemLogger.error('Stack trace: ' + (error as any)?.stack);
      }

      process.exit(1);
    }
  });
*/

/**
 * Get colored status text
 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return '✓ COMPLETED';
    case 'failed':
      return '✗ FAILED';
    case 'running':
      return '⏳ RUNNING';
    case 'pending':
      return '⏸ PENDING';
    default:
      return '❓ UNKNOWN';
  }
}

// Handle unhandled promise rejections and uncaught exceptions
// Only add these handlers if we're not in a test environment
if (process.env.NODE_ENV !== 'test') {
  process.on('unhandledRejection', (reason, promise) => {
    systemLogger.error('Unhandled Rejection at: promise=' + promise + ', reason=' + reason);
    process.exit(1);
  });

  process.on('uncaughtException', (error) => {
    systemLogger.error('Uncaught Exception: ' + error);
    process.exit(1);
  });
}

// Parse command line arguments
program.parse();
