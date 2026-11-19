const test = require('node:test');
const assert = require('node:assert/strict');
const { isOfficial1VpnAccountUrl } = require('../account_url.js');

test('recognizes the account page in Spanish and other supported locales', () => {
  for (const url of [
    'https://1vpn.org/account/',
    'https://1vpn.org/account',
    'https://1vpn.org/es/account/',
    'https://1vpn.org/en/account/',
    'https://1vpn.org/pt-br/account/',
    'https://1vpn.org/es-419/account/',
    'https://1vpn.org/es/account/?utm_source=account',
    'https://1vpn.org/es/account/#settings',
  ]) {
    assert.equal(isOfficial1VpnAccountUrl(url), true, url);
  }
});

test('fails closed for unrelated sites, unsafe schemes and pages', () => {
  for (const url of [
    'http://1vpn.org/es/account/',
    'https://evil.example/es/account/',
    'https://1vpn.org.evil.example/es/account/',
    'https://account.1vpn.org/es/account/',
    'https://1vpn.org/evil/account/',
    'https://1vpn.org/es/login/',
    'https://1vpn.org/es/account/other',
    'https://1vpn.org/es/account/../login/',
    'https://1vpn.org:444/es/account/',
    'https://user:secret@1vpn.org/es/account/',
    'https://1vpn.org@evil.example/es/account/',
    'https://1vpn.org/es/other/account/',
    'javascript:alert(1)',
    '/es/account/',
    '',
    null,
    undefined,
  ]) {
    assert.equal(isOfficial1VpnAccountUrl(url), false, String(url));
  }
});
