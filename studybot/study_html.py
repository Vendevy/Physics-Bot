"""Web study interface HTML template for PhysicsBot.

Served by dashboard.py at /study.  Vanilla JS + KaTeX from CDN.
"""

STUDY_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Study — PhysicsBot</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
    background:#0a0a0a; color:#e4e4e7; min-height:100vh; line-height:1.55;
    -webkit-font-smoothing:antialiased;
}
.header {
    position:sticky; top:0; z-index:50;
    background:rgba(10,10,10,0.85); backdrop-filter:blur(12px);
    border-bottom:1px solid rgba(255,255,255,0.06);
}
.header-inner {
    max-width:800px; margin:0 auto; padding:16px 24px;
    display:flex; align-items:center; justify-content:space-between; gap:12px;
}
.header-left h1 { font-size:16px; font-weight:600; letter-spacing:-0.01em; }
.header-left p { font-size:13px; color:#52525b; margin-top:2px; }
.header-actions { display:flex; gap:8px; }
.container { max-width:800px; margin:0 auto; padding:32px 24px 80px; }
.card {
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:16px; padding:28px;
}
.section-label {
    font-size:11px; font-weight:600; text-transform:uppercase;
    letter-spacing:0.08em; color:#52525b; margin-bottom:12px;
}
.progress-track {
    background:#18181b; border-radius:3px; height:4px; overflow:hidden;
    margin-bottom:24px;
}
.progress-fill {
    height:100%; background:#6366f1; border-radius:3px;
    transition:width 0.5s ease;
}
.badge {
    display:inline-flex; align-items:center; gap:6px;
    padding:3px 10px; border-radius:6px; font-size:11px; font-weight:600;
    text-transform:uppercase; letter-spacing:0.05em;
}
.badge-new { background:rgba(99,102,241,0.12); color:#818cf8; }
.badge-recall { background:rgba(34,197,94,0.12); color:#4ade80; }
.question-meta {
    display:flex; align-items:center; gap:12px; margin-bottom:16px;
    flex-wrap:wrap;
}
.question-marks { font-size:13px; color:#71717a; font-weight:500; }
.question-text {
    font-size:15px; color:#e4e4e7; line-height:1.7; margin-bottom:24px;
}
.question-text p { margin-bottom:12px; }
.question-text p:last-child { margin-bottom:0; }
.figure-wrap {
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px;
    padding:14px 16px 8px;
    margin-bottom:20px;
}
.figure-title {
    font-size:12px; color:#a1a1aa; font-weight:500;
    margin-bottom:8px; text-align:center;
}
.figure-canvas-box { position:relative; height:260px; }
@media (max-width: 720px) {
    .figure-canvas-box { height:220px; }
}
.answer-area {
    width:100%; min-height:160px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:12px; padding:14px 16px;
    color:#e4e4e7; font-size:14px; font-family:inherit; line-height:1.6;
    resize:vertical; outline:none;
    transition:border-color 0.15s;
}
.answer-area:focus { border-color:rgba(99,102,241,0.5); }
.answer-area::placeholder { color:#3f3f46; }
.kbd-hint {
    font-size:11px; color:#52525b; margin-top:6px;
    font-variant-numeric:tabular-nums;
}
.kbd-hint kbd {
    background:#27272a; border:1px solid rgba(255,255,255,0.08);
    padding:1px 5px; border-radius:4px; font-size:10px;
    font-family:'SF Mono','Fira Code',monospace; color:#a1a1aa;
}
.btn {
    display:inline-flex; align-items:center; justify-content:center; gap:6px;
    padding:10px 20px; border-radius:10px;
    border:1px solid rgba(255,255,255,0.08);
    font-family:inherit; font-size:14px; font-weight:500; cursor:pointer;
    background:#18181b; color:#a1a1aa;
    transition:background 0.2s, border-color 0.2s, color 0.2s;
}
.btn:hover { background:#27272a; border-color:rgba(255,255,255,0.12); color:#e4e4e7; }
.btn:disabled { opacity:0.35; cursor:not-allowed; }
.btn-primary {
    background:#6366f1; border-color:#6366f1; color:#fff;
}
.btn-primary:hover:not(:disabled) { background:#5558e6; border-color:#5558e6; }
.btn-primary:disabled:hover { background:#6366f1; border-color:#6366f1; }
.btn-ghost {
    background:transparent; border-color:rgba(255,255,255,0.06);
    color:#71717a; padding:6px 12px; font-size:12px;
}
.btn-ghost:hover { color:#e4e4e7; background:rgba(255,255,255,0.04); }
.btn-flag {
    background:transparent; border:1px solid rgba(239,68,68,0.2);
    color:#ef4444; padding:6px 10px; font-size:12px; gap:4px;
}
.btn-flag:hover { background:rgba(239,68,68,0.08); border-color:rgba(239,68,68,0.4); }
.btn-flag.flagged { background:rgba(239,68,68,0.12); border-color:rgba(239,68,68,0.5); }
.spinner {
    display:none; width:14px; height:14px;
    border:2px solid transparent; border-top-color:currentColor; border-radius:50%;
    animation:spin 0.7s linear infinite;
}
@keyframes spin { to { transform:rotate(360deg); } }
.result-card {
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; padding:20px; margin-bottom:20px;
}
.result-score {
    font-size:32px; font-weight:700; letter-spacing:-0.02em;
    margin-bottom:4px;
}
.result-score.correct { color:#22c55e; }
.result-score.partial { color:#eab308; }
.result-score.incorrect { color:#ef4444; }
.result-sm2 {
    font-size:12px; color:#52525b; font-weight:500;
    margin-bottom:16px;
}
.result-feedback {
    font-size:14px; color:#a1a1aa; line-height:1.7;
    white-space:pre-wrap;
}
.result-feedback p { margin-bottom:10px; }
.result-feedback p:last-child { margin-bottom:0; }
.result-feedback.streaming { border-left:2px solid #6366f1; padding-left:12px; }
.empty-state {
    text-align:center; padding:48px 24px; color:#52525b;
}
.empty-state h2 { font-size:20px; font-weight:600; color:#e4e4e7; margin-bottom:8px; }
.empty-state p { font-size:14px; line-height:1.6; }
.start-btn-wrap { margin-top:24px; }
.build-progress {
    margin-top:24px; text-align:left;
    background:rgba(99,102,241,0.05);
    border:1px solid rgba(99,102,241,0.15);
    border-radius:10px; padding:14px 16px;
    display:none;
}
.build-progress.active { display:block; }
.build-progress-line {
    font-size:12px; color:#a1a1aa; line-height:1.6;
    font-variant-numeric:tabular-nums;
}
.build-progress-current {
    font-size:13px; color:#818cf8; font-weight:500; margin-top:4px;
}
.resume-banner {
    background:rgba(234,179,8,0.06);
    border:1px solid rgba(234,179,8,0.2);
    border-radius:10px; padding:14px 16px;
    margin-bottom:16px;
    display:none;
    align-items:center; justify-content:space-between; gap:12px;
}
.resume-banner.active { display:flex; }
.resume-text { font-size:13px; color:#fde68a; }
.resume-actions { display:flex; gap:8px; }

.mode-toggle {
    display:flex; gap:6px; padding:4px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px;
    margin-top:24px; margin-bottom:8px;
}
.mode-toggle button {
    flex:1; background:transparent; border:none; cursor:pointer;
    color:#71717a; font-family:inherit; font-size:13px; font-weight:500;
    padding:8px 12px; border-radius:7px;
    transition:background 0.15s, color 0.15s;
}
.mode-toggle button.active {
    background:rgba(99,102,241,0.15); color:#e4e4e7;
}
.mode-toggle button:hover:not(.active) { color:#a1a1aa; }

.paper-picker {
    margin-top:16px; text-align:left;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px; padding:14px 16px;
    display:none;
}
.paper-picker.active { display:block; }
.paper-picker .opt-label { margin-bottom:8px; }
.paper-meta {
    margin-top:8px; font-size:12px; color:#52525b;
    font-variant-numeric:tabular-nums;
}

.mock-timer {
    position:sticky; top:64px; z-index:30;
    margin:0 auto 16px;
    background:rgba(99,102,241,0.08);
    border:1px solid rgba(99,102,241,0.25);
    border-radius:10px; padding:8px 14px;
    display:flex; align-items:center; justify-content:space-between;
    font-variant-numeric:tabular-nums;
}
.mock-timer-label { font-size:11px; color:#818cf8; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; }
.mock-timer-value { font-size:16px; font-weight:600; color:#e4e4e7; }

.session-options {
    margin-top:24px; text-align:left;
    display:grid; grid-template-columns:1fr 1fr; gap:12px;
}
@media (max-width: 540px) {
    .session-options { grid-template-columns:1fr; }
}
.opt-cell {
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px; padding:12px 14px;
}
.opt-label {
    font-size:11px; color:#52525b; font-weight:600;
    text-transform:uppercase; letter-spacing:0.06em;
    margin-bottom:8px;
}
.opt-row { display:flex; align-items:center; gap:8px; }
.num-stepper {
    display:flex; align-items:center;
    border:1px solid rgba(255,255,255,0.08);
    border-radius:8px; overflow:hidden;
    width:fit-content;
}
.num-stepper button {
    background:transparent; border:none; cursor:pointer;
    color:#a1a1aa; padding:6px 10px; font-size:14px;
    font-family:inherit; line-height:1;
    transition:background 0.15s, color 0.15s;
}
.num-stepper button:hover:not(:disabled) {
    background:rgba(255,255,255,0.04); color:#e4e4e7;
}
.num-stepper button:disabled { opacity:0.3; cursor:not-allowed; }
.num-stepper input {
    width:44px; text-align:center;
    background:transparent; border:none;
    color:#e4e4e7; font-size:14px; font-weight:600;
    font-family:inherit; outline:none;
    border-left:1px solid rgba(255,255,255,0.06);
    border-right:1px solid rgba(255,255,255,0.06);
    padding:6px 0;
    -moz-appearance:textfield;
}
.num-stepper input::-webkit-outer-spin-button,
.num-stepper input::-webkit-inner-spin-button { -webkit-appearance:none; margin:0; }
.opt-hint { font-size:11px; color:#52525b; margin-left:8px; }
.diff-select {
    width:100%;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:8px; padding:7px 10px;
    color:#e4e4e7; font-size:13px; font-family:inherit;
    outline:none; cursor:pointer;
    appearance:none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%2371717a' d='M0 0l5 6 5-6z'/></svg>");
    background-repeat:no-repeat;
    background-position:right 10px center;
    padding-right:28px;
}
.diff-select:focus { border-color:rgba(99,102,241,0.4); }
.diff-select option { background:#18181b; color:#e4e4e7; }

.topic-picker {
    margin-top:16px; text-align:left;
    border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; overflow:hidden;
}
.topic-picker-header {
    display:flex; align-items:center; justify-content:space-between;
    padding:12px 16px; cursor:pointer;
    background:rgba(255,255,255,0.02);
    transition:background 0.15s;
}
.topic-picker-header:hover { background:rgba(255,255,255,0.04); }
.topic-picker-title { font-size:13px; font-weight:500; color:#a1a1aa; }
.topic-picker-counter {
    font-size:11px; color:#52525b; font-weight:500;
    font-variant-numeric:tabular-nums;
}
.topic-picker-counter.active { color:#818cf8; }
.topic-picker-chevron {
    width:12px; height:12px; color:#52525b;
    transition:transform 0.2s;
}
.topic-picker.open .topic-picker-chevron { transform:rotate(90deg); }
.topic-picker-body {
    display:none; padding:12px 16px 16px;
    border-top:1px solid rgba(255,255,255,0.04);
}
.topic-picker.open .topic-picker-body { display:block; }
.topic-search-row {
    display:flex; gap:8px; margin-bottom:10px;
}
.topic-search {
    flex:1; background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:8px; padding:7px 10px;
    color:#e4e4e7; font-size:13px; font-family:inherit;
    outline:none;
}
.topic-search:focus { border-color:rgba(99,102,241,0.4); }
.topic-search::placeholder { color:#3f3f46; }
.topic-list {
    max-height:280px; overflow-y:auto;
    border:1px solid rgba(255,255,255,0.04);
    border-radius:8px; padding:4px;
}
.topic-list-item {
    display:flex; align-items:center; gap:10px;
    padding:6px 10px; border-radius:6px;
    font-size:12px; color:#a1a1aa;
    cursor:pointer; user-select:none;
    transition:background 0.1s;
}
.topic-list-item:hover { background:rgba(255,255,255,0.03); }
.topic-list-item input[type="checkbox"] {
    width:14px; height:14px; cursor:pointer;
    accent-color:#6366f1; flex-shrink:0;
}
.topic-list-item.selected { color:#e4e4e7; background:rgba(99,102,241,0.06); }
.topic-list-item code {
    font-family:'SF Mono','Fira Code',monospace; font-size:11px;
    color:#71717a; background:rgba(255,255,255,0.03);
    padding:1px 6px; border-radius:4px; flex-shrink:0;
}
.topic-list-title { flex:1; }
.topic-list-mastery {
    font-size:11px; color:#52525b; font-variant-numeric:tabular-nums;
    flex-shrink:0;
}
.topic-list-empty {
    padding:20px; text-align:center; font-size:12px; color:#52525b;
}
.topic-picker-actions {
    display:flex; justify-content:space-between; gap:8px;
    margin-top:10px; align-items:center;
}
.topic-hint { font-size:11px; color:#52525b; }

/* Review modal */
.review-overlay {
    position:fixed; inset:0; z-index:100;
    background:rgba(0,0,0,0.8); backdrop-filter:blur(10px);
    display:none; align-items:center; justify-content:center; padding:24px;
}
.review-overlay.active { display:flex; }
.review-modal {
    background:#18181b; border:1px solid rgba(255,255,255,0.1);
    border-radius:16px; width:100%; max-width:720px; max-height:90vh;
    overflow-y:auto; display:flex; flex-direction:column;
}
.review-header {
    display:flex; align-items:center; justify-content:space-between;
    padding:20px 24px; border-bottom:1px solid rgba(255,255,255,0.06);
    position:sticky; top:0; background:#18181b; z-index:2;
}
.review-counter { font-size:12px; color:#52525b; font-weight:500; }
.review-result-tag {
    font-size:12px; font-weight:700; text-transform:uppercase;
    letter-spacing:0.05em;
}
.review-body { padding:24px; }
.review-section { margin-bottom:20px; }
.review-section:last-child { margin-bottom:0; }
.review-label {
    font-size:11px; font-weight:600; text-transform:uppercase;
    letter-spacing:0.06em; color:#52525b; margin-bottom:6px;
}
.review-content {
    font-size:13px; color:#a1a1aa; line-height:1.7;
    background:rgba(255,255,255,0.02); border-radius:10px;
    padding:14px; border:1px solid rgba(255,255,255,0.04);
}
.review-content.user-answer { color:#d4d4d8; }
.consolidate-box {
    margin-top:20px; padding-top:20px;
    border-top:1px solid rgba(255,255,255,0.06);
}
.consolidate-label {
    font-size:12px; font-weight:600; color:#6366f1; margin-bottom:6px;
}
.consolidate-hint {
    font-size:12px; color:#52525b; margin-bottom:10px;
}
.consolidate-area {
    width:100%; min-height:100px;
    background:rgba(99,102,241,0.05);
    border:1px solid rgba(99,102,241,0.2); border-radius:10px;
    padding:12px 14px; color:#e4e4e7; font-size:13px;
    font-family:inherit; line-height:1.6; resize:vertical;
    outline:none; transition:border-color 0.15s;
}
.consolidate-area:focus { border-color:rgba(99,102,241,0.5); }
.consolidate-area::placeholder { color:#3f3f46; }
.consolidate-saved {
    font-size:11px; color:#22c55e; margin-top:6px;
    opacity:0; transition:opacity 0.3s;
}
.consolidate-saved.visible { opacity:1; }
.review-actions {
    display:flex; justify-content:space-between; align-items:center;
    padding:16px 24px; border-top:1px solid rgba(255,255,255,0.06);
    position:sticky; bottom:0; background:#18181b; z-index:2;
}
.review-actions-right { display:flex; gap:8px; }
.status-toast {
    position:fixed; top:20px; left:50%; transform:translateX(-50%);
    background:#18181b; border:1px solid rgba(255,255,255,0.08);
    border-radius:10px; padding:10px 18px; font-size:13px; color:#a1a1aa;
    z-index:200; display:none; box-shadow:0 8px 32px rgba(0,0,0,0.4);
}
.status-toast.error { border-color:rgba(239,68,68,0.3); color:#fca5a5; }
.status-toast.visible { display:block; }
</style>
</head>
<body>
<div class="header">
    <div class="header-inner">
        <div class="header-left">
            <h1>PhysicsBot</h1>
            <p>Interactive Study Session</p>
        </div>
        <div class="header-actions">
            <a href="/" class="btn" style="text-decoration:none;">Dashboard</a>
        </div>
    </div>
</div>

<div class="container">
    <!-- START SCREEN -->
    <div id="start-screen">
        <div id="resume-banner" class="resume-banner">
            <span class="resume-text" id="resume-text">You have an unfinished session. Resume it?</span>
            <div class="resume-actions">
                <button class="btn btn-ghost" onclick="discardSession()">Discard</button>
                <button class="btn btn-primary" onclick="resumeSession()">Resume</button>
            </div>
        </div>
        <div class="card" style="padding:48px 32px;">
            <div class="empty-state" style="padding:0;">
                <h2 id="start-heading">Ready to study?</h2>
                <p id="start-blurb">Each session generates up to {{DAILY_NEW}} fresh questions<br>plus {{DAILY_RECALL}} past-paper questions for spaced review.</p>
                <div class="start-btn-wrap">
                    <button class="btn btn-primary" id="btn-start" onclick="startSession()" style="padding:12px 28px; font-size:15px;">
                        Start Session
                        <span class="spinner" id="spin-start"></span>
                    </button>
                </div>
                <div class="build-progress" id="build-progress">
                    <div class="build-progress-line" id="build-progress-count">Preparing...</div>
                    <div class="build-progress-current" id="build-progress-current"></div>
                </div>
            </div>

            <div class="mode-toggle">
                <button id="mode-daily" class="active" onclick="setMode('daily')">Daily Session</button>
                <button id="mode-mock" onclick="setMode('mock')">Mock Paper</button>
            </div>

            <div class="paper-picker" id="paper-picker">
                <div class="opt-label">Choose a past paper</div>
                <select class="diff-select" id="select-paper" onchange="onPaperChange()">
                    <option value="">Loading papers…</option>
                </select>
                <div class="paper-meta" id="paper-meta"></div>
            </div>

            <div id="daily-options-wrap">
            <div class="session-options">
                <div class="opt-cell">
                    <div class="opt-label">Number of new questions</div>
                    <div class="opt-row">
                        <div class="num-stepper">
                            <button type="button" id="btn-n-down" onclick="adjustNNew(-1)">−</button>
                            <input type="number" id="input-n-new" value="{{DAILY_NEW}}" min="1" max="15" oninput="onNNewChange()">
                            <button type="button" id="btn-n-up" onclick="adjustNNew(1)">+</button>
                        </div>
                        <span class="opt-hint">+ {{DAILY_RECALL}} recall</span>
                    </div>
                </div>
                <div class="opt-cell">
                    <div class="opt-label">Difficulty</div>
                    <select class="diff-select" id="select-difficulty" onchange="onDifficultyChange()">
                        <option value="3" selected>3 — Standard A-Level</option>
                        <option value="4">4 — Difficult A-Level</option>
                        <option value="5">5 — Very Difficult A-Level</option>
                        <option value="6">6 — Extremely Difficult A-Level</option>
                    </select>
                </div>
            </div>

            <div class="topic-picker" id="topic-picker">
                <div class="topic-picker-header" onclick="toggleTopicPicker()">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <svg class="topic-picker-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                        <span class="topic-picker-title">Choose specific topics (optional)</span>
                    </div>
                    <span class="topic-picker-counter" id="topic-picker-counter">Auto: weakest topics</span>
                </div>
                <div class="topic-picker-body">
                    <div class="topic-search-row">
                        <input type="text" class="topic-search" id="topic-search" placeholder="Search topics..." oninput="filterTopics()">
                    </div>
                    <div class="topic-list" id="topic-list">
                        <div class="topic-list-empty">Loading topics...</div>
                    </div>
                    <div class="topic-picker-actions">
                        <span class="topic-hint" id="topic-hint">Pick up to {{DAILY_NEW}} topics. Leave empty to auto-pick weakest.</span>
                        <button class="btn btn-ghost" onclick="clearTopicSelection()">Clear</button>
                    </div>
                </div>
            </div>
            </div><!-- /daily-options-wrap -->
        </div>
    </div>

    <!-- QUESTION SCREEN -->
    <div id="question-screen" style="display:none;">
        <div class="mock-timer" id="mock-timer" style="display:none;">
            <span class="mock-timer-label">Mock paper — elapsed</span>
            <span class="mock-timer-value" id="mock-timer-value">0:00</span>
        </div>
        <div class="section-label" id="progress-label">Question 1 / 10</div>
        <div class="progress-track"><div class="progress-fill" id="progress-bar" style="width:0%"></div></div>

        <div class="card">
            <div class="question-meta">
                <span class="badge" id="kind-badge">NEW</span>
                <span class="question-marks" id="marks-display">5 marks</span>
                <button class="btn btn-flag" id="btn-flag" onclick="flagCurrent()" title="Report a problem with this question">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>
                    <span id="flag-label">Flag</span>
                </button>
            </div>
            <div id="question-figure"></div>
            <div class="question-text" id="question-text">Loading...</div>
            <textarea class="answer-area" id="answer-input" placeholder="Type your answer here..." oninput="autosaveAnswer()"></textarea>
            <div class="kbd-hint">Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to submit</div>
            <div style="margin-top:16px; display:flex; justify-content:flex-end;">
                <button class="btn btn-primary" id="btn-submit" onclick="submitAnswer()">
                    Submit Answer
                    <span class="spinner" id="spin-submit"></span>
                </button>
            </div>
        </div>
    </div>

    <!-- RESULT SCREEN -->
    <div id="result-screen" style="display:none;">
        <div class="card">
            <div class="result-card">
                <div class="result-score" id="result-score">3 / 5</div>
                <div class="result-sm2" id="result-sm2">SM-2 grade: 3 / 5</div>
                <div class="result-feedback" id="result-feedback">Feedback here...</div>
            </div>
            <div style="display:flex; justify-content:flex-end;">
                <button class="btn btn-primary" id="btn-next" onclick="nextQuestion()" disabled>
                    <span id="next-label">Next Question</span>
                    <span class="spinner" id="spin-next"></span>
                </button>
            </div>
            <div class="kbd-hint" style="margin-top:8px;">Press <kbd>→</kbd> for next</div>
        </div>
    </div>

    <!-- DONE SCREEN -->
    <div id="done-screen" style="display:none;">
        <div class="card" style="text-align:center; padding:48px 32px;">
            <div class="empty-state" style="padding:0;">
                <h2>Session complete!</h2>
                <p id="done-summary">You answered 10 questions.</p>
                <div class="start-btn-wrap">
                    <button class="btn btn-primary" onclick="showReview()">Review &amp; Consolidate</button>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- REVIEW MODAL -->
<div class="review-overlay" id="review-overlay">
    <div class="review-modal">
        <div class="review-header">
            <span class="review-counter" id="review-counter">1 / 10</span>
            <span class="review-result-tag" id="review-tag">CORRECT</span>
        </div>
        <div class="review-body">
            <div class="review-section">
                <div class="review-label">Question</div>
                <div id="review-figure"></div>
                <div class="review-content" id="review-question">...</div>
            </div>
            <div class="review-section">
                <div class="review-label">Your Answer</div>
                <div class="review-content user-answer" id="review-answer">...</div>
            </div>
            <div class="review-section">
                <div class="review-label">Markscheme</div>
                <div class="review-content" id="review-markscheme">...</div>
            </div>
            <div class="review-section">
                <div class="review-label">Feedback</div>
                <div class="review-content" id="review-feedback">...</div>
            </div>
            <div class="consolidate-box">
                <div class="consolidate-label">Consolidate</div>
                <div class="consolidate-hint">Summarise your understanding in your own words before moving on. Saved automatically.</div>
                <textarea class="consolidate-area" id="consolidate-input" placeholder="Write something..."
                    oninput="onConsolidateInput(this)"></textarea>
                <div class="consolidate-saved" id="consolidate-saved">Saved</div>
            </div>
        </div>
        <div class="review-actions">
            <button class="btn" id="btn-review-prev" onclick="reviewPrev()">Back</button>
            <div class="review-actions-right">
                <button class="btn btn-primary" id="btn-review-next" onclick="reviewNext()" disabled style="opacity:0.35;cursor:not-allowed;">
                    <span id="review-next-label">Next</span>
                </button>
            </div>
        </div>
    </div>
</div>

<div class="status-toast" id="status-toast"></div>

<script>
const DAILY_NEW = {{DAILY_NEW}};
const DAILY_RECALL = {{DAILY_RECALL}};
const SUBJECT_ID = (new URLSearchParams(location.search)).get('subject') || null;

let sessionId = null;
let questions = [];
let currentPos = 0;
let attempts = [];
let reviewIndex = 0;
let reviewData = [];
let buildPollTimer = null;
let consolidateSaveTimer = null;
let allTopics = [];
let selectedTopicIds = new Set();
let questionShownAt = null;  // ms timestamp when current question was rendered

let sessionMode = 'daily'; // 'daily' or 'mock'
let allPapers = [];
let mockAnswers = [];      // {position, answer, time_spent_seconds}
let mockTimerStart = null; // ms
let mockTimerHandle = null;
function getNNew() {
    const v = parseInt(document.getElementById('input-n-new').value, 10);
    if (!Number.isFinite(v)) return DAILY_NEW;
    return Math.max(1, Math.min(15, v));
}
function getDifficulty() {
    const v = parseInt(document.getElementById('select-difficulty').value, 10);
    return [3,4,5,6].includes(v) ? v : 3;
}
function adjustNNew(delta) {
    const el = document.getElementById('input-n-new');
    el.value = Math.max(1, Math.min(15, getNNew() + delta));
    onNNewChange();
}
function onNNewChange() {
    const n = getNNew();
    document.getElementById('input-n-new').value = n;
    document.getElementById('btn-n-down').disabled = n <= 1;
    document.getElementById('btn-n-up').disabled = n >= 15;
    const hintEl = document.getElementById('topic-hint');
    if (hintEl) hintEl.textContent = `Pick up to ${n} topics. Leave empty to auto-pick weakest.`;
    // If user already selected more topics than the new cap, trim from the most recent
    if (selectedTopicIds.size > n) {
        const arr = Array.from(selectedTopicIds);
        selectedTopicIds = new Set(arr.slice(0, n));
        if (allTopics.length) renderTopicList();
    }
    updateTopicCounter();
}
function onDifficultyChange() { /* no UI to update yet, just a reactive hook */ }

function toast(msg, isError) {
    const el = document.getElementById('status-toast');
    el.textContent = msg;
    el.className = 'status-toast' + (isError ? ' error' : '') + ' visible';
    setTimeout(() => el.classList.remove('visible'), 3000);
}

function setLoading(id, loading) {
    const btn = document.getElementById(id);
    const spin = document.getElementById(id.replace('btn-', 'spin-'));
    if (!btn) return;
    btn.disabled = loading;
    if (spin) spin.style.display = loading ? 'inline-block' : 'none';
}

/* ----- KaTeX with proper readiness gating (fix #5: race) ----- */
let _katexReady = false;
const _katexQueue = [];
function _flushKatexQueue() {
    while (_katexQueue.length) {
        const el = _katexQueue.shift();
        try {
            renderMathInElement(el, {
                delimiters: [
                    {left: '$$', right: '$$', display: true},
                    {left: '$', right: '$', display: false}
                ],
                throwOnError: false
            });
        } catch (e) { /* swallow */ }
    }
}
function _waitForKatex() {
    if (typeof renderMathInElement !== 'undefined') {
        _katexReady = true;
        _flushKatexQueue();
    } else {
        setTimeout(_waitForKatex, 50);
    }
}
_waitForKatex();
function renderMath(el) {
    el = el || document.body;
    if (_katexReady) {
        _katexQueue.push(el);
        _flushKatexQueue();
    } else {
        _katexQueue.push(el);
    }
}

/* ----- Chart.js figure rendering ----- */
const _activeCharts = new Map(); // container id -> Chart instance
function renderFigure(figure, containerId) {
    const wrap = document.getElementById(containerId);
    if (!wrap) return;
    // Tear down any prior chart in this container
    const prior = _activeCharts.get(containerId);
    if (prior) { try { prior.destroy(); } catch (e) {} _activeCharts.delete(containerId); }
    if (!figure || !figure.series || !figure.x) {
        wrap.innerHTML = '';
        return;
    }
    const titleHtml = figure.title
        ? `<div class="figure-title">${escapeHtml(figure.title)}</div>` : '';
    wrap.innerHTML = `
        <div class="figure-wrap">
            ${titleHtml}
            <div class="figure-canvas-box"><canvas></canvas></div>
        </div>
    `;
    const canvas = wrap.querySelector('canvas');
    const palette = ['#818cf8', '#4ade80', '#fbbf24', '#f472b6', '#22d3ee'];
    const isScatter = figure.type === 'scatter';
    const datasets = figure.series.map((s, i) => {
        const color = palette[i % palette.length];
        if (isScatter) {
            return {
                label: s.name,
                data: figure.x.map((xv, idx) => ({x: xv, y: s.y[idx]})),
                backgroundColor: color,
                borderColor: color,
                showLine: false,
                pointRadius: 4,
            };
        }
        return {
            label: s.name,
            data: s.y,
            borderColor: color,
            backgroundColor: figure.type === 'bar' ? color + 'cc' : color + '33',
            tension: 0.15,
            pointRadius: figure.type === 'line' ? 3 : undefined,
            fill: false,
        };
    });
    const cfg = {
        type: figure.type === 'scatter' ? 'scatter' : (figure.type === 'bar' ? 'bar' : 'line'),
        data: isScatter ? {datasets} : {labels: figure.x, datasets},
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: figure.series.length > 1,
                    labels: {color: '#a1a1aa', font: {size: 12}},
                },
                tooltip: {
                    backgroundColor: '#18181b',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    titleColor: '#e4e4e7',
                    bodyColor: '#a1a1aa',
                },
            },
            scales: {
                x: {
                    type: isScatter ? 'linear' : 'category',
                    title: {display: !!figure.xlabel, text: figure.xlabel || '', color: '#a1a1aa', font: {size: 12}},
                    grid: {color: 'rgba(255,255,255,0.04)'},
                    ticks: {color: '#71717a', font: {size: 11}},
                },
                y: {
                    title: {display: !!figure.ylabel, text: figure.ylabel || '', color: '#a1a1aa', font: {size: 12}},
                    grid: {color: 'rgba(255,255,255,0.04)'},
                    ticks: {color: '#71717a', font: {size: 11}},
                },
            },
        },
    };
    try {
        const chart = new Chart(canvas, cfg);
        _activeCharts.set(containerId, chart);
    } catch (e) {
        wrap.innerHTML = `<div class="figure-wrap"><div style="color:#fca5a5;font-size:12px;">Chart error: ${escapeHtml(e.message)}</div></div>`;
    }
}

/* ----- Markdown rendering (fix #2: real paragraphs/line breaks) ----- */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}
function markdownToHtml(md) {
    if (md == null) return '';
    const escaped = escapeHtml(md);
    // Inline formatting first
    let s = escaped
        .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
        .replace(/\\*(.+?)\\*/g, '<em>$1</em>')
        .replace(/`(.+?)`/g, '<code style="background:rgba(255,255,255,0.06);padding:2px 5px;border-radius:4px;font-family:monospace;font-size:12px;">$1</code>');
    // Block: split on blank lines into paragraphs, single \\n becomes <br>
    const paras = s.split(/\\n{2,}/).map(p => '<p>' + p.replace(/\\n/g, '<br>') + '</p>');
    return paras.join('');
}

/* ----- localStorage autosave (fix #8) ----- */
function autosaveKey(pos) { return `pb:answer:${sessionId}:${pos}`; }
function autosaveAnswer() {
    if (sessionId == null) return;
    const v = document.getElementById('answer-input').value;
    try { localStorage.setItem(autosaveKey(currentPos), v); } catch (e) {}
}
function loadAutosave(pos) {
    if (sessionId == null) return '';
    try { return localStorage.getItem(autosaveKey(pos)) || ''; } catch (e) { return ''; }
}
function clearAutosave(pos) {
    if (sessionId == null) return;
    try { localStorage.removeItem(autosaveKey(pos)); } catch (e) {}
}

/* ----- Mode toggle (daily / mock) ----- */
function setMode(mode) {
    sessionMode = mode;
    document.getElementById('mode-daily').classList.toggle('active', mode === 'daily');
    document.getElementById('mode-mock').classList.toggle('active', mode === 'mock');
    document.getElementById('daily-options-wrap').style.display = mode === 'daily' ? 'block' : 'none';
    document.getElementById('paper-picker').classList.toggle('active', mode === 'mock');
    if (mode === 'mock') {
        document.getElementById('start-heading').textContent = 'Mock paper';
        document.getElementById('start-blurb').innerHTML = 'Sit a full past paper end-to-end with a count-up timer. No mid-session feedback — answers are graded all at once at the end.';
        document.getElementById('btn-start').firstChild.textContent = 'Start Mock Paper ';
        if (allPapers.length === 0) loadPapers();
    } else {
        document.getElementById('start-heading').textContent = 'Ready to study?';
        document.getElementById('start-blurb').innerHTML = `Each session generates up to ${DAILY_NEW} fresh questions<br>plus ${DAILY_RECALL} past-paper questions for spaced review.`;
        document.getElementById('btn-start').firstChild.textContent = 'Start Session ';
    }
}

async function loadPapers() {
    const url = '/api/papers' + (SUBJECT_ID ? `?subject_id=${encodeURIComponent(SUBJECT_ID)}` : '');
    try {
        const res = await fetch(url);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Failed to load papers');
        allPapers = data.papers || [];
        const sel = document.getElementById('select-paper');
        if (allPapers.length === 0) {
            sel.innerHTML = '<option value="">No papers available — extract questions first</option>';
            document.getElementById('paper-meta').textContent = '';
            return;
        }
        sel.innerHTML = allPapers.map((p, i) =>
            `<option value="${p.id}">${escapeHtml(p.label)} — ${p.n_questions} Qs · ${p.total_marks} marks</option>`
        ).join('');
        onPaperChange();
    } catch (e) {
        document.getElementById('select-paper').innerHTML = `<option value="">Error: ${escapeHtml(e.message)}</option>`;
    }
}

function onPaperChange() {
    const sel = document.getElementById('select-paper');
    const id = parseInt(sel.value, 10);
    const p = allPapers.find(x => x.id === id);
    document.getElementById('paper-meta').textContent =
        p ? `${p.n_questions} questions · ${p.total_marks} marks` : '';
}

function fmtMMSS(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    return `${m}:${String(s).padStart(2,'0')}`;
}

function startMockTimer() {
    mockTimerStart = Date.now();
    document.getElementById('mock-timer').style.display = 'flex';
    if (mockTimerHandle) clearInterval(mockTimerHandle);
    mockTimerHandle = setInterval(() => {
        document.getElementById('mock-timer-value').textContent =
            fmtMMSS(Date.now() - mockTimerStart);
    }, 1000);
}

function stopMockTimer() {
    if (mockTimerHandle) { clearInterval(mockTimerHandle); mockTimerHandle = null; }
    document.getElementById('mock-timer').style.display = 'none';
}

/* ----- Topic picker ----- */
function toggleTopicPicker() {
    const el = document.getElementById('topic-picker');
    el.classList.toggle('open');
    if (el.classList.contains('open') && allTopics.length === 0) {
        loadTopics();
    }
}

async function loadTopics() {
    const url = '/api/study/topics' + (SUBJECT_ID ? `?subject_id=${encodeURIComponent(SUBJECT_ID)}` : '');
    try {
        const res = await fetch(url);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Failed to load topics');
        allTopics = data.topics;
        renderTopicList();
    } catch (e) {
        document.getElementById('topic-list').innerHTML =
            `<div class="topic-list-empty">Error: ${escapeHtml(e.message)}</div>`;
    }
}

function renderTopicList() {
    const search = (document.getElementById('topic-search').value || '').toLowerCase().trim();
    const items = allTopics.filter(t => {
        if (!search) return true;
        return t.code.toLowerCase().includes(search)
            || t.title.toLowerCase().includes(search);
    });
    const listEl = document.getElementById('topic-list');
    if (items.length === 0) {
        listEl.innerHTML = '<div class="topic-list-empty">No topics match.</div>';
        return;
    }
    listEl.innerHTML = items.map(t => {
        const checked = selectedTopicIds.has(t.id) ? 'checked' : '';
        const sel = selectedTopicIds.has(t.id) ? ' selected' : '';
        const pct = Math.round((t.score || 0) * 100);
        const masteryLabel = t.reviewed ? `${pct}%` : 'new';
        return `
            <label class="topic-list-item${sel}" data-id="${t.id}">
                <input type="checkbox" ${checked} onchange="toggleTopic(${t.id}, this.checked)">
                <code>${escapeHtml(t.code)}</code>
                <span class="topic-list-title">${escapeHtml(t.title)}</span>
                <span class="topic-list-mastery">${masteryLabel}</span>
            </label>
        `;
    }).join('');
}

function toggleTopic(id, checked) {
    const cap = getNNew();
    if (checked) {
        if (selectedTopicIds.size >= cap) {
            toast(`At most ${cap} topics per session. Increase the question count to add more.`, true);
            renderTopicList();
            return;
        }
        selectedTopicIds.add(id);
    } else {
        selectedTopicIds.delete(id);
    }
    updateTopicCounter();
    // Re-render to update .selected class without losing search filter
    renderTopicList();
}

function clearTopicSelection() {
    selectedTopicIds.clear();
    updateTopicCounter();
    renderTopicList();
}

function updateTopicCounter() {
    const el = document.getElementById('topic-picker-counter');
    const n = selectedTopicIds.size;
    if (n === 0) {
        el.textContent = 'Auto: weakest topics';
        el.classList.remove('active');
    } else {
        el.textContent = `${n} / ${getNNew()} selected`;
        el.classList.add('active');
    }
}

function filterTopics() { renderTopicList(); }

/* ----- Session lifecycle ----- */
async function checkResume() {
    try {
        const url = '/api/study/resume' + (SUBJECT_ID ? `?subject_id=${encodeURIComponent(SUBJECT_ID)}` : '');
        const res = await fetch(url);
        const data = await res.json();
        if (data.ok && data.session_id) {
            window._resumeData = data;
            const banner = document.getElementById('resume-banner');
            const remaining = data.questions.length - data.attempts.length;
            document.getElementById('resume-text').textContent =
                `Unfinished session: ${data.attempts.length}/${data.questions.length} answered. Resume?`;
            banner.classList.add('active');
        }
    } catch (e) { /* silent */ }
}

async function startSession() {
    if (sessionMode === 'mock') return startMockSession();
    setLoading('btn-start', true);
    const topicIds = Array.from(selectedTopicIds);
    const nNew = getNNew();
    const difficulty = getDifficulty();
    const expectedCount = topicIds.length || nNew;
    document.getElementById('build-progress').classList.add('active');
    document.getElementById('build-progress-count').textContent = `Preparing ${expectedCount} new questions...`;
    document.getElementById('build-progress-current').textContent = '';
    try {
        const body = {n_new: nNew, difficulty: difficulty};
        if (SUBJECT_ID) body.subject_id = parseInt(SUBJECT_ID, 10);
        if (topicIds.length) body.topic_ids = topicIds;
        const res = await fetch('/api/study/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Failed to start session');
        pollBuild(data.build_id);
    } catch (e) {
        toast(e.message, true);
        setLoading('btn-start', false);
        document.getElementById('build-progress').classList.remove('active');
    }
}

async function startMockSession() {
    const sel = document.getElementById('select-paper');
    const paperId = parseInt(sel.value, 10);
    if (!Number.isFinite(paperId)) {
        toast('Pick a paper first.', true);
        return;
    }
    setLoading('btn-start', true);
    try {
        const body = {paper_id: paperId};
        if (SUBJECT_ID) body.subject_id = parseInt(SUBJECT_ID, 10);
        const res = await fetch('/api/study/mock-start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Failed to start mock');
        sessionId = data.session_id;
        questions = data.questions;
        currentPos = 0;
        attempts = [];
        mockAnswers = new Array(questions.length).fill(null).map(() => ({answer: '', time_spent_seconds: 0}));
        document.getElementById('start-screen').style.display = 'none';
        document.getElementById('question-screen').style.display = 'block';
        startMockTimer();
        showQuestion();
    } catch (e) {
        toast(e.message, true);
    }
    setLoading('btn-start', false);
}

function pollBuild(buildId) {
    if (buildPollTimer) clearTimeout(buildPollTimer);
    const tick = async () => {
        try {
            const res = await fetch(`/api/study/build-status?build_id=${encodeURIComponent(buildId)}`);
            const data = await res.json();
            if (!data.ok) throw new Error(data.error || 'build status failed');
            const ev = data.events;
            if (ev.length) {
                const last = ev[ev.length - 1];
                document.getElementById('build-progress-count').textContent =
                    `Generated ${last.done} / ${last.total} questions`;
                document.getElementById('build-progress-current').textContent = last.label;
            }
            if (data.done) {
                if (data.error) throw new Error(data.error);
                sessionId = data.session_id;
                questions = data.questions;
                currentPos = 0;
                attempts = [];
                document.getElementById('start-screen').style.display = 'none';
                document.getElementById('question-screen').style.display = 'block';
                showQuestion();
                setLoading('btn-start', false);
                return;
            }
            buildPollTimer = setTimeout(tick, 1000);
        } catch (e) {
            toast(e.message, true);
            setLoading('btn-start', false);
            document.getElementById('build-progress').classList.remove('active');
        }
    };
    tick();
}

async function resumeSession() {
    const data = window._resumeData;
    if (!data) return;
    sessionId = data.session_id;
    questions = data.questions;
    attempts = (data.attempts || []).map(a => ({...a}));
    // Find first unanswered position
    const answeredPos = new Set(attempts.map(a => a.position));
    currentPos = 0;
    for (let i = 0; i < questions.length; i++) {
        if (!answeredPos.has(i)) { currentPos = i; break; }
        currentPos = i + 1;
    }
    document.getElementById('start-screen').style.display = 'none';
    if (currentPos >= questions.length) {
        document.getElementById('done-screen').style.display = 'block';
        document.getElementById('done-summary').textContent =
            `You answered ${attempts.length} question${attempts.length !== 1 ? 's' : ''}.`;
    } else {
        document.getElementById('question-screen').style.display = 'block';
        showQuestion();
    }
}

async function discardSession() {
    const data = window._resumeData;
    if (!data) return;
    try {
        await fetch('/api/study/discard', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({session_id: data.session_id}),
        });
    } catch (e) {}
    document.getElementById('resume-banner').classList.remove('active');
    window._resumeData = null;
}

function showQuestion() {
    const q = questions[currentPos];
    document.getElementById('progress-label').textContent = `Question ${currentPos + 1} / ${questions.length}`;
    document.getElementById('progress-bar').style.width = `${(currentPos / questions.length) * 100}%`;
    document.getElementById('kind-badge').textContent = q.kind;
    document.getElementById('kind-badge').className = 'badge badge-' + q.kind;
    document.getElementById('marks-display').textContent = q.marks + (q.marks === 1 ? ' mark' : ' marks');
    document.getElementById('question-text').innerHTML = markdownToHtml(q.text);
    renderFigure(q.figure, 'question-figure');
    // Restore any autosaved draft (or, in mock mode, the previously-typed answer)
    let restored = '';
    if (sessionMode === 'mock' && mockAnswers[currentPos] && mockAnswers[currentPos].answer) {
        restored = mockAnswers[currentPos].answer;
    } else {
        restored = loadAutosave(currentPos);
    }
    document.getElementById('answer-input').value = restored;
    document.getElementById('answer-input').focus();
    // Submit-button label varies by mode
    const submitBtn = document.getElementById('btn-submit');
    if (submitBtn && submitBtn.firstChild) {
        submitBtn.firstChild.textContent = sessionMode === 'mock'
            ? (currentPos >= questions.length - 1 ? 'Finish & Submit Paper ' : 'Save & Next ')
            : 'Submit Answer ';
    }
    // Reset flag UI
    const flagBtn = document.getElementById('btn-flag');
    flagBtn.classList.remove('flagged');
    document.getElementById('flag-label').textContent = 'Flag';
    renderMath(document.getElementById('question-text'));
    questionShownAt = Date.now();
}

/* ----- Submit (with streaming feedback, fix #17) ----- */
async function submitAnswer() {
    if (sessionMode === 'mock') return submitMockAnswer();
    const answer = document.getElementById('answer-input').value.trim();
    if (!answer) { toast('Please type an answer before submitting.', true); return; }
    const q = questions[currentPos];
    setLoading('btn-submit', true);

    // Pre-show result screen with empty feedback for live streaming
    document.getElementById('question-screen').style.display = 'none';
    document.getElementById('result-screen').style.display = 'block';
    document.getElementById('result-score').textContent = '...';
    document.getElementById('result-score').className = 'result-score';
    document.getElementById('result-sm2').textContent = 'Grading...';
    const fbEl = document.getElementById('result-feedback');
    fbEl.textContent = '';
    fbEl.classList.add('streaming');
    document.getElementById('btn-next').disabled = true;

    let buffer = '';
    let finalResult = null;
    try {
        const elapsed = questionShownAt ? Math.max(0, Math.floor((Date.now() - questionShownAt) / 1000)) : null;
        const res = await fetch('/api/study/submit-stream', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                session_id: sessionId,
                position: currentPos,
                answer: answer,
                time_spent_seconds: elapsed,
            }),
        });
        if (!res.ok || !res.body) throw new Error('Stream failed');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let textBuf = '';
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            textBuf += decoder.decode(value, {stream: true});
            const events = textBuf.split('\\n\\n');
            textBuf = events.pop();
            for (const block of events) {
                const line = block.split('\\n').find(l => l.startsWith('data: '));
                if (!line) continue;
                let ev;
                try { ev = JSON.parse(line.slice(6)); } catch (e) { continue; }
                if (ev.type === 'delta') {
                    buffer += ev.text;
                    fbEl.textContent = extractFeedbackPreview(buffer);
                } else if (ev.type === 'final') {
                    finalResult = ev;
                } else if (ev.type === 'error') {
                    throw new Error(ev.message);
                }
            }
        }
        if (!finalResult) throw new Error('No grade returned');
        attempts.push({
            ...finalResult,
            position: currentPos,
            text: q.text,
            markscheme: q.markscheme || '',
            user_answer: answer,
        });
        clearAutosave(currentPos);
        showResult(finalResult);
    } catch (e) {
        toast(e.message, true);
        // Revert to question screen so user can retry
        document.getElementById('result-screen').style.display = 'none';
        document.getElementById('question-screen').style.display = 'block';
    }
    setLoading('btn-submit', false);
}

/** Mock paper: store the answer locally and advance — no grading until Finish. */
function submitMockAnswer() {
    const answer = document.getElementById('answer-input').value;
    const elapsed = questionShownAt
        ? Math.max(0, Math.floor((Date.now() - questionShownAt) / 1000))
        : 0;
    mockAnswers[currentPos] = {
        answer: (answer || '').trim(),
        time_spent_seconds: (mockAnswers[currentPos].time_spent_seconds || 0) + elapsed,
    };
    clearAutosave(currentPos);
    if (currentPos >= questions.length - 1) {
        finishMockSession();
    } else {
        currentPos++;
        showQuestion();
    }
}

async function finishMockSession() {
    stopMockTimer();
    document.getElementById('question-screen').style.display = 'none';
    document.getElementById('done-screen').style.display = 'block';
    const summary = document.getElementById('done-summary');
    summary.innerHTML = `Grading ${questions.length} questions in parallel… <span class="spinner" style="display:inline-block;vertical-align:middle;"></span>`;
    document.getElementById('done-screen').querySelector('.start-btn-wrap').style.display = 'none';
    try {
        const res = await fetch('/api/study/mock-submit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                session_id: sessionId,
                attempts: mockAnswers.map((a, i) => ({
                    position: i,
                    answer: a.answer,
                    time_spent_seconds: a.time_spent_seconds,
                })),
            }),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Grading failed');
        const pct = data.total_possible
            ? Math.round((data.total_awarded / data.total_possible) * 100)
            : 0;
        summary.innerHTML =
            `Mock complete. <strong>${data.total_awarded} / ${data.total_possible}</strong> (${pct}%) ` +
            `over ${data.graded_count} answered question${data.graded_count !== 1 ? 's' : ''}.`;
        document.getElementById('done-screen').querySelector('.start-btn-wrap').style.display = '';
    } catch (e) {
        summary.textContent = `Error: ${e.message}`;
    }
}

/** Extract anything after FEEDBACK: from a streaming partial response. */
function extractFeedbackPreview(text) {
    const idx = text.search(/FEEDBACK:\\s*/i);
    if (idx === -1) return text;
    return text.slice(idx).replace(/^FEEDBACK:\\s*/i, '');
}

function showResult(data) {
    const fbEl = document.getElementById('result-feedback');
    fbEl.classList.remove('streaming');
    const scoreEl = document.getElementById('result-score');
    scoreEl.textContent = `${data.marks_awarded} / ${data.total_marks}`;
    const pct = data.total_marks ? (data.marks_awarded / data.total_marks) : 0;
    scoreEl.className = 'result-score ' + (pct >= 0.8 ? 'correct' : pct >= 0.5 ? 'partial' : 'incorrect');
    document.getElementById('result-sm2').textContent = `SM-2 grade: ${data.sm2_grade} / 5`;
    fbEl.innerHTML = markdownToHtml(data.feedback);
    const isLast = currentPos >= questions.length - 1;
    document.getElementById('next-label').textContent = isLast ? 'Finish Session' : 'Next Question';
    document.getElementById('btn-next').disabled = false;
    renderMath(fbEl);
}

function nextQuestion() {
    document.getElementById('result-screen').style.display = 'none';
    currentPos++;
    if (currentPos >= questions.length) {
        document.getElementById('done-screen').style.display = 'block';
        document.getElementById('done-summary').textContent =
            `You answered ${attempts.length} question${attempts.length !== 1 ? 's' : ''}.`;
    } else {
        document.getElementById('question-screen').style.display = 'block';
        showQuestion();
    }
}

/* ----- Flag (#19) ----- */
async function flagCurrent() {
    const q = questions[currentPos];
    const flagBtn = document.getElementById('btn-flag');
    const becomingFlagged = !flagBtn.classList.contains('flagged');
    let reason = '';
    if (becomingFlagged) {
        reason = prompt('What\\'s wrong with this question? (optional)') || '';
    }
    try {
        const res = await fetch('/api/study/flag', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question_id: q.question_id, flagged: becomingFlagged, reason: reason}),
        });
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Flag failed');
        flagBtn.classList.toggle('flagged', becomingFlagged);
        document.getElementById('flag-label').textContent = becomingFlagged ? 'Flagged' : 'Flag';
        toast(becomingFlagged ? 'Question flagged for review' : 'Flag removed', false);
    } catch (e) {
        toast(e.message, true);
    }
}

/* ----- Review modal ----- */
async function showReview() {
    try {
        const res = await fetch(`/api/study/complete?session_id=${sessionId}`);
        const data = await res.json();
        if (!data.ok) throw new Error(data.error || 'Failed to load review');
        reviewData = data.attempts;
        reviewIndex = 0;
        renderReviewCard();
        document.getElementById('review-overlay').classList.add('active');
    } catch (e) {
        toast(e.message, true);
    }
}

function renderReviewCard() {
    const item = reviewData[reviewIndex];
    const pct = item.total_marks ? (item.marks_awarded / item.total_marks) : 0;
    const result = pct >= 0.8 ? 'CORRECT' : pct >= 0.5 ? 'PARTIAL' : 'INCORRECT';
    const color = pct >= 0.8 ? '#22c55e' : pct >= 0.5 ? '#eab308' : '#ef4444';
    document.getElementById('review-counter').textContent = `${reviewIndex + 1} / ${reviewData.length}`;
    const tagEl = document.getElementById('review-tag');
    tagEl.textContent = result;
    tagEl.style.color = color;
    document.getElementById('review-question').innerHTML = markdownToHtml(item.text);
    renderFigure(item.figure, 'review-figure');
    document.getElementById('review-answer').innerHTML = markdownToHtml(item.user_answer);
    document.getElementById('review-markscheme').innerHTML = markdownToHtml(item.markscheme);
    document.getElementById('review-feedback').innerHTML = markdownToHtml(item.feedback);
    document.getElementById('consolidate-input').value = item.consolidation || '';
    document.getElementById('btn-review-prev').style.visibility = reviewIndex > 0 ? 'visible' : 'hidden';
    const isLast = reviewIndex >= reviewData.length - 1;
    document.getElementById('review-next-label').textContent = isLast ? 'Done' : 'Next';
    updateNextButton();
    renderMath(document.getElementById('review-question'));
    renderMath(document.getElementById('review-answer'));
    renderMath(document.getElementById('review-markscheme'));
    renderMath(document.getElementById('review-feedback'));
}

function onConsolidateInput(el) {
    const item = reviewData[reviewIndex];
    item.consolidation = el.value;
    updateNextButton();
    // Debounced save to server (fix #1: persist consolidation)
    if (consolidateSaveTimer) clearTimeout(consolidateSaveTimer);
    consolidateSaveTimer = setTimeout(() => saveConsolidation(item), 500);
}

async function saveConsolidation(item) {
    try {
        await fetch('/api/study/consolidate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                session_id: sessionId,
                position: item.position,
                note: item.consolidation || '',
            }),
        });
        const saved = document.getElementById('consolidate-saved');
        saved.classList.add('visible');
        setTimeout(() => saved.classList.remove('visible'), 1200);
    } catch (e) { /* silent */ }
}

function updateNextButton() {
    const btn = document.getElementById('btn-review-next');
    const item = reviewData[reviewIndex];
    const hasContent = (item.consolidation || '').trim().length > 0;
    btn.disabled = !hasContent;
    btn.style.opacity = hasContent ? '1' : '0.35';
    btn.style.cursor = hasContent ? 'pointer' : 'not-allowed';
}

function reviewNext() {
    if (reviewIndex >= reviewData.length - 1) {
        document.getElementById('review-overlay').classList.remove('active');
        location.href = '/' + (SUBJECT_ID ? `?subject=${encodeURIComponent(SUBJECT_ID)}` : '');
    } else {
        reviewIndex++;
        renderReviewCard();
    }
}

function reviewPrev() {
    if (reviewIndex > 0) {
        reviewIndex--;
        renderReviewCard();
    }
}

/* ----- Keyboard shortcuts (#14) ----- */
document.addEventListener('keydown', (e) => {
    const overlayActive = document.getElementById('review-overlay').classList.contains('active');
    if (overlayActive) {
        if (e.key === 'Escape') {
            document.getElementById('review-overlay').classList.remove('active');
        } else if (e.key === 'ArrowRight') {
            const btn = document.getElementById('btn-review-next');
            if (!btn.disabled) { e.preventDefault(); reviewNext(); }
        } else if (e.key === 'ArrowLeft') {
            if (reviewIndex > 0) { e.preventDefault(); reviewPrev(); }
        }
        return;
    }
    // Question screen: Ctrl+Enter submits
    if (document.getElementById('question-screen').style.display !== 'none') {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            submitAnswer();
        }
    }
    // Result screen: → advances
    if (document.getElementById('result-screen').style.display !== 'none') {
        if (e.key === 'ArrowRight' || e.key === 'Enter') {
            const btn = document.getElementById('btn-next');
            if (!btn.disabled) { e.preventDefault(); nextQuestion(); }
        }
    }
});

/* On load: check for resumable session and prime stepper button state */
checkResume();
onNNewChange();
</script>
</body>
</html>'''
