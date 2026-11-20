import { T } from '../i18n.js';
import { S } from '../state.js';
import { openModal } from '../ui.js';
import { $ } from '../utils.js';

/* opts.cancelLabel: text of the left button (default Cancel); opts.noCancel: only the OK button;
   opts.primary: blue OK button (for a notice), otherwise red (for a delete or discard). */
export function openConfirmDialog(title, msg, okLabel, cb, opts) {
  opts = opts || {};
  $('#mcfTitle').textContent = title; $('#mcfMsg').textContent = msg; $('#mcfOk').textContent = okLabel;
  const cancel = $('#confirmDialog [data-close]');
  cancel.textContent = opts.cancelLabel || T('common.cancel'); cancel.hidden = !!opts.noCancel;
  $('#mcfOk').className = 'btn ' + (opts.primary ? 'btn-primary' : 'btn-record');
  S.confirmCb = cb;
  openModal('confirmDialog', { focus: opts.noCancel ? '#mcfOk' : '[data-close]' });
}
