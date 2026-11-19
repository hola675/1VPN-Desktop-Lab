/* URL gate for the user-triggered 1VPN browser-account pairing flow.
 * Accept the exact official account page (including the site's locale prefix).
 * Reject lookalike domains, unrelated paths, HTTP and URL credentials.
 * No authentication or session material is accessed here.
 */
function isOfficial1VpnAccountUrl(candidate) {
  if (typeof candidate !== 'string') return false;
  let url;
  try {
    url = new URL(candidate);
  } catch (_) {
    return false;
  }
  if (url.protocol !== 'https:' || url.hostname !== '1vpn.org' ||
      url.port || url.username || url.password) {
    return false;
  }
  // 1vpn.org may localize its account page as /es/account/,
  // /pt-br/account/, /es-419/account/, etc.; allow no other page.
  return /^\/(?:[a-z]{2}(?:-(?:[a-z]{2}|[0-9]{3}))?\/)?account\/?$/i
    .test(url.pathname);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { isOfficial1VpnAccountUrl };
}
