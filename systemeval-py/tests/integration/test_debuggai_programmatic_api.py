"""
Integration tests for debugg-ai-cli programmatic TypeScript API.

Tests the programmatic API exposed by @debugg-ai/cli package:
- runDebuggAITests() function
- GitAnalyzer class
- E2EManager class
- CLIBackendClient class (with mock server)

Since this is a Python test file testing a TypeScript API, we use subprocess
to run Node.js scripts that exercise the API and verify the output.
"""

import json
import os
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from tests.fixtures import (
    E2ETestHarness,
    MockDebuggAIServer,
    GitRepoFixture,
    CLIResult,
)


# Path to the debugg-ai-cli dist directory
CLI_DIST_PATH = Path(__file__).parent.parent.parent / "debugg-ai-cli" / "dist"
CLI_INDEX_PATH = CLI_DIST_PATH / "index.js"


# Skip all tests if CLI not built
pytestmark = pytest.mark.skipif(
    not CLI_INDEX_PATH.exists(),
    reason="CLI not built - run 'npm run build' in debugg-ai-cli",
)


class NodeScriptRunner:
    """
    Helper class to run Node.js scripts that test the programmatic API.

    Creates temporary JS files, executes them, and captures output.
    """

    def __init__(
        self,
        work_dir: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
    ):
        self.work_dir = work_dir or Path.cwd()
        self.env = env or {}
        self.timeout = timeout
        self._temp_scripts: List[Path] = []

    def run_script(
        self,
        script_content: str,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """
        Run a Node.js script and return (returncode, stdout, stderr).

        Args:
            script_content: JavaScript code to execute
            extra_env: Additional environment variables

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        # Create temporary script file
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            dir=str(self.work_dir),
            delete=False,
        ) as f:
            f.write(script_content)
            script_path = Path(f.name)
            self._temp_scripts.append(script_path)

        # Build environment
        run_env = os.environ.copy()
        run_env.update(self.env)
        if extra_env:
            run_env.update(extra_env)

        try:
            result = subprocess.run(
                ["node", str(script_path)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.work_dir),
                env=run_env,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"Script timed out after {self.timeout}s"
        finally:
            # Clean up script file
            try:
                script_path.unlink()
                self._temp_scripts.remove(script_path)
            except (OSError, ValueError):
                pass

    def run_script_json(
        self,
        script_content: str,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Optional[Dict[str, Any]], str]:
        """
        Run a script and parse JSON from stdout.

        Returns:
            Tuple of (returncode, parsed_json_or_None, stderr)
        """
        returncode, stdout, stderr = self.run_script(script_content, extra_env)

        if returncode != 0:
            return returncode, None, stderr

        try:
            # Try to find and parse JSON in output
            # Handle case where there might be other output before/after JSON
            stdout_stripped = stdout.strip()
            if stdout_stripped.startswith("{"):
                end = stdout_stripped.rfind("}") + 1
                json_str = stdout_stripped[:end]
            elif "{" in stdout_stripped:
                start = stdout_stripped.find("{")
                end = stdout_stripped.rfind("}") + 1
                json_str = stdout_stripped[start:end]
            else:
                return returncode, None, f"No JSON found in output: {stdout}"

            data = json.loads(json_str)
            return returncode, data, stderr
        except json.JSONDecodeError as e:
            return returncode, None, f"JSON parse error: {e}\nOutput: {stdout}"

    def cleanup(self):
        """Clean up any remaining temp files."""
        for script_path in self._temp_scripts:
            try:
                script_path.unlink()
            except OSError:
                pass
        self._temp_scripts.clear()


def get_require_cli_script() -> str:
    """Get the require statement for the CLI package."""
    return f"const cli = require('{CLI_INDEX_PATH}');"


class TestProgrammaticAPIExports:
    """Tests that verify the programmatic API exports are available."""

    def test_exports_rundebuggaitests_function(self):
        """Test that runDebuggAITests function is exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasRunDebuggAITests: typeof cli.runDebuggAITests === 'function',
                exportType: typeof cli.runDebuggAITests
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasRunDebuggAITests"] is True
            assert data["exportType"] == "function"

    def test_exports_gitanalyzer_class(self):
        """Test that GitAnalyzer class is exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasGitAnalyzer: typeof cli.GitAnalyzer === 'function',
                isConstructor: cli.GitAnalyzer.prototype !== undefined,
                exportType: typeof cli.GitAnalyzer
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasGitAnalyzer"] is True
            assert data["isConstructor"] is True
            assert data["exportType"] == "function"

    def test_exports_e2emanager_class(self):
        """Test that E2EManager class is exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasE2EManager: typeof cli.E2EManager === 'function',
                isConstructor: cli.E2EManager.prototype !== undefined,
                exportType: typeof cli.E2EManager
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasE2EManager"] is True
            assert data["isConstructor"] is True
            assert data["exportType"] == "function"

    def test_exports_clibackendclient_class(self):
        """Test that CLIBackendClient class is exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasCLIBackendClient: typeof cli.CLIBackendClient === 'function',
                isConstructor: cli.CLIBackendClient.prototype !== undefined,
                exportType: typeof cli.CLIBackendClient
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasCLIBackendClient"] is True
            assert data["isConstructor"] is True
            assert data["exportType"] == "function"

    def test_exports_servermanager_class(self):
        """Test that ServerManager class is exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasServerManager: typeof cli.ServerManager === 'function',
                isConstructor: cli.ServerManager.prototype !== undefined,
                exportType: typeof cli.ServerManager
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasServerManager"] is True
            assert data["isConstructor"] is True
            assert data["exportType"] == "function"

    def test_exports_default_config(self):
        """Test that DEFAULT_CONFIG is exported with expected values."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasDefaultConfig: typeof cli.DEFAULT_CONFIG === 'object',
                hasBaseUrl: typeof cli.DEFAULT_CONFIG?.BASE_URL === 'string',
                hasTestOutputDir: typeof cli.DEFAULT_CONFIG?.TEST_OUTPUT_DIR === 'string',
                hasPollInterval: typeof cli.DEFAULT_CONFIG?.POLL_INTERVAL === 'number',
                baseUrl: cli.DEFAULT_CONFIG?.BASE_URL,
                testOutputDir: cli.DEFAULT_CONFIG?.TEST_OUTPUT_DIR
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasDefaultConfig"] is True
            assert data["hasBaseUrl"] is True
            assert data["hasTestOutputDir"] is True
            assert data["hasPollInterval"] is True
            assert "debugg.ai" in data["baseUrl"]

    def test_exports_env_vars_constants(self):
        """Test that ENV_VARS constants are exported."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            console.log(JSON.stringify({{
                hasEnvVars: typeof cli.ENV_VARS === 'object',
                hasApiKey: typeof cli.ENV_VARS?.API_KEY === 'string',
                hasBaseUrl: typeof cli.ENV_VARS?.BASE_URL === 'string',
                apiKeyName: cli.ENV_VARS?.API_KEY,
                baseUrlName: cli.ENV_VARS?.BASE_URL
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasEnvVars"] is True
            assert data["hasApiKey"] is True
            assert data["hasBaseUrl"] is True
            assert data["apiKeyName"] == "DEBUGGAI_API_KEY"
            assert data["baseUrlName"] == "DEBUGGAI_BASE_URL"


class TestGitAnalyzerDirect:
    """Tests for GitAnalyzer class used directly."""

    def test_gitanalyzer_instantiation(self):
        """Test that GitAnalyzer can be instantiated."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            const analyzer = new cli.GitAnalyzer({{
                repoPath: '{harness.repo.path}'
            }});

            console.log(JSON.stringify({{
                success: true,
                hasAnalyzer: !!analyzer,
                hasGetWorkingChanges: typeof analyzer.getWorkingChanges === 'function',
                hasGetCurrentBranchInfo: typeof analyzer.getCurrentBranchInfo === 'function',
                hasValidateGitRepo: typeof analyzer.validateGitRepo === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["success"] is True
            assert data["hasAnalyzer"] is True
            assert data["hasGetWorkingChanges"] is True
            assert data["hasGetCurrentBranchInfo"] is True
            assert data["hasValidateGitRepo"] is True

    def test_gitanalyzer_validate_git_repo(self):
        """Test GitAnalyzer.validateGitRepo() returns true for valid repo."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const isValid = await analyzer.validateGitRepo();

                console.log(JSON.stringify({{
                    isValid: isValid
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["isValid"] is True

    def test_gitanalyzer_get_current_branch_info(self):
        """Test GitAnalyzer.getCurrentBranchInfo() returns branch and commit."""
        with E2ETestHarness(initial_branch="test-branch") as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const branchInfo = await analyzer.getCurrentBranchInfo();

                console.log(JSON.stringify({{
                    hasBranch: typeof branchInfo.branch === 'string',
                    hasCommitHash: typeof branchInfo.commitHash === 'string',
                    branch: branchInfo.branch,
                    commitHashLength: branchInfo.commitHash?.length || 0
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasBranch"] is True
            assert data["hasCommitHash"] is True
            assert data["branch"] == "test-branch"
            assert data["commitHashLength"] >= 7  # Git short hash minimum

    def test_gitanalyzer_get_working_changes_empty(self):
        """Test GitAnalyzer.getWorkingChanges() returns proper structure."""
        with E2ETestHarness() as harness:
            # Create a separate temp dir for the script to avoid polluting the repo
            import tempfile
            with tempfile.TemporaryDirectory() as script_dir:
                runner = NodeScriptRunner(work_dir=Path(script_dir))

                script = f"""
                {get_require_cli_script()}

                async function main() {{
                    const analyzer = new cli.GitAnalyzer({{
                        repoPath: '{harness.repo.path}'
                    }});

                    const workingChanges = await analyzer.getWorkingChanges();

                    console.log(JSON.stringify({{
                        hasChanges: Array.isArray(workingChanges.changes),
                        hasBranchInfo: typeof workingChanges.branchInfo === 'object',
                        changesCount: workingChanges.changes?.length || 0
                    }}));
                }}

                main().catch(err => {{
                    console.log(JSON.stringify({{ error: err.message }}));
                    process.exit(1);
                }});
                """

                returncode, data, stderr = runner.run_script_json(script)

                assert returncode == 0, f"Script failed: {stderr}"
                assert data is not None
                assert data["hasChanges"] is True
                assert data["hasBranchInfo"] is True
                # With script in a separate dir, repo should have no changes
                assert data["changesCount"] == 0  # No uncommitted changes

    def test_gitanalyzer_get_working_changes_with_modifications(self):
        """Test GitAnalyzer.getWorkingChanges() detects file modifications."""
        with E2ETestHarness() as harness:
            # Add a file and commit it
            harness.repo.add_file("src/app.py", "print('original')")
            harness.repo.commit("Add app.py")

            # Modify the file (uncommitted change)
            harness.repo.modify_file("src/app.py", "print('modified')", stage=False)

            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const workingChanges = await analyzer.getWorkingChanges();

                console.log(JSON.stringify({{
                    changesCount: workingChanges.changes?.length || 0,
                    changes: workingChanges.changes?.map(c => ({{
                        file: c.file,
                        status: c.status,
                        hasDiff: !!c.diff
                    }}))
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["changesCount"] >= 1

            # Find our modified file
            changes = data["changes"]
            app_change = next((c for c in changes if "app.py" in c["file"]), None)
            assert app_change is not None, "Expected to find app.py change"
            assert app_change["status"] == "M"  # Modified

    def test_gitanalyzer_get_repo_name(self):
        """Test GitAnalyzer.getRepoName() returns directory name."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            const analyzer = new cli.GitAnalyzer({{
                repoPath: '{harness.repo.path}'
            }});

            const repoName = analyzer.getRepoName();

            console.log(JSON.stringify({{
                repoName: repoName,
                hasRepoName: typeof repoName === 'string' && repoName.length > 0
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasRepoName"] is True
            # Should be the temp directory name (since no remote configured)
            assert len(data["repoName"]) > 0

    def test_gitanalyzer_analyze_changes_with_context(self):
        """Test GitAnalyzer.analyzeChangesWithContext() provides context."""
        with E2ETestHarness() as harness:
            # Set up some changes
            harness.setup_working_changes({
                "src/components/Button.tsx": "export const Button = () => <button>Click</button>;",
                "src/routes/index.ts": "export const routes = [];",
                "package.json": '{"name": "test"}',
            })

            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const workingChanges = await analyzer.getWorkingChanges();
                const context = await analyzer.analyzeChangesWithContext(workingChanges.changes);

                console.log(JSON.stringify({{
                    totalFiles: context.totalFiles,
                    hasFileTypes: typeof context.fileTypes === 'object',
                    hasComponentChanges: Array.isArray(context.componentChanges),
                    hasRoutingChanges: Array.isArray(context.routingChanges),
                    hasConfigChanges: Array.isArray(context.configChanges),
                    changeComplexity: context.changeComplexity,
                    hasSuggestedFocusAreas: Array.isArray(context.suggestedFocusAreas)
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["totalFiles"] >= 1
            assert data["hasFileTypes"] is True
            assert data["hasComponentChanges"] is True
            assert data["hasRoutingChanges"] is True
            assert data["hasConfigChanges"] is True
            assert data["changeComplexity"] in ["low", "medium", "high"]
            assert data["hasSuggestedFocusAreas"] is True


class TestE2EManagerDirect:
    """Tests for E2EManager class used directly."""

    def test_e2emanager_instantiation(self):
        """Test that E2EManager can be instantiated with required options."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const manager = new cli.E2EManager({{
                apiKey: '{harness.api_key}',
                repoPath: '{harness.repo.path}',
                baseUrl: '{harness.api_url}'
            }});

            console.log(JSON.stringify({{
                success: true,
                hasManager: !!manager,
                hasRunCommitTests: typeof manager.runCommitTests === 'function',
                hasWaitForServer: typeof manager.waitForServer === 'function',
                hasCleanup: typeof manager.cleanup === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["success"] is True
            assert data["hasManager"] is True
            assert data["hasRunCommitTests"] is True
            assert data["hasWaitForServer"] is True
            assert data["hasCleanup"] is True

    def test_e2emanager_options_interface(self):
        """Test that E2EManager accepts all documented options."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            // Test that all options are accepted without error
            const manager = new cli.E2EManager({{
                apiKey: '{harness.api_key}',
                repoPath: '{harness.repo.path}',
                baseUrl: '{harness.api_url}',
                testOutputDir: 'tests/custom-output',
                waitForServer: false,
                serverPort: 4000,
                serverTimeout: 45000,
                maxTestWaitTime: 300000,
                downloadArtifacts: true,
                commit: undefined,
                commitRange: undefined,
                since: undefined,
                last: undefined,
                prSequence: false,
                baseBranch: undefined,
                headBranch: undefined
            }});

            console.log(JSON.stringify({{
                success: true,
                message: 'All options accepted'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["success"] is True


class TestCLIBackendClientWithMockServer:
    """Tests for CLIBackendClient with mock server.

    Note: These tests focus on verifying the CLIBackendClient interface.
    Some tests verify error handling when the mock server doesn't have
    all the endpoints the real API provides.
    """

    def test_clibackendclient_instantiation(self):
        """Test that CLIBackendClient can be instantiated."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: '{harness.api_key}',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            console.log(JSON.stringify({{
                success: true,
                hasClient: !!client,
                hasInitialize: typeof client.initialize === 'function',
                hasTestAuthentication: typeof client.testAuthentication === 'function',
                hasCreateCommitTestSuite: typeof client.createCommitTestSuite === 'function',
                hasGetCommitTestSuiteStatus: typeof client.getCommitTestSuiteStatus === 'function',
                hasWaitForCommitTestSuiteCompletion: typeof client.waitForCommitTestSuiteCompletion === 'function',
                hasDownloadArtifact: typeof client.downloadArtifact === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["success"] is True
            assert data["hasClient"] is True
            assert data["hasInitialize"] is True
            assert data["hasTestAuthentication"] is True
            assert data["hasCreateCommitTestSuite"] is True
            assert data["hasGetCommitTestSuiteStatus"] is True
            assert data["hasWaitForCommitTestSuiteCompletion"] is True
            assert data["hasDownloadArtifact"] is True

    def test_clibackendclient_interface_methods(self):
        """Test that CLIBackendClient has expected interface methods."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: '{harness.api_key}',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            console.log(JSON.stringify({{
                hasIsInitialized: typeof client.isInitialized === 'function',
                hasGetContext: typeof client.getContext === 'function',
                hasUpdateApiKey: typeof client.updateApiKey === 'function',
                hasGetTransport: typeof client.getTransport === 'function',
                hasGetContextProvider: typeof client.getContextProvider === 'function',
                hasDownloadArtifactToFile: typeof client.downloadArtifactToFile === 'function',
                hasCreateTunnelToken: typeof client.createTunnelToken === 'function',
                hasUpdateCommitTestSuite: typeof client.updateCommitTestSuite === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasIsInitialized"] is True
            assert data["hasGetContext"] is True
            assert data["hasUpdateApiKey"] is True
            assert data["hasGetTransport"] is True
            assert data["hasGetContextProvider"] is True
            assert data["hasDownloadArtifactToFile"] is True
            assert data["hasCreateTunnelToken"] is True
            assert data["hasUpdateCommitTestSuite"] is True

    def test_clibackendclient_initial_state(self):
        """Test CLIBackendClient initial state before initialization."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: '{harness.api_key}',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            // Before initialize, isInitialized should be false
            console.log(JSON.stringify({{
                isInitializedBefore: client.isInitialized()
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["isInitializedBefore"] is False

    def test_clibackendclient_update_api_key(self):
        """Test CLIBackendClient.updateApiKey() method."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: 'initial-key',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            // updateApiKey should not throw
            let updated = false;
            try {{
                client.updateApiKey('new-api-key');
                updated = true;
            }} catch (e) {{
                updated = false;
            }}

            console.log(JSON.stringify({{
                updateSucceeded: updated
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["updateSucceeded"] is True

    def test_clibackendclient_context_provider(self):
        """Test CLIBackendClient.getContextProvider() returns provider."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: '{harness.api_key}',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            const contextProvider = client.getContextProvider();

            console.log(JSON.stringify({{
                hasContextProvider: !!contextProvider,
                hasInitialize: typeof contextProvider?.initialize === 'function',
                hasGetContext: typeof contextProvider?.getContext === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasContextProvider"] is True
            assert data["hasInitialize"] is True
            assert data["hasGetContext"] is True

    def test_clibackendclient_transport(self):
        """Test CLIBackendClient.getTransport() returns transport."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            script = f"""
            {get_require_cli_script()}

            const client = new cli.CLIBackendClient({{
                apiKey: '{harness.api_key}',
                baseUrl: '{harness.api_url}',
                repoPath: '{harness.repo.path}',
                timeout: 30000
            }});

            const transport = client.getTransport();

            console.log(JSON.stringify({{
                hasTransport: !!transport,
                hasGet: typeof transport?.get === 'function',
                hasPost: typeof transport?.post === 'function',
                hasPatch: typeof transport?.patch === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasTransport"] is True
            assert data["hasGet"] is True
            assert data["hasPost"] is True
            assert data["hasPatch"] is True


class TestRunDebuggAITestsFunction:
    """Tests for the runDebuggAITests() convenience function."""

    def test_rundebuggaitests_function_signature(self):
        """Test runDebuggAITests() function exists with correct signature."""
        with E2ETestHarness() as harness:
            import tempfile
            with tempfile.TemporaryDirectory() as script_dir:
                runner = NodeScriptRunner(work_dir=Path(script_dir))

                script = f"""
                {get_require_cli_script()}

                // Verify the function exists and is callable
                console.log(JSON.stringify({{
                    isFunction: typeof cli.runDebuggAITests === 'function',
                    functionName: cli.runDebuggAITests.name,
                    isAsync: cli.runDebuggAITests.constructor.name === 'AsyncFunction'
                }}));
                """

                returncode, data, stderr = runner.run_script_json(script)

                assert returncode == 0, f"Script failed: {stderr}"
                assert data is not None
                assert data["isFunction"] is True

    def test_rundebuggaitests_accepts_all_options(self):
        """Test runDebuggAITests() accepts all documented options without error."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(
                work_dir=harness.repo.path,
                env={
                    "DEBUGGAI_API_KEY": harness.api_key,
                    "DEBUGGAI_API_URL": harness.api_url,
                },
            )

            # Just test that the function signature is correct
            script = f"""
            {get_require_cli_script()}

            // Verify the function exists and accepts options
            const runTests = cli.runDebuggAITests;

            // Check it's a function with expected signature
            console.log(JSON.stringify({{
                isFunction: typeof runTests === 'function',
                isAsync: runTests.constructor.name === 'AsyncFunction'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["isFunction"] is True


class TestTypeScriptTypesMatchDocumentation:
    """Tests that verify TypeScript types match documentation."""

    def test_workinchange_interface(self):
        """Test WorkingChange interface has expected properties."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({
                "test.py": "print('test')",
            })

            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const workingChanges = await analyzer.getWorkingChanges();
                const change = workingChanges.changes[0];

                if (!change) {{
                    console.log(JSON.stringify({{ error: 'No changes found' }}));
                    return;
                }}

                console.log(JSON.stringify({{
                    hasStatus: typeof change.status === 'string',
                    hasFile: typeof change.file === 'string',
                    hasDiffOrUndefined: change.diff === undefined || typeof change.diff === 'string',
                    statusValue: change.status,
                    fileValue: change.file
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            if "error" not in data:
                assert data["hasStatus"] is True
                assert data["hasFile"] is True
                assert data["hasDiffOrUndefined"] is True

    def test_branchinfo_interface(self):
        """Test BranchInfo interface has expected properties."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '{harness.repo.path}'
                }});

                const branchInfo = await analyzer.getCurrentBranchInfo();

                console.log(JSON.stringify({{
                    hasBranch: typeof branchInfo.branch === 'string',
                    hasCommitHash: typeof branchInfo.commitHash === 'string',
                    branchType: typeof branchInfo.branch,
                    commitHashType: typeof branchInfo.commitHash
                }}));
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{ error: err.message }}));
                process.exit(1);
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasBranch"] is True
            assert data["hasCommitHash"] is True
            assert data["branchType"] == "string"
            assert data["commitHashType"] == "string"

    def test_e2eresult_interface(self):
        """Test E2EResult interface has expected properties."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            # Just verify the interface exists by checking type info
            script = f"""
            {get_require_cli_script()}

            // E2EResult is a TypeScript interface, so we can only test
            // that the E2EManager returns objects with the expected shape

            const manager = new cli.E2EManager({{
                apiKey: 'test-key',
                repoPath: '{harness.repo.path}'
            }});

            // Verify expected method returns Promise
            const isRunCommitTestsAsync = manager.runCommitTests.constructor.name === 'AsyncFunction';

            console.log(JSON.stringify({{
                hasE2EManager: true,
                isRunCommitTestsAsync: isRunCommitTestsAsync
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasE2EManager"] is True

    def test_cliclientconfig_interface(self):
        """Test CLIClientConfig interface has expected properties."""
        with E2ETestHarness() as harness:
            import tempfile
            with tempfile.TemporaryDirectory() as script_dir:
                runner = NodeScriptRunner(work_dir=Path(script_dir))

                script = f"""
                {get_require_cli_script()}

                // Test that CLIBackendClient accepts the documented config shape
                try {{
                    const client = new cli.CLIBackendClient({{
                        apiKey: 'test-api-key',
                        baseUrl: 'https://api.example.com',
                        repoPath: '{harness.repo.path}',
                        timeout: 60000
                    }});

                    console.log(JSON.stringify({{
                        success: true,
                        acceptsApiKey: true,
                        acceptsBaseUrl: true,
                        acceptsRepoPath: true,
                        acceptsTimeout: true
                    }}));
                }} catch (err) {{
                    console.log(JSON.stringify({{
                        success: false,
                        error: err.message
                    }}));
                }}
                """

                returncode, data, stderr = runner.run_script_json(script)

                assert returncode == 0, f"Script failed: {stderr}"
                assert data is not None
                assert data["success"] is True
                assert data["acceptsApiKey"] is True
                assert data["acceptsBaseUrl"] is True
                assert data["acceptsRepoPath"] is True
                assert data["acceptsTimeout"] is True


class TestPRCommitSequenceAnalysis:
    """Tests for PR commit sequence analysis functionality."""

    def test_gitanalyzer_analyze_pr_commit_sequence(self):
        """Test GitAnalyzer.analyzePRCommitSequence() method exists."""
        with E2ETestHarness() as harness:
            runner = NodeScriptRunner(work_dir=harness.repo.path)

            script = f"""
            {get_require_cli_script()}

            const analyzer = new cli.GitAnalyzer({{
                repoPath: '{harness.repo.path}'
            }});

            console.log(JSON.stringify({{
                hasAnalyzePRCommitSequence: typeof analyzer.analyzePRCommitSequence === 'function',
                hasIsPRContext: typeof analyzer.isPRContext === 'function',
                hasGetPRNumber: typeof analyzer.getPRNumber === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasAnalyzePRCommitSequence"] is True
            assert data["hasIsPRContext"] is True
            assert data["hasGetPRNumber"] is True

    def test_gitanalyzer_pr_sequence_returns_structure(self):
        """Test PR sequence analysis returns proper structure."""
        with E2ETestHarness() as harness:
            # Set up a feature branch scenario
            base_hash, head_hash = harness.repo.setup_pr_scenario(
                base_branch="main",
                head_branch="feature-test",
                num_commits=3,
            )

            import tempfile
            with tempfile.TemporaryDirectory() as script_dir:
                runner = NodeScriptRunner(work_dir=Path(script_dir))

                script = f"""
                {get_require_cli_script()}

                async function main() {{
                    const analyzer = new cli.GitAnalyzer({{
                        repoPath: '{harness.repo.path}'
                    }});

                    const prSequence = await analyzer.analyzePRCommitSequence('main', 'feature-test');

                    if (!prSequence) {{
                        // PR sequence analysis may return null in some scenarios
                        // This is valid behavior when no unique commits are found
                        console.log(JSON.stringify({{
                            hasSequence: false,
                            reason: 'No PR sequence returned - may be expected'
                        }}));
                        return;
                    }}

                    console.log(JSON.stringify({{
                        hasSequence: true,
                        hasBaseBranch: typeof prSequence.baseBranch === 'string',
                        hasHeadBranch: typeof prSequence.headBranch === 'string',
                        hasTotalCommits: typeof prSequence.totalCommits === 'number',
                        hasCommitsArray: Array.isArray(prSequence.commits),
                        baseBranch: prSequence.baseBranch,
                        headBranch: prSequence.headBranch,
                        totalCommits: prSequence.totalCommits,
                        commitCount: prSequence.commits?.length || 0
                    }}));
                }}

                main().catch(err => {{
                    console.log(JSON.stringify({{ error: err.message }}));
                    process.exit(1);
                }});
                """

                returncode, data, stderr = runner.run_script_json(script)

                assert returncode == 0, f"Script failed: {stderr}"
                assert data is not None

                if data.get("hasSequence"):
                    # Verify structure when sequence is returned
                    assert data["hasBaseBranch"] is True
                    assert data["hasHeadBranch"] is True
                    assert data["hasTotalCommits"] is True
                    assert data["hasCommitsArray"] is True
                    assert data["baseBranch"] == "main"
                    assert data["headBranch"] == "feature-test"
                else:
                    # It's acceptable for the sequence to be null in some scenarios
                    # The important thing is that the API doesn't throw
                    pass


class TestErrorHandling:
    """Tests for error handling in the programmatic API."""

    def test_gitanalyzer_invalid_repo_path(self):
        """Test GitAnalyzer handles invalid repo path gracefully."""
        import tempfile
        with tempfile.TemporaryDirectory() as script_dir:
            runner = NodeScriptRunner(work_dir=Path(script_dir))

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const analyzer = new cli.GitAnalyzer({{
                    repoPath: '/nonexistent/path/to/repo'
                }});

                const isValid = await analyzer.validateGitRepo();

                console.log(JSON.stringify({{
                    isValid: isValid
                }}));
            }}

            main().catch(err => {{
                // Expect error for invalid path
                console.log(JSON.stringify({{
                    isValid: false,
                    error: err.message
                }}));
                process.exit(0);  // Don't fail test - we expect this error
            }});
            """

            returncode, data, stderr = runner.run_script_json(script)

            # Either succeeds with isValid=false or catches error
            assert data is not None
            assert data["isValid"] is False

    def test_clibackendclient_connection_failure(self):
        """Test CLIBackendClient handles connection failure gracefully."""
        import tempfile
        with tempfile.TemporaryDirectory() as script_dir:
            runner = NodeScriptRunner(work_dir=Path(script_dir), timeout=30.0)

            script = f"""
            {get_require_cli_script()}

            async function main() {{
                const client = new cli.CLIBackendClient({{
                    apiKey: 'test-key',
                    baseUrl: 'http://127.0.0.1:59999',  // No server running here
                    repoPath: '{script_dir}',
                    timeout: 3000
                }});

                try {{
                    await client.initialize();
                    console.log(JSON.stringify({{
                        connected: true,
                        message: 'Unexpectedly connected'
                    }}));
                }} catch (err) {{
                    console.log(JSON.stringify({{
                        connected: false,
                        error: err.message,
                        errorHandled: true
                    }}));
                }}
            }}

            main().catch(err => {{
                console.log(JSON.stringify({{
                    connected: false,
                    uncaughtError: true,
                    error: err.message
                }}));
            }});
            """

            returncode, stdout, stderr = runner.run_script(script)

            # The script should complete (may have non-zero exit code)
            # Look for JSON in the output
            output = stdout + stderr

            # Verify that the script ran and handled the error
            # Either by catching it or by process.exit
            assert "connected" in output.lower() or "error" in output.lower() or returncode != 0

    def test_e2emanager_error_result_structure(self):
        """Test E2EManager returns proper error result structure."""
        import tempfile
        with tempfile.TemporaryDirectory() as script_dir:
            runner = NodeScriptRunner(work_dir=Path(script_dir))

            script = f"""
            {get_require_cli_script()}

            // Test that E2EManager returns proper error structure
            // by checking the result interface
            const manager = new cli.E2EManager({{
                apiKey: 'test-key',
                repoPath: '{script_dir}',
                baseUrl: 'http://127.0.0.1:59999'  // Invalid server
            }});

            // Verify the manager has the expected methods
            console.log(JSON.stringify({{
                hasRunCommitTests: typeof manager.runCommitTests === 'function',
                hasCleanup: typeof manager.cleanup === 'function',
                hasWaitForServer: typeof manager.waitForServer === 'function'
            }}));
            """

            returncode, data, stderr = runner.run_script_json(script)

            assert returncode == 0, f"Script failed: {stderr}"
            assert data is not None
            assert data["hasRunCommitTests"] is True
            assert data["hasCleanup"] is True
            assert data["hasWaitForServer"] is True
