import { useCallback, useEffect, useRef, useState } from "react";

function getSpeechRecognitionConstructor() {
  if (typeof window === "undefined") {
    return null;
  }

  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function toSpeechErrorMessage(errorCode) {
  if (!errorCode) {
    return "Speech recognition failed. Please try again.";
  }

  if (errorCode === "not-allowed" || errorCode === "service-not-allowed") {
    return "Microphone permission denied. Please allow mic access.";
  }

  if (errorCode === "audio-capture") {
    return "No microphone was found. Please check your audio input device.";
  }

  if (errorCode === "no-speech") {
    return "No speech was detected. Try speaking again.";
  }

  if (errorCode === "network") {
    return "Speech recognition network error. Please check your connection.";
  }

  if (errorCode === "aborted") {
    return "Speech recognition stopped.";
  }

  return "Speech recognition failed. Please try again.";
}

export function useSpeechRecognition(options = {}) {
  const { lang = "en-US", interimResults = true, continuous = false } = options;
  const recognitionRef = useRef(null);
  const [isSupported, setIsSupported] = useState(Boolean(getSpeechRecognitionConstructor()));
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
      setIsSupported(false);
      recognitionRef.current = null;
      return undefined;
    }

    setIsSupported(true);
    const recognition = new Recognition();
    recognition.lang = lang;
    recognition.interimResults = interimResults;
    recognition.continuous = continuous;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
      setError("");
    };

    recognition.onend = () => {
      setIsListening(false);
      setInterimTranscript("");
    };

    recognition.onerror = (event) => {
      const errorCode = event?.error;
      setError(toSpeechErrorMessage(errorCode));
    };

    recognition.onresult = (event) => {
      const finalParts = [];
      const interimParts = [];

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const text = String(result?.[0]?.transcript || "").trim();

        if (!text) {
          continue;
        }

        if (result.isFinal) {
          finalParts.push(text);
        } else {
          interimParts.push(text);
        }
      }

      if (finalParts.length) {
        setTranscript((current) => `${current} ${finalParts.join(" ")}`.trim());
      }

      setInterimTranscript(interimParts.join(" ").trim());
    };

    recognitionRef.current = recognition;

    return () => {
      recognition.onstart = null;
      recognition.onend = null;
      recognition.onerror = null;
      recognition.onresult = null;

      try {
        recognition.stop();
      } catch {
        // Ignore teardown stop failures.
      }

      recognitionRef.current = null;
    };
  }, [continuous, interimResults, lang]);

  const startListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      setError("Voice not supported in this browser.");
      return false;
    }

    setError("");
    setTranscript("");
    setInterimTranscript("");

    try {
      recognition.start();
      return true;
    } catch (startError) {
      const message = String(startError?.message || "").toLowerCase();
      if (message.includes("already started")) {
        return true;
      }

      setError("Unable to start microphone listening.");
      return false;
    }
  }, []);

  const stopListening = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) {
      return;
    }

    try {
      recognition.stop();
    } catch {
      // Ignore explicit stop failures.
    }
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
  }, []);

  const clearError = useCallback(() => {
    setError("");
  }, []);

  return {
    isSupported,
    isListening,
    transcript,
    interimTranscript,
    error,
    startListening,
    stopListening,
    resetTranscript,
    clearError,
  };
}
