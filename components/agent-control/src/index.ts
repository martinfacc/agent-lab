import { McpServer } from '@modelcontextprotocol/server';
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { loadConfig } from './config.ts';
import { registerDevelopmentTools } from './development/tools.ts';
import { registerResearchTools } from './research/tools.ts';
import { asText } from './shared/mcp.ts';
import { packageVersion } from './version.ts';

export function createServer(): McpServer {
  const config = loadConfig();
  const server = new McpServer({
    name: 'agent-control',
    version: packageVersion,
  });

  server.registerTool(
    'ping',
    {
      description: 'Comprueba que el servidor MCP de agent-control esté disponible.',
    },
    () => asText({ status: 'ok', version: packageVersion }),
  );

  registerDevelopmentTools(server, config.development, asText);
  if (config.researchEnabled) {
    registerResearchTools(server, config.research, asText);
  }
  return server;
}

void serveStdio(createServer);
console.error(`autonomous-agent-lab-control v${packageVersion} ejecutándose por stdio`);
