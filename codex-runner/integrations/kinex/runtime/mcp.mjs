// Use authentic Kinex MCP/core with a bounded catalog for this public playground.
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const source = process.env.KINEX_SOURCE;
const require = createRequire(path.join(source, 'package.json'));
const {createKinexMcpServer} = await import(pathToFileURL(path.join(source, 'packages/mcp/dist/index.js')));
const {coreContribution} = await import(pathToFileURL(path.join(source,'node_modules/@kinex/core/dist/integration.js')));
const {StdioServerTransport} = await import(pathToFileURL(path.join(source,'node_modules/@modelcontextprotocol/sdk/dist/esm/server/stdio.js')));
const allowed = new Set(['device', 'devices', 'device_stop', 'servo']);
const adapter = await createKinexMcpServer({directory: process.cwd(), permissionMode: 'host',
  diagnostic: message => process.stderr.write(message + '\n'),
  composition: {contributions(runtime) {
    const core = coreContribution(runtime);
    return [{...core, commands: core.commands.filter(c => ['devices','load','unload','ping','stop'].includes(c.name)),
      tools: {
        async list() { const catalog = await core.tools.list(); return {...catalog, tools: catalog.tools.filter(t => allowed.has(t.name))}; },
        async call(name, input, invocation) {
          if (!allowed.has(name)) throw new Error('This public joint-control integration does not expose ' + name);
          return core.tools.call(name, input, invocation);
        }
      }}];
  }}
});
await adapter.connect(new StdioServerTransport());
for (const signal of ['SIGINT','SIGTERM']) process.on(signal, () => { void adapter.dispose().finally(() => process.exit()); });
