const REFRESH_MS = 30_000;
const NOW_WINDOW_MIN = 60;

const DAY_NAMES = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]; // Date.getDay() order

const boardEl = document.getElementById("board");
const clockEl = document.getElementById("clock");
const dateEl  = document.getElementById("date");

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

function splitCats(catStr) {
  return (catStr || "").split(",").map(s => s.trim()).filter(Boolean);
}

function firstCat(catStr) {
  return splitCats(catStr)[0] || "other";
}

function catSpans(catStr) {
  return splitCats(catStr)
    .map(c => `<span data-category="${escape(c)}">${escape(c)}</span>`)
    .join('<span class="cat-sep">·</span>');
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

function pickNext(timed, now) {
  let best = null;
  let bestMins = Infinity;
  for (const t of timed) {
    const mins = toMinutes(t.scheduled_time);
    if (mins > now && mins < bestMins) {
      best = t;
      bestMins = mins;
    }
  }
  return best;
}

function formatUntil(mins) {
  if (mins < 1) return "now";
  if (mins < 60) return `in ${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `in ${h}h` : `in ${h}h ${m}m`;
}

/* ─── Today rendering ──────────────────────────────────── */

function renderHero(t, kind, untilMins) {
  const tag = kind === "now"
    ? "◀ NOW"
    : `▶ NEXT UP · ${formatUntil(untilMins)}`;
  const notes = t.notes
    ? `<div class="hero-notes">${escape(t.notes)}</div>`
    : "";
  return `
    <div class="hero is-${kind}" data-category="${escape(firstCat(t.category))}">
      <div class="hero-meta">
        <div class="hero-time">${escape(format12hr(t.scheduled_time))}</div>
        <div class="hero-category">${catSpans(t.category)}</div>
      </div>
      <div class="hero-main">
        <div class="hero-title">${escape(t.title)}</div>
        ${notes}
      </div>
      <div class="hero-tag">${tag}</div>
    </div>
  `;
}

function renderCompact(t, isPast) {
  const classes = ["task"];
  if (isPast) classes.push("is-past");
  const notes = t.notes ? `<span class="notes">${escape(t.notes)}</span>` : "";
  return `
    <div class="${classes.join(" ")}" data-category="${escape(firstCat(t.category))}">
      <div class="time">${escape(format12hr(t.scheduled_time))}</div>
      <div class="category">${catSpans(t.category)}</div>
      <div class="body">
        <span class="title">${escape(t.title)}</span>
        ${notes}
      </div>
    </div>
  `;
}

function renderChip(t) {
  return `
    <div class="chip" data-category="${escape(firstCat(t.category))}">
      <span class="category">${catSpans(t.category)}</span>
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
  const nextTask = currentTask ? null : pickNext(timed, now);
  const featured = currentTask || nextTask;
  const featuredKind = currentTask ? "now" : "next";

  const timelineHtml = timed.map(t => {
    if (t === featured) {
      const until = t === nextTask ? toMinutes(t.scheduled_time) - now : 0;
      return renderHero(t, featuredKind, until);
    }
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

/* ─── Main render ──────────────────────────────────────── */

function render(payload) {
  const allTasks = payload.tasks || [];
  dateEl.textContent = payload.date || "";
  renderToday(tasksForDay(allTasks, todayKey()));
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
