import { $$ } from './utils.js';

/* =====================================================================
   ALL TEXT SHOWN ON SCREEN
   data-t="group.key" (HTML) and T('group.key', {vars}) (JS) read from here.
   ===================================================================== */
export const TEXT = {
  app: { loading: 'Loading your practice…', name: 'Public Speaking Assistant', tagline: 'Read your script aloud. See exactly where to improve.' },
  busy: { saving: 'Saving…', deleting: 'Deleting…', loading: 'Loading…', signingIn: 'Logging in…', signingUp: 'Creating your account…', verifying: 'Checking the code…' },
  common: { skip: 'Skip to content', back: 'Back', cancel: 'Cancel', save: 'Save', close: 'Close', play: 'Play', pause: 'Pause', delete: 'Delete', na: 'N/A' },
  /* Same slugs and labels as CATEGORY_SLUG_MAP (src/text_processing/contracts.py) and data/templates/<slug>/ */
  topics: { cinematography: 'Cinematography', gender_studies: 'Gender Studies', information_technology: 'Information Technology', learning_experiences: 'Learning Experiences', sports: 'Sports', wildlife: 'Wildlife' },
  nav: { label: 'Main', home: 'Home', script: 'Script', practice: 'Practice' },
  top: { login: 'Log in', signup: 'Sign up', profile: 'Profile', settings: 'Settings', logout: 'Log out' },

  landing: {
    title: 'Read your script aloud. See exactly where to improve.',
    lead: 'Prepare a script, record yourself, and get a marked-up transcript with your pace, pauses and pitch.',
    cta: 'Create account', login: 'Log in',
    note: 'Free to try. You decide when recording is allowed.',
    sWpm: 'words per minute', sPauses: 'hesitation pauses', sPitch: 'pitch range',
    sampleCap: 'Red = a word that did not match. Yellow = a close match. Struck through = a word that was skipped.',
    h1n: 'Step 1', h1t: 'Prepare', h1d: 'Generate a script from your topic or a PDF, or paste your own.',
    h2n: 'Step 2', h2t: 'Record', h2d: 'Read it aloud into your microphone, or upload an audio file.',
    h3n: 'Step 3', h3t: 'Review', h3d: 'Click any marked word to hear that moment, then practise what stands out.'
  },

  auth: {
    otpTitle: 'Check your email', otpSent: 'We sent a {n}-digit code to {email}.', otpSentLogin: 'Confirm your email first. We sent a {n}-digit code to {email}.',
    otpLabel: 'Verification code', otpVerify: 'Verify email', otpResend: 'Resend code', otpResendIn: 'Resend code in {t}', otpResending: 'Sending…', otpResent: 'We sent a new code.', otpBack: 'Use a different email',
    otpExpiry: 'If you do not confirm, this account is deleted {n} minutes after the last code we sent.',
    errOtpFormat: 'Enter the {n}-digit code from the email.', errOtpInvalid: "That code doesn't match. Use the latest email, or send a new code.", errOtpExpired: 'This code has expired. Send a new one.', errRateLimited: 'Too many tries. Wait a moment, then try again.',
    hintVerified: 'Email verified. Log in to continue.', hintVerifiedOldPassword: 'Email verified, but your new password could not be saved. Log in with the password you set first.', okVerified: 'Email verified.', okVerifiedOff: 'Email verified. Recording is off: you can turn it on in Permissions after you log in.',
    tabLogin: 'Log in', tabSignup: 'Sign up', btnLogin: 'Log in', btnSignup: 'Create account',
    username: 'Email', password: 'Password', show: 'Show', hide: 'Hide',
    errEmpty: 'Enter your email and a password.', errEmail: 'Enter a valid email address.',
    errWeak: 'Use a password with at least 8 characters.', errLogin: 'Wrong email or password.',
    errServer: 'Could not reach the account service. Please try again.',
    expired: 'Your session has ended. Please log in again.',
    okSignup: 'Account created. Please log in.', okSignupOff: 'Account created. Recording is off: you can turn it on in Permissions after you log in.', okLogin: 'Signed in.',
    errTaken: 'An account with this email already exists. Log in instead.', password2: 'Repeat password', errMismatch: 'The two passwords do not match.', errRepeat: 'Repeat your password.', hintSignedUp: 'Account created. Log in to continue.'
  },

  home: {
    greetMorning: 'Good morning, {name}', greetAfternoon: 'Good afternoon, {name}', greetEvening: 'Good evening, {name}',
    summaryNew: 'Pick a script, read it aloud and get your first report.',
    summaryWeek: '{n} sessions this week · latest score {score}', summaryWeekOne: '1 session this week · latest score {score}', summaryIdle: 'No practice this week yet · latest score {score}',
    ctaFirst: 'Start your first practice', ctaFocus: 'Practise {area}', ctaScript: 'Create a script',
    more: 'Your progress and history', moreNew: 'Your progress will appear below',
    later: 'Your charts and practice history will appear here after your first practice.',
    progressTitle: 'Your progress', detailsTitle: 'Pace, pitch and clarity',
    cScore: 'Score over time', cActivity: 'Practice minutes (last 14 days)', cWpm: 'Speaking pace (WPM)', cPitch: 'Pitch range (semitones)', cClarity: 'Clarity score',
    capScore: 'Latest {v}. Range {lo} to {hi}.', capActivity: 'Practised on {days} of the last {n} days. Current streak: {streak}.',
    capWpm: 'Latest {v} WPM. Target 130 to 160.', capPitch: 'Latest {v} st. Below 4 st sounds monotone.', capClarity: 'Latest {v}. Based on what the recogniser heard, not a pronunciation grade.',
    latestTitle: 'Latest score',
    deltaUp: '{d} points vs your previous 3 sessions', deltaDown: '{d} points vs your previous 3 sessions', deltaFlat: 'No change vs your previous 3 sessions',
    deltaNeed: 'Progress appears after 6 scored sessions ({n} so far).',
    openReport: 'Open latest report',
    emptyT: 'No practice sessions yet', emptyD: 'Your score, pace and pitch charts will appear here after your first practice.',
    streakNone: 'none', streakDays: '{n} days', streakDay: '1 day'
  },

  script: {
    title: 'Generate Script', sub: 'Choose a topic, describe your event or attach a PDF, Markdown (.md) or text (.txt) file. You get an English script you can practise with.',
    feedLabel: 'Conversation', topic: 'Category', duration: 'Duration', attach: 'Attach a PDF, Markdown or text file', inputLabel: 'Describe your event or paste material',
    placeholder: 'Describe your event, or paste some material...', send: 'Send', fold: 'Make the text box smaller', unfold: 'Show more of your text',
    hint: 'The assistant can make mistakes. Read the script and check names, facts and figures before you practise.',
    fileHint: 'PDF (up to 25 MB), Markdown (.md), or Text (.txt, up to 2 MB).',
    assistant: 'Assistant',
    newChat: 'New chat', newChatAria: 'Start a new chat. The current conversation is cleared.',
    errSession: 'This chat has expired, so a new one was started. Please send your request again.',
    errRate: 'Too many requests right now. Please wait a moment and try again.',
    errModeration: 'The safety check is not available right now, so no script was written. Please try again in a few minutes.',
    errGeneric: 'Something went wrong while writing your script. Please try again.',
    errChat: 'Something went wrong. Please try again.',
    greeting: 'Hi {name}. Pick a topic, then tell me about your event or attach a PDF, Markdown or text file with the key points.',
    errFile: 'That file cannot be used. Attach a PDF (up to 25 MB and 10 pages, not password-protected) or a .md or .txt file (up to 2 MB).',
    errFileType: 'Only .pdf, .md and .txt files can be attached.',
    errFileBig: 'That file is too large. PDF files can be up to 25 MB, .md and .txt files up to 2 MB.',
    errFileSmall: 'That file is empty or too small to use.',
    errFileEncoding: 'That text file is not valid UTF-8. Save it as UTF-8 and try again.',
    errFileWords: 'That text file is too long (over 15,000 words). Use a shorter file.',
    errFileNoText: 'That PDF has no readable text. Use a PDF with selectable text.',
    errLong: 'The text is longer than {max} words. Shorten it and send again.',
    extracting: 'Reading your material and checking it is safe to use...',
    generating: 'Writing your script...', regenerating: 'Writing another version...',
    scriptHeader: 'Script · {title}',
    viewNow: 'View now', viewAria: 'View script: {title}', words: 'words', min: 'min', readerLabel: 'Script text', hasNotes: 'Has notes. Open to read.',
    practice: 'Practise with this script', copy: 'Copy text', download: 'Download', regenerate: 'Regenerate',
    copied: 'Script copied.', copyFail: 'Copy is not available in this browser.', downloadName: 'script.txt',
    citeNone: 'No source document attached, so this script has no citations. Attach a PDF to get citations.',
    uncited: 'uncited', uncitedHelp: 'No matching passage was found in your PDF for this paragraph.',
    checking: 'Checking your request against the content rules...',
    blockedTag: 'Blocked by content rules',
    blockedTitle: 'Cannot generate script based on regulations.',
    blockedHarm: 'Your request was blocked by our safety check, so no script was written.',
    blockedNext: 'Edit your message or material to remove anything unsafe, then send it again.',
    pickTopic: 'Pick the topic that fits best, or write freely without a template.', noTopics: 'No template matched. You can write freely without a template.',
    writeFreely: 'No template — Write freely (AI)', generate: 'Generate Script', thinking: 'Working on it...',
    sessionFiles: 'Files used in this chat',
    regenPlaceholder: 'Optional: what to adjust? (Leave blank to rewrite)', regenConfirm: 'Rewrite script'
  },
  safety: { title: 'This material cannot be used', msg: 'It contains inappropriate or restricted language. Edit your text and try again.', ack: 'Edit my text' },

  practice: {
    title: 'Practice', sub: 'Get your text, read it aloud, then record or upload your audio.', stepsLabel: 'Progress',
    step1: 'Choose text', step2: 'Record', step3: 'Review',
    tabsLabel: 'Text to read', tabMine: 'My script', tabSample: 'Sample', tabOwn: 'Write my own',
    sheetLabel: 'Text to read aloud',
    makeScript: 'Generate a script',
    emptySampleT: 'No sample chosen yet.', sampleBtn: 'Show a sample', sampleAnother: 'Show another sample',
    emptyOwnT: 'Type your text in the box, then choose Use this script.',
    ownLabel: 'Your text', ownCounter: '{n} / {max} words', errOwnMax: 'Keep the text to {max} words or fewer.', errOwnEmpty: 'Type some text first.',
    fromScript: 'From Script · {title}', sampleTitle: 'Sample · {title}', ownTitle: 'Your own text',
    words: '{n} words · about {t} at a steady pace', readTime: 'about {t} at a steady pace',
    voiceTitle: 'Your voice', tabRec: 'Record', tabUp: 'Upload',
    useScript: 'Use this script',
    followWpmLabel: 'Highlight speed (follow-along only, not scored)', followWpmVal: '{n} words per minute', followWpmShort: '{n} wpm',
    start: 'Start recording', stop: 'Stop recording', pause: 'Pause', resume: 'Resume', pausedNote: 'Paused. Press Resume to go on with the same recording.', discard: 'Discard',
    recording: 'Recording...',
    recordingFollow: 'Recording... Read the text aloud. The highlight follows along.',
    dropText: 'Choose an audio file (mp3, wav, webm, m4a)', errAudio: 'That is not an audio file.',
    micDenied: 'Microphone access was blocked. Allow it in your browser, or upload an audio file instead.',
    micNodevice: 'No usable microphone was found. Upload an audio file instead.',
    micUnsupported: 'This browser cannot record audio here. Upload an audio file instead.',
    noAudio: 'No audio yet.',
    audioReady: 'Recording ready ({time}).', fileReady: 'File ready: {name}',
    evaluate: 'Evaluate', hintNoText: 'Choose the text to read first.', hintNoOwn: 'Type your text first.', hintNoAudio: 'Record or upload your audio.',
    stepBackT: 'Go back and discard this audio?', stepBackD: 'Your recording belongs to the current text, so it will be removed. You can record again.',
    discardT: 'Discard this audio?', discardD: 'The recording will be removed. You can record again.', discardOk: 'Discard audio'
  },

  /* Script Reader: edit in place and the slide-out menu */
  reader: {
    more: 'More actions', editSaved: 'Changes kept in this chat.',
    unsavedTitle: 'Your edits are not saved', unsavedMsg: 'This uses the script as it was before your edits. Save your edits first to use the new version.',
    useLast: 'Use the last saved version'
  },

  /* Saved Scripts: the user's own list on Practice (My script) and in Script Studio (Show my scripts) */
  saved: {
    title: 'My scripts', count: '{n} / {max}', countLong: '{n} / {max} scripts saved', words: '{n} words', showMine: 'Show my scripts',
    empty: 'No saved scripts yet. Save a script in Script, or write your own and save it.',
    pickOne: 'No script chosen yet. Choose a script on the left to see its text here.', notSaved: 'Not saved',
    saveScript: 'Save script', saveTitle: 'Save script', nameLabel: 'Script name', errNameEmpty: 'Enter a name for the script.',
    saved: 'Saved as "{title}".',
    nameCount: '{n} / {max} characters', foldList: 'Hide the script list', unfoldList: 'Show the script list',
    edit: 'Edit', editTitle: 'Edit script', editAria: 'Edit {title}', bodyLabel: 'Script text', errBodyEmpty: 'The script text cannot be empty.', edited: 'Script updated.',
    deleteAria: 'Delete {title}', deleteTitle: 'Delete this script?', deleteMsg: '"{title}" will be removed from your list. Reports of sessions you practised with it stay.',
    deleted: 'Script deleted.',
    dupBodyT: 'This script is already saved', dupBodyMsg: 'Your saved script "{title}" has exactly the same text, so this one was not saved.',
    dupTitleT: 'This name is already used', dupTitleMsg: 'You already have a saved script named "{title}". Pick another name.',
    fullTitle: 'Your script list is full', fullMsg: 'You can keep up to {max} saved scripts. Delete one before you save another.'
  },

  consent: {
    title: 'Allow recording?',
    msg: 'To score your speech we need to record your voice in this browser.',
    p1: 'Your audio is sent to an external speech-to-text service to get the words and their timing.',
    p2: 'Pitch and pauses are measured on our server.',
    p3: 'Recordings are kept in your History until you delete them.',
    note: 'You can change this any time in Permissions.',
    deny: 'Not now', allow: 'Allow recording',
    toastOn: 'Recording allowed.', toastDenied: 'Recording is off. You can turn it on in Permissions.', toastOff: 'Recording turned off.'
  },

  eval: {
    stages: { upload: 'Upload', decode: 'Decode audio', vad: 'Find speech', stt: 'Transcribe', align: 'Match words', fluency: 'Pace and pauses', pitch: 'Pitch and loudness', semantic: 'Meaning match', save: 'Save' },
    percentLabel: '{n}% done', stepSkipped: 'Skipped', estimateNote: 'Transcription progress is estimated.',
    title: 'Analysing your recording',
    bgT: 'Your evaluation keeps running', bgD: 'You can keep using the app. Practice and recording open again when your report is ready. The progress card at the top right shows how far it is.',
    dockLabel: 'Evaluating',
    busyT: 'An evaluation is still running', busyD: 'Practice and recording open again when your report is ready. Please wait a moment.', busyOk: 'OK',
    readyT: 'Your report is ready', readyD: 'The evaluation of "{title}" has finished.', readyView: 'View report',
    errTitle: 'We could not transcribe your recording', errMsg: 'Nothing was scored or saved. Check your connection and try again.', retry: 'Try again',
    saved: 'Saved to History.', notSaved: 'Could not save to History. Your report is shown below.',
    errBaselineRequired: 'Record your baseline voice first, then try again.',
    errBaselineUnavailable: 'Your baseline could not be loaded right now. Nothing was scored. Please try again.',
    errBaselineNotSaved: 'Your baseline was analysed but could not be saved. Please record it again.',
    errScriptNotFound: 'This script no longer exists. Choose another text and try again.',
    errScriptEmpty: 'The practice text is empty. Choose or write a text first.',
    errScriptTooLong: 'The practice text is too long. Please use a shorter text.',
    errScriptStorage: 'Saved scripts are not available right now. Please try again.',
    errTooLong: 'This recording is longer than the allowed limit. Please choose a shorter one.',
    errTooLarge: 'This file is too large (maximum 100 MB). Please send the recording as MP3 or M4A.',
    errNoStream: 'No audio was found in this file. Please check the file and try again.',
    errFormat: 'This file format is not supported. Please upload an audio-only file.',
    errCorrupt: 'This audio could not be read. It may be damaged; try another file or record again.',
    errBaseline: 'Your saved baseline could not be used. Please record it again in Profile.',
    errNet: 'Could not reach the server. Nothing was scored or saved. Check your connection and try again.',
    errStt: 'Speech recognition is not available right now. Nothing was scored or saved. Please try again in a few minutes.',
    errServer: 'The server could not score this recording. Nothing was scored or saved. Please try again.',
    errTimeout: 'The analysis took too long and was stopped. Nothing was scored or saved. Please try again.',
    insEmpty: 'We could not recognise any words in this recording. Please record again in a quieter place, closer to the microphone.',
    noPitch: 'No pitch could be measured in this recording.',
    noVol: 'No loudness could be measured in this recording.',
    naPart: 'This part could not be scored for this recording, so there is no breakdown to show.'
  },

  report: {
    title: 'Evaluation report', again: 'Practise again', history: 'View history',
    meta: '{title}{accent}', accentPart: ' · {accent}',
    txSr: 'Hover or focus a marked word to see what went wrong. Click any word or time to jump to that moment in the recording.', transcript: 'Transcript',
    seek: 'Position in your recording', asideLabel: 'Score and next steps',
    overall: 'Overall score', outOf: '/ 100',
    parts: 'Score breakdown',
    pA: 'Accuracy', pF: 'Fluency and pacing', pP: 'Clarity and intonation', pS: 'Meaning match',
    wA: '40%', wF: '30%', wP: '20%', wS: '10%',
    dA: '{n} of {total} words wrong or missing',
    dF: 'Pace, pauses and filler words',
    dP: 'Close matches and pitch variation',
    dS: '{n} of {total} sentences keep the meaning',
    delta: 'Progress', deltaUp: '+{d} vs your previous 3 sessions', deltaDown: '{d} vs your previous 3 sessions', deltaNeed: 'Progress shows after 6 scored sessions ({n} so far).',
    noBaseline: 'No baseline voice yet: pitch is compared with this session only.',
    lgNote: 'Clarity reflects what the recogniser heard. It is not a pronunciation grade.',
    cPace: 'Pace over time (WPM)', capPace: 'Words per minute in 5-second windows. Shaded band is the 130 to 160 target.',
    cPause: 'Pauses (seconds)', capPause: '{n} pauses of 0.25 s or more. {h} were hesitations.',
    cPitch: 'Pitch (semitones vs baseline)', capPitch: 'Range {r} st. Under 4 st sounds monotone.',
    cVol: 'Voice loudness over time (dB)', capVol: 'How loud your voice was at each moment, so you can see where you spoke loudly or softly. This is loudness, not pitch: pitch is in Clarity and intonation. Shown for reference, not scored.',
    volRead: 'Loudest around {tHi} ({hi} dB), softest around {tLo} ({lo} dB). Range {r} dB.',
    lgNatural: 'Natural (at punctuation)', lgHesitation: 'Hesitation (0.5 s or more)', lgForgot: 'Long (1.2 s or more)',
    pauseNatural: 'natural pause', pauseHes: 'hesitation', pauseForgot: 'long pause, maybe a forgotten word',
    stInsT: 'We could not score this recording',
    stInsD: "Speech covers only {p}% of the file, and at least 30% is needed.",
    stInsNotScored: "This attempt isn't scored and won't count toward your progress.",
    stInsKept: "It is deleted after {n} days.",
    stInsCta: 'Record again',
    unitWpm: 'WPM', unitSt: 'st', unitDb: 'dB', unitS: 's',
    adv_wpm: 'Pace: {v} WPM. Aim for 130 to 160.',
    adv_pause: '{v} hesitation pauses per minute. A hesitation is a pause of 0.5 s or more that is not at punctuation. Aim for 1 or fewer.',
    adv_filler: 'Filler words: {v}% of your words. Aim for under 4%.',
    adv_accuracy: 'Words wrong or skipped: {v}. Click the red and struck-through words.',
    adv_clarity: 'Words heard as close matches: {v}. Click the yellow words to review them.',
    adv_pitch: 'Pitch range {v} st. Under 4 st sounds monotone. Aim for 6 or more.',
    adv_semantic: 'Sentences that drifted from the script: {v}. Check the red words in them.',
    compactNote: 'older session: scores and marked words only, no audio or charts',
    areaWpm: 'pace', areaPause: 'pauses', areaFiller: 'filler words', areaAccuracy: 'accuracy', areaClarity: 'clarity', areaPitch: 'pitch variation', areaSemantic: 'meaning match'
  },

  history: {
    title: 'History', sub: 'Your saved recordings and scores. Open a row to see its full report.', deleteAll: 'Delete all recordings',
    colDate: 'Date', colScript: 'Script', colDuration: 'Duration', colScore: 'Score', colActions: 'Actions',
    open: 'Open report', delete: 'Delete',
    delT: 'Delete this recording?', delD: 'The audio and its report will be removed. This cannot be undone.', delOk: 'Delete recording',
    delAllT: 'Delete all recordings?', delAllD: 'All audio and reports will be removed. This cannot be undone.', delAllOk: 'Delete all',
    deleted: 'Recording deleted.', deletedAll: 'All recordings deleted.',
    untitled: 'Practice session', loadErr: 'Could not load your history. Reload the page to try again.',
    opening: 'Opening report…', openErr: 'Could not open this report. Please try again.', delErr: 'Could not delete. Please try again.'
  },

  profile: {
    title: 'Profile', sub: 'Your details and your 30-second baseline voice.',
    userInfo: 'Your details', editInfo: 'Edit details', changeAvatar: 'Change photo', removeAvatar: 'Remove photo',
    rowName: 'Name', rowGender: 'Gender', rowAge: 'Age', rowAccent: 'Target accent', rowBaseline: 'Baseline voice', rowBaselineDone: 'Recorded on {date}', rowNotSet: 'Not set',
    baselineTitle: 'Baseline voice', baselineNote: 'Read the passage naturally, as in a normal conversation. Your pitch and pauses are compared with this recording.',
    start: 'Start recording', stop: 'Stop recording', again: 'Record again', recording: 'Recording...',
    saved: 'Baseline saved on {date}', none: 'No baseline yet', tooShort: 'Too short: record at least {n} s',
    analysing: 'Analysing your baseline...',
    listen: 'Listen to my baseline', listenAria: 'Your baseline recording',
    errListenNone: 'No baseline recording was found.', errListen: 'Could not load your baseline recording. Please try again.',
    errInsufficient: 'We could not hear enough speech in this recording. Please record again, reading the passage aloud.',
    toastSaved: 'Baseline voice saved.', timerSuffix: ' / {t}', progress: 'Baseline recording progress',
    okAvatar: 'Photo updated.', okRemoved: 'Photo removed.',
    removeT: 'Remove profile photo?', removeD: 'Your photo will be deleted. Your initial is shown instead.', removeOk: 'Remove', errImage: 'Choose an image file.',
    errAvatarSave: 'Could not save your profile picture. Please try again.',
    errAvatarRemove: 'Could not remove your profile picture. Please try again.'
  },

  pm: {
    displayName: 'Your name', displayNamePh: 'What should we call you?', errName: 'Enter your name.',
    titleFirst: 'Welcome. Tell us how you want to practise', titleEdit: 'Edit your details',
    subFirst: 'Choose your accent to continue. Gender and age are optional.',
    subEdit: 'Update your details and press Save.',
    gender: 'Gender', optional: '(optional)', genderPh: 'Prefer not to say', genders: ['Male', 'Female', 'Other'],
    age: 'Age', agePh: 'For example 21',
    accent: 'Target accent', accents: ['American English', 'British English'],
    errAge: 'Enter an age between 1 and 120, or leave it empty.', errAccent: 'Choose one accent.',
    saved: 'Details saved.', saveErr: 'Could not save your details. Please try again.'
  },
  pass: {
    title: 'Change password', sub: 'Enter your current password, then choose a new one. You stay logged in.', username: 'Email',
    current: 'Current password', newPass: 'New password', newPass2: 'Repeat new password',
    errEmpty: 'Fill in all three password fields.', errMismatch: 'The two new passwords do not match.',
    errSame: 'The new password must be different from the current one.', errWrong: 'The current password is not correct.',
    errRate: 'Too many attempts. Please wait a few minutes and try again.', ok: 'Password changed.'
  },
  audio: {
    title: 'Audio settings', sub: 'Choose the microphone used for practice, your baseline and the word and sentence coach.', mic: 'Microphone',
    micDefault: 'Default microphone', micN: 'Microphone {n}',
    micHint: 'Device names are hidden until you allow the microphone. Press Test microphone to show them.',
    micGone: 'The chosen microphone was not found. Using the default microphone.',
    test: 'Test microphone', testing: 'Say a few words...', testOk: 'The microphone is working.', ok: 'Audio settings saved.'
  },
  settings: { title: 'Settings', back: 'Back', permissions: 'Permissions', audio: 'Audio', speed: 'Reading speed', password: 'Change password', delete: 'Delete account' },
  del: {
    title: 'Delete account', sub: 'This permanently deletes your account with all your recordings, your baseline, your scripts and your practice history. It cannot be undone.',
    password: 'Enter your current password to confirm', agree: 'Agree',
    errWrong: 'The password is not correct. Nothing was deleted.', errRate: 'Too many attempts. Please wait a few minutes and try again.',
    failed: 'Your account could not be deleted right now. Please try again later.', done: 'Your account was deleted.'
  },
  speed: {
    title: 'Reading speed', sub: 'Choose the range of the follow-along speed slider on Practice ({lo}–{hi} words per minute).',
    min: 'Slowest speed', max: 'Fastest speed',
    auto: 'Auto speed', autoNote: 'While recording, tap the sentence you have reached: the speed slider adjusts to how fast you read. You can still move it yourself.', wpm: '{n} wpm', reset: 'Use default',
    errOrder: 'The slowest speed must be lower than the fastest speed.', ok: 'Reading speed saved.', err: 'Could not save the reading speed. Please try again.'
  },
  perm: { title: 'Permissions', sub: 'Control recording in this browser.', allow: 'Allow recording', note: 'Needed to record and score your speech.' },
  overview: {
    title: 'Overview',
    verdict_good: 'A strong take. Keep it this steady.',
    verdict_fair: 'A solid base, with clear room to improve.',
    verdict_improve: 'A few areas need work before this sounds confident.',
    verdict_more: 'This take needs more practice. Fix one thing at a time.',
    na: 'No overall assessment: one part could not be scored.',
    strongest: 'Strongest', improve: 'Improve', focus: 'Focus next', allGood: 'All four parts are in good shape.',
    gPace: 'Pace', gHes: 'Hesitations / min', gFiller: 'Filler words', gWrong: 'Wrong / skipped', gPitch: 'Pitch range', gWords: '{n} of {total}',
    keyNumbers: 'Key numbers', onTarget: 'On target', workOn: 'Work on it',
    coachWho: 'Assistant', coachTag: 'Preview',
    aiLabelNoScore: 'AI feedback on this recording',
    ruleLabelNoScore: 'Tips for your next recording',
    insLowSummary: 'Most of this recording was silence, so it could not be checked.',
    insLowFocus1: 'Start speaking soon after you press record.',
    insLowFocus2: 'Keep the microphone close and make sure it is not muted.',
    insLowNext: 'Record again and read the text aloud from start to finish.',
    insEmptySummary: 'No words could be recognised in this recording, so it could not be checked.',
    insEmptyFocus1: 'Speak clearly in English at a steady volume.',
    insEmptyFocus2: 'Reduce background noise if you can.',
    insEmptyNext: 'Record again in a quiet place.',
    aiLabel: 'AI feedback, based on your scores',
    ruleLabel: 'Summary based on your scores',
    nextStep: 'Next step',
    coachPlaceholder: 'Well done for finishing this take! Every run-through makes the next one easier. Read the focus point below, then give it one more try.'
  },
  gate: {
    title: 'Record your baseline voice',
    msg: 'We compare your pitch and pauses with your own voice. Read the passage below once, in a natural voice. It takes about 30 seconds.',
    passageLabel: 'Read this passage aloud',
    passage: 'Good morning, everyone, and thank you for joining me today. My name is Alex, and I would like to share a short story about learning to speak with confidence. At first, my voice shook, and my words felt too fast. Slowly, I learned to breathe, to pause, and to look at my audience. Now, each time I speak, I try to be clear, calm, and kind. Thank you for listening.',
    note: 'Your baseline is only used to compare your pitch and pauses. You can record it again in Profile.',
    agree: 'Agree and continue to record', logout: 'No record and log out', done: 'Continue'
  },
  tip: {
    wrong: 'Wrong word: heard as a different word. Counts against Accuracy.',
    near: 'Close match: heard as a close-sounding word. Counts in Clarity, not Accuracy.',
    missing: 'Skipped: not found in the transcript. Counts against Accuracy.',
    fillerAfter: 'Filler word “{f}” right after it. Counts in Fluency.',
    hesAfter: 'Hesitation pause of {d} s right after it. Counts in Fluency.',
    forgotAfter: 'Long pause of {d} s right after it (maybe a forgotten word). Counts in Fluency.',
    after: 'After “{w}”',
    hes: 'Hesitation pause of {d} s: 0.5 s or more, not at punctuation. Counts in Fluency.',
    forgot: 'Long pause of {d} s: 1.2 s or more, maybe a forgotten word. Counts in Fluency.',
    filler: 'Filler word “{f}”. Counts in Fluency.',
    wrongT: 'wrong word', nearT: 'close match', missT: 'skipped'
  },
  part: {
    view: 'View details', title: 'Score details', tabsLabel: 'Score parts', weight: 'Weight in the overall score: {w}',
    band_good: 'Strong', band_mid: 'Fair', band_low: 'Needs work',
    assess: 'Assessment', measured: 'What we measured', suggest: 'Suggestions', review: 'Words to review',
    reviewHint: 'Click a word to hear it in the recording.', more: '+{n} more', nothing: 'Nothing to fix here. Keep practising to confirm it.',
    colMeasure: 'Measure', colNote: 'What it means', colCount: 'Count', colResult: 'Your result', colTarget: 'Target', colScore: 'Part score',
    A_good: 'Almost every word of the script was heard as written ({ok} of {total}).',
    A_mid: 'Most words match the script, but {bad} of {total} were wrong or skipped.',
    A_low: '{bad} of {total} words were wrong or skipped. Your reading and the script differ quite a lot.',
    A_total: 'Words in the script', A_totalH: 'Every word you were asked to read',
    A_wrong: 'Wrong words', A_wrongH: 'Heard as a different word',
    A_miss: 'Skipped words', A_missH: 'Not found in the transcript',
    A_near: 'Close matches', A_nearH: 'Counted in Clarity, not here',
    A_formula: 'Accuracy = 100 × (1 − {bad} ÷ {total}) = {a}. Filler words are not counted here; they are in Fluency.',
    A_tipWrong: 'Re-read the {n} word(s) marked red, slowly, then read the whole sentence again.',
    A_tipMiss: '{n} word(s) were skipped. Keep your eyes one phrase ahead of your voice so no word gets lost.',
    F_good: 'Your pace, pauses and filler words are steady.',
    F_mid: 'Your delivery is fairly steady, with some points to smooth out.',
    F_low: 'Your delivery is uneven and needs work.',
    F_watch: 'Look at: {areas}.',
    F_pace: 'Pace', F_paceT: 'Target: 130 to 160 WPM',
    F_pause: 'Hesitation pauses', F_pauseT: 'Aim for 1 or fewer per minute',
    F_filler: 'Filler words', F_fillerT: 'Aim for under 4% of your words',
    F_avg: 'Fluency is the average of these three part scores.',
    F_paceRead: '{n} of {total} five-second windows were inside the 130 to 160 target. The pace score uses your average pace over the whole recording.',
    F_pauseRead: 'Longest pause: {d} s at {t}. {h} of {n} pauses were hesitations.',
    F_tipSlow: 'Your pace was {v} WPM, below the 130 to 160 target. Join phrases together instead of stopping between them.',
    F_tipFast: 'Your pace was {v} WPM, above the 130 to 160 target. Breathe at each comma and full stop.',
    F_tipPause: '{v} hesitation pauses per minute (aim for 1 or fewer). Read each sentence silently once before saying it, so the next words are ready.',
    F_tipFiller: 'Filler words were {v}% of your words (aim for under 4%). Swap “um” for a short silent pause.',
    P_good: 'Your words were recognised clearly and your pitch has good variety.',
    P_mid: 'Fair: some words were heard as close matches, or your pitch is fairly flat.',
    P_low: 'Clarity and pitch variety both need work.',
    P_watch: 'Look at: {areas}.',
    P_clar: 'Clarity (as recognised)', P_clarT: 'Fewer close matches is better',
    P_pitch: 'Pitch range', P_pitchT: 'Aim for 6 st or more. Under 4 st sounds monotone',
    P_avg: 'Clarity and intonation is the average of these two part scores.',
    P_tipNear: '{n} word(s) were heard as close matches. Replay them in the transcript, then say each one slowly and clearly. A close match can also come from the microphone or background noise, not only from pronunciation.',
    P_tipMono: 'Your pitch range was {v} st, which sounds monotone (under 4 st). Pick two key words in each sentence and give them more rise or fall.',
    P_tipRange: 'Your pitch range was {v} st. Aim for 6 st or more by lifting your voice on key words.',
    S_good: 'Almost every sentence keeps the meaning of the script.',
    S_mid: 'Most sentences keep the meaning, but {n} of {total} drifted.',
    S_low: '{n} of {total} sentences drifted from the meaning of the script.',
    S_ok: 'Sentences matching meaning', S_okT: 'Similarity of 0.82 or more',
    S_listTitle: 'Similarity per sentence', S_listHint: 'Rephrasing is fine when the meaning stays the same. Sentences below 0.82 are marked red.',
    S_tipDrift: 'Check the {n} red sentence(s): skipped or replaced key words change the meaning.'
  },
  chart: { table: 'View as table', time: 'Time', value: 'Value', type: 'Type', minutes: 'Minutes' }
};
TEXT.wc = { title: 'Practice', heardAs: 'Heard as: {x}', hearIt: 'Hear it', hearYourself: 'Hear yourself', tryAgain: 'Try again', stop: 'Stop', checking: 'Checking...', recognised: 'Recognised as {x}', close: 'Close, listen again', heard: 'Heard {y}', notHeard: "We couldn't hear that, try again", sampleVoice: 'Sample voice from your browser', practiceOnly: 'Practice only: your score does not change', noVoice: 'No English voice is available', practiceSentence: 'Practice this sentence', stillWrong: 'Still to practise: {x}', errMic: 'Microphone unavailable. Check your permissions and device.', errRate: 'Too many attempts. Please try again later.', errStt: 'Speech recognition is unavailable. Try again later.', errNet: 'Could not check the recording. Try again.', closeLabel: 'Close practice', timer: '{elapsed} / {max}' };
TEXT.script.page = 'p. {n}';
TEXT.report.playFrom = 'Play from {t}';
export const TOPICS = TEXT.topics;


/* ---------- text helpers ---------- */
export function T(path, vars) {
  const v = path.split('.').reduce((o, k) => (o == null ? o : o[k]), TEXT);
  if (v == null) { console.error('Missing TEXT key: ' + path); return path; }
  if (typeof v !== 'string') return v;
  return vars ? v.replace(/\{(\w+)\}/g, (_, k) => (vars[k] != null ? vars[k] : '{' + k + '}')) : v;
}
export function applyText(root) {
  root = root || document;
  $$('[data-t]', root).forEach(e => { e.textContent = T(e.getAttribute('data-t')); });
  $$('[data-t-ph]', root).forEach(e => { e.setAttribute('placeholder', T(e.getAttribute('data-t-ph'))); });
  $$('[data-t-title]', root).forEach(e => { e.setAttribute('title', T(e.getAttribute('data-t-title'))); });
  $$('[data-t-aria]', root).forEach(e => { e.setAttribute('aria-label', T(e.getAttribute('data-t-aria'))); });
}
