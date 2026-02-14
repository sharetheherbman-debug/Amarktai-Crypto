import { useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Volume2, VolumeX } from 'lucide-react';

export default function Landing() {
  const navigate = useNavigate();
  const [isMuted, setIsMuted] = useState(true);
  const [hasInteracted, setHasInteracted] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    const userMuted = localStorage.getItem('amarktai_userMuted');
    if (userMuted === 'false') {
      setIsMuted(false);
    }

    const tryAutoplay = async () => {
      try {
        if (audioRef.current && !isMuted) {
          await audioRef.current.play();
          setHasInteracted(true);
        }
      } catch (err) {
        console.log('Autoplay blocked');
      }
    };

    tryAutoplay();

    const handleVisibilityChange = () => {
      if (document.hidden && audioRef.current) {
        audioRef.current.pause();
      } else if (!document.hidden && audioRef.current && !isMuted && hasInteracted) {
        audioRef.current.play();
      }
    };

    const handleBlur = () => {
      if (audioRef.current) audioRef.current.pause();
    };

    const handleFocus = () => {
      if (audioRef.current && !isMuted && hasInteracted) audioRef.current.play();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
    window.addEventListener('focus', handleFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
      window.removeEventListener('focus', handleFocus);
    };
  }, [isMuted, hasInteracted]);

  const toggleSound = async () => {
    setHasInteracted(true);
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    localStorage.setItem('amarktai_userMuted', String(newMuted));

    if (audioRef.current) {
      if (newMuted) {
        audioRef.current.pause();
      } else {
        try {
          await audioRef.current.play();
        } catch (err) {
          console.error('Failed to play audio:', err);
        }
      }
    }
  };

  return (
    <div className="landing-container">
      <audio
        ref={audioRef}
        src="/assets/thunderstruck.mp3"
        loop
        preload="auto"
      />

      {/* Sound Control */}
      <button
        onClick={toggleSound}
        className={`sound-btn ${isMuted ? 'pulse' : ''}`}
        title={isMuted ? 'Play Sound' : 'Mute Sound'}
        data-testid="sound-toggle"
      >
        {isMuted ? <VolumeX size={20} /> : <Volume2 size={20} />}
      </button>

      {/* Left Column - Content */}
      <div className="left">
        <div className="content">
          <div className="hero">
            <h1>Amarktai Crypto</h1>
            <h2>for autonomous wealth.</h2>
            <p className="hero-description">
              AI self-trading automation with self-healing, self-learning intelligence running 24/7 to protect and grow capital.
            </p>
          </div>

          <div className="actions">
            <Button
              onClick={() => navigate('/register')}
              className="btn btn-primary"
              data-testid="get-started-button"
            >
              Get Started
            </Button>
            <Button
              onClick={() => navigate('/login')}
              className="btn btn-secondary"
            >
              Sign In
            </Button>
          </div>
        </div>
      </div>

      {/* Right Column - Video */}
      <div className="right">
        <video
          autoPlay
          muted
          loop
          playsInline
          poster="/assets/poster.jpg"
        >
          <source src="/assets/background.mp4" type="video/mp4" />
        </video>
        <img src="/assets/ai/ai-orb.svg" alt="" className="ai-orb" />
        <img src="/assets/ai/ai-grid.svg" alt="" className="ai-grid" />
      </div>

      <style jsx>{`
        .landing-container {
          display: flex;
          height: 100vh;
          align-items: center;
          background: var(--bg);
          color: var(--text);
          position: relative;
          overflow: hidden;
        }

        .sound-btn {
          position: fixed;
          top: 28px;
          right: 24px;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: rgba(15, 15, 20, 0.75);
          backdrop-filter: blur(var(--blur));
          border: 1px solid var(--line);
          color: var(--accent2);
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          z-index: 100;
          transition: all 0.3s ease;
        }

        .sound-btn:hover {
          background: rgba(15, 15, 20, 0.9);
          border-color: rgba(56, 189, 248, 0.6);
        }

        .sound-btn.pulse {
          animation: pulse 2s infinite;
        }

        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(46, 223, 163, 0.7); }
          50% { box-shadow: 0 0 0 10px rgba(46, 223, 163, 0); }
        }

        .left {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 40px;
          z-index: 2;
        }

        .right {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .right video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }

        .content {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          max-width: 520px;
          width: 100%;
          gap: 24px;
          background: var(--glass);
          border: 1px solid var(--line);
          border-radius: var(--radius);
          padding: 48px 44px;
          backdrop-filter: blur(var(--blur));
          box-shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
          position: relative;
          overflow: hidden;
        }

        .content::after {
          content: '';
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at 10% 90%, rgba(56, 189, 248, 0.18), transparent 55%);
          opacity: 0.35;
          pointer-events: none;
        }

        .content > * {
          position: relative;
          z-index: 1;
        }

        .hero h1 {
          font-size: 2.9rem;
          font-weight: 700;
          line-height: 1.1;
          margin: 0;
        }

        .hero h2 {
          font-size: 1.5rem;
          font-weight: 600;
          color: var(--accent2);
          margin: 10px 0 0;
        }

        .hero-description {
          font-size: 1.05rem;
          color: var(--muted);
          margin: 12px 0 0;
          line-height: 1.6;
        }

        .actions {
          display: flex;
          gap: 16px;
          width: 100%;
        }

        .btn {
          flex: 1;
          padding: 16px 24px;
          border-radius: 999px;
          font-weight: 600;
          font-size: 1rem;
          cursor: pointer;
          transition: all 0.3s ease;
          border: none;
        }

        .btn-primary {
          background: linear-gradient(135deg, rgba(34, 197, 94, 0.9), rgba(34, 197, 94, 0.65));
          color: #0b0d14;
        }

        .btn-primary:hover {
          opacity: 0.85;
          transform: translateY(-2px);
        }

        .btn-secondary {
          background: rgba(56, 189, 248, 0.12);
          border: 1px solid rgba(56, 189, 248, 0.35);
          color: var(--text);
        }

        .btn-secondary:hover {
          background: rgba(56, 189, 248, 0.2);
          transform: translateY(-2px);
        }

        .ai-orb {
          position: absolute;
          bottom: 40px;
          right: 40px;
          width: 180px;
          opacity: 0.7;
        }

        .ai-grid {
          position: absolute;
          top: 20px;
          left: 20px;
          width: 260px;
          opacity: 0.35;
        }

        /* Mobile Responsive */
        @media (max-width: 900px) {
          .landing-container {
            flex-direction: column;
          }

          .left {
            position: absolute;
            inset: 0;
            z-index: 2;
            padding: 32px 20px;
            background: rgba(10, 12, 20, 0.55);
          }

          .right {
            position: fixed;
            inset: 0;
            z-index: 1;
          }

          .content {
            background: rgba(15, 15, 20, 0.6);
            border: 1px solid var(--line);
            backdrop-filter: blur(var(--blur));
            box-shadow: 0 16px 32px rgba(0, 0, 0, 0.35);
            gap: 24px;
            padding: 24px;
          }

          .hero h1 {
            font-size: 2rem;
          }

          .hero h2 {
            font-size: 1.2rem;
          }

          .hero-description {
            font-size: 0.95rem;
          }

          .actions {
            flex-direction: column;
          }

          .ai-orb {
            width: 140px;
            bottom: 20px;
            right: 20px;
          }
        }
      `}</style>
    </div>
  );
}
