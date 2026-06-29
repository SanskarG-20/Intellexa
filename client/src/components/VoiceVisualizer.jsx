import React, { useEffect, useRef } from 'react';

export default function VoiceVisualizer({ isListening, isThinking, isSpeaking }) {
  const canvasRef = useRef(null);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animationFrameId;
    let time = 0;
    
    // Web Audio Setup
    let audioCtx;
    let analyser;
    let dataArray;
    let streamRef;
    
    const initAudio = async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) return;
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        streamRef = stream;
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        const source = audioCtx.createMediaStreamSource(stream);
        source.connect(analyser);
        const bufferLength = analyser.frequencyBinCount;
        dataArray = new Uint8Array(bufferLength);
      } catch (err) {
        // Silently fallback to procedural animation if permission denied
        console.warn("Audio input for visualizer denied, using procedural fallback.", err);
      }
    };
    
    if (isListening && !audioCtx) {
      initAudio();
    }
    
    const render = () => {
      const width = canvas.width = canvas.offsetWidth;
      const height = canvas.height = canvas.offsetHeight;
      
      ctx.clearRect(0, 0, width, height);
      
      let volume = 0;
      if (analyser && isListening) {
        analyser.getByteFrequencyData(dataArray);
        const sum = dataArray.reduce((a, b) => a + b, 0);
        volume = sum / dataArray.length / 255.0; // 0 to 1
      }
      
      // Base line setup
      const centerY = height / 2;
      const waves = 4; // Multiple waves for depth
      
      for (let i = 0; i < waves; i++) {
        ctx.beginPath();
        ctx.lineWidth = i === 0 ? 3 : 1.5;
        
        // Colors depend on state
        let strokeColor = 'rgba(255, 255, 255, 0.2)';
        if (isSpeaking) {
          strokeColor = `rgba(130, 220, 255, ${0.9 - i * 0.2})`;
        } else if (isThinking) {
          strokeColor = `rgba(200, 130, 255, ${0.9 - i * 0.2})`;
        } else if (isListening) {
          strokeColor = `rgba(130, 255, 180, ${0.9 - i * 0.2})`;
        }
        
        ctx.strokeStyle = strokeColor;
        
        for (let x = 0; x < width; x++) {
          const normalizedX = x / width;
          // Apply hanning window so edges are smoothly 0
          const windowFunc = Math.sin(normalizedX * Math.PI);
          
          let amplitude = 10;
          let speed = 0.05;
          let frequency = 0.02;
          
          if (isListening) {
            // If we have real audio volume, scale amplitude dramatically
            amplitude = 15 + (volume * 60); 
            speed = 0.12;
            frequency = 0.025;
          } else if (isThinking) {
            amplitude = 25;
            speed = 0.04;
            frequency = 0.04;
          } else if (isSpeaking) {
            amplitude = 35 + Math.sin(time * 0.1) * 15;
            speed = 0.18;
            frequency = 0.035;
          }
          
          const offset = i * Math.PI * 0.75;
          const y = Math.sin(x * frequency + time * speed + offset) * amplitude * windowFunc;
          
          if (x === 0) {
            ctx.moveTo(x, centerY + y);
          } else {
            ctx.lineTo(x, centerY + y);
          }
        }
        ctx.stroke();
      }
      
      time += 1;
      animationFrameId = requestAnimationFrame(render);
    };
    
    render();
    
    return () => {
      cancelAnimationFrame(animationFrameId);
      if (audioCtx && audioCtx.state !== 'closed') {
        audioCtx.close().catch(() => {});
      }
      if (streamRef) {
        streamRef.getTracks().forEach(track => track.stop());
      }
    };
  }, [isListening, isThinking, isSpeaking]);
  
  return (
    <canvas 
      ref={canvasRef} 
      className={`voice-visualizer-canvas ${isListening ? 'is-listening' : ''} ${isThinking ? 'is-thinking' : ''} ${isSpeaking ? 'is-speaking' : ''}`}
      aria-hidden="true"
    />
  );
}
