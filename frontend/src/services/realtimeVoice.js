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
    this.ratio = sampleRate / this.targetRate;
    this.buffer = [];
    this.position = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    // Linear decimation to the target rate; adequate for speech and far
    // cheaper than a full resampler on the audio thread.
    for (let i = 0; i < channel.length; i += 1) {
      this.position += 1;
      if (this.position >= this.ratio) {
        this.position -= this.ratio;
        const sample = Math.max(-1, Math.min(1, channel[i]));
        this.buffer.push(sample < 0 ? sample * 0x8000 : sample * 0x7fff);
      }
    }
    // Emit in blocks so the socket sees a steady, low-latency trickle.
    if (this.buffer.length >= 512) {
      const frame = new Int16Array(this.buffer.splice(0, this.buffer.length));
      this.port.postMessage(frame.buffer, [frame.buffer]);
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
    this.source = null;
    this.stopped = false;
    // Assistant playback: a strictly ordered queue so segments never overlap
    // or arrive out of sequence.
    this.audioQueue = [];
    this.currentAudio = null;
    this.objectUrls = new Set();
    this.playingTurn = null;
  }

  async start(sessionPayload) {
    this.stopped = false;
    const session = await openVoiceSession(sessionPayload);
    this.token = session.session_token;
    await this.#openMicrophone();
    await this.#connect(session);
    return session;
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
      processorOptions: { targetRate: TARGET_SAMPLE_RATE },
    });
    this.node.port.onmessage = (event) => {
      if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(event.data);
    };
    this.source.connect(this.node);
    // Not connected to the destination: capture must never be audible.
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
        if (payload.type === "assistant.audio_chunk") this.#enqueueAudio(payload);
        else this.onEvent(payload);
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
    this.stopPlayback();
    this.send({ type: "response.cancel", turn_id: turnId || this.playingTurn });
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
  }

  #enqueueAudio(payload) {
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
    this.stopPlayback();
    this.send({ type: "session.stop" });
    try {
      this.node?.port?.close?.();
      this.node?.disconnect();
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
