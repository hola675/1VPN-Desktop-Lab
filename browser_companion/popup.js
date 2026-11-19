/* Consent-only account handoff. Never read cookies or other extensions' storage.
 * The website's API must provide the session explicitly under its own origin.
 * If it does not, this bridge fails closed (no extraction, spoofing or bypass).
 */
const form = document.querySelector('#pair');
const message = document.querySelector('#message');
const button = document.querySelector('#send');

function setMessage(text) {
  message.textContent = text;
}

async function fetchFromSignedInPage() {
  // Execute on the actual first-party account page, NOT in extension-origin
  // background. No auth secret is passed INTO the page.
  const response = await fetch('/api/get_user_data_web/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    cache: 'no-store',
    body: '{}',
  });
  if (!response.ok) return { ok: false, status: response.status };
  const raw = await response.text();
  if (raw.length > 30000) return { ok: false, status: 0 };
  let data;
  try { data = JSON.parse(raw); } catch (_) { return { ok: false, status: 0 }; }
  if (!data || data.isPremium !== true || !data.username ||
      !data.sessionAuthToken || !data.locations) {
    return { ok: false, status: 0 };
  }
  // Only these official account fields are transferred, no browser cookies.
  return {
    ok: true,
    data: {
      username: data.username,
      sessionAuthToken: data.sessionAuthToken,
      isPremium: data.isPremium,
      email: data.email,
      locations: data.locations,
    },
  };
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  setMessage('Consultando sesión Premium en la página oficial…');
  const port = Number(document.querySelector('#port').value);
  const code = document.querySelector('#code').value.trim();
  if (!Number.isInteger(port) || port < 1 || port > 65535 ||
      !/^[A-Za-z0-9_-]{20,80}$/.test(code)) {
    setMessage('Puerto o código temporal incorrecto.');
    button.disabled = false;
    return;
  }
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id || !/^https:\/\/1vpn\.org\/account\/?(?:[?#].*)?$/.test(tab.url || '')) {
      setMessage('Abre primero la pestaña oficial https://1vpn.org/account/ e inicia sesión.');
      return;
    }
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: 'MAIN',
      func: fetchFromSignedInPage,
    });
    const account = result?.result;
    if (!account?.ok) {
      setMessage('La página oficial no entregó una sesión Premium transferible.' +
        (account?.status ? ' HTTP ' + account.status + '.' : '') +
        '\nNo es un problema confirmado de contraseña: esta API web puede exigir una integración oficial.');
      return;
    }
    const reply = await fetch('http://127.0.0.1:' + port + '/premium-session', {
      method: 'POST',
      mode: 'cors',
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-OneTunnel-Pairing': code,
      },
      body: JSON.stringify(account.data),
    });
    if (!reply.ok) {
      setMessage('OneTunnel rechazó el emparejamiento (' + reply.status +
        '). Comprueba puerto, código y que no haya caducado.');
      return;
    }
    document.querySelector('#code').value = '';
    setMessage('Datos Premium recibidos en OneTunnel. Ahora verifica salida HTTPS por el proxy.');
  } catch (_) {
    setMessage('No se completó la vinculación. Verifica la pestaña oficial, el permiso de la extensión y el puerto local.');
  } finally {
    button.disabled = false;
  }
});
