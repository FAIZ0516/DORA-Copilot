/**
 * Transport for the realtime voice session.
 *
 * Owns three things the React layer should not: the WebSocket, microphone
 * capture, and assistant audio playback. Everything is disposable — `stop()`
 * releases the microphone, the audio graph, the socket and any queued audio,
 * so a component unmount can never leave a hot microphone behind.
 */

import { getDevelopmentSession } from "./conversations";

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");

// Silero needs 16 kHz mono; the worklet downsamples to this before sending.
export const TARGET_SAMPLE_RATE = 16000;
// Silero's frame size. Emitting exactly this avoids server-side re-chunking.
export const FRAME_SAMPLES = 512;

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Development-Session": getDevelopmentSession(),
  };
}

export async function fetchVoiceCapabilities() {
  const response = await fetch(`${API_BASE}/api/voice/capabilities`);
  if (!response.ok) throw new Error("Voice capabilities could not be read.");
  return response.json();
}

/** Mint a short-lived socket token over the authenticated HTTP API. */
export async function openVoiceSession(payload) {
  const response = await fetch(`${API_BASE}/api/voice/session`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload || {}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Voice mode could not be started.");
  }
  return response.json();
}

export async function closeVoiceSession(token) {
  if (!token) return;
  await fetch(`${API_BASE}/api/voice/session/${token}`, {
    method: "DELETE",
    headers: headers(),
  }).catch(() => {
    // The socket closing already invalidates the token server-side; a failed
    // courtesy DELETE must never block teardown.
  });
}

export function voiceSocketUrl(token) {
  const base = API_BASE || window.location.origin;
  const url = new URL(`${base}/api/voice/session/${token}`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/**
 * The capture worklet, inlined so there is no extra file to serve and no
 * chance of the worklet and its consumer drifting apart.
 *
 * A worklet runs on the audio thread, so capture is not affected by React
 * rendering — MediaRecorder restarted per chunk would drop audio exactly when
 * someone starts speaking, which is when it matters most.
 */
const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions.targetRate;
    this.frameSamples = options.processorOptions.frameSamples;
    this.ratio = sampleRate / this.targetRate;
    this.frame = new Int16Array(this.frameSamples);
    this.filled = 0;
    // Accumulator for box-filter decimation.
    this.sum = 0;
    this.count = 0;
    this.position = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i += 1) {
      // Average every input sample that maps to one output sample instead of
      // picking one and discarding the rest. Dropping samples at 48k -> 16k
      // folds everything above 8 kHz back into the speech band as noise, and
      // that aliasing is what makes speech recognition mishear words.
      this.sum += channel[i];
      this.count += 1;
      this.position += 1;
      if (this.position >= this.ratio) {
        this.position -= this.ratio;
        let sample = this.count ? this.sum / this.count : 0;
        this.sum = 0;
        this.count = 0;
        sample = Math.max(-1, Math.min(1, sample));
        this.frame[this.filled] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
        this.filled += 1;
        // Emit exactly one detector frame at a time, so the server never has
        // to re-chunk and every frame costs the same to process.
        if (this.filled === this.frameSamples) {
          const out = this.frame;
          this.frame = new Int16Array(this.frameSamples);
          this.filled = 0;
          this.port.postMessage(out.buffer, [out.buffer]);
        }
      }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

export class VoiceTransport {
  constructor({ onEvent, onError } = {}) {
    this.onEvent = onEvent || (() => {});
    this.onError = onError || (() => {});
    this.socket = null;
    this.token = null;
    this.stream = null;
    this.context = null;
    this.node = null;
    this.silence = null;
    this.source = null;
    this.stopped = false;
    // Assistant playback: a strictly ordered queue so segments never overlap
    // or arrive out of sequence.
    this.audioQueue = [];
    this.currentAudio = null;
    this.objectUrls = new Set();
    this.playingTurn = null;
    // Capture is silent when it breaks, so it gets counted and watched.
    this.framesSent = 0;
    this.captureWatchdog = null;
    // The turn whose last segment has arrived, still waiting to be played out.
    this.pendingFinish = null;
    // Turns the user has cut off. Segments for these are dropped rather than
    // played: the server delivers a whole answer in about a second, so several
    // are usually already in hand when the interruption happens.
    this.cancelledTurns = new Set();
  }

  async start(sessionPayload) {
    this.stopped = false;
    const session = await openVoiceSession(sessionPayload);
    this.token = session.session_token;
    await this.#openMicrophone();
    await this.#connect(session);
    this.#watchCapture();
    return session;
  }

  /**
   * Notice when the microphone produces nothing.
   *
   * The worklet emits frames continuously whether or not anyone is speaking,
   * so silence here does not mean a quiet room -- it means capture is dead.
   * Without this the failure looks exactly like the assistant ignoring you.
   */
  #watchCapture() {
    clearTimeout(this.captureWatchdog);
    this.captureWatchdog = setTimeout(() => {
      if (this.stopped || this.framesSent > 0) return;
      this.onError(
        new Error(
          "No audio is reaching the server. Check that the right microphone is "
          + "selected and that this tab is not muted, then start voice again."
        )
      );
    }, 3000);
  }

  async #openMicrophone() {
    // Echo cancellation is what stops the assistant's own voice being captured
    // and submitted back as if the user had asked it.
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.context = new (window.AudioContext || window.webkitAudioContext)();
    const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
    const url = URL.createObjectURL(blob);
    try {
      await this.context.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    this.source = this.context.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.context, "pcm-capture", {
      processorOptions: { targetRate: TARGET_SAMPLE_RATE, frameSamples: FRAME_SAMPLES },
    });
    this.node.port.onmessage = (event) => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.framesSent += 1;
        this.socket.send(event.data);
      }
    };
    this.source.connect(this.node);
    // A worklet with no path to the destination is never pulled by the
    // rendering graph, so process() simply never runs and not one frame is
    // captured. Leaving it unconnected to keep capture silent is what made the
    // microphone appear dead while the socket sat happily open.
    //
    // Routing through a muted gain node gives the graph its path without
    // making anything audible, which is what feeding the mic back to the
    // speakers would do.
    this.silence = this.context.createGain();
    this.silence.gain.value = 0;
    this.node.connect(this.silence);
    this.silence.connect(this.context.destination);

    // Starting a session involves two awaits before this point — minting the
    // token and the microphone permission — and the click that authorised it
    // has been spent by then. A context created without live user activation
    // starts suspended, and a suspended context never runs the worklet: the
    // socket opens, no audio is ever captured, and nothing at all happens.
    if (this.context.state === "suspended") await this.context.resume();
  }

  #connect(session) {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(voiceSocketUrl(session.session_token));
      socket.binaryType = "arraybuffer";
      this.socket = socket;
      socket.onopen = () => resolve(session);
      socket.onerror = () => reject(new Error("The voice connection could not be opened."));
      socket.onclose = (event) => {
        if (!this.stopped) this.onError(new Error(closeReason(event)));
      };
      socket.onmessage = (message) => {
        let payload;
        try {
          payload = JSON.parse(message.data);
        } catch {
          return;
        }
        if (payload.type === "assistant.audio_chunk") {
          this.#enqueueAudio(payload);
          return;
        }
        if (payload.type === "assistant.audio_finished") {
          // Sent, not heard. Report back once the queue actually drains.
          this.pendingFinish = payload.turn_id;
          this.#reportPlaybackFinished();
        }
        if (payload.type === "assistant.interrupted") this.cancelledTurns.add(payload.turn_id);
        this.onEvent(payload);
      };
    });
  }

  send(event) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(event));
    }
  }

  /**
   * Stop the assistant immediately.
   *
   * Ordering matters: kill local playback first so the user hears silence at
   * once, then tell the server to stop synthesising. Waiting for the round
   * trip would leave the assistant talking over them.
   */
  interrupt(turnId) {
    const turn = turnId || this.playingTurn;
    if (turn) this.cancelledTurns.add(turn);
    this.stopPlayback();
    this.send({ type: "response.cancel", turn_id: turn });
  }

  /**
   * Tell the server the assistant has genuinely stopped talking.
   *
   * It cannot know: a half-minute answer is delivered to the browser in about
   * a second, so the server's own idea of "speaking" ends long before the user
   * stops hearing it. Without this the session went back to listening while
   * the answer was still playing, and an interruption had nothing left to
   * interrupt.
   */
  #reportPlaybackFinished() {
    if (!this.pendingFinish) return;
    if (this.currentAudio || this.audioQueue.length) return;
    const turnId = this.pendingFinish;
    this.pendingFinish = null;
    this.send({ type: "playback.finished", turn_id: turnId });
  }

  stopPlayback() {
    if (this.currentAudio) {
      this.currentAudio.pause();
      this.currentAudio.src = "";
      this.currentAudio = null;
    }
    this.audioQueue = [];
    for (const url of this.objectUrls) URL.revokeObjectURL(url);
    this.objectUrls.clear();
    this.playingTurn = null;
    // The server is told separately, by the cancel; nothing is owed here.
    this.pendingFinish = null;
  }

  #enqueueAudio(payload) {
    // Segments already in flight when the user cut in. Playing them is exactly
    // the "it keeps talking after I interrupt" problem.
    if (this.cancelledTurns.has(payload.turn_id)) return;
    const bytes = Uint8Array.from(atob(payload.data), (character) => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: payload.mime || "audio/mpeg" }));
    this.objectUrls.add(url);
    this.audioQueue.push({ url, turnId: payload.turn_id, index: payload.index });
    if (!this.currentAudio) this.#playNext();
  }

  #playNext() {
    const next = this.audioQueue.shift();
    if (!next) {
      this.currentAudio = null;
      this.#reportPlaybackFinished();
      return;
    }
    const audio = new Audio(next.url);
    this.currentAudio = audio;
    this.playingTurn = next.turnId;
    const advance = () => {
      URL.revokeObjectURL(next.url);
      this.objectUrls.delete(next.url);
      if (this.currentAudio === audio) this.#playNext();
    };
    audio.onended = advance;
    // A failed segment must not stall the queue behind it.
    audio.onerror = advance;
    audio.play().catch(() => advance());
  }

  async stop() {
    this.stopped = true;
    clearTimeout(this.captureWatchdog);
    this.captureWatchdog = null;
    this.stopPlayback();
    this.send({ type: "session.stop" });
    try {
      this.node?.port?.close?.();
      this.node?.disconnect();
      this.silence?.disconnect();
      this.source?.disconnect();
    } catch {
      /* already torn down */
    }
    // Releasing the tracks is what actually turns the microphone light off.
    this.stream?.getTracks().forEach((track) => track.stop());
    try {
      await this.context?.close();
    } catch {
      /* already closed */
    }
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) this.socket.close();
    await closeVoiceSession(this.token);
    this.socket = null;
    this.stream = null;
    this.context = null;
    this.node = null;
    this.source = null;
    this.token = null;
  }
}

export function closeReason(event) {
  if (event?.code === 4403) return "This page is not allowed to open a voice session.";
  if (event?.code === 4404) return "The voice session expired. Start it again.";
  if (event?.code === 4401) return "Voice models are unavailable on the server.";
  return "The voice connection was lost.";
}
