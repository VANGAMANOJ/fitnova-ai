/* ═══════════════════════════════════════════════════════════════════════
   FitAI v4 – Frontend
   New in v4:
     • Dark / Light mode toggle (localStorage persisted)
     • Auto workout timer – starts on first valid movement, pauses on idle
     • All 26 fitness goals passed to Daily Plan
     • PDF downloads as nutrition_plan.pdf
   ═══════════════════════════════════════════════════════════════════════ */

// ── Global state ──────────────────────────────────────────────────────────
const S = {
  exercise:     'squat',
  cameraOn:     false,
  processing:   false,
  voiceOn:      true,
  sessionId:    'sid_' + Date.now(),
  repMap:       {},
  totalReps:    parseInt(localStorage.getItem('fitai_totalReps') || '0'),
  streak:       parseInt(localStorage.getItem('fitai_streak')    || '1'),
  sessionStart: Date.now(),
  restTimer:    null,
  loopId:       null,
  lastFeedback: '',
  profile:      null,
  timeline:     [],
  planDone:     {},

  // Workout timer (starts on first detected movement, pauses on idle)
  workoutTimerSec:  0,
  workoutTimerId:   null,
  workoutRunning:   false,
  lastMovementTime: 0,
  IDLE_PAUSE_MS:    4000,   // pause after 4 s of no movement detection
};

// ── Exercise metadata ──────────────────────────────────────────────────────
const EX_META = {
  squat:          { icon:'squat', name:'Squat' },
  pushup:         { icon:'pushup', name:'Push-up' },
  bicep_curl:     { icon:'bicep', name:'Bicep Curl' },
  lunge:          { icon:'lunge', name:'Lunge' },
  shoulder_press: { icon:'shoulder', name:'Shoulder Press' },
  plank:          { icon:'plank', name:'Plank' },
  jumping_jacks:  { icon:'jacks', name:'Jumping Jacks' },
  high_knees:     { icon:'knees', name:'High Knees' },
  arm_raises:     { icon:'armraise', name:'Arm Raises' },
  side_lunge:     { icon:'sidelunge', name:'Side Lunge' },
};

const INSTRUCTIONS = {
  squat:          'Feet shoulder-width · Lower hips below knees · Chest up',
  pushup:         'Plank position · Hands under shoulders · Lower chest to floor',
  bicep_curl:     'Elbow pinned to side · Curl to shoulder · Lower slowly',
  lunge:          'Step forward · Rear knee toward floor · Torso upright',
  shoulder_press: 'Weights at shoulders · Core braced · Press straight overhead',
  plank:          'Forearms on floor · Body straight line · Hold as long as possible',
  jumping_jacks:  'Feet together · Jump wide arms+legs · Return to start',
  high_knees:     'Run in place · Drive knees to hip height · Stay on toes',
  arm_raises:     'Arms at sides · Raise to shoulder height · Lower with control',
  side_lunge:     'Step wide sideways · Bend one knee · Keep torso upright',
};

const FOOD_EMOJIS = {}; // no emoji — text only

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const webcamEl      = $('webcam');
const procImgEl     = $('processedFrame');
const noCamEl       = $('noCam');
const startBtn      = $('startBtn');
const fbText        = $('fbText');
const fbIcon        = $('fbIcon');
const fbStrip       = $('feedbackStrip');
const repNumEl      = $('repNum');
const repLblEl      = $('repLbl');
const sAngle        = $('sAngle');
const sCorrect      = $('sCorrect');
const sWrong        = $('sWrong');
const sForm         = $('sForm');
const accFill       = $('accFill');
const accPct        = $('accPct');
const cabFill       = $('cabFill');
const cabPct        = $('cabPct');
const corrList      = $('corrList');
const statusDot     = $('statusDot');
const statusText    = $('statusText');
const streakEl      = $('streakEl');
const totalRepsEl   = $('totalRepsEl');
const sessionTimEl  = $('sessionTimer');
const workoutTimEl  = $('workoutTimerEl');
const timerDot      = $('timerDot');

// ══════════════════════════════════════════════════════════════════════════
//  DARK MODE
// ══════════════════════════════════════════════════════════════════════════
function applyDark(dark) {
  document.body.classList.toggle('dark', dark);
  const icon = $('darkIcon');
  const btn  = $('darkToggle');
  if (!icon || !btn) return;
  if (dark) {
    icon.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>';
    btn.querySelector('span:last-child').textContent = ' Light';
  } else {
    icon.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    btn.querySelector('span:last-child').textContent = ' Dark';
  }
  // Logo mode switching handled by CSS body.dark / body:not(.dark) selectors automatically
}

function toggleDark() {
  const dark = !document.body.classList.contains('dark');
  localStorage.setItem('fitai_dark', dark ? '1' : '0');
  applyDark(dark);
  // Sync dropdown icon
  const el = document.getElementById('ddDarkIcon');
  if (el) el.innerHTML = dark ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
}

// ══════════════════════════════════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', async () => {
  // Apply saved theme immediately
  // Only apply saved theme if user explicitly set one — null means no choice made
  const savedTheme = localStorage.getItem('fitai_dark');
  if (savedTheme !== null) {
    applyDark(savedTheme === '1');
  }
  // Default stays light (no class = light mode)

  updateStreakDisplay();
  totalRepsEl.textContent = S.totalReps;
  startSessionTimer();
  updateStreak();
  renderWorkoutTimer();
  await loadProfile();

  // Handle deep-link tab (?tab=...)
  const tab = new URLSearchParams(location.search).get('tab');
  if (tab) {
    const btn = document.querySelector(`[data-tab="${tab}"]`);
    if (btn) switchTab(tab, btn);
  }
});

function updateStreakDisplay() {
  if (streakEl)           streakEl.textContent     = S.streak + ' day' + (S.streak !== 1 ? 's' : '');
  if ($('dashStreak'))    $('dashStreak').textContent = S.streak;
}

function updateStreak() {
  const last  = localStorage.getItem('fitai_lastDate');
  const today = new Date().toDateString();
  if (last && last !== today) {
    const diff = (new Date(today) - new Date(last)) / 86400000;
    S.streak = diff === 1 ? S.streak + 1 : 1;
    localStorage.setItem('fitai_streak', S.streak);
  }
  localStorage.setItem('fitai_lastDate', today);
  updateStreakDisplay();
}

function startSessionTimer() {
  setInterval(() => {
    const e = Math.floor((Date.now() - S.sessionStart) / 1000);
    if (sessionTimEl)
      sessionTimEl.textContent =
        String(Math.floor(e / 60)).padStart(2, '0') + ':' + String(e % 60).padStart(2, '0');
  }, 1000);
}

async function loadProfile() {
  try {
    const d = await (await fetch('/api/get_profile')).json();
    if (d.profile) {
      S.profile = d.profile;
      renderDailyPlan(d.plan, d.diet);
    }
  } catch(e) {}
}

// ══════════════════════════════════════════════════════════════════════════
//  WORKOUT TIMER  (auto-start on first movement, auto-pause on idle)
// ══════════════════════════════════════════════════════════════════════════
function startWorkoutTimer() {
  if (S.workoutRunning) return;
  S.workoutRunning  = true;
  S.lastMovementTime = Date.now();
  if (timerDot) timerDot.classList.add('running');
  S.workoutTimerId = setInterval(() => {
    // Pause if no movement for IDLE_PAUSE_MS
    if (Date.now() - S.lastMovementTime > S.IDLE_PAUSE_MS) {
      pauseWorkoutTimer();
      return;
    }
    S.workoutTimerSec++;
    renderWorkoutTimer();
  }, 1000);
}

function pauseWorkoutTimer() {
  if (!S.workoutRunning) return;
  S.workoutRunning = false;
  clearInterval(S.workoutTimerId);
  if (timerDot) timerDot.classList.remove('running');
}

function resetWorkoutTimer() {
  pauseWorkoutTimer();
  S.workoutTimerSec = 0;
  renderWorkoutTimer();
}

function renderWorkoutTimer() {
  const s = S.workoutTimerSec;
  if (workoutTimEl)
    workoutTimEl.textContent =
      String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

function touchMovement() {
  // Called whenever a valid pose is detected
  S.lastMovementTime = Date.now();
  if (!S.workoutRunning) startWorkoutTimer();
}

// ══════════════════════════════════════════════════════════════════════════
//  TAB SWITCHING
// ══════════════════════════════════════════════════════════════════════════
function switchTab(tabId, btnEl) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-tab:not([href])').forEach(b => b.classList.remove('active'));
  const tabEl = $('tab-' + tabId);
  if (tabEl) tabEl.classList.add('active');
  if (btnEl) btnEl.classList.add('active');
  if (tabId === 'dashboard') refreshDashboard();
  if (tabId === 'dailyplan') checkDailyPlan();
}

// ══════════════════════════════════════════════════════════════════════════
//  EXERCISE SELECTION
// ══════════════════════════════════════════════════════════════════════════
function selectExercise(el) {
  document.querySelectorAll('.ex-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  S.exercise = el.dataset.ex;

  const meta = EX_META[S.exercise] || { name: S.exercise, icon: '•' };
  $('exBadge').textContent = meta.name.toUpperCase();
  $('dashEx').textContent  = meta.name;
  $('instrStrip').textContent =
    (INSTRUCTIONS[S.exercise] || 'Full body in frame · Good lighting') + ' · Space=Start · R=Reset';

  resetDisplayOnly();
  resetWorkoutTimer();
}

function resetDisplayOnly() {
  updateRepDisplay(S.repMap[S.exercise] || 0);
  sAngle.textContent   = '—°';
  sCorrect.textContent = 0;
  sWrong.textContent   = 0;
  sForm.textContent    = '—'; sForm.className = 'stat-val form-tag';
  accFill.style.width  = '0%'; accPct.textContent = '0%';
  cabFill.style.width  = '0%'; cabPct.textContent = '—';
  corrList.innerHTML   = '<div class="no-corr">Great form so far – keep going!</div>';
  fbText.textContent   = 'Press Start, then begin exercising.';
  fbStrip.className    = 'feedback-strip';
}

// ══════════════════════════════════════════════════════════════════════════
//  CAMERA
// ══════════════════════════════════════════════════════════════════════════
async function toggleCamera() {
  S.cameraOn ? stopCamera() : await startCamera();
}

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width:{ideal:640}, height:{ideal:480}, facingMode:'user' },
      audio: false,
    });
    webcamEl.srcObject = stream;
    await webcamEl.play();
    noCamEl.style.display  = 'none';
    webcamEl.style.display = 'block';
    S.cameraOn = true;
    startBtn.textContent = '⏸ Stop';
    setStatus('active', 'Camera ON');
    startLoop();
    speak('Camera started. Begin exercising when ready.');
    addTimeline('Camera started', '');
  } catch(e) {
    alert('Camera error: ' + e.message + '\n\nMust use HTTPS or localhost.');
  }
}

function stopCamera() {
  if (webcamEl.srcObject) webcamEl.srcObject.getTracks().forEach(t => t.stop());
  webcamEl.srcObject = null;
  webcamEl.style.display   = 'block';
  procImgEl.style.display  = 'none';
  noCamEl.style.display    = 'flex';
  S.cameraOn = false;
  startBtn.textContent = '▶ Start';
  stopLoop();
  pauseWorkoutTimer();
  setStatus('', 'Ready');
}

function setStatus(cls, txt) {
  statusDot.className    = 'status-dot' + (cls ? ' ' + cls : '');
  statusText.textContent = txt;
}

// ══════════════════════════════════════════════════════════════════════════
//  FRAME CAPTURE LOOP  (~6 fps)
// ══════════════════════════════════════════════════════════════════════════
function startLoop() {
  stopLoop();
  S.loopId = setInterval(captureFrame, 165);
}
function stopLoop() {
  if (S.loopId) { clearInterval(S.loopId); S.loopId = null; }
}

async function captureFrame() {
  if (!S.cameraOn || S.processing || webcamEl.readyState < 2) return;
  S.processing = true;

  const cap = document.createElement('canvas');
  cap.width  = 320; cap.height = 240;
  const ctx  = cap.getContext('2d');
  ctx.translate(320, 0); ctx.scale(-1, 1);          // mirror to match user view
  ctx.drawImage(webcamEl, 0, 0, 320, 240);

  try {
    const res  = await fetch('/api/process_frame', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        frame:      cap.toDataURL('image/jpeg', 0.72),
        exercise:   S.exercise,
        session_id: S.sessionId,
      }),
    });
    const data = await res.json();
    handleResult(data);
  } catch(e) {
    console.error('Frame error:', e);
  } finally {
    S.processing = false;
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  RESULT HANDLING
// ══════════════════════════════════════════════════════════════════════════
function handleResult(data) {
  if (data.error) { console.error(data.error); return; }

  // Show processed frame with skeleton drawn by backend
  if (data.processed_frame) {
    webcamEl.style.display  = 'none';
    procImgEl.style.display = 'block';
    procImgEl.src = data.processed_frame;
  }

  if (!data.detected) {
    setFeedback('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>', data.feedback, '');
    setStatus('active', 'Searching…');
    return;
  }

  setStatus('live', 'Detecting');

  // ── Trigger workout timer on valid movement ──
  touchMovement();

  // ── Feedback ──
  if (data.feedback !== S.lastFeedback) {
    S.lastFeedback = data.feedback;
    setFeedback(data.form_ok ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"/></svg>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>', data.feedback, data.form_ok ? 'ok' : 'bad');
    if (S.voiceOn) speak(data.feedback);
    if (!data.form_ok) checkInjury(data.feedback);
  }

  // ── Rep counting ──
  const prev = S.repMap[S.exercise] || 0;
  if (data.reps > prev) {
    S.repMap[S.exercise] = data.reps;
    S.totalReps += (data.reps - prev);
    localStorage.setItem('fitai_totalReps', S.totalReps);
    totalRepsEl.textContent = S.totalReps;
    updateSidebarRep(S.exercise, data.reps);
    bumpRep();
    addTimeline(
      `${EX_META[S.exercise]?.name || S.exercise}: rep ${data.reps}`,
      data.form_ok ? 'Good form' : 'Fix form'
    );
    updateAchievements();
  }
  updateRepDisplay(data.reps);

  // ── Stats panel ──
  sAngle.textContent   = data.angle + '°';
  sCorrect.textContent = data.correct_reps || 0;
  sWrong.textContent   = data.wrong_reps   || 0;
  sForm.textContent    = data.form_ok ? 'CORRECT' : 'FIX FORM';
  sForm.className      = 'stat-val form-tag ' + (data.form_ok ? 'ok' : 'bad');

  const acc = Math.round(data.accuracy);
  accFill.style.width = acc + '%';
  accPct.textContent  = acc + '%';
  cabFill.style.width = acc + '%';
  cabPct.textContent  = acc + '%';

  const col = acc > 75 ? '#00c87a' : acc > 40 ? '#ff9500' : '#ff3b5c';
  accFill.style.background = `linear-gradient(90deg,${col},${col}bb)`;
  cabFill.style.background = `linear-gradient(90deg,${col},${col}bb)`;

  // ── Live corrections ──
  if (data.mistakes && data.mistakes.length) {
    corrList.innerHTML = data.mistakes.map(m =>
      `<div class="corr-item slide-in"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ${m}</div>`).join('');
  } else if (data.form_ok) {
    corrList.innerHTML = '<div class="no-corr">Great form so far – keep going!</div>';
  }
}

function setFeedback(icon, text, cls) {
  fbIcon.textContent = icon;
  fbText.textContent = text;
  fbStrip.className  = 'feedback-strip' + (cls ? ' ' + cls : '');
}

function updateRepDisplay(reps) {
  repNumEl.textContent = reps;
  repLblEl.textContent = S.exercise === 'plank' ? 'SECONDS' : 'REPS';
}

function bumpRep() {
  repNumEl.classList.remove('bump');
  void repNumEl.offsetWidth;
  repNumEl.classList.add('bump');
  setTimeout(() => repNumEl.classList.remove('bump'), 380);
}

function updateSidebarRep(ex, reps) {
  const el = $('sb_' + ex);
  if (el) el.textContent = ex === 'plank' ? reps + 's' : reps;
}

// ══════════════════════════════════════════════════════════════════════════
//  RESET / SUMMARY
// ══════════════════════════════════════════════════════════════════════════
function resetExercise() {
  fetch('/api/reset_exercise', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ session_id: S.sessionId, exercise: S.exercise }),
  });
  S.repMap[S.exercise] = 0;
  resetDisplayOnly();
  updateSidebarRep(S.exercise, 0);
  resetWorkoutTimer();
  speak('Exercise reset. Ready to go again.');
}

async function showSummaryModal() {
  $('summaryModal').style.display = 'flex';
  $('modalBody').innerHTML = '<p style="color:var(--text2)">Loading…</p>';
  try {
    const d = await (await fetch('/api/get_summary', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ session_id: S.sessionId, exercise: S.exercise }),
    })).json();
    const name    = EX_META[S.exercise]?.name || S.exercise;
    const acColor = d.accuracy>75 ? 'var(--green)' : d.accuracy>40 ? 'var(--orange)' : 'var(--red)';
    $('modalBody').innerHTML = `
      <div class="sum-row"><span>Exercise</span><strong>${name}</strong></div>
      <div class="sum-row"><span>Total Reps</span><strong>${d.total_reps}</strong></div>
      <div class="sum-row"><span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="20 6 9 17 4 12"/></svg> Correct Reps</span><strong style="color:var(--green)">${d.correct_reps}</strong></div>
      <div class="sum-row"><span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Fix-Form Reps</span><strong style="color:var(--red)">${d.wrong_reps}</strong></div>
      <div class="sum-row"><span>Form Accuracy</span><strong style="color:${acColor}">${d.accuracy}%</strong></div>
      <div class="sum-row"><span>⏱ Workout Time</span><strong>${workoutTimEl?.textContent||'—'}</strong></div>
      ${d.mistakes.length ? `<div class="sum-mistakes" style="margin-top:10px">
        <div style="font-size:11.5px;font-weight:700;color:var(--text2);margin-bottom:6px">⚠️ Common Mistakes</div>
        ${d.mistakes.map(m=>`<span class="sum-tag">${m}</span>`).join('')}
      </div>` : '<div style="color:var(--green);margin-top:10px;font-weight:600">🎉 No form mistakes! Excellent.</div>'}
    `;
  } catch(e) {
    $('modalBody').innerHTML = '<p>Error loading summary.</p>';
  }
}

function closeModal() { $('summaryModal').style.display = 'none'; }

// ══════════════════════════════════════════════════════════════════════════
//  REST TIMER
// ══════════════════════════════════════════════════════════════════════════
function startRest(sec) {
  const section = $('restSection');
  const numEl   = $('restNum');
  section.style.display = 'block';
  let remaining = sec;
  numEl.textContent = remaining;
  speak('Rest for ' + sec + ' seconds.');
  if (S.restTimer) clearInterval(S.restTimer);
  S.restTimer = setInterval(() => {
    remaining--;
    numEl.textContent = remaining;
    if (remaining <= 0) {
      clearInterval(S.restTimer); S.restTimer = null;
      section.style.display = 'none';
      speak("Rest over – let's go!");
    }
  }, 1000);
}

function skipRest() {
  if (S.restTimer) { clearInterval(S.restTimer); S.restTimer = null; }
  $('restSection').style.display = 'none';
}

// ══════════════════════════════════════════════════════════════════════════
//  INJURY ALERT
// ══════════════════════════════════════════════════════════════════════════
const INJURY_WORDS = ['arch','sag','cave','lean','drift','wide','pain','half','inward'];
let injTimeout;
function checkInjury(msg) {
  if (INJURY_WORDS.some(k => msg.toLowerCase().includes(k))) {
    const el = $('injuryToast');
    $('injuryMsg').textContent = msg;
    el.style.display = 'flex';
    clearTimeout(injTimeout);
    injTimeout = setTimeout(() => el.style.display = 'none', 5500);
  }
}

// ══════════════════════════════════════════════════════════════════════════
//  VOICE
// ══════════════════════════════════════════════════════════════════════════
let speechQ;
function speak(txt) {
  if (!S.voiceOn || !window.speechSynthesis) return;
  clearTimeout(speechQ);
  speechQ = setTimeout(() => {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(txt);
    u.rate = 1.05; u.pitch = 1; u.volume = 0.88;
    window.speechSynthesis.speak(u);
  }, 180);
}

function toggleVoice() {
  S.voiceOn = !S.voiceOn;
  $('voiceBtn').innerHTML = S.voiceOn ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg> Voice' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg> Voice';
  if (!S.voiceOn) window.speechSynthesis?.cancel();
}

// ══════════════════════════════════════════════════════════════════════════
//  DAILY PLAN TAB
// ══════════════════════════════════════════════════════════════════════════
function checkDailyPlan() {
  if (S.profile) {
    $('planNoProfile').style.display = 'none';
    $('planContent').style.display   = 'block';
  } else {
    $('planNoProfile').style.display = 'flex';
    $('planContent').style.display   = 'none';
  }
}

function renderDailyPlan(plan, diet) {
  if (!plan || !diet) return;
  $('planNoProfile').style.display = 'none';
  $('planContent').style.display   = 'block';

  const h = new Date().getHours();
  $('phcGreeting').textContent = h < 12 ? 'Good morning!' : h < 17 ? 'Good afternoon!' : 'Good evening!';
  $('phcName').textContent     = `${S.profile?.name || 'Athlete'}'s Plan`;
  $('phcGoal').textContent     = plan.label || diet.goal;

  const totalSets = plan.workout.reduce((a, e) => a + (e.sets || 0), 0);
  $('phcExCount').textContent  = plan.workout.length;
  $('phcTotalSets').textContent = totalSets;
  $('phcDuration').textContent = `~${Math.max(20, totalSets * 3)} min`;

  $('warmupList').innerHTML   = plan.warmup.map(e  => buildPlanRow(e, 'wu')).join('');
  $('workoutList').innerHTML  = plan.workout.map(e => buildPlanRow(e, 'wo')).join('');
  $('cooldownList').innerHTML = plan.cooldown.map(e => `
    <div class="plan-ex-row" style="cursor:default">
      <span class="per-icon">—</span>
      <div class="per-info"><div class="per-name">${e.name}</div><div class="per-meta">${e.duration||''}</div></div>
    </div>`).join('');

  $('planProtRange').textContent = diet.protein_range;
  $('planProtNote').textContent  = `per day (based on ${S.profile?.weight||'—'} kg body weight)`;

  const m = diet.meals;
  $('planMealList').innerHTML = [
    ['Breakfast', m.breakfast], ['Lunch', m.lunch],
    ['Snack', m.snack], ['Dinner', m.dinner], ['Before Bed', m.pre_bed],
  ].map(([t,c]) => `<div class="mpl-row"><span class="mpl-time">${t}</span><span class="mpl-food">${c}</span></div>`).join('');

  $('planFoodGrid').innerHTML = (m.foods || []).map(f =>
    `<div class="food-pill">${f}</div>`).join('');
}

function buildPlanRow(ex, type) {
  const key  = ex.key || '';
  const meta = EX_META[key] || { icon:'•', name: ex.name };
  const done = S.planDone[key + type];
  const reps = ex.reps ? `${ex.sets} × ${ex.reps}` : '';
  return `<div class="plan-ex-row ${done?'done':''}" id="planrow_${key}_${type}">
    <span class="per-icon">${meta.icon}</span>
    <div class="per-info">
      <div class="per-name">${ex.name}</div>
      <div class="per-meta">${reps}${ex.rest?' · Rest '+ex.rest:''}</div>
    </div>
    ${key ? (done
      ? '<span class="per-done">✓</span>'
      : `<button class="per-start" onclick="startFromPlan('${key}','${type}')">▶ Start</button>`)
    : ''}
  </div>`;
}

function startFromPlan(exKey, type) {
  switchTab('trainer', document.querySelector('[data-tab="trainer"]'));
  const exItem = document.querySelector(`.ex-item[data-ex="${exKey}"]`);
  if (exItem) { selectExercise(exItem); exItem.scrollIntoView({ behavior:'smooth', block:'nearest' }); }
  S.planDone[exKey + type] = true;
  const row = $(`planrow_${exKey}_${type}`);
  if (row) {
    row.classList.add('done');
    const btn = row.querySelector('.per-start');
    if (btn) { const sp=document.createElement('span'); sp.className='per-done'; sp.textContent="✓"; sp.textContent="✓"; btn.replaceWith(sp); }
  }
  speak(`Starting ${EX_META[exKey]?.name || exKey}. Get into position.`);
}

// ══════════════════════════════════════════════════════════════════════════
//  DASHBOARD TAB
// ══════════════════════════════════════════════════════════════════════════
const QUOTES = [
  '"The only bad workout is the one that didn\'t happen." — Fitnova AI',
  '"Discipline is choosing between what you want now and what you want most."',
  '"Strength doesn\'t come from what you can do. It comes from overcoming what you thought you couldn\'t."',
  '"Take care of your body. It\'s the only place you have to live." — Jim Rohn',
  '"Your body can stand almost anything. It\'s your mind you have to convince."',
  '"Push yourself, because no one else is going to do it for you."',
];

function buildWeeklyHeatmap() {
  const row = $('heatmapRow'); if (!row) return;
  const days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  const today = new Date().getDay();
  const todayIdx = today === 0 ? 6 : today - 1;
  row.innerHTML = days.map((d, i) => {
    const isToday = i === todayIdx;
    const hasSess = isToday && S.totalReps > 0;
    const lvl = hasSess ? (S.totalReps > 50 ? 3 : S.totalReps > 20 ? 2 : 1) : 0;
    return `<div class="hm-day">
      <div class="hm-day-label">${d}</div>
      <div class="hm-cell level-${lvl}" title="${isToday?'Today':''}"></div>
    </div>`;
  }).join('');
}

async function refreshDashboard() {
  $('dashTotalReps').textContent = S.totalReps;
  $('dashStreak').textContent    = S.streak;

  // Random motivational quote
  const qEl = $('dashQuote');
  if (qEl) qEl.textContent = '"' + QUOTES[Math.floor(Math.random() * QUOTES.length)].replace(/^"|"$/g,'') + '"';

  // Estimated calories (rough: ~5 cal per rep)
  const calEl = $('dashCalories');
  if (calEl) calEl.textContent = Math.round(S.totalReps * 5);

  // Active time
  const atEl = $('dashActiveTime');
  if (atEl) {
    const mins = Math.floor(S.workoutTimerSec / 60);
    atEl.textContent = mins > 0 ? mins + 'm' : S.workoutTimerSec + 's';
  }

  buildWeeklyHeatmap();

  try {
    const data = await (await fetch('/api/dashboard_stats?session_id=' + S.sessionId)).json();
    $('dashWorkouts').textContent  = data.workouts_completed;
    $('dashTotalReps').textContent = data.total_reps || S.totalReps;
    $('dashAccuracy').textContent  = (data.overall_accuracy || 0) + '%';

    const exList = $('dashExerciseList');
    if (data.exercises && data.exercises.length) {
      const maxR = Math.max(...data.exercises.map(e => e.reps), 1);
      const iconMap = {squat:'S',pushup:'P',bicep_curl:'B',lunge:'L',
        shoulder_press:'SP',plank:'PL',jumping_jacks:'JJ',high_knees:'HK',
        arm_raises:'AR',side_lunge:'SL'};
      exList.innerHTML = data.exercises.map((ex, i) => {
        const pct = Math.round(ex.reps / maxR * 100);
        const ic  = iconMap[ex.exercise.toLowerCase().replace(/ /g,'_')] || '💪';
        const accColor = ex.accuracy>75 ? 'var(--green)' : ex.accuracy>40 ? 'var(--orange)' : 'var(--red)';
        return `<div class="ex-breakdown-item" style="animation-delay:${i*0.07}s">
          <div class="exb-icon">${ic}</div>
          <div class="exb-info">
            <div class="exb-name">${ex.exercise} <span class="exb-acc" style="color:${accColor}">${ex.accuracy}% form</span></div>
            <div class="exb-bar-wrap"><div class="exb-bar-fill" style="width:${pct}%"></div></div>
          </div>
          <div class="exb-reps">${ex.reps}</div>
        </div>`;
      }).join('');
    } else {
      exList.innerHTML = `<div class="dash-empty-v2"><div class="dev2-icon">--</div><p>Start a workout to see your exercise breakdown here.</p></div>`;
    }
  } catch(e) {}

  // Timeline v2
  const tlEl = $('dashTimeline');
  if (S.timeline.length) {
    const fmt = ts => { const d=new Date(ts); return d.getHours()+':'+String(d.getMinutes()).padStart(2,'0'); };
    tlEl.innerHTML = S.timeline.slice(-8).reverse().map((item,i) => `
      <div class="tl-item" style="animation-delay:${i*0.06}s">
        <div class="tl-time">${fmt(item.ts)}</div>
        <div class="tl-body"><b>${item.text}</b>${item.sub ? ' — '+item.sub : ''}</div>
      </div>`).join('');
  } else {
    tlEl.innerHTML = `<div class="dash-empty-v2"><div class="dev2-icon">--</div><p>No activity yet. Start your workout!</p></div>`;
  }

  // Profile summary
  if (S.profile) {
    $('dashProfileCard').style.display = 'block';
    $('dashProfileSummary').innerHTML = [
      ['Name',   S.profile.name   || '—'],
      ['Age',    S.profile.age    || '—'],
      ['Weight', (S.profile.weight||'—') + ' kg'],
      ['Height', (S.profile.height||'—') + ' cm'],
      ['Goal',   (S.profile.fitness_goal||'—').replace(/_/g,' ')],
    ].map(([k,v]) => `<div class="ps-row"><span>${k}</span><b>${String(v).replace(/\b\w/g,c=>c.toUpperCase())}</b></div>`).join('');
  }

  updateAchievements();
}

function addTimeline(text, sub) {
  S.timeline.push({ text, sub, ts: Date.now() });
  if (S.timeline.length > 20) S.timeline.shift();
}

function updateAchievements() {
  const toggle = (id, unlock) => {
    const el = $(id); if (!el) return;
    const wasLocked = el.classList.contains('locked');
    el.className = 'ach-v2 ' + (unlock ? 'unlocked' : 'locked');
    if (unlock && wasLocked) {
      // Flash on unlock
      el.style.transform = 'scale(1.15)';
      setTimeout(() => el.style.transform = '', 400);
    }
  };
  const tr  = S.totalReps;
  const acc = parseFloat($('dashAccuracy')?.textContent) || 0;
  toggle('ach-10',     tr  >= 10);
  toggle('ach-50',     tr  >= 50);
  toggle('ach-100',    tr  >= 100);
  toggle('ach-streak', S.streak >= 3);
  toggle('ach-acc',    acc >= 80);
  toggle('ach-plank',  (S.repMap['plank'] || 0) >= 30);
  const unlocked = ['ach-10','ach-50','ach-100','ach-streak','ach-acc','ach-plank']
    .filter(id => $(id)?.classList.contains('unlocked')).length;
  const achCountEl = $('achCount');
  if (achCountEl) achCountEl.textContent = unlocked + ' / 6 unlocked';
}

// ══════════════════════════════════════════════════════════════════════════
//  KEYBOARD SHORTCUTS
// ══════════════════════════════════════════════════════════════════════════
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
  if (e.code === 'Space')  { e.preventDefault(); toggleCamera(); }
  if (e.code === 'KeyR')   resetExercise();
  if (e.code === 'KeyV')   toggleVoice();
  if (e.code === 'KeyS')   showSummaryModal();
  if (e.code === 'KeyD')   toggleDark();
  if (e.code === 'Escape') closeModal();
});

// ══════════════════════════════════════════════════════════════════════════
//  WELCOME PAGE
// ══════════════════════════════════════════════════════════════════════════


// ══════════════════════════════════════════════════════════════════════════
//  3-DOT MENU
// ══════════════════════════════════════════════════════════════════════════
function toggleDotsMenu() {
  const dd = document.getElementById('dotsDropdown');
  if (!dd) return;
  dd.classList.toggle('open');
}
function closeDotsMenu() {
  const dd = document.getElementById('dotsDropdown');
  if (dd) dd.classList.remove('open');
}
// Close on outside click
document.addEventListener('click', e => {
  const wrap = document.getElementById('dotsMenuWrap');
  if (wrap && !wrap.contains(e.target)) closeDotsMenu();
});
// Sync dark icon in dropdown
const _origToggle = window.toggleDark;
window.toggleDark = function() {
  _origToggle();
  const el = document.getElementById('ddDarkIcon');
  if (el) el.innerHTML = document.body.classList.contains('dark') ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
};

// Init welcome
document.addEventListener('DOMContentLoaded', () => {
  const wp = document.getElementById('welcomePage');
  // Always show on fresh load; skip only if user already dismissed in same session
  if (sessionStorage.getItem('fn_welcomed_session')) {
    if (wp) { wp.classList.add('hidden'); }
  }
});
function dismissWelcome() {
  const wp = document.getElementById('welcomePage');
  if (!wp) return;
  wp.classList.add('hiding');
  setTimeout(() => { wp.classList.add('hidden'); }, 560);
  sessionStorage.setItem('fn_welcomed_session', '1');
}

// ══════════════════════════════════════════════════════════════════════════
//  FEEDBACK MODAL
// ══════════════════════════════════════════════════════════════════════════
let _fbRating = 5;

function openFeedback() {
  document.getElementById('feedbackOverlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  setRating(5);
}
function closeFeedback() {
  document.getElementById('feedbackOverlay').classList.remove('open');
  document.body.style.overflow = '';
  document.getElementById('fbSuccess').style.display = 'none';
  document.getElementById('fbError').style.display   = 'none';
  document.getElementById('fbName').value = '';
  document.getElementById('fbMsg').value  = '';
}
function setRating(v) {
  _fbRating = v;
  document.querySelectorAll('.fb-star').forEach(s => {
    s.classList.toggle('active', parseInt(s.dataset.v) <= v);
  });
}
async function submitFeedback() {
  const name    = document.getElementById('fbName').value.trim();
  const message = document.getElementById('fbMsg').value.trim();
  const btn     = document.querySelector('.fb-submit-btn');
  btn.disabled  = true;
  btn.textContent = 'Submitting…';
  try {
    const res = await fetch('/api/submit_feedback', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name, rating: _fbRating, message })
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById('fbSuccess').style.display = 'block';
      document.getElementById('fbError').style.display   = 'none';
      btn.style.display = 'none';
      setTimeout(closeFeedback, 2200);
    } else {
      throw new Error(data.error || 'Failed');
    }
  } catch(e) {
    document.getElementById('fbError').style.display   = 'block';
    document.getElementById('fbError').textContent = e.message || 'Something went wrong.';
    document.getElementById('fbSuccess').style.display = 'none';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Submit Review';
  }
}
// Close on overlay click
document.getElementById('feedbackOverlay')?.addEventListener('click', e => {
  if (e.target.id === 'feedbackOverlay') closeFeedback();
});

// ══════════════════════════════════════════════════════════════════════════
//  ANNOUNCEMENT BANNER
// ══════════════════════════════════════════════════════════════════════════
(async () => {
  try {
    const res = await fetch('/api/announcement');
    const d = await res.json();
    if (d.announcement && d.announcement.trim()) {
      document.getElementById('annText').textContent = d.announcement;
      document.getElementById('annBanner').style.display = 'flex';
    }
  } catch(e) {}
})();

// ══════════════════════════════════════════════════════════════════════════
//  HIDDEN ADMIN PANEL — triggered by long-press OR triple-click on © text
// ══════════════════════════════════════════════════════════════════════════
let _adminOpen = false;
let _holdTimer = null;
let _clickCount = 0;
let _clickTimer = null;
let _adminCreds = null; // cached after login {u, p}
let _adminChart = null;

function openAdmin() {
  const ov = document.getElementById('adminOverlay');
  if (!ov) return;
  ov.classList.add('open');
  document.body.style.overflow = 'hidden';
  _adminOpen = true;
  if (_adminCreds) loadAdminDash();
}
function closeAdmin() {
  const ov = document.getElementById('adminOverlay');
  if (!ov) return;
  ov.classList.remove('open');
  document.body.style.overflow = '';
  _adminOpen = false;
  document.getElementById('adminLoginError').style.display = 'none';
}
function adminLogout() {
  _adminCreds = null;
  document.getElementById('adminDashScreen').style.display = 'none';
  document.getElementById('adminLoginScreen').style.display = 'block';
  document.getElementById('adminUser').value = '';
  document.getElementById('adminPass').value = '';
}

// Long-press + triple-click trigger
(function() {
  const el = document.getElementById('hiddenAdminTrigger');
  if (!el) return;

  // Long press (mobile)
  el.addEventListener('touchstart', () => {
    _holdTimer = setTimeout(() => { openAdmin(); }, 3000);
    el.classList.add('holding');
  }, { passive: true });
  el.addEventListener('touchend',   () => { clearTimeout(_holdTimer); el.classList.remove('holding'); });
  el.addEventListener('touchmove',  () => { clearTimeout(_holdTimer); el.classList.remove('holding'); });

  // Long press (desktop)
  el.addEventListener('mousedown', () => {
    _holdTimer = setTimeout(() => { openAdmin(); }, 3000);
    el.classList.add('holding');
  });
  el.addEventListener('mouseup',   () => { clearTimeout(_holdTimer); el.classList.remove('holding'); });
  el.addEventListener('mouseleave',() => { clearTimeout(_holdTimer); el.classList.remove('holding'); });

  // Triple-click (desktop)
  el.addEventListener('click', () => {
    _clickCount++;
    clearTimeout(_clickTimer);
    _clickTimer = setTimeout(() => { _clickCount = 0; }, 600);
    if (_clickCount >= 3) { _clickCount = 0; openAdmin(); }
  });
})();

// Close on overlay background click
document.getElementById('adminOverlay')?.addEventListener('click', e => {
  if (e.target.id === 'adminOverlay') closeAdmin();
});

// Admin Login
async function adminLogin() {
  const u = document.getElementById('adminUser').value.trim();
  const p = document.getElementById('adminPass').value.trim();
  const btn = document.querySelector('#adminLoginScreen .admin-btn');
  const errEl = document.getElementById('adminLoginError');
  if (!u || !p) { errEl.style.display = 'block'; errEl.textContent = 'Enter both fields'; return; }
  btn.disabled = true; btn.textContent = 'Checking…';
  try {
    const res = await fetch('/api/admin_stats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p })
    });
    const data = await res.json();
    if (data.ok) {
      _adminCreds = { u, p };
      errEl.style.display = 'none';
      document.getElementById('adminLoginScreen').style.display = 'none';
      document.getElementById('adminDashScreen').style.display = 'block';
      renderAdminDash(data);
    } else {
      errEl.style.display = 'block';
      errEl.textContent = 'Invalid credentials';
    }
  } catch(e) {
    errEl.style.display = 'block';
    errEl.textContent = 'Connection error. Try again.';
  } finally {
    btn.disabled = false; btn.textContent = 'Access Dashboard';
  }
}

async function loadAdminDash() {
  if (!_adminCreds) return;
  const res = await fetch('/api/admin_stats', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(_adminCreds)
  });
  const data = await res.json();
  if (data.ok) renderAdminDash(data);
}

function renderAdminDash(data) {
  // KPIs
  document.getElementById('akTotal').textContent  = data.total;
  document.getElementById('akToday').textContent  = data.today;
  document.getElementById('akWeek').textContent   = data.week;
  document.getElementById('akUniq').textContent   = data.unique;
  document.getElementById('akFb').textContent     = data.fb_count;
  document.getElementById('akRating').textContent = data.avg_rating + '';

  // Announcement
  document.getElementById('adminAnn').value = data.announcement || '';

  // Chart
  const canvas = document.getElementById('adminChart');
  if (canvas && window.Chart) {
    if (_adminChart) _adminChart.destroy();
    _adminChart = new Chart(canvas.getContext('2d'), {
      type: 'bar',
      data: {
        labels: data.daily_labels,
        datasets: [{ label: 'Visitors', data: data.daily_counts,
          backgroundColor: 'rgba(77,140,255,0.45)',
          borderColor: '#4d8cff', borderWidth: 2, borderRadius: 5 }]
      },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#0e0e0e' }, ticks: { color: '#444', font: { size: 10 } } },
          y: { grid: { color: '#0e0e0e' }, ticks: { color: '#444', font: { size: 10 }, stepSize: 1 } }
        }
      }
    });
  }

  // Reviews with delete button
  const rvEl = document.getElementById('adminReviews');
  if (data.reviews && data.reviews.length) {
    rvEl.innerHTML = data.reviews.map(r => {
      const stars = '★'.repeat(r.rating || 0) + '☆'.repeat(5 - (r.rating || 0));
      return `<div class="admin-rv-item" id="arv-${r.id}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div class="admin-rv-name">${r.name || 'Anonymous'} <span class="admin-rv-stars">${stars}</span></div>
            <div class="admin-rv-msg">${r.message || ''}</div>
            <div class="admin-rv-ts">${r.ts}</div>
          </div>
          <button class="admin-del-btn" onclick="deleteReview(${r.id})">Del</button>
        </div>
      </div>`;
    }).join('');
  } else {
    rvEl.innerHTML = '<div class="admin-empty">No reviews yet.</div>';
  }

  // Recent visits
  const visEl = document.getElementById('adminVisits');
  if (data.recent_visits && data.recent_visits.length) {
    visEl.innerHTML = data.recent_visits.map(v =>
      `<div class="admin-vi-item"><span class="admin-vi-path">${v.path}</span><span>${v.ip}</span><span>${v.ts.slice(-8)}</span></div>`
    ).join('');
  } else {
    visEl.innerHTML = '<div class="admin-empty">No visits logged yet.</div>';
  }
}

async function deleteReview(id) {
  if (!_adminCreds) return;
  if (!confirm('Delete this review?')) return;
  const res = await fetch('/api/delete_review', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: _adminCreds.u, password: _adminCreds.p, id })
  });
  const data = await res.json();
  if (data.ok) {
    const el = document.getElementById('arv-' + id);
    if (el) { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }
  }
}

async function saveAnnouncement() {
  if (!_adminCreds) return;
  const val = document.getElementById('adminAnn').value;
  await fetch('/fn-admin-2026/api/setting', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'announcement', value: val })
  });
  const ok = document.getElementById('adminAnnOk');
  ok.style.display = 'inline'; setTimeout(() => ok.style.display = 'none', 2500);
  // Refresh banner on page
  const banner = document.getElementById('annBanner');
  const text = document.getElementById('annText');
  if (val.trim()) { text.textContent = val; banner.style.display = 'flex'; }
  else { banner.style.display = 'none'; }
}

// Enter key on password field
document.getElementById('adminPass')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') adminLogin();
});

// ══════════════════════════════════════════════════════════════════════════
//  PUBLIC REVIEWS PAGE
// ══════════════════════════════════════════════════════════════════════════
async function loadPublicReviews() {
  const listEl = document.getElementById('publicReviewsList');
  if (!listEl) return;
  try {
    const res  = await fetch('/api/public_reviews');
    const data = await res.json();
    const reviews = data.reviews || [];

    if (!reviews.length) {
      listEl.innerHTML = '<div class="rv-empty"><div style="font-size:40px;margin-bottom:12px">💬</div><p>No reviews yet. Be the first!</p><button class="reviews-write-btn" onclick="openFeedback()" style="margin-top:14px">Write a Review</button></div>';
      return;
    }

    // Compute stats
    const total = reviews.length;
    const avg   = reviews.reduce((s, r) => s + (r.rating || 0), 0) / total;
    const counts = [1,2,3,4,5].map(v => reviews.filter(r => r.rating === v).length);

    // Stats bar
    document.getElementById('rsAvg').textContent = avg.toFixed(1);
    document.getElementById('rsStars').innerHTML = '★'.repeat(Math.round(avg)) + '☆'.repeat(5 - Math.round(avg));
    document.getElementById('rsCount').textContent = total + ' review' + (total !== 1 ? 's' : '');
    document.getElementById('rsBars').innerHTML = [5,4,3,2,1].map(v => {
      const pct = total ? Math.round(counts[v-1] / total * 100) : 0;
      return `<div class="rsbar-row">
        <span class="rsbar-lbl">${v}★</span>
        <div class="rsbar-wrap"><div class="rsbar-fill" style="width:${pct}%"></div></div>
        <span class="rsbar-pct">${counts[v-1]}</span>
      </div>`;
    }).join('');

    // Cards
    listEl.innerHTML = reviews.map((r, i) => {
      const stars = '★'.repeat(r.rating || 0) + '☆'.repeat(5 - (r.rating || 0));
      const initials = (r.name || 'A').substring(0, 2).toUpperCase();
      const colors = ['#4d8cff','#7b2ff7','#00c87a','#ff6b35','#ffc107'];
      const color = colors[i % colors.length];
      const date = new Date(r.ts).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' });
      return `<div class="rv-card" style="animation-delay:${i*0.06}s">
        <div class="rv-card-top">
          <div class="rv-avatar" style="background:${color}">${initials}</div>
          <div class="rv-meta">
            <div class="rv-name">${r.name || 'Anonymous'}</div>
            <div class="rv-date">${date}</div>
          </div>
          <div class="rv-stars">${stars}</div>
        </div>
        ${r.message ? `<div class="rv-msg">"${r.message}"</div>` : ''}
      </div>`;
    }).join('');

  } catch(e) {
    listEl.innerHTML = '<div class="rv-empty"><p>Could not load reviews.</p></div>';
  }
}

// Load reviews when tab is opened
const _origSwitchTab = window.switchTab || function(){};
window.switchTab = function(tabId, btnEl) {
  _origSwitchTab(tabId, btnEl);
  if (tabId === 'reviews') loadPublicReviews();
};

// Also reload after submitting feedback
const _origSubmit = window.submitFeedback;
window.submitFeedback = async function() {
  await _origSubmit?.();
  setTimeout(loadPublicReviews, 800);
};

// ══════════════════════════════════════════════════════════════════════════
//  ABOUT PAGE — MINI REVIEWS + FAQ
// ══════════════════════════════════════════════════════════════════════════
async function loadMiniReviews() {
  const el = document.getElementById('aboutMiniReviews');
  if (!el) return;
  try {
    const res  = await fetch('/api/public_reviews');
    const data = await res.json();
    const reviews = (data.reviews || []).slice(0, 6);
    if (!reviews.length) {
      el.innerHTML = '<div class="mr-no-reviews">No reviews yet — be the first! ⭐</div>';
      return;
    }
    const colors = ['#4d8cff','#7b2ff7','#00c87a','#ff6b35','#ffc107','#e91e8c'];
    el.innerHTML = reviews.map((r, i) => {
      const stars   = '★'.repeat(r.rating || 0) + '☆'.repeat(5 - (r.rating || 0));
      const initials = (r.name || 'A').slice(0, 2).toUpperCase();
      return `<div class="mr-card" style="animation-delay:${i * 0.07}s">
        <div class="mr-top">
          <div class="mr-avatar" style="background:${colors[i % colors.length]}">${initials}</div>
          <div><div class="mr-name">${r.name || 'Anonymous'}</div><div class="mr-stars">${stars}</div></div>
        </div>
        ${r.message ? `<div class="mr-msg">"${r.message}"</div>` : ''}
      </div>`;
    }).join('');
  } catch(e) {
    el.innerHTML = '<div class="mr-no-reviews">Could not load reviews.</div>';
  }
}

function toggleFaq(item) {
  const isOpen = item.classList.contains('open');
  // Close all
  document.querySelectorAll('.faq-item.open').forEach(f => f.classList.remove('open'));
  // Toggle clicked
  if (!isOpen) item.classList.add('open');
}

// Load mini reviews when About tab opens
const __origSwitch = window.switchTab;
window.switchTab = function(tabId, btnEl) {
  __origSwitch(tabId, btnEl);
  if (tabId === 'about') loadMiniReviews();
};

// ══════════════════════════════════════════════════════════════════════════
//  STOP BUTTON — show/hide with camera state
// ══════════════════════════════════════════════════════════════════════════
// ── Stop Button Management ───────────────────────────────────────────────
function updateStopBtn() {
  const sb = document.getElementById('stopBtn');
  const st = document.getElementById('startBtn');
  if (!sb) return;
  if (S.cameraOn) {
    sb.style.display = 'inline-flex';
    if (st) st.textContent = '⏸ Pause';
  } else {
    sb.style.display = 'none';
    if (st) st.textContent = '▶ Start';
  }
}
// Hook into existing toggleCamera and stopCamera via MutationObserver on S
const _camInterval = setInterval(() => {
  updateStopBtn();
}, 500);

// ══════════════════════════════════════════════════════════════════════════
//  EXERCISE INSTRUCTION MODAL
// ══════════════════════════════════════════════════════════════════════════
const EX_DATA = {
  squat: {
    icon: '🏋️', name: 'Squat', muscle: 'Quads · Glutes · Hamstrings',
    yt: 'https://www.youtube.com/results?search_query=how+to+do+squats+properly',
    steps: [
      'Stand with feet shoulder-width apart, toes slightly turned out.',
      'Brace your core and keep your chest tall throughout the movement.',
      'Push your hips back and bend your knees, lowering down as if sitting in a chair.',
      'Go until thighs are parallel to the floor (or as low as comfortable).',
      'Drive through your heels to push back up to standing.',
      'Squeeze your glutes at the top to complete the rep.'
    ],
    tips: '💡 Keep knees tracking over toes. Avoid caving inward. Keep your back straight — do not round forward.'
  },
  pushup: {
    icon: '💪', name: 'Push-up', muscle: 'Chest · Triceps · Shoulders',
    yt: 'https://www.youtube.com/results?search_query=how+to+do+push+ups+correctly',
    steps: [
      'Start in a high plank — hands slightly wider than shoulder-width, wrists under shoulders.',
      'Keep your body in a straight line from head to heels — engage your core.',
      'Lower your chest toward the floor by bending your elbows at a 45° angle.',
      'Go until your chest nearly touches the ground.',
      'Press through your palms to push back up to the starting position.',
      'Do not let your hips sag or pike up.'
    ],
    tips: '💡 If too hard, drop to your knees. Keep elbows at 45° — not flared out — to protect shoulders.'
  },
  bicep_curl: {
    icon: '🦾', name: 'Bicep Curl', muscle: 'Biceps · Forearms',
    yt: 'https://www.youtube.com/results?search_query=bicep+curl+proper+form',
    steps: [
      'Stand tall, feet shoulder-width apart, hold weights with palms facing forward.',
      'Keep your upper arms pinned to your sides throughout the movement.',
      'Curl the weights up toward your shoulders by bending at the elbow.',
      'Squeeze your biceps hard at the top of the movement.',
      'Slowly lower the weights back down in a controlled manner.',
      'Avoid swinging your back or using momentum to lift.'
    ],
    tips: '💡 Use slow, controlled movements. Full range of motion is more effective than heavy weight with half reps.'
  },
  lunge: {
    icon: '🦵', name: 'Lunge', muscle: 'Quads · Hamstrings · Glutes',
    yt: 'https://www.youtube.com/results?search_query=how+to+do+lunges+properly',
    steps: [
      'Stand tall with feet together, hands on hips or at your sides.',
      'Step one foot forward about 2–3 feet.',
      'Lower your hips until both knees form 90° angles.',
      'Keep your front knee directly above your ankle — not past your toes.',
      'Push through your front heel to return to starting position.',
      'Alternate legs or complete all reps on one side first.'
    ],
    tips: '💡 Keep your torso upright. Do not let your back knee slam into the floor — control the descent.'
  },
  shoulder_press: {
    icon: '💪', name: 'Shoulder Press', muscle: 'Deltoids · Triceps · Traps',
    yt: 'https://www.youtube.com/results?search_query=shoulder+press+proper+form',
    steps: [
      'Stand or sit with weights at shoulder height, palms facing forward.',
      'Keep your core braced and avoid arching your lower back.',
      'Press the weights straight up overhead until arms are fully extended.',
      'Bring the weights close together at the top without locking elbows.',
      'Slowly lower back to shoulder height in a controlled motion.',
      'Exhale as you press up, inhale as you lower.'
    ],
    tips: '💡 Avoid flaring elbows too wide. Do not lean back excessively — tighten core to protect your spine.'
  },
  plank: {
    icon: '🧘', name: 'Plank', muscle: 'Core · Shoulders · Back',
    yt: 'https://www.youtube.com/results?search_query=how+to+do+plank+correctly',
    steps: [
      'Start in a forearm plank — elbows directly under shoulders, forearms flat.',
      'Keep your body in a perfectly straight line from head to heels.',
      'Engage your core, squeeze your glutes, and tuck your pelvis slightly.',
      'Do not let your hips sag toward the floor or pike up.',
      'Keep your neck neutral — look at the floor, not up.',
      'Hold the position and breathe steadily for the target time.'
    ],
    tips: '💡 Quality beats quantity. A 20-second perfect plank is better than a 60-second sagging one. Build up gradually.'
  },
  jumping_jacks: {
    icon: '⭐', name: 'Jumping Jacks', muscle: 'Full Body · Cardio',
    yt: 'https://www.youtube.com/results?search_query=jumping+jacks+proper+form',
    steps: [
      'Stand upright with feet together and arms at your sides.',
      'Jump and simultaneously spread your feet wider than shoulder-width.',
      'As you jump, raise both arms out and up over your head.',
      'Land softly on the balls of your feet with knees slightly bent.',
      'Jump again to bring feet back together and arms down.',
      'Keep a steady rhythm and land softly each time.'
    ],
    tips: '💡 Land softly to protect knees. Start slow to get the coordination right, then increase speed.'
  },
  high_knees: {
    icon: '🏃', name: 'High Knees', muscle: 'Legs · Core · Cardio',
    yt: 'https://www.youtube.com/results?search_query=high+knees+exercise+form',
    steps: [
      'Stand tall with feet hip-width apart.',
      'Drive your right knee up toward your chest as high as possible.',
      'Quickly switch to the left knee in a running motion.',
      'Pump your arms in opposition to your legs (right arm with left leg).',
      'Land on the balls of your feet and keep your core engaged.',
      'Maintain an upright posture — do not lean backward.'
    ],
    tips: '💡 Drive knees as high as you can for max benefit. Start at a moderate pace and increase speed as you warm up.'
  },
  arm_raises: {
    icon: '🙌', name: 'Arm Raises', muscle: 'Shoulders · Upper Back',
    yt: 'https://www.youtube.com/results?search_query=lateral+arm+raises+form',
    steps: [
      'Stand with feet shoulder-width apart, arms at your sides holding weights.',
      'Keep a slight bend in your elbows throughout the movement.',
      'Raise both arms out to the sides until they are parallel to the floor.',
      'Hold briefly at the top, feeling the burn in your shoulders.',
      'Slowly lower back down in a controlled motion — resist gravity.',
      'Do not shrug your shoulders up during the lift.'
    ],
    tips: '💡 Use lighter weights for lateral raises. Controlled slow lowering builds more strength than dropping fast.'
  },
  side_lunge: {
    icon: '↔️', name: 'Side Lunge', muscle: 'Inner Thigh · Glutes · Quads',
    yt: 'https://www.youtube.com/results?search_query=side+lunge+proper+form',
    steps: [
      'Stand with feet together, hands clasped at chest or on hips.',
      'Take a wide step to the right with your right foot.',
      'Bend your right knee and push your hips back, keeping your left leg straight.',
      'Lower until your right thigh is roughly parallel to the floor.',
      'Keep your chest up and back flat — do not hunch forward.',
      'Push off the right foot to return to center, then repeat on the other side.'
    ],
    tips: '💡 Keep the straight leg fully extended for a good inner thigh stretch. Go slow and controlled to build stability.'
  }
};

function openExerciseModal(exKey) {
  const ex = EX_DATA[exKey];
  if (!ex) return;
  document.getElementById('emIcon').textContent  = ex.icon;
  document.getElementById('emTitle').textContent = ex.name;
  document.getElementById('emMuscle').textContent = ex.muscle;
  document.getElementById('emSteps').innerHTML = ex.steps.map((s, i) =>
    `<div class="em-step"><div class="em-step-num">${i+1}</div><div>${s}</div></div>`
  ).join('');
  document.getElementById('emTips').innerHTML = `<strong>Pro Tip:</strong> ${ex.tips.replace('💡 ', '')}`;
  const ytEl = document.getElementById('emYT');
  ytEl.href = ex.yt;
  const modal = document.getElementById('exModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeExModal() {
  document.getElementById('exModal').style.display = 'none';
  document.body.style.overflow = '';
}

// ══════════════════════════════════════════════════════════════════════════
//  PAGE-LEVEL REVIEWS (bottom of page, always visible)
// ══════════════════════════════════════════════════════════════════════════
async function loadPageReviews() {
  const el = document.getElementById('prsCards');
  if (!el) return;
  try {
    const res  = await fetch('/api/public_reviews');
    const data = await res.json();
    const reviews = data.reviews || [];

    if (!reviews.length) {
      el.innerHTML = '<div class="prs-empty">No reviews yet — be the first to share your experience!</div>';
      return;
    }

    // Summary stats
    const total = reviews.length;
    const avg   = reviews.reduce((s,r) => s + (r.rating||0), 0) / total;
    const avgEl = document.getElementById('prsAvgWrap');
    if (avgEl) {
      avgEl.style.display = 'block';
      document.getElementById('prsAvgNum').textContent   = avg.toFixed(1);
      document.getElementById('prsAvgStars').textContent = '★'.repeat(Math.round(avg)) + '☆'.repeat(5-Math.round(avg));
      document.getElementById('prsAvgCount').textContent = total + ' review' + (total!==1?'s':'');
    }

    const colors = ['#4d8cff','#7b2ff7','#00c87a','#ff6b35','#ffc107','#e91e8c'];
    el.innerHTML = reviews.map((r, i) => {
      const stars   = '★'.repeat(r.rating||0) + '☆'.repeat(5-(r.rating||0));
      const initials = (r.name||'A').slice(0,2).toUpperCase();
      const date     = new Date(r.ts).toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'});
      return `<div class="rv-card" style="animation-delay:${i*0.05}s">
        <div class="rv-card-top">
          <div class="rv-avatar" style="background:${colors[i%colors.length]}">${initials}</div>
          <div class="rv-meta">
            <div class="rv-name">${r.name||'Anonymous'}</div>
            <div class="rv-date">${date}</div>
          </div>
          <div class="rv-stars">${stars}</div>
        </div>
        ${r.message?`<div class="rv-msg">"${r.message}"</div>`:''}
      </div>`;
    }).join('');
  } catch(e) {
    const el2 = document.getElementById('prsCards');
    if(el2) el2.innerHTML = '<div class="prs-empty">Could not load reviews.</div>';
  }
}

// Load on page ready
document.addEventListener('DOMContentLoaded', () => { loadPageReviews(); });

// Reload after new submission
const __origFbSubmit = window.submitFeedback;
window.submitFeedback = async function() {
  await __origFbSubmit?.();
  setTimeout(loadPageReviews, 1000);
};
