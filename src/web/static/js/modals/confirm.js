import { S } from '../state.js';
import { openModal } from '../ui.js';
import { $ } from '../utils.js';

export function openConfirmDialog(title, msg, okLabel, cb) {
  $('#mcfTitle').textContent = title; $('#mcfMsg').textContent = msg; $('#mcfOk').textContent = okLabel;
  S.confirmCb = cb;
  openModal('confirmDialog', { focus: '[data-close]' });
}
