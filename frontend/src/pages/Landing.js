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
          <img
            src="/assets/logo.png"
            alt="Amarktai Logo"
            className="logo"
            onClick={() => navigate('/')}
          />
          
          <div className="hero">
            <h1>
              Your journey to <span className="emph">autonomous wealth</span>
            </h1>
            <p>Intelligent, adaptive, unstoppable.</p>
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
      </div>

      {/* Footer */}
      <div className="footer">
        <p>
          © 2026 Amarktai Crypto · a part of Amarktai Network. All rights reserved.
        </p>
      </div>

      <style jsx>{`
        .landing-container {
          display: flex;
          height: 100vh;
          align-items: center;
          background: #000;
          color: #f0f8f5;
          font-family: system-ui, 'Segoe UI', Roboto, Arial, sans-serif;
          position: relative;
          overflow: hidden;
        }

        .sound-btn {
          position: fixed;
          top: 24px;
          right: 24px;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: rgba(6, 12, 16, 0.75);
          backdrop-filter: blur(8px);
          border: 1px solid rgba(46, 223, 163, 0.25);
          color: #2edfa3;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
          z-index: 100;
          transition: all 0.3s ease;
        }

        .sound-btn:hover {
          background: rgba(6, 12, 16, 0.9);
          border-color: #2edfa3;
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
          gap: 32px;
          background: rgba(6, 12, 16, 0.75);
          border: 1px solid rgba(46, 223, 163, 0.25);
          border-radius: 16px;
          padding: 48px;
          backdrop-filter: blur(8px);
          box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
        }

        .logo {
          width: 110px;
          height: 110px;
          cursor: pointer;
          transition: transform 0.3s ease;
        }

        .logo:hover {
          transform: scale(1.05);
        }

        .hero h1 {
          font-size: 2.8rem;
          font-weight: 700;
          line-height: 1.2;
          margin: 0 0 16px 0;
        }

        .hero .emph {
          background: linear-gradient(135deg, #008a65, #2edfa3);
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }

        .hero p {
          font-size: 1.25rem;
          color: #8a9bb0;
          margin: 0;
        }

        .actions {
          display: flex;
          gap: 16px;
          width: 100%;
        }

        .btn {
          flex: 1;
          padding: 16px 24px;
          border-radius: 8px;
          font-weight: 600;
          font-size: 1rem;
          cursor: pointer;
          transition: all 0.3s ease;
          border: none;
        }

        .btn-primary {
          background: linear-gradient(135deg, #008a65, #2edfa3);
          color: #fff;
        }

        .btn-primary:hover {
          opacity: 0.85;
          transform: translateY(-2px);
        }

        .btn-secondary {
          background: transparent;
          border: 2px solid #2edfa3;
          color: #2edfa3;
        }

        .btn-secondary:hover {
          background: rgba(46, 223, 163, 0.1);
          transform: translateY(-2px);
        }

        .footer {
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          text-align: center;
          padding: 12px;
          color: #8a9bb0;
          font-size: 0.85rem;
          z-index: 10;
          background: rgba(0, 0, 0, 0.5);
        }

        .footer a {
          color: #2edfa3;
          text-decoration: none;
        }

        .footer a:hover {
          text-decoration: underline;
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
            background: rgba(0, 0, 0, 0.55);
          }

          .right {
            position: fixed;
            inset: 0;
            z-index: 1;
          }

          .content {
            background: transparent;
            border: none;
            backdrop-filter: none;
            box-shadow: none;
            gap: 24px;
            padding: 24px;
          }

          .hero h1 {
            font-size: 2rem;
          }

          .hero p {
            font-size: 1rem;
          }

          .actions {
            flex-direction: column;
          }

          .footer {
            z-index: 3;
            color: #fff;
          }
        }
      `}</style>
    </div>
  );
}
