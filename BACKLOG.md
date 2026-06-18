# AETHER — Build Backlog

Yaro decides WHAT. Builder decides HOW and ships one item per run.
Top unblocked item gets pulled first. Keep entries concrete: a change + an
acceptance check. Vague items get marked `NEEDS-SPEC` and escalated, not guessed.

Status keys: `[ ]` todo · `[~]` on a branch awaiting review · `[x]` shipped to main · `[!]` blocked

---

## Now (top of stack)

- [~] **iOS Health sync (Shortcuts + Health Auto Export)** — a PWA can't read
  HealthKit directly, so the iPhone PUSHES Health data to a host receiver and the
  app PULLS it. `health_sync.py` (stdlib, port 8848): `POST /ingest` accepts BOTH
  the Apple Shortcuts shape AND the Health Auto Export nested shape, normalizes to
  one record list (sleep/steps/workouts) with stable `sid`s so re-syncs upsert (no
  dupes); `GET /latest` serves them; token-guarded (public funnel). Client:
  `hxPullSync()` merges by `sid` into HX_ENTRIES on open (throttled 60s), steps
  show in the ambient strip, synced sleep flows into the Sleep tab. Settings → iOS
  Health Sync (token field + "Sync now"). `start_sync.bat` + Startup launcher;
  funnel route `/aether-sync`. sw v87->v88. _Verified: receiver normalizes both
  payloads + dedupes (re-POST stayed 6, value updated 437->450); PUBLIC funnel path
  ingest+latest OK; headless app merge — changed=true, 6 synced, re-pull stayed 6,
  2 sleep nights into Sleep tab; verify.py 15/15; no JS errors._ iPhone-side setup
  recipe handed to Yaro (Shortcuts automation + Health Auto Export config).

- [~] **Health experience overhaul + Sleep tab** — replaced the basic meal-logger
  with the full Aether wellbeing screen (Yaro's aether-health.html mockup): small
  water orb + cross-domain **synthesis line** ("Aether noticed — …"), macro rings
  with the lowest one accented, ambient strip (hydration/movement/sleep), voice +
  photo + chip logging dock, timeline, hydration sparkline, orb "drinks" each log.
  **Sleep is its own screen** (`screenSleep`): last-night big number, 7-night bar
  chart, sleep→performance reflection. One `HX_ENTRIES[]` localStorage model
  across food/water/move/sleep/mood. Photo→macros still routes to LOCAL vision
  first (vision_local.py) then jarvis fallback. Namespaced `hx-`, scoped teal
  world, battery-safe orbs (stop when screen inactive). Home cards for Health +
  Sleep. sw v86->v87. _Verified: verify.py 15/15; headless Chrome run — openHealth/
  openSleep execute clean, 6 entries render, rings compute (56g protein), synthesis
  fires cross-domain, 7 week bars, water log updates ambient. No JS errors._

- [x] **Local vision backend (Ollama) — UNBLOCKS Health, no cloud/credits** —
  SHIPPED. Installed Ollama on the host + pulled `qwen2.5vl:7b` (runs on the RTX
  5070). Added `vision_local.py` (stdlib proxy port 8846, `POST /analyze`
  {image_url|image_b64, prompt} -> Ollama `/api/generate` -> {text}, CORS, health
  check) + `start_vision.bat`. Wired Health to try local vision FIRST (free,
  fast, private), falling back to the jarvis/ntfy path; Settings toggle
  (`aetherLocalVision`, default on). sw v85->v86. _Verified END-TO-END: real meal
  photo -> tailnet upload -> local model returned correct nutrition JSON
  ({chicken/rice/broccoli, 450 kcal, 35P/25C/15F, high}); hlParse handles the
  model's ```json fences; verify.py 15/15._ Expose:
  `tailscale serve --bg --set-path /aether-vision http://127.0.0.1:8846`.

- [!] **Health meal AI estimate — credit blocker RESOLVED via local vision** —
  superseded by the local backend above; cloud credits no longer required.

- [x] **Pre-ship verify script** — SHIPPED to main. `verify.py` checks JS syntax
  (sw.js + all inline scripts via node --check), manifest JSON + theme/bg ==
  `#021014`, every SHELL_ASSETS precache file exists, and `<meta theme-color>` ==
  manifest. _Verified: passes clean on main (15 checks, exit 0); catches all 3
  failure modes (color mismatch, missing asset, JS syntax) with exit 1._

- [!] **Health meal AI estimate — BLOCKED on credits** — feature shipped (PR #5)
  but the live nutrition estimate is unverified: Nous account hit a credit limit
  mid-test ("Model 'anthropic/claude-opus-4.8' requires available credits"), and
  jarvis looked for the attachment "in Downloads" instead of calling
  vision_analyze on the URL. _Unblock: Yaro tops up credits, then re-test a real
  meal photo; if jarvis still mis-routes, add a vision-on-URL rule to AGENTS.md._

- [x] **Health tab — photo meal logging** — SHIPPED to main (PR #5, squash
  `96ad49c`). `screenHealth` from a Home fcard; snap/pick photo -> upload ->
  jarvis estimates `{name,calories,protein,carbs,fat,confidence}` -> localStorage
  -> today's meals + macro totals vs. editable kcal goal. Reuses Radar spine.

- [x] **Build version + Force update** — SHIPPED to main (PR #6, `ff9b48a`).
  Settings → About shows the running SW build (`aether-vNN`), flags a waiting
  update, and a Force-update button clears caches + reloads. sw v84->v85. Durable
  fix for "phone vs repo" cache confusion.

- [x] **Persistent mic grant (getUserMedia + host Whisper)** — SHIPPED on branch
  `feat/persistent-mic-whisper` (PR open). Added `stt_proxy.py` (stdlib HTTP +
  faster-whisper `base`, lazy-loaded; `/transcribe` + `/health`; CORS for the PWA
  origin) and `start_stt.bat`. Client: `makeSttRecognizer()` — a getUserMedia +
  MediaRecorder shim with the SAME interface as webkitSpeechRecognition (VAD
  auto-endpoint on silence), so the whole voice loop runs unchanged; native SR
  kept as automatic fallback (`fallbackToSR`) if the endpoint is down. All `!SR`
  control-flow guards swapped to `!recog`/`VOICE_OK`. Expose tailnet-only:
  `tailscale serve --bg --set-path /aether-stt http://127.0.0.1:8847`.
  _Verified: server transcribes real mp3/webm-opus/m4a-aac clips correctly; CORS
  preflight OK; all 8 inline scripts pass node --check. Live payoff = Yaro's
  iPhone: grant mic once, no re-ask next session._

## Next (unblocked, not yet pulled)

- [x] **Icon brand audit** — install icons had a stale light-theme ground
  (`#f8fafc` white tile) clashing with the dark app. Recomposited the cyan AETHER
  mark onto dark navy `#021014`: icon-180/192/512 at 76% scale; maskable-192/512
  at 50% (tips ±25% from center, inside the circular safe zone). Shipped on
  branch `feat/icon-dark-ground`. _Accept: 192/512/maskable render the cyan mark
  on #021014; no white box; maskable safe-zone clear._
- [x] **Offline shell completeness** — sw.js precache was missing `mark-256.png`
  (home-screen logo), `icon-180`, `maskable-512`. Added all three + bumped to
  v82. Cross-origin Google Fonts intentionally not cached (system fallback stack
  covers offline). Shipped on `feat/offline-shell-precache`. _Accept: all 9
  same-origin shell assets precached & serve 200; SW syntax valid._

## Icebox (needs spec / a decision from Yaro)

- [ ] NEEDS-SPEC: in-app `BUILDER_TOKEN` field (BUILDER.md notes it's typed as a
  prefix today; an in-app field was floated). Decide UX before building.

---

_Builder loop: ORIENT → PLAN → BRANCH → ACT → VERIFY → SHIP. One feature per run,
finish or revert, never ship red, never auto-merge. Log lives in BUILD_LOG.md._

## Ideas (eval-generated)

- [ ] **Sleep Reflection** [Sleep] — The app should provide a sleep reflection feature that analyzes the user's sleep patterns and suggests improvements based on their performance metrics. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Daily Focus Boost** [Sleep] — The app should offer a daily focus boost feature that recommends activities or tasks to improve concentration and productivity based on the user's sleep patterns. This could include personalized recommendations for morning routines, study sessions, or physical exercises. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Personalized Learning Assistant** [Talk] — Integrate a personalized learning assistant that can provide tailored study tips and resources based on the user's progress in preparing for the CPA exam. This feature would be triggered when AETHER detects the user is studying or reviewing past exam questions. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Actionable Recommendations** [Home] — Including actionable recommendations based on Yaro's activities (e.g., workout tips, sleep improvement suggestions) could further enhance the app’s utility and engagement. `effort:large` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Daily Summary with AI Recommendations** [Home] — Implement a feature that provides Yaro with a daily summary of his activities, health status, and actionable recommendations. This would make the app feel more like JARVIS by offering personalized insights and guidance. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Agent-Assisted Prioritization Dashboard** [Plan] — The app could introduce a dashboard that visually represents the prioritization of tasks and appointments. This feature would dynamically update based on user input from the calendar sync, providing a clear view of what needs attention next. It would be triggered when users open the app or navigate to their task management section. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Daily Routine Planner** [Home] — Implement a feature that allows users to set their daily routines, track progress, and receive reminders. This would be particularly useful for someone like Yaro who tracks sleep, food, and workouts. The feature could trigger based on the time of day or specific activities. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Upload Feature** [Radar] — The screenshot lacks an upload feature for workpapers, which is crucial to the app's purpose. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Activity Stream** [Stream] — Implement an Epic Bar at the top of the screen displaying a live feed of all agent activities, such as tool calls and completion notifications. This feature would provide Yaro with immediate visibility into his AI team's progress and efficiency. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Tutoring** [Learn] — Implement real-time tutoring where AETHER provides instant feedback and guidance on the user's performance. This feature would enhance the learning experience by addressing specific areas of weakness in real time, making it more engaging and effective. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent Switcher** [Talk] — The agent-switcher should be more prominently displayed and easily accessible to allow users to switch between different agents if needed. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **Upload functionality** [Radar] — The screenshot does not show the upload feature, which is crucial for AETHER's purpose. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **Conversation History** [Learn] — The screenshot lacks a visible history of previous conversations, which would be useful for AETHER to provide context and continuity. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **Agent-Switcher UI** [Talk] — A clear visual indicator or button to switch between different agents would enhance user experience. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Voice-Activated Mode** [Settings] — Implement a feature that automatically switches the app into voice-activated mode when the user taps on the orb. This would allow for hands-free interaction, enhancing convenience and accessibility. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Agent Activity Dashboard** [Studio] — Implement a dashboard that displays real-time activity and status updates for each agent. This feature would enhance the control hub by providing AETHER with immediate insights into his agents' performance, allowing him to make informed decisions in real time. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Visual Confirmation of Voice Input** [Talk] — Add a small icon or text overlay that appears when the user speaks, indicating 'Listening' or similar. This would provide immediate visual feedback and enhance the user experience by showing they are being heard. `effort:small` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Personalized Insights** [Talk] — Implement personalized insights based on user activity and preferences. For example, if AETHER notices Yaro is preparing for the CPA exam, it could suggest relevant resources or track progress in specific areas. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Ambient health insights** [Health] — Integrate ambient health insights directly into the home screen. For example, display hydration levels and sleep quality in a subtle way to provide users with quick feedback on their health status without needing to open additional sections. `effort:small` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-time Agent Status Updates** [Studio] — Implement a real-time update feature for each agent card that shows the current status of tasks, progress, and any pending actions. This would enhance user experience by providing immediate feedback on what needs attention. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Tutoring Progress Tracking** [Learn] — The app should display AETHER's progress in each topic to help Yaro track his learning journey. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Live Tutoring Session Feedback** [Learn] — Implement a feature that provides immediate feedback on MCQ answers during tutoring sessions. This would help Yaro understand his mistakes in real-time and improve his performance. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Daily Summary Feature** [Home] — Implement a feature that provides Yaro with a concise daily summary of his activities, tasks completed, and any important notifications. This would align well with the epic bar's goal of providing living insight into one’s day. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Personalized Learning Mode** [Settings] — Implement a personalized learning mode that adapts to Yaro's study schedule, providing him with tailored questions and resources based on his progress. This feature would be triggered when he starts preparing for the FAR CPA exam. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Review Feedback** [Radar] — Implement real-time feedback from senior reviewers during the upload process. This feature would allow users to receive immediate insights and corrections, significantly reducing the time needed for review. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Agent Activity Feed** [Stream] — Implementing an interactive real-time stream showing all agent activity, such as tool calls and completion notifications. This feature would enhance the user's experience by providing a clear view of what is happening within their AI team in real time. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent Activity Feed** [Stream] — The screenshot lacks a live feed of agent activity, which is the purpose stated in the EPIC BAR. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Agent Activity Stream** [Stream] — Implement a real-time stream showing all agent activities such as tool calls, completions, and notifications. This feature would provide Yaro with an overview of his AI team's performance in real time, enhancing the user experience by making it feel like he is watching his AI team at work. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Privacy Mode** [Radar] — While the privacy mode is mentioned in the description, there's no visual indicator for users to switch into this mode. Adding a toggle or icon would make it more accessible. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Ambient strip integration** [Health] — Integrate the ambient strip data directly into the main interface, providing a continuous view of hydration, movement, and sleep. This would enhance user engagement by making it easier to monitor these metrics without needing additional taps or screens. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Advanced Voice Commands** [Settings] — Implement a feature that allows AETHER to recognize and execute specific voice commands without the need for manual activation. This could include setting reminders, checking progress on tasks, or even providing quick updates on current activities. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Tutoring Progress Bar** [Learn] — Implement a progress bar that visually represents how far along the user has progressed through their study plan. This feature would provide AETHER with an intuitive way to track and adjust the tutoring sessions based on the user's performance. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Privacy Mode UI** [Radar] — There is no visible indication of the privacy mode or its status. Users might not know if they are in privacy mode and how to switch back. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Voice-Activated Workpaper Review** [Radar] — Implement a voice-activated feature that allows users to upload workpapers directly via voice commands. This would significantly reduce the time needed for initial uploads and could be triggered by saying 'Review workpaper' or similar, enhancing user experience. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Sleep Reflection Text Entry** [Sleep] — A text entry field for users to reflect on their sleep, focus, and food intake would enhance the user experience by allowing them to track and analyze these factors. `effort:small` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Sleep Focus Reflection** [Sleep] — Implement a feature that prompts users with personalized feedback based on their sleep patterns, focus levels, and food intake. This would help users identify trends and make adjustments to improve their performance the next day. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Ambient Health Dashboard** [Health] — An ambient health dashboard that integrates real-time data from various sources (meal logging, macro rings, hydration sparkline) into a single, visually appealing interface. This feature would provide Yaro with an at-a-glance view of his health metrics and progress towards his goals. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent-Specific Commands** [Talk] — Adding specific commands for different agents (e.g., 'Ask CPA', 'Workout Tips') would enhance user experience by providing direct access to relevant information. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Personalized Learning Path** [Talk] — Implement a feature that suggests personalized learning paths based on the user's past interactions and goals. This could include recommended study materials, practice questions, and tips tailored to their CPA exam preparation. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Action Buttons** [Radar] — Adding action buttons below the 'Tap to Talk' prompt could provide quicker access to common functions or commands. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Agent Control Hub** [Studio] — Implement an interface that allows Yaro to manage all agents, view their statuses, switch between them, and trigger builds. This feature is crucial for a control room experience as described in the epic bar. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Command Interface** [Radar] — The current interface lacks a clear voice command feature, which is essential for an AI assistant like AETHER. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Quick Review Mode** [Radar] — Implement a 'Quick Review Mode' that allows users to upload workpapers and receive immediate feedback from senior reviewers. This feature would significantly reduce the time needed for review, aligning with AETHER's epic bar of getting a first pass in under 60 seconds. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Tutoring Feedback** [Learn] — Implement a feature where AETHER provides real-time feedback and encouragement based on the user's responses. This would enhance the learning experience by providing immediate guidance, which is crucial for a spaced-repetition tutor like FSRS. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Task Prioritization Assistant** [Plan] — The app should automatically prioritize tasks by analyzing their urgency and importance, using the Covey quadrant. This feature would help Yaro focus on high-impact activities first, enhancing his productivity during exam prep. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice-first dock** [Health] — The voice-first dock is not visible, which could be a feature to enhance user interaction. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Ambient Health Timeline** [Health] — A timeline that aggregates and visualizes daily health metrics (hydration, movement, sleep) from the Watch in a single, easy-to-read format. This feature would provide Yaro with an at-a-glance view of his health status throughout the day. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Contextual Voice-First Calendar Integration** [Talk] — Integrate a feature that allows AETHER to access and provide updates on Yaro's calendar directly through voice commands. This would be particularly useful during exam prep, as it could help manage time effectively by suggesting breaks or scheduling study sessions. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Real-Time Reviewer Feedback** [Radar] — Implement an AI feature that provides real-time feedback to the uploader during the upload process, helping them correct any issues before submission. This would significantly reduce the time needed for senior reviewers and enhance user experience. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Agent-Assisted Prioritization with AI Insights** [Plan] — Integrate AETHER's AI to provide real-time insights and suggestions for prioritizing tasks based on user habits, calendar events, and task importance. This feature would enhance the app’s intelligence and utility. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Contextual Voice Summary** [Talk] — Implementing a feature that provides a quick summary of the last conversation, such as 'Last said: [summary]' when the user taps to talk. This would help users quickly recall what was discussed and ensure they are on track with their goals or tasks. `effort:small` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Agent Status Overview** [Studio] — Implement a dashboard that provides an overview of all agents, their recent activities, and current statuses. This feature would be invaluable for Yaro to quickly assess the progress and status of his various tasks. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Epic Bar** [Stream] — The screenshot lacks a clear visual representation of the 'EPIC BAR' as described in the stream purpose. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Activity Feed** [Stream] — Implement a real-time activity feed that shows all agent activities, tool calls, completions, and notifications in a clear, readable format. This feature would allow users to see their AI team at work in real time, enhancing transparency and engagement. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Quick Review Notification** [Radar] — Implement a quick review notification system where the app sends a push notification with senior reviewer's findings within 60 seconds of upload. This feature would significantly enhance user experience by providing immediate feedback. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Tutor Feedback** [Learn] — The screenshot lacks a clear indication of the tutoring feedback or progress tracking. It would be beneficial to have a visual representation of where AETHER is in the learning process. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Progress Tracking** [Learn] — Implement a progress bar or gauge that visually represents how far along the user is with their learning. This feature would provide AETHER's users with an intuitive way to see their progress and areas where they need more focus, enhancing the overall experience. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Health Tracking** [Health] — The screenshot lacks specific health tracking features such as calorie intake, heart rate monitoring, and detailed sleep analysis. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Daily Health Summary** [Health] — A feature that provides a comprehensive daily health summary based on the user's activity data from their iPhone and Watch. This includes calorie intake, heart rate trends, sleep quality analysis, and hydration levels. It would trigger automatically at the end of each day to provide a holistic view of the user’s health. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **✨ Visual Conversation Timeline** [Talk] — Implementing a visual timeline at the bottom of the screen that shows past conversations and highlights key points would enhance user experience by providing context without needing to scroll through text history. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent Control Hub** [Studio] — The screenshot lacks a clear representation of the agent control hub, which is described as showing recent work and live status for each agent. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **Calendar Sync Confirmation** [Plan] — The app should confirm calendar sync after the user confirms tasks and plans. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Agent-Assisted Prioritization** [Plan] — Implement a feature where AETHER suggests prioritized tasks based on the user's calendar, sleep patterns, and recent activity. This would help users focus on high-priority items while maintaining balance. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Orb Animation** [Talk] — The orb could have a subtle animation to indicate it's active and ready for voice input. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **Agent-Switcher Feedback** [Talk] — Adding feedback when switching agents would enhance user experience by providing clarity on the current agent handling the conversation. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Daily Briefing** [Home] — Implement a daily briefing feature that summarizes AETHER's tasks for the day, highlights important upcoming events or deadlines, and provides personalized health tips. This would align with the epic bar concept of providing living insight into one’s day. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Control Toggle** [Settings] — A toggle for enabling/disabling voice control would be useful, as it allows users to switch between voice and text input. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Smart Mode** [Settings] — Implement a 'Smart Mode' that automatically adjusts the app's settings based on user activity, such as turning off voice control during intense study sessions and enabling it for casual conversations. This feature would enhance the app’s ability to adapt to different user needs. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent Status Updates** [Studio] — The screenshot lacks a clear indication of the status of each agent, such as 'Online', 'Offline', or 'Busy'. This is crucial for Yaro to quickly assess which agents are available. `effort:small` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Agent Control Hub Dashboard** [Studio] — Implement a dashboard that displays the status of all agents, recent work logs, and live triggers. This would provide Yaro with an overview of his AI assistants' activities and availability in real-time, enhancing productivity. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent Activity Stream** [Stream] — The screenshot lacks a visual representation of agent activity, making it difficult to understand the live feed's purpose. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Agent Activity Visualization** [Stream] — Implement an interactive timeline or dashboard that visually represents agent activity, tool calls, and completion events in real-time. This feature would provide Yaro with a clear overview of his AI team's performance, enhancing the app's utility for exam preparation. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Input** [Radar] — The current design lacks a clear visual cue for voice input, which is crucial for an AI assistant. Adding a microphone icon or a 'Speak Now' button would enhance user experience. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Real-Time Workpaper Reviewer** [Radar] — Implement an AI-driven real-time workpaper review feature that provides immediate feedback and suggestions to Yaro. This would significantly reduce the time needed for senior reviewers, making it possible to get a first pass in under 60 seconds. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Feedback** [Learn] — The user should receive immediate voice feedback after asking a question to ensure they understand the response. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Personalized Study Plan** [Learn] — Implement a feature that generates a personalized study plan based on the user's performance in each topic. This would help Yaro focus on areas where he needs improvement, such as governmental funds, and provide structured guidance for his preparation. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Agent-assisted prioritization** [Plan] — The app should provide an agent-assisted prioritization feature to help Yaro prioritize his tasks and exam preparation. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Calendar Sync with Task Management** [Plan] — Integrate a seamless calendar sync with task management, allowing Yaro to see his schedule and tasks in one place. This feature would help him manage his time more effectively for both work and exam preparation. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Sleep Log Entry** [Sleep] — The screenshot lacks a direct way to enter sleep log details, such as duration and quality. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Daily Sleep Reflection** [Sleep] — Implement a feature that prompts AETHER with personalized reflections based on the user's sleep data. For example, if it detects three consecutive nights of less than seven hours' sleep, it could suggest strategies to improve sleep quality and alert the user about potential impacts on focus and performance. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Health Tracking Integration** [Health] — The app should integrate with Yaro's iPhone and Watch to automatically log his meals, hydration, movement, and sleep data. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Personalized Health Timeline** [Health] — A feature that displays a daily timeline of Yaro's health metrics (meals, hydration, movement, sleep) with visual sparklines. This would provide an at-a-glance view of his health status and help him make informed decisions. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice History** [Talk] — It would be beneficial to have a voice history feature that allows users to review previous conversations with AETHER. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **Customizable Greeting** [Talk] — Adding the ability for users to customize their greeting when starting a conversation could enhance personalization and user experience. `effort:small` `impact:medium` _(eval 2026-06-17)_
- [ ] **✨ Personalized Calendar Integration** [Talk] — Integrate AETHER with the user's calendar to provide real-time updates on upcoming events, deadlines, and appointments. This feature would be particularly useful for professionals like Yaro who need to manage their schedule efficiently. `effort:medium` `impact:high` _(epic idea, eval 2026-06-17)_
- [ ] **Voice Commands** [Home] — The current design only allows for voice input through a tap. Adding more natural voice commands could enhance the user experience. `effort:medium` `impact:high` _(eval 2026-06-17)_
- [ ] **Personalized Insights** [Home] — Displaying personalized insights or summaries of today's activities and tasks would help users quickly understand their day-to-day progress and priorities. `effort:large` `impact:high` _(eval 2026-06-17)_
- [ ] **✨ Daily Summary Card** [Home] — Implement a daily summary card that appears when the app is opened, providing a quick glance at today's tasks and progress. This feature would align with AETHER's goal of delivering living insight. `effort:large` `impact:high` _(epic idea, eval 2026-06-17)_
