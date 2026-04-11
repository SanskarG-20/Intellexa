function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function isSpeechSynthesisSupported() {
  if (typeof window === "undefined") {
    return false;
  }

  return (
    "speechSynthesis" in window &&
    typeof window.SpeechSynthesisUtterance !== "undefined"
  );
}

export function stopSpeaking() {
  if (!isSpeechSynthesisSupported()) {
    return;
  }

  window.speechSynthesis.cancel();
}

export function speakText(text, options = {}) {
  const value = String(text || "").trim();
  if (!value) {
    return { ok: false, error: "No text available for voice output." };
  }

  if (!isSpeechSynthesisSupported()) {
    return { ok: false, error: "Voice output is not supported in this browser." };
  }

  const utterance = new window.SpeechSynthesisUtterance(value);
  const rate = Number(options.rate);
  const pitch = Number(options.pitch);
  const volume = Number(options.volume);

  utterance.rate = Number.isFinite(rate) ? clamp(rate, 0.5, 2) : 1;
  utterance.pitch = Number.isFinite(pitch) ? clamp(pitch, 0, 2) : 1;
  utterance.volume = Number.isFinite(volume) ? clamp(volume, 0, 1) : 1;

  if (typeof options.lang === "string" && options.lang.trim()) {
    utterance.lang = options.lang.trim();
  }

  utterance.onstart = () => {
    if (typeof options.onStart === "function") {
      options.onStart();
    }
  };

  utterance.onend = () => {
    if (typeof options.onEnd === "function") {
      options.onEnd();
    }
  };

  utterance.onerror = () => {
    if (typeof options.onError === "function") {
      options.onError();
    }
  };

  stopSpeaking();
  window.speechSynthesis.speak(utterance);

  return { ok: true };
}
