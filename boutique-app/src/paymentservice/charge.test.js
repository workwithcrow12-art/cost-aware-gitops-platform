const assert = require('node:assert/strict');
const { test } = require('node:test');
const charge = require('./charge');
const HipsterShopServer = require('./server');
const logger = require('./logger');

function request(number = '4111111111111111', year = new Date().getFullYear() + 1) {
  return {
    amount: { currency_code: 'USD', units: '25', nanos: 500000000 },
    credit_card: {
      credit_card_number: number,
      credit_card_expiration_month: 12,
      credit_card_expiration_year: year,
      credit_card_cvv: 123
    }
  };
}

for (const [type, number] of [['Visa', '4111111111111111'], ['MasterCard', '5555555555554444']]) {
  test(`accepts a valid ${type} and returns a transaction ID`, () => {
    assert.match(charge(request(number)).transaction_id,
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  });
}

test('rejects an invalid card number', () => {
  assert.throws(() => charge(request('4111111111111112')), /invalid/);
});

test('rejects an expired card', () => {
  assert.throws(() => charge(request('4111111111111111', new Date().getFullYear() - 1)), /expired/);
});

test('rejects a valid but unsupported card type', () => {
  assert.throws(() => charge(request('378282246310005')), /Only VISA or MasterCard/);
});

test('charge handler does not log the card number or CVV', (t) => {
  const messages = [];
  t.mock.method(logger, 'info', (...args) => messages.push(args));
  const payment = request();
  let completed = false;
  HipsterShopServer.ChargeServiceHandler({ request: payment }, (error, response) => {
    assert.equal(error, null);
    assert.ok(response.transaction_id);
    completed = true;
  });
  assert.ok(completed);
  const output = JSON.stringify(messages);
  assert.ok(!output.includes(payment.credit_card.credit_card_number));
  assert.ok(!output.includes(String(payment.credit_card.credit_card_cvv)));
});

test('constructs the supported OTLP gRPC trace exporter', async () => {
  const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');
  const exporter = new OTLPTraceExporter({ url: 'http://127.0.0.1:4317' });
  assert.equal(typeof exporter.export, 'function');
  await exporter.shutdown();
});
