import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const transportSource = read("../src/services/realtimeVoice.js");
const hookSource = read("../src/hooks/useRealtimeVoiceSession.js");
const panelSource = read("../src/components/voice/VoiceConversation.jsx");
const chatSource = read("../src/components/Chat.jsx");
const cssSource = read("../src/styles.css");

test("one click starts a persistent session, not a per-utterance recorder", () => {
  // MediaRecorder restarted per chunk drops audio exactly when someone starts
  // speaking, which is when it matters most.
  assert.match(panelSource, /Start voice conversation/);
  assert.match(panelSource, /End voice conversation/);
  // The word appears in a comment explaining why it is not used.
  assert.doesNotMatch(transportSource, /new MediaRecorder/);
  assert.match(transportSource, /audioWorklet\.addModule/);
  assert.match(transportSource, /registerProcessor\("pcm-capture"/);
});

test("the microphone is opened with echo cancellation", () => {
  // Without it the assistant's own voice is captured and resubmitted as if the
  // user had asked it.
  assert.match(transportSource, /echoCancellation: true/);
  assert.match(transportSource, /noiseSuppression: true/);
  assert.match(transportSource, /autoGainControl: true/);
});

test("no credential ever reaches the socket URL", () => {
  assert.match(transportSource, /openVoiceSession/);
  assert.match(transportSource, /session\.session_token/);
  for (const secret of ["api_key", "apiKey", "elevenlabs", "deepseek", "password"]) {
    assert.doesNotMatch(transportSource, new RegExp(secret, "i"), secret);
  }
  // The authenticated header is used for the HTTP mint, never the socket.
  assert.match(transportSource, /"X-Development-Session": getDevelopmentSession\(\)/);
});

test("the transcript is submitted automatically with no send button", () => {
  assert.match(hookSource, /case "transcript\.final"/);
  assert.match(hookSource, /onTranscript\?\.\(/);
  assert.match(panelSource, /there is no send button/i);
});

test("the answer plays automatically and in order", () => {
  assert.match(transportSource, /assistant\.audio_chunk/);
  assert.match(transportSource, /this\.audioQueue\.push/);
  assert.match(transportSource, /#playNext/);
  // A failed segment must not stall the queue behind it.
  assert.match(transportSource, /audio\.onerror = advance/);
});

test("interruption stops playback before telling the server", () => {
  // Waiting for the round trip would leave the assistant talking over the user.
  const interrupt = transportSource.slice(
    transportSource.indexOf("interrupt(turnId)"),
    transportSource.indexOf("stopPlayback() {"),
  );
  assert.ok(interrupt.indexOf("this.stopPlayback()") < interrupt.indexOf("response.cancel"));
  assert.match(transportSource, /type: "response\.cancel"/);
});

test("interrupting clears every queued segment and its object URL", () => {
  const stop = transportSource.slice(
    transportSource.indexOf("stopPlayback() {"),
    transportSource.indexOf("#enqueueAudio(payload) {"),
  );
  assert.match(stop, /this\.currentAudio\.pause\(\)/);
  assert.match(stop, /this\.audioQueue = \[\]/);
  assert.match(stop, /URL\.revokeObjectURL/);
  assert.match(stop, /this\.objectUrls\.clear\(\)/);
});

test("stopping releases the microphone, the graph, the socket and the token", () => {
  const stop = transportSource.slice(transportSource.indexOf("async stop()"));
  assert.match(stop, /this\.stopPlayback\(\)/);
  // Stopping the tracks is what actually turns the microphone light off.
  assert.match(stop, /getTracks\(\)\.forEach\(\(track\) => track\.stop\(\)\)/);
  assert.match(stop, /this\.node\?\.disconnect\(\)/);
  assert.match(stop, /this\.context\?\.close\(\)/);
  assert.match(stop, /this\.socket\.close\(\)/);
  assert.match(stop, /closeVoiceSession\(this\.token\)/);
});

test("unmounting tears the session down rather than leaving a hot microphone", () => {
  assert.match(hookSource, /return \(\) => \{/);
  assert.match(hookSource, /mountedRef\.current = false;/);
  assert.match(hookSource, /teardown\(\);/);
});

test("a denied microphone is explained, not shown as a generic failure", () => {
  assert.match(hookSource, /NotAllowedError/);
  assert.match(hookSource, /Microphone access was blocked/);
});

test("reconnection is bounded so a dead backend cannot spin forever", () => {
  assert.match(hookSource, /MAX_RECONNECTS/);
  assert.match(hookSource, /attemptsRef\.current >= MAX_RECONNECTS/);
});

test("voice mode degrades to the text composer when unavailable", () => {
  assert.match(panelSource, /voice-panel--unavailable/);
  assert.match(panelSource, /You can still type your question below/);
  assert.match(hookSource, /fetchVoiceCapabilities/);
  assert.match(hookSource, /capabilities\?\.stt_available && capabilities\?\.vad_available/);
});

test("every voice state is announced to the user", () => {
  for (const state of [
    "listening", "user_speaking", "transcribing", "thinking", "assistant_speaking", "interrupted",
  ]) {
    assert.match(panelSource, new RegExp(state), state);
  }
  assert.match(panelSource, /Zara is speaking/);
  assert.match(panelSource, /You&apos;re speaking|You're speaking/);
});

test("an interruption is visible to the user", () => {
  assert.match(panelSource, /Zara was interrupted/);
  assert.match(hookSource, /case "assistant\.interrupted"/);
});

test("controls are keyboard reachable and labelled", () => {
  assert.match(panelSource, /aria-label="Voice conversation"/);
  assert.match(panelSource, /aria-label="Stop Zara speaking"/);
  assert.match(panelSource, /aria-live="polite"/);
  assert.match(panelSource, /role="alert"/);
  assert.match(cssSource, /\.voice-panel-actions button:focus-visible/);
});

test("voice turns render in the normal conversation, not a second copy", () => {
  assert.match(chatSource, /<VoiceConversation/);
  assert.match(chatSource, /onTranscript=\{addVoiceTranscript\}/);
  assert.match(chatSource, /onAnswer=\{addVoiceAnswer\}/);
  // The backend already persisted the spoken turn; re-sending it would double it.
  assert.doesNotMatch(chatSource, /addVoiceTranscript[\s\S]{0,200}sendMessage\(/);
  assert.match(chatSource, /answer_source: "voice"/);
});

test("the text composer stays available while voice is on", () => {
  assert.match(chatSource, /copilot-composer-wrap/);
  const panelIndex = chatSource.indexOf("<VoiceConversation");
  const composerIndex = chatSource.indexOf("copilot-composer-wrap");
  assert.ok(panelIndex < composerIndex, "voice sits above the composer, replacing nothing");
});

test("the dev proxy forwards the WebSocket upgrade, not just HTTP", () => {
  // Without ws:true Vite proxies /api/voice/session as HTTP and silently drops
  // the upgrade, so the socket never connects and voice mode looks broken.
  const viteConfig = read("../vite.config.js");
  assert.match(viteConfig, /ws: true/);
});

test("audio is downsampled with a filter, not by dropping samples", () => {
  // Decimating 48k -> 16k by keeping one sample in three folds everything
  // above 8 kHz back into the speech band, and that aliasing is what makes
  // speech recognition mishear words.
  const worklet = transportSource.slice(
    transportSource.indexOf("const WORKLET_SOURCE"),
    transportSource.indexOf("export class VoiceTransport"),
  );
  assert.match(worklet, /this\.sum \+= channel\[i\]/);
  assert.match(worklet, /this\.sum \/ this\.count/);
  // Exact detector frames, so the server never re-chunks.
  assert.match(worklet, /this\.filled === this\.frameSamples/);
  assert.match(transportSource, /export const FRAME_SAMPLES = 512/);
});

test("the audio context is resumed, since it starts suspended after the click is spent", () => {
  // Starting a session awaits the session token and the microphone permission
  // before the context is built, by which point the click that authorised it
  // no longer counts as user activation. Chrome then creates the context
  // suspended, and a suspended context never runs the worklet -- the socket
  // opens, no audio is ever captured, and the session looks like the assistant
  // simply ignoring you.
  const source = readFileSync(
    new URL("../src/services/realtimeVoice.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /if \(this\.context\.state === "suspended"\) await this\.context\.resume\(\)/);
});

test("capture that produces nothing is reported instead of failing silently", () => {
  // The worklet emits frames whether or not anyone is speaking, so zero frames
  // means capture is dead, never a quiet room.
  const source = readFileSync(
    new URL("../src/services/realtimeVoice.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /framesSent/);
  assert.match(source, /No audio is reaching the server/);
  // And the watchdog must not outlive the session.
  assert.match(source, /clearTimeout\(this\.captureWatchdog\)/);
});

test("the browser reports when the answer has actually finished playing", () => {
  // The server delivers a half-minute answer in about a second, so it cannot
  // know when the user stops hearing it. Without this report the session went
  // back to listening mid-answer and interrupting had nothing to interrupt.
  const source = readFileSync(
    new URL("../src/services/realtimeVoice.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /playback\.finished/);
  // Reported when the queue drains, not when the last segment arrives.
  assert.match(source, /if \(this\.currentAudio \|\| this\.audioQueue\.length\) return;/);
});

test("segments already in flight are dropped once the turn is cut off", () => {
  // Several segments are usually already in the browser when the user cuts in.
  // Playing them is exactly the "it keeps talking after I interrupt" problem.
  const source = readFileSync(
    new URL("../src/services/realtimeVoice.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /cancelledTurns/);
  assert.match(source, /if \(this\.cancelledTurns\.has\(payload\.turn_id\)\) return;/);
});

test("the capture worklet has a silent path to the destination", () => {
  // A worklet with no route to the destination is never pulled by the
  // rendering graph, so process() never runs and not a single frame is
  // captured. Leaving it unconnected to keep capture inaudible is what made
  // the microphone look dead while the socket sat open -- the failure the
  // "No audio is reaching the server" warning was reporting.
  //
  // A muted gain node gives the graph its path without routing the microphone
  // to the speakers.
  const source = readFileSync(
    new URL("../src/services/realtimeVoice.js", import.meta.url),
    "utf8",
  );
  assert.match(source, /this\.silence\.gain\.value = 0;/);
  assert.match(source, /this\.node\.connect\(this\.silence\);/);
  assert.match(source, /this\.silence\.connect\(this\.context\.destination\);/);

  // The source still feeds the worklet, and the worklet is still the only
  // thing that reaches the socket.
  assert.match(source, /this\.source\.connect\(this\.node\);/);
  assert.doesNotMatch(source, /this\.source\.connect\(this\.context\.destination\)/);

  // And the extra node is torn down with the rest of the graph.
  assert.match(source, /this\.silence\?\.disconnect\(\);/);
});
