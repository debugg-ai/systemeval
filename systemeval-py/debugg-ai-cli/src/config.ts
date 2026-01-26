import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs-extra';

export interface DebuggAiCliConfig {
  token?: string;
  tokenType?: 'token' | 'bearer';
  baseUrl?: string;
}

const CONFIG_FILE_NAME = '.debuggai-config.json';

export function getConfigFilePath(): string {
  return path.join(os.homedir(), CONFIG_FILE_NAME);
}

export async function loadCliConfig(): Promise<DebuggAiCliConfig> {
  const configPath = getConfigFilePath();
  try {
    if (!(await fs.pathExists(configPath))) {
      return {};
    }
    return (await fs.readJson(configPath)) as DebuggAiCliConfig;
  } catch (error) {
    return {};
  }
}

export async function saveCliConfig(config: DebuggAiCliConfig): Promise<void> {
  const configPath = getConfigFilePath();
  await fs.outputJson(configPath, config, { spaces: 2 });
}
