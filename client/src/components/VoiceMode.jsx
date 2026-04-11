import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import {
  isSpeechSynthesisSupported,
  speakText,
  stopSpeaking,
} from "../utils/speechSynthesis";

const SILENCE_TIMEOUT_MS = 1500;
const LISTEN_RESTART_MS = 420;

function isFatalRecognitionError(message) {
  const value = String(message || "").toLowerCase();
  return value.includes("permission denied") || value.includes("voice not supported");
}

function VoiceMode({ onSubmitVoiceQuery, onStopVoiceMode }) {
  const {
    isSupported,
    isListening,
    transcript,
    interimTranscript,
    error,
    startListening,
    stopListening,
    resetTranscript,
    clearError,
  } = useSpeechRecognition({
    lang: "en-US",
    interimResults: true,
    continuous: true,
  });

  const [statusText, setStatusText] = useState("Initializing voice mode...");
  const [modeError, setModeError] = useState("");
  const [isThinking, setIsThinking] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVoiceOutputEnabled, setIsVoiceOutputEnabled] = useState(true);
  const [voiceRate, setVoiceRate] = useState(1);
  const [voicePitch, setVoicePitch] = useState(1);

  const activeRef = useRef(true);
  const silenceTimeoutRef = useRef(null);
  const listeningRestartTimeoutRef = useRef(null);
  const speechInterruptedRef = useRef(false);
  const lastSpokenTextRef = useRef("");
  const isSpeechOutputSupported = isSpeechSynthesisSupported();

  const liveTranscript = useMemo(
    () => [transcript, interimTranscript].filter(Boolean).join(" ").trim(),
    [interimTranscript, transcript]
  );

  const clearTimers = useCallback(() => {
    if (silenceTimeoutRef.current) {
      window.clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }

    if (listeningRestartTimeoutRef.current) {
      window.clearTimeout(listeningRestartTimeoutRef.current);
      listeningRestartTimeoutRef.current = null;
    }
  }, []);

  const scheduleListeningRestart = useCallback(
    (delay = LISTEN_RESTART_MS) => {
      clearTimers();
      listeningRestartTimeoutRef.current = window.setTimeout(() => {
        if (!activeRef.current || isThinking || isSpeaking) {
          return;
        }

        clearError();
        resetTranscript();
        const started = startListening();
        if (started) {
          setStatusText("Listening...");
        }
      }, delay);
    },
    [clearError, clearTimers, isSpeaking, isThinking, resetTranscript, startListening]
  );

  const stopVoiceModeSafely = useCallback(() => {
    activeRef.current = false;
    clearTimers();
    stopListening();
    stopSpeaking();
    setIsSpeaking(false);
    onStopVoiceMode();
  }, [clearTimers, onStopVoiceMode, stopListening]);

  const processVoiceTurn = useCallback(
    async (rawUtterance) => {
      const utterance = String(rawUtterance || "").trim();
      if (!utterance || !activeRef.current) {
        scheduleListeningRestart(220);
        return;
      }

      speechInterruptedRef.current = false;
      setModeError("");
      setIsThinking(true);
      setStatusText("Thinking...");
      stopListening();

      const result = await onSubmitVoiceQuery(utterance);

      if (!activeRef.current) {
        return;
      }

      setIsThinking(false);

      if (!result?.ok) {
        if (result?.interrupted) {
          setStatusText("Listening...");
          scheduleListeningRestart(220);
          return;
        }

        setModeError(String(result?.error || "Voice request failed."));
        setStatusText("Listening...");
        scheduleListeningRestart(620);
        return;
      }

      const answerText = String(result?.answer || "").trim();
      if (!answerText) {
        setStatusText("Listening...");
        scheduleListeningRestart();
        return;
      }

      if (!isVoiceOutputEnabled || !isSpeechOutputSupported) {
        setStatusText("Listening...");
        scheduleListeningRestart();
        return;
      }

      lastSpokenTextRef.current = answerText.toLowerCase();
      speechInterruptedRef.current = false;
      setIsSpeaking(true);
      setStatusText("Speaking...");

      // Keep listening while speaking so user can interrupt naturally.
      clearError();
      resetTranscript();
      startListening();

      const speechResult = speakText(answerText, {
        rate: voiceRate,
        pitch: voicePitch,
        onStart: () => {
          if (activeRef.current) {
            setIsSpeaking(true);
            setStatusText("Speaking...");
          }
        },
        onEnd: () => {
          if (!activeRef.current) {
            return;
          }

          const wasInterrupted = speechInterruptedRef.current;
          speechInterruptedRef.current = false;
          setIsSpeaking(false);

          if (!wasInterrupted) {
            stopListening();
            setStatusText("Listening...");
            scheduleListeningRestart();
          }
        },
        onError: () => {
          if (!activeRef.current) {
            return;
          }

          setIsSpeaking(false);
          setModeError("Voice output failed. Continuing with listening mode.");
          setStatusText("Listening...");
          scheduleListeningRestart();
        },
      });

      if (!speechResult.ok) {
        setIsSpeaking(false);
        setModeError(String(speechResult.error || "Voice output failed."));
        setStatusText("Listening...");
        scheduleListeningRestart();
      }
    },
    [
      clearError,
      isSpeechOutputSupported,
      isVoiceOutputEnabled,
      onSubmitVoiceQuery,
      resetTranscript,
      scheduleListeningRestart,
      startListening,
      stopListening,
      voicePitch,
      voiceRate,
    ]
  );

  useEffect(() => {
    activeRef.current = true;

    if (!isSupported) {
      setModeError("Voice not supported in this browser.");
      setStatusText("Voice unavailable");
      const timeoutId = window.setTimeout(() => {
        stopVoiceModeSafely();
      }, 900);

      return () => {
        window.clearTimeout(timeoutId);
      };
    }

    setStatusText("Listening...");
    clearError();
    resetTranscript();
    const started = startListening();
    if (!started) {
      setModeError("Unable to start microphone listening.");
      setStatusText("Voice unavailable");
      const timeoutId = window.setTimeout(() => {
        stopVoiceModeSafely();
      }, 900);

      return () => {
        window.clearTimeout(timeoutId);
      };
    }

    return () => {
      activeRef.current = false;
      clearTimers();
      stopListening();
      stopSpeaking();
    };
  }, [clearError, clearTimers, isSupported, resetTranscript, startListening, stopListening, stopVoiceModeSafely]);

  useEffect(() => {
    if (!error) {
      return;
    }

    setModeError(error);

    if (isFatalRecognitionError(error)) {
      setStatusText("Voice unavailable");
      const timeoutId = window.setTimeout(() => {
        stopVoiceModeSafely();
      }, 900);
      return () => {
        window.clearTimeout(timeoutId);
      };
    }

    if (String(error).toLowerCase().includes("no speech")) {
      setStatusText("Listening...");
      scheduleListeningRestart(260);
      return;
    }

    setStatusText("Listening...");
    scheduleListeningRestart(520);
  }, [error, scheduleListeningRestart, stopVoiceModeSafely]);

  useEffect(() => {
    if (!isSpeaking || !isListening) {
      return;
    }

    const detected = liveTranscript.trim();
    const normalizedDetected = detected.toLowerCase();
    const words = normalizedDetected.split(/\s+/).filter(Boolean);

    if (words.length < 3) {
      return;
    }

    // Guard against simple echo from the current spoken answer.
    if (lastSpokenTextRef.current && lastSpokenTextRef.current.includes(normalizedDetected)) {
      return;
    }

    speechInterruptedRef.current = true;
    stopSpeaking();
    setIsSpeaking(false);
    setStatusText("Listening...");
  }, [isListening, isSpeaking, liveTranscript]);

  useEffect(() => {
    if (!isListening || isThinking) {
      return;
    }

    if (isSpeaking && !speechInterruptedRef.current) {
      return;
    }

    if (!liveTranscript) {
      return;
    }

    if (silenceTimeoutRef.current) {
      window.clearTimeout(silenceTimeoutRef.current);
    }

    silenceTimeoutRef.current = window.setTimeout(() => {
      if (!activeRef.current) {
        return;
      }

      const finalUtterance = String(transcript || interimTranscript || "").trim();
      if (!finalUtterance) {
        return;
      }

      clearError();
      resetTranscript();
      void processVoiceTurn(finalUtterance);
    }, SILENCE_TIMEOUT_MS);

    return () => {
      if (silenceTimeoutRef.current) {
        window.clearTimeout(silenceTimeoutRef.current);
        silenceTimeoutRef.current = null;
      }
    };
  }, [
    clearError,
    interimTranscript,
    isListening,
    isSpeaking,
    isThinking,
    liveTranscript,
    processVoiceTurn,
    resetTranscript,
    transcript,
  ]);

  return (
    <section className="voice-mode-shell" aria-live="polite">
      <div className="voice-mode-panel">
        <p className="voice-mode-kicker">Voice Conversation Mode</p>
        <h2 className="voice-mode-title">Hands-free Intellexa</h2>

        <div
          className={`voice-mode-orb ${isListening ? "is-listening" : ""}${
            isThinking ? " is-thinking" : ""
          }${isSpeaking ? " is-speaking" : ""}`}
          aria-hidden="true"
        >
          <span />
        </div>

        <p className="voice-mode-status">{statusText}</p>

        {modeError ? <p className="voice-mode-error">{modeError}</p> : null}

        <div className="voice-mode-actions">
          <button
            type="button"
            className={`voice-mode-action ${isVoiceOutputEnabled ? "is-active" : ""}`}
            onClick={() => {
              if (!isSpeechOutputSupported) {
                setModeError("Voice output is not supported in this browser.");
                return;
              }

              setIsVoiceOutputEnabled((current) => {
                const next = !current;
                if (!next) {
                  stopSpeaking();
                  setIsSpeaking(false);
                }
                return next;
              });
            }}
          >
            {isVoiceOutputEnabled ? "Voice Output: On" : "Voice Output: Off"}
          </button>

          {isSpeaking ? (
            <button
              type="button"
              className="voice-mode-action voice-mode-stop-speech"
              onClick={() => {
                speechInterruptedRef.current = true;
                stopSpeaking();
                setIsSpeaking(false);
                setStatusText("Listening...");
              }}
            >
              Stop Speaking
            </button>
          ) : null}

          <label className="voice-mode-select-wrap" htmlFor="voice-mode-rate">
            <span>Rate</span>
            <select
              id="voice-mode-rate"
              className="voice-mode-select"
              value={String(voiceRate)}
              onChange={(event) => setVoiceRate(Number(event.target.value))}
            >
              <option value="0.9">0.9x</option>
              <option value="1">1.0x</option>
              <option value="1.15">1.15x</option>
            </select>
          </label>

          <label className="voice-mode-select-wrap" htmlFor="voice-mode-pitch">
            <span>Pitch</span>
            <select
              id="voice-mode-pitch"
              className="voice-mode-select"
              value={String(voicePitch)}
              onChange={(event) => setVoicePitch(Number(event.target.value))}
            >
              <option value="0.9">0.9x</option>
              <option value="1">1.0x</option>
              <option value="1.1">1.1x</option>
            </select>
          </label>

          <button
            type="button"
            className="voice-mode-action voice-mode-exit"
            onClick={stopVoiceModeSafely}
          >
            Stop Voice Mode
          </button>
        </div>
      </div>
    </section>
  );
}

export default VoiceMode;