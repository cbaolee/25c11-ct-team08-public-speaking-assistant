import { go } from './nav.js';
import { isDropOpen, slideDown, slideUp } from './ui.js';
import { $ } from './utils.js';

/* ---------- user menu ----------
   With a mouse: hovering opens the menu, clicking the avatar or name goes to Profile.
   On touch screens (no hover) a tap opens and closes the menu, which also lists Profile.
   Keyboard: Enter goes to Profile, Arrow Down opens the menu. */
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
export function onUserButtonClick() {
  if (matchMedia('(hover: hover)').matches) { closeUserMenu(); go('profile'); }
  else toggleUserMenu();
}
export function setupUserMenuHover() {
  $('#userBtn').addEventListener('keydown', e => { if (e.key === 'ArrowDown') { e.preventDefault(); openUserMenu(true); } });
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
