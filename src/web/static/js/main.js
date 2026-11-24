import './state.js';
import './i18n.js';
import './data.js';
import './charts.js';
import './utils.js';
import './ui.js';
import './modals/confirm.js';
import './nav.js';
import './screens/landing.js';
import './top_bar.js';
import './api.js';
import './modals/auth_panel.js';
import './modals/baseline_gate.js';
import './screens/home.js';
import { scrollHomeDown } from './screens/home.js';
import './screens/history.js';
import './screens/script_studio.js';
import './recorder.js';
import './screens/practice.js';
import './screens/report.js';
import './screens/profile.js';
import './modals/profile_modal.js';
import './modals/settings_modal.js';
import { api, dropOldStoredTokens, refreshAuth } from './api.js';
import { T, TOPICS, applyText } from './i18n.js';
import { onAuthSubmit, openAuth, setAuthMode, showAppLoader, startSession, updateSignupButton } from './modals/auth_panel.js';
import { openResetStep } from './modals/reset_panel.js';
import { logout, onGateAgree, onGatePause } from './modals/baseline_gate.js';
import { openConfirmDialog } from './modals/confirm.js';
import { openProfileModal, saveConsent, saveProfileModal } from './modals/profile_modal.js';
import { openSettings, setupSettings } from './modals/settings_modal.js';
import { go, moveNavPill, moveSegPills, paintAvatar, renderAccount, showView, syncHeader, syncScrollThumb } from './nav.js';
import { deleteSession, openReport } from './screens/history.js';
import { kickFollow, setStageAuth, syncHero, syncStage } from './screens/landing.js';
import { cancelEval, togglePause, onSheetClick, cancelMineEdit, goStep, loadFollowWpm, onAudioFile, onFollowWpm, paintFollowWpm, pickSample, renderPractice, runEval, saveMineEdit, saveOwn, setupMineTitle, toggleMineList, selectPickerTab, toggleEvalDock, toggleRecording, updateOwnCount, useScript } from './screens/practice.js';
import { closeStudioSavedMenu, confirmScriptName, onSavedListClick, paintNameCount, toggleStudioSavedMenu } from './screens/saved_scripts.js';
import { closeMenu, onMenuClick, onReaderClosed, saveEdit, setupReaderTitle, toggleEdit, toggleMenu } from './screens/script_reader.js';
import { listenBaseline, onBaselineAudioError, openBaselineRecorder, toggleBaseline } from './screens/profile.js';
import { bindTxTips, onTxClick, openDetails, openPart, seekTo, seekWord, startPlayback, stopPlayback } from './screens/report.js';
import { fitComposer, onChatAction, onComposerFile, renderChatFile, sendChat, toggleComposerFold } from './screens/script_studio.js';
import { CONFIG, RENDER, S } from './state.js';
import { initHeroMic } from './hero_mic.js';
import { watchLineNumbers } from './line_numbers.js';
import { closeUserMenu, onUserButtonClick, setupUserMenuHover } from './top_bar.js';
import { FOCUSABLE, closeModal, focusHeading, openModal, setupPwEyes, setupSelects, toast, usable, withBusy } from './ui.js';
import { $, $$, clearErr, esc, showErr } from './utils.js';

/* ---------- init / events ---------- */
/* Tunable values from app_constants.toml [web] (GET /api/config). The defaults above stay if the call fails. */
export function loadConfig() {
  return fetch('/api/config').then(r => (r.ok ? r.json() : null)).then(c => {
    if (!c) return;
    CONFIG.auth = c.auth ?? CONFIG.auth;
    const job = c.evaluate_job || {};
    CONFIG.EVAL_JOB = { pollMs: job.poll_interval_ms ?? CONFIG.EVAL_JOB.pollMs, maxWaitS: job.max_wait_s ?? CONFIG.EVAL_JOB.maxWaitS, weights: job.stage_weights ?? CONFIG.EVAL_JOB.weights, tauS: job.stt_estimate_tau_s ?? CONFIG.EVAL_JOB.tauS, closeDelayMs: job.done_close_delay_ms ?? CONFIG.EVAL_JOB.closeDelayMs, announcePct: job.announce_step_pct ?? CONFIG.EVAL_JOB.announcePct };
    CONFIG.RETENTION = { insufficientDays: (c.retention || {}).insufficient_days ?? CONFIG.RETENTION.insufficientDays };
    CONFIG.COACH = { maxFocus: (c.coach || {}).max_focus_items ?? CONFIG.COACH.maxFocus };
    const retry = c.retry || {};
    CONFIG.RETRY = { minRatio: retry.sentence_min_error_ratio ?? CONFIG.RETRY.minRatio, wordMax: retry.word_max_seconds ?? CONFIG.RETRY.wordMax, sentenceMax: retry.sentence_max_seconds ?? CONFIG.RETRY.sentenceMax, clipPad: retry.clip_pad_s ?? CONFIG.RETRY.clipPad };
    CONFIG.OWN_MAX_WORDS = c.own_max_words ?? CONFIG.OWN_MAX_WORDS;
    CONFIG.MAX_AUDIO_SECONDS = c.max_audio_seconds ?? CONFIG.MAX_AUDIO_SECONDS;
    CONFIG.BASELINE_SECONDS = c.baseline_seconds ?? CONFIG.BASELINE_SECONDS;
    CONFIG.BASELINE_MIN_SECONDS = c.baseline_min_seconds ?? CONFIG.BASELINE_MIN_SECONDS;
    CONFIG.SPEAKING_WPM_FOR_ESTIMATE = c.speaking_wpm_for_estimate ?? CONFIG.SPEAKING_WPM_FOR_ESTIMATE;
    CONFIG.FOLLOW_LEAD_S = c.follow_lead_s ?? CONFIG.FOLLOW_LEAD_S;
    CONFIG.FOLLOW_GAP_S = c.follow_gap_s ?? CONFIG.FOLLOW_GAP_S;
    CONFIG.HISTORY_PAGE_SIZE = c.history_page_size ?? CONFIG.HISTORY_PAGE_SIZE;
    CONFIG.HISTORY_MAX_PAGES = c.history_max_pages ?? CONFIG.HISTORY_MAX_PAGES;
    CONFIG.FOLLOW_WPM_MIN = c.follow_wpm_min ?? CONFIG.FOLLOW_WPM_MIN;
    CONFIG.FOLLOW_WPM_MAX = c.follow_wpm_max ?? CONFIG.FOLLOW_WPM_MAX;
    CONFIG.FOLLOW_WPM_MIN_CHOOSE = c.follow_wpm_min_choose ?? CONFIG.FOLLOW_WPM_MIN_CHOOSE;
    CONFIG.FOLLOW_WPM_MAX_CHOOSE = c.follow_wpm_max_choose ?? CONFIG.FOLLOW_WPM_MAX_CHOOSE;
    CONFIG.FOLLOW_WPM_STEP = c.follow_wpm_step ?? CONFIG.FOLLOW_WPM_STEP;
    CONFIG.FOLLOW_WPM_DEFAULT = c.follow_wpm_default ?? CONFIG.FOLLOW_WPM_DEFAULT;
    CONFIG.FOLLOW_AUTO_WEIGHT = c.follow_auto_weight ?? CONFIG.FOLLOW_AUTO_WEIGHT;
    CONFIG.FOLLOW_AUTO_MIN_S = c.follow_auto_min_s ?? CONFIG.FOLLOW_AUTO_MIN_S;
    CONFIG.FOLLOW_AUTO_MIN_WORDS = c.follow_auto_min_words ?? CONFIG.FOLLOW_AUTO_MIN_WORDS;
    CONFIG.FOLLOW_AUTO_MAX_AHEAD = c.follow_auto_max_ahead ?? CONFIG.FOLLOW_AUTO_MAX_AHEAD;
    CONFIG.FOLLOW_WPM_SAVE_DELAY_MS = c.follow_wpm_save_delay_ms ?? CONFIG.FOLLOW_WPM_SAVE_DELAY_MS;
    CONFIG.CHAT_HISTORY_MAX_MESSAGES = c.chat_history_max_messages ?? CONFIG.CHAT_HISTORY_MAX_MESSAGES;
    CONFIG.COMPOSER_MAX_WORDS = c.composer_max_words ?? CONFIG.COMPOSER_MAX_WORDS;
    CONFIG.COMPOSER_MAX_LINES = c.composer_max_lines ?? CONFIG.COMPOSER_MAX_LINES;
    CONFIG.SCRIPT_POLL_INTERVAL_MS = c.script_poll_interval_ms ?? CONFIG.SCRIPT_POLL_INTERVAL_MS;
    CONFIG.EVALUATE_BACKGROUND_AFTER_MS = c.evaluate_background_after_ms ?? CONFIG.EVALUATE_BACKGROUND_AFTER_MS;
    CONFIG.MAX_SAVED_SCRIPTS = c.max_saved_scripts ?? CONFIG.MAX_SAVED_SCRIPTS;
    CONFIG.SCRIPT_TITLE_MAX_CHARS = c.script_title_max_chars ?? CONFIG.SCRIPT_TITLE_MAX_CHARS;
    CONFIG.MAX_PDF_SIZE_BYTES = c.max_pdf_size_bytes ?? CONFIG.MAX_PDF_SIZE_BYTES;
    CONFIG.MAX_PDF_PAGES = c.max_pdf_pages ?? CONFIG.MAX_PDF_PAGES;
    CONFIG.PART_GOOD_MIN = c.part_good_min ?? CONFIG.PART_GOOD_MIN;
  }).catch(() => {});
}
export function init() {
  applyText();
  document.title = T('app.name');
  $$('.mbg .box').forEach(b => { b.tabIndex = -1; });
  $('#composerTopic').innerHTML = Object.keys(TOPICS).map(k => '<option value="' + k + '">' + esc(TOPICS[k]) + '</option>').join('');

  // generic delegated clicks
  document.addEventListener('click', e => {
    const g = e.target.closest('[data-go]');
    if (g) {
      closeUserMenu(); go(g.getAttribute('data-go'), { scrollTo: g.getAttribute('data-scroll') });   // data-scroll: open the screen at that element
      return;
    }
    if (e.target.closest('[data-back]')) { go(S.from || 'home'); return; }
    const o = e.target.closest('[data-open]'); if (o) { openReport(o.getAttribute('data-open')); return; }
    const d = e.target.closest('[data-del]');
    if (d) {
      const id = d.getAttribute('data-del');
      openConfirmDialog(T('history.delT'), T('history.delD'), T('history.delOk'), () => {
        deleteSession(id).then(() => { RENDER.home(); toast(T('history.deleted')); focusHeading(); }, () => toast(T('history.delErr'), true));
      });
      return;
    }
    const c = e.target.closest('[data-close]'); if (c) { const m = c.closest('.mbg'); if (m) closeModal(m.id); return; }
    if (e.target.classList && e.target.classList.contains('mbg')) { const id = e.target.id; if (!e.target._lock && id !== 'evaluatingOverlay') closeModal(id); return; }
    if (!e.target.closest('#userMenuButton')) closeUserMenu();
  });
  // keyboard: Esc, focus trap, menu arrows, tab arrows
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const top = S.modal[S.modal.length - 1];
      if (top) { e.preventDefault(); if (top === 'evaluatingOverlay') cancelEval(); else if (!$('#' + top)._lock) closeModal(top); return; }
      if (!$('#userMenu').hidden) { closeUserMenu(true); return; }
    }
    if (e.key === 'Tab' && S.modal.length) {
      const m = $('#' + S.modal[S.modal.length - 1]), f = $$(FOCUSABLE, m).filter(usable);
      if (!f.length) { e.preventDefault(); return; }
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === m.firstElementChild)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      else if (!m.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    }
    const menu = $('#userMenu');
    if (!menu.hidden && menu.contains(document.activeElement)) {
      const items = $$('[role=menuitem]', menu), i = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
      else if (e.key === 'Tab') closeUserMenu();
    }
    const tab = e.target.closest && e.target.closest('.seg [role=tab]');
    if (tab && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      const tabs = $$('[role=tab]', tab.parentElement), i = tabs.indexOf(tab), nx = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      nx.focus(); nx.click();
    }
  });

  // header / landing / auth
  $('#brandBtn').onclick = () => { if (S.user) go('home'); else { setStageAuth(false); showView('landing'); window.scrollTo(0, 0); } };
  $('#hLogin').onclick = $('#lLogin').onclick = () => openAuth('in');
  $('#hSignup').onclick = $('#lCta').onclick = () => openAuth('up');
  $('#authBack').onclick = () => { setStageAuth(false); $('#lLogin').focus({ preventScroll: true }); };
  $('#authLoginTab').onclick = () => setAuthMode('in'); $('#authSignupTab').onclick = () => setAuthMode('up');
  $('#authForm').addEventListener('submit', onAuthSubmit);
  ['input', 'change'].forEach(type => $('#authForm').addEventListener(type, updateSignupButton));
  $('#forgotLink').onclick = openResetStep;
  setupPwEyes();
  setupSelects();
  setupUserMenuHover();
  $('#userBtn').onclick = onUserButtonClick;
  $('#userMenu').addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const a = b.getAttribute('data-act'); closeUserMenu(true);
    if (a === 'profile') go('profile');
    else if (a === 'settings') openSettings();
    else if (a === 'logout') logout();
  });

  // script
  $('#attachBtn').onclick = () => $('#composerFileInput').click();
  $('#composerFileInput').onchange = onComposerFile;
  $('#composerFile').addEventListener('click', e => { if (e.target.closest('#chatFileX')) { S.chatFile = null; renderChatFile(); $('#attachBtn').focus(); } });
  $('#composerSend').onclick = sendChat;
  $('#composerInput').addEventListener('input', fitComposer);   // grows with the text (1.5 to 5.5 lines)
  $('#composerFold').onclick = toggleComposerFold;
  window.addEventListener('resize', () => { if (S.screen === 'scriptStudio') fitComposer(); });
  fitComposer();
  $('#composerInput').addEventListener('keydown', e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendChat(); } });
  $('#chatFeed').addEventListener('click', onChatAction);
  $('#studioSavedButton').onclick = toggleStudioSavedMenu;
  $('#studioSavedList').addEventListener('click', e => onSavedListClick(e, 'studio'));
  $('#studioSavedMenu').addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeStudioSavedMenu(true); } });
  document.addEventListener('click', e => { if (!e.target.closest('.studio-saved') && !e.target.closest('.mbg')) closeStudioSavedMenu(false); });
  // Saved Scripts dialogs
  $('#scriptNameOk').onclick = confirmScriptName;
  $('#scriptNameInput').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); confirmScriptName(); } });
  $('#scriptNameInput').addEventListener('input', () => { clearErr($('#scriptNameError')); $('#scriptNameInput').removeAttribute('aria-invalid'); paintNameCount(); });
  // Script Reader: edit in place, Save, and the slide-out menu
  $('#mrEdit').onclick = toggleEdit;
  $('#mrSave').onclick = saveEdit;
  setupReaderTitle();
  $('#mrMoreButton').onclick = toggleMenu;
  $('#mrMenu').addEventListener('click', onMenuClick);
  $('#scriptReader').addEventListener('mouseleave', closeMenu);
  new MutationObserver(() => { if (!$('#scriptReader').classList.contains('show')) { onReaderClosed(); closeMenu(); } })
    .observe($('#scriptReader'), { attributes: true, attributeFilter: ['class'] });

  // practice
  $$('[data-src]').forEach(b => { b.onclick = () => selectPickerTab(b.getAttribute('data-src')); });
  $('#goScript').onclick = () => go('scriptStudio');
  $('#homeMore').onclick = scrollHomeDown;
  $('#useScript').onclick = useScript;
  loadFollowWpm(); paintFollowWpm(); $('#followWpm').addEventListener('input', onFollowWpm);
  $('#mineList').addEventListener('click', e => onSavedListClick(e, 'practice'));
  $('#mineEditSave').onclick = saveMineEdit;
  $('#mineEditCancel').onclick = cancelMineEdit;
  setupMineTitle();
  $('#mineFold').onclick = toggleMineList;
  ['#sheet', '#minePreview', '#mrBody'].forEach(id => watchLineNumbers($(id)));   // line numbers on every script text
  $('#sampleBtn').onclick = pickSample;
  $('#recPause').onclick = togglePause;
  $('#sheet').addEventListener('click', onSheetClick);
  $('#ownText').addEventListener('input', () => { updateOwnCount(); clearErr($('#ownErr')); $('#ownText').removeAttribute('aria-invalid'); renderPractice(); });
  $('#ownSave').onclick = saveOwn;
  $('#voiceRecordTab').onclick = () => { if (S.rec) return; S.voiceTab = 'rec'; renderPractice(); };
  $('#voiceUploadTab').onclick = () => { if (S.rec) return; S.voiceTab = 'up'; renderPractice(); };
  $('#recBtn').onclick = toggleRecording;
  $$('#steps [data-step]').forEach(b => { b.onclick = () => goStep(+b.getAttribute('data-step')); });
  $('#recClear').onclick = () => openConfirmDialog(T('practice.discardT'), T('practice.discardD'), T('practice.discardOk'), () => { S.audio = null; renderPractice(); $('#recBtn').focus(); });
  $('#dropBtn').onclick = () => $('#fileIn').click();
  $('#fileIn').onchange = onAudioFile;
  $('#evalBtn').onclick = runEval;
  $('#ovCancel').onclick = cancelEval;
  $('#evDockHead').onclick = toggleEvalDock;
  $('#evDockCancel').onclick = cancelEval;
  window.addEventListener('pagehide', () => { if (S.evaluation) cancelEval(); });
  new MutationObserver(() => { if (S.evaluation && !S.evaluation.background && S.screen !== 'practice') cancelEval(); }).observe($('#screenPractice'), { attributes: true, attributeFilter: ['class'] });
  $('#meRetry').onclick = () => { closeModal('errorDialog', false); runEval(); };

  // report
  $('#transcriptView').addEventListener('click', onTxClick);
  $('#playBtn').onclick = () => { if (S.play.on) stopPlayback(); else startPlayback(); };
  $('#seek').addEventListener('input', e => seekTo(+e.target.value / 10, false));

  // history (bottom of Home) / profile
  $('#delAll').onclick = () => openConfirmDialog(T('history.delAllT'), T('history.delAllD'), T('history.delAllOk'), () => {
    const ids = S.sessions.map(x => x.id);   // one DELETE per session, one after another
    ids.reduce((p, id) => p.then(() => deleteSession(id)), Promise.resolve())
      .then(() => { RENDER.home(); toast(T('history.deletedAll')); focusHeading(); }, () => { RENDER.home(); toast(T('history.delErr'), true); });
  });
  $('#mcfOk').onclick = () => { const cb = S.confirmCb; S.confirmCb = null; closeModal('confirmDialog'); if (cb) cb(); };
  $('#editInfo').onclick = () => openProfileModal(false);
  $('#avChange').onclick = () => $('#avFile').click();
  $('#avFile').onchange = e => {
    const f = e.target.files && e.target.files[0]; e.target.value = '';
    if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    withBusy(api('/api/profile/avatar', { method: 'PUT', body: fd }), T('busy.saving')).then(r => r.json().catch(() => null).then(j => {
      if (!r.ok) { toast((j && j.message) || T('profile.errImage'), true); return; }
      S.avatar = j.avatar_url; paintAvatar($('#avTop')); RENDER.profile(); toast(T('profile.okAvatar'));
    })).catch(() => toast(T('profile.errAvatarSave'), true));
  };
  $('#avRemove').onclick = () => openConfirmDialog(T('profile.removeT'), T('profile.removeD'), T('profile.removeOk'), () => {
    withBusy(api('/api/profile/avatar', { method: 'DELETE' }), T('busy.saving')).then(r => r.json().catch(() => null).then(j => {
      if (!r.ok) { toast((j && j.message) || T('profile.errAvatarRemove'), true); return; }
      S.avatar = null; paintAvatar($('#avTop')); RENDER.profile(); toast(T('profile.okRemoved'));
    })).catch(() => toast(T('profile.errAvatarRemove'), true));
  });
  $('#profileBaselineStart').onclick = toggleBaseline;
  $('#profileBaselineAgain').onclick = openBaselineRecorder;
  $('#profileBaselineListen').onclick = listenBaseline;
  $('#profileBaselineAudio').addEventListener('error', onBaselineAudioError);

  // baseline window (after log in)
  $('#baselineGateAgree').onclick = onGateAgree;
  $('#baselineGatePause').onclick = onGatePause;
  $('#baselineGateLogout').onclick = () => logout();

  // report: hover notes, score details
  bindTxTips();
  initHeroMic();   // Home: the 3D mic under the greeting
  new ResizeObserver(syncScrollThumb).observe(document.body);   // short pages: no scrollbar thumb (see nav.js)
  window.addEventListener('resize', syncScrollThumb);
  syncScrollThumb();
  $('#repScoreCard').addEventListener('click', e => { if (e.target.closest('[data-details]')) openDetails(); });
  $('#mpartTabs').addEventListener('click', e => { const b = e.target.closest('[data-part]'); if (b) openPart(b.getAttribute('data-part')); });
  $('#mpartBody').addEventListener('click', e => {
    const c = e.target.closest('[data-wi]'); if (!c || !S.currentSession) return;
    const i = +c.getAttribute('data-wi');
    closeModal('componentDetail', false);
    seekWord(i);
    const el = $('#transcriptView [data-i="' + i + '"]');
    if (el) { el.scrollIntoView({ block: 'center' }); if (el.focus) el.focus({ preventScroll: true }); }
  });

  // modals
  $('#mpSave').onclick = saveProfileModal;
  $('#mpCancel').onclick = () => closeModal('profileModal');
  // Consent Modal: the locked feature runs only after the server has saved consent_recording = true
  $('#mcAllow').onclick = () => {
    const btn = $('#mcAllow');
    if (btn.disabled) return;
    btn.disabled = true;
    saveConsent(true).then(ok => {
      btn.disabled = false;
      if (!ok) { toast(T('consent.errSave'), true); return; }
      S.consent = true; closeModal('consentModal'); toast(T('consent.toastOn'));
      const cb = S.afterConsent; S.afterConsent = null; if (cb) cb();
    });
  };
  $('#mcDeny').onclick = () => { S.afterConsent = null; closeModal('consentModal'); toast(T('consent.toastDenied')); };
  setupSettings();

  window.addEventListener('resize', () => { syncHeader(); syncStage(); moveNavPill(false); moveSegPills(false); moveSegPills(false, $('#lAuth')); });
  window.addEventListener('scroll', () => { syncHero(); kickFollow(); }, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(syncStage).observe($('#lStage'));
  showView('landing'); renderAccount();
  // Page load: the refresh cookie (if any) gives a new access token. The loading screen stays up
  // meanwhile, so the Landing page does not flash before Home.
  dropOldStoredTokens();
  showAppLoader(true);
  refreshAuth().then(ok => { if (ok) startSession(false); else showAppLoader(false); }, () => showAppLoader(false));
}
loadConfig().then(init);
