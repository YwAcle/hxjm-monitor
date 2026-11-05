// Vite's CLI writes a temporary ESM config beside the source. Import it directly
// so an arbitrary developer UID can run the immutable release image.
import { build, preview } from '/app/frontend/node_modules/vite/dist/node/index.js';
import config from '/app/frontend/vite.config.js';

const common = { ...config, configFile: false, root: '/app/frontend',
  cacheDir: '/tmp/hxjm-vite', build: { ...config.build, outDir: '/tmp/hxjm-dist' } };
// Browser flags are set by deployment configuration, so compile them at startup.
// Output stays in the container's private writable layer, never the source tree.
await build(common);
await preview({ ...common, preview: { host: '0.0.0.0',
  port: Number(process.env.APP_HTTP_PORT || 3000), strictPort: true,
  proxy: config.server.proxy } });
console.log(`HXJM frontend revision=${process.env.HXJM_REVISION || 'unknown'}`);
