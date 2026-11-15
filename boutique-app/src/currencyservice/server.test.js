const assert = require('node:assert/strict');
const { after, before, test } = require('node:test');
const { spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const { promisify } = require('node:util');
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');

let child;
let client;
after(() => {
  if (client) client.close();
  if (child) child.kill();
});

before(async () => {
  const reservation = net.createServer();
  await new Promise((resolve, reject) => {
    reservation.once('error', reject);
    reservation.listen(0, '127.0.0.1', resolve);
  });
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));
  child = spawn(process.execPath, ['server.js'], {
    cwd: __dirname,
    env: { ...process.env, PORT: String(port), DISABLE_PROFILER: '1', ENABLE_TRACING: '0' },
    stdio: ['ignore', 'ignore', 'pipe']
  });
  let errors = '';
  child.stderr.on('data', data => { errors += data; });
  const definition = protoLoader.loadSync(path.join(__dirname, 'proto/demo.proto'), {
    keepCase: true, longs: String, enums: String, defaults: true, oneofs: true
  });
  const api = grpc.loadPackageDefinition(definition).hipstershop;
  client = new api.CurrencyService(`127.0.0.1:${port}`, grpc.credentials.createInsecure());
  try {
    await promisify(client.waitForReady.bind(client))(Date.now() + 15000);
  } catch (error) {
    throw new Error(`Currency service failed to start: ${errors}`, { cause: error });
  }
}, { timeout: 20000 });

test('lists currencies served by the running gRPC service', async () => {
  const result = await promisify(client.getSupportedCurrencies.bind(client))({});
  assert.ok(result.currency_codes.includes('USD'));
  assert.ok(result.currency_codes.includes('EUR'));
});

test('preserves fractional amounts when converting to the same currency', async () => {
  const result = await promisify(client.convert.bind(client))({
    from: { currency_code: 'USD', units: '10', nanos: 250000000 }, to_code: 'USD'
  });
  assert.equal(result.currency_code, 'USD');
  assert.equal(result.units, '10');
  assert.ok(Math.abs(result.nanos - 250000000) <= 1);
});

test('converts EUR to USD using the published rate', async () => {
  const result = await promisify(client.convert.bind(client))({
    from: { currency_code: 'EUR', units: '1', nanos: 0 }, to_code: 'USD'
  });
  assert.equal(result.currency_code, 'USD');
  const rate = require('./data/currency_conversion.json').USD;
  assert.ok(Math.abs(Number(result.units) + result.nanos / 1e9 - rate) < 1e-8);
});

test('constructs the supported OTLP gRPC trace exporter', async () => {
  const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');
  const exporter = new OTLPTraceExporter({ url: 'http://127.0.0.1:4317' });
  assert.equal(typeof exporter.export, 'function');
  await exporter.shutdown();
});
