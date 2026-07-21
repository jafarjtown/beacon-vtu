/**
 * Registers the service worker and drives the "Install Beacon" banner.
 *
 * Two install paths, because there's no single API that covers both:
 *  - Chrome/Edge/Android: the browser fires `beforeinstallprompt`, which
 *    we capture and replay later when the person taps our own button
 *    (browsers suppress their native mini-infobar once you've called
 *    preventDefault() on this event, so a custom banner is expected).
 *  - iOS Safari: there is no install-prompt API at all. The only way to
 *    install is the manual Share -> Add to Home Screen flow, so on iOS
 *    we show instructions instead of a button.
 *
 * Dismissal is remembered in localStorage so the banner doesn't nag on
 * every visit — this is a real Django-served static file (not a
 * sandboxed artifact), so localStorage is the right tool here.
 */
(function () {
  const DISMISS_KEY = 'beacon_install_dismissed_at';
  const DISMISS_COOLDOWN_DAYS = 14;

  // ---------- Service worker ----------
  // Registered from the site root, not /static/ — a service worker's
  // scope defaults to the path it's served from, so registering it from
  // under /static/ would silently limit it to only ever seeing requests
  // under /static/*, and the offline fallback would never trigger for
  // an actual page. See pwa_views.py for the view that serves this.
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch((err) => {
        console.warn('Beacon: service worker registration failed', err);
      });
    });
  }

  // ---------- Install banner ----------
  const banner = document.getElementById('installBanner');
  if (!banner) return; // partial not included on this page

  const installBtn = document.getElementById('installBannerBtn');
  const dismissBtn = document.getElementById('installBannerDismiss');
  const bodyText = document.getElementById('installBannerText');

  function recentlyDismissed() {
    const raw = localStorage.getItem(DISMISS_KEY);
    if (!raw) return false;
    const elapsedDays = (Date.now() - parseInt(raw, 10)) / (1000 * 60 * 60 * 24);
    return elapsedDays < DISMISS_COOLDOWN_DAYS;
  }

  function isStandalone() {
    return (
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true // iOS Safari's own flag
    );
  }

  function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
  }

  if (isStandalone() || recentlyDismissed()) return;

  let deferredPrompt = null;

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    showBanner();
  });

  if (isIOS()) {
    bodyText.textContent = 'Install Beacon: tap the Share icon, then "Add to Home Screen".';
    installBtn.style.display = 'none';
    showBanner();
  }

  function showBanner() {
    banner.hidden = false;
  }

  function hideBanner() {
    banner.hidden = true;
  }

  installBtn.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
    hideBanner();
  });

  dismissBtn.addEventListener('click', () => {
    localStorage.setItem(DISMISS_KEY, String(Date.now()));
    hideBanner();
  });
})();
