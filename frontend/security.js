function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function safeApiBase(value) {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.href);
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin || url.username || url.password || url.search || url.hash) return null;
    return url.href.replace(/\/$/, '');
  } catch {
    return null;
  }
}

function safeLocalRedirect(value) {
  if (!value || !value.startsWith('/')) return 'index.html';
  try {
    const url = new URL(value, window.location.href);
    return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : 'index.html';
  } catch {
    return 'index.html';
  }
}