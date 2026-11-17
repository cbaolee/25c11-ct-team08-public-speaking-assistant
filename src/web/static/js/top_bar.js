import { isDropOpen, slideDown, slideUp } from './ui.js';
import { $ } from './utils.js';

/* ---------- user menu: opens on hover or click, a second click rolls it back up ---------- */
export let menuLeaveTimer = 0;
export function closeUserMenu(focusBtn) {
  const m = $('#userMenu');
  if (!m) return;
  clearTimeout(menuLeaveTimer);
  if (isDropOpen(m)) slideUp(m);
  $('#userBtn').setAttribute('aria-expanded', 'false');
  if (focusBtn) $('#userBtn').focus();
}
export function openUserMenu(focusFirst) {
  const m = $('#userMenu');
  clearTimeout(menuLeaveTimer);
  if (!isDropOpen(m)) slideDown(m);
  $('#userBtn').setAttribute('aria-expanded', 'true');
  if (focusFirst) $('[role=menuitem]', m).focus();
}
export function toggleUserMenu() {
  const m = $('#userMenu');
  // a click right after the hover opened it means "open", not "close"
  if (isDropOpen(m) && Date.now() - (m._hoverAt || 0) > 600) closeUserMenu(true);
  else openUserMenu(true);
}
export function setupUserMenuHover() {
  const acct = $('#userMenuButton'), m = $('#userMenu');
  if (!acct || !matchMedia('(hover: hover)').matches) return;
  acct.addEventListener('mouseenter', () => {
    if ($('#userBtn').hidden) return;
    clearTimeout(menuLeaveTimer);
    if (!isDropOpen(m)) { m._hoverAt = Date.now(); openUserMenu(false); }
  });
  acct.addEventListener('mouseleave', () => {
    clearTimeout(menuLeaveTimer);
    menuLeaveTimer = setTimeout(() => { if (!m.contains(document.activeElement)) closeUserMenu(); }, 280);
  });
}
