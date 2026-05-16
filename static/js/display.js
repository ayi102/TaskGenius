const REFRESH_MS = 30_000;
const NOW_WINDOW_MIN = 60;
const WEEK_STRIP_MAX_PER_DAY = 6;

const DAY_NAMES   = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]; // Date.getDay() order
const WEEK_ORDER  = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]; // Mon-first for display
const DAY_LABEL   = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const DAY_FULL    = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday",
                      fri: "Friday", sat: "Saturday", sun: "Sunday" };

const boardEl  = document.getElementById("board");
const stripEl  = document.getElementById("week-strip");
const clockEl  = document.getElementById("clock");
const dateEl   = document.getElementById("date");

function toMinutes(hhmm) {
  if (!hhmm) return null;
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

function nowMinutes() {
  const d = new Date();
  return d.getHours() * 60 + d.getMinutes();
}

function todayKey() {
  return DAY_NAMES[new Date().getDay()];
}

function tasksForDay(allTasks, dayKey) {
  return allTasks.filter(t => {
    if (!t.days_of_week) return true;            // NULL = every day
    return t.days_of_week.split(",").includes(dayKey);
  });
}

function format12hr(hhmm) {
  if (!hhmm) return "";
  const [hRaw, m] = hhmm.split(":").map(Number);
  const ampm = hRaw >= 12 ? "pm" : "am";
  const h = hRaw % 12 || 12;
  return `${h}:${String(m).padStart(2, "0")}${ampm}`;
}

function formatClock() {
  const d = new Date();
  let h = d.getHours();
  const m = String(d.getMinutes()).padStart(2, "0");
  const ampm = h >= 12 ? "pm" : "am";
  h = h % 12 || 12;
  return `${h}:${m}${ampm}`;
}

function escape(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function pickCurrent(timed, now) {
  let best = null;
  let bestDiff = Infinity;
  for (const t of timed) {
    const mins = toMinutes(t.scheduled_time);
    const diff = Math.abs(mins - now);
    if (diff <= NOW_WINDOW_MIN && diff < bestDiff) {
      best = t;
      bestDiff = diff;
    }
  }
  return best;
}

/* ─── Today rendering ──────────────────────────────────── */

function renderHero(t) {
  const notes = t.notes
    ? `<div class="hero-notes">${escape(t.notes)}</div>`
    : "";
  return `
    <div class="hero" data-category="${escape(t.category)}">
      <div class="hero-top">
        <span class="hero-time">${escape(format12hr(t.scheduled_time))}</span>
        <span class="hero-category">${escape(t.category)}</span>
        <span class="hero-now-tag">◀ NOW</span>
      </div>
      <div class="hero-title">${escape(t.title)}</div>
      ${notes}
    </div>
  `;
}

function renderCompact(t, isPast) {
  const classes = ["task"];
  if (isPast) classes.push("is-past");
  const notes = t.notes ? `<span class="notes">${escape(t.notes)}</span>` : "";
  return `
    <div class="${classes.join(" ")}" data-category="${escape(t.category)}">
      <div class="time">${escape(format12hr(t.scheduled_time))}</div>
      <div class="category">${escape(t.category)}</div>
      <div class="body">
        <span class="title">${escape(t.title)}</span>
        ${notes}
      </div>
    </div>
  `;
}

function renderChip(t) {
  return `
    <div class="chip" data-category="${escape(t.category)}">
      <span class="category">${escape(t.category)}</span>
      <span class="title">${escape(t.title)}</span>
    </div>
  `;
}

function renderToday(tasks) {
  if (tasks.length === 0) {
    boardEl.innerHTML = `<p class="empty">No tasks for today.</p>`;
    return;
  }

  const timed   = tasks.filter(t => t.scheduled_time);
  const untimed = tasks.filter(t => !t.scheduled_time);

  const now = nowMinutes();
  const currentTask = pickCurrent(timed, now);

  const timelineHtml = timed.map(t => {
    if (t === currentTask) return renderHero(t);
    const isPast = toMinutes(t.scheduled_time) < now;
    return renderCompact(t, isPast);
  }).join("");

  const anytimeHtml = untimed.length === 0 ? "" : `
    <section class="anytime">
      <div class="anytime-header">Anytime today</div>
      <div class="anytime-list">${untimed.map(renderChip).join("")}</div>
    </section>
  `;

  boardEl.innerHTML = `<div class="timeline">${timelineHtml}</div>${anytimeHtml}`;
}

/* ─── Week strip rendering ─────────────────────────────── */

function renderDayEntry(t) {
  const time = t.scheduled_time ? format12hr(t.scheduled_time) : "—";
  const classes = ["day-entry"];
  if (!t.scheduled_time) classes.push("untimed");
  return `
    <div class="${classes.join(" ")}" data-category="${escape(t.category)}">
      <span class="time">${escape(time)}</span>
      <span class="title">${escape(t.title)}</span>
    </div>
  `;
}

function renderDayColumn(dayKey, allTasks, isToday) {
  const tasks = tasksForDay(allTasks, dayKey);
  const shown = tasks.slice(0, WEEK_STRIP_MAX_PER_DAY);
  const overflow = tasks.length - shown.length;

  const body = tasks.length === 0
    ? `<p class="day-empty">—</p>`
    : shown.map(renderDayEntry).join("")
      + (overflow > 0 ? `<div class="day-overflow">+${overflow} more</div>` : "");

  const classes = ["day-col"];
  if (isToday) classes.push("is-today");

  return `
    <section class="${classes.join(" ")}">
      <header class="day-col-header">
        <span class="day-col-name">${DAY_LABEL[dayKey]}</span>
        <span class="day-col-count">${tasks.length}</span>
      </header>
      <div class="day-col-list">${body}</div>
    </section>
  `;
}

function renderWeek(allTasks) {
  const today = todayKey();
  stripEl.innerHTML = WEEK_ORDER
    .map(d => renderDayColumn(d, allTasks, d === today))
    .join("");
}

/* ─── Main render ──────────────────────────────────────── */

function render(payload) {
  const allTasks = payload.tasks || [];
  dateEl.textContent = payload.date || "";

  renderToday(tasksForDay(allTasks, todayKey()));
  renderWeek(allTasks);
}

async function refresh() {
  try {
    const r = await fetch("/api/tasks", { cache: "no-store" });
    if (!r.ok) throw new Error(r.statusText);
    render(await r.json());
  } catch (e) {
    console.error("refresh failed", e);
  }
}

function tickClock() { clockEl.textContent = formatClock(); }

tickClock();
setInterval(tickClock, 30_000);
refresh();
setInterval(refresh, REFRESH_MS);
