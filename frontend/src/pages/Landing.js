import { useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import GlassCard from '@/ui/components/GlassCard';
import SecondaryButton from '@/ui/components/SecondaryButton';
import { Volume2, VolumeX } from 'lucide-react';
import './Landing.css';

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
    <div className="landing-shell">
      <audio
        ref={audioRef}
        src="/assets/thunderstruck.mp3"
        loop
        preload="auto"
      />

      {/* Sound Control */}
      <button
        onClick={toggleSound}
        className={`landing-sound ${isMuted ? 'pulse' : ''}`}
        title={isMuted ? 'Play Sound' : 'Mute Sound'}
        data-testid="sound-toggle"
      >
        {isMuted ? <VolumeX size={20} /> : <Volume2 size={20} />}
      </button>

      <div className="landing-left">
        <div className="landing-content bright-glass-panel">
          <img src="/assets/logo.png" alt="Amarktai Network" className="landing-logo" />
          <div className="landing-hero">
            <span className="landing-kicker">Executive Command Center</span>
            <h1>Amarktai Network Command Center</h1>
            <p>
              Self-trading AI that self-heals, self-learns, and manages risk in real time while
              protecting capital across every market session.
            </p>
          </div>
          <div className="landing-feature-grid">
            {[
              { title: 'Autonomous AI', copy: 'Always-on decision engine with adaptive strategy tuning.' },
              { title: 'Risk Guardrails', copy: 'Live loss locks, drawdown protection, and safety checks.' },
              { title: 'Self-Healing Ops', copy: 'Automatic recovery, bot health checks, and alerts.' },
              { title: 'Real-Time Intelligence', copy: 'Live pricing, trades, and performance telemetry.' }
            ].map((feature) => (
              <GlassCard key={feature.title} className="landing-feature-card">
                <h3>{feature.title}</h3>
                <p>{feature.copy}</p>
              </GlassCard>
            ))}
          </div>
          <div className="landing-cta">
            <SecondaryButton onClick={() => navigate('/login')}>
              Enter Command Center
            </SecondaryButton>
          </div>
        </div>
      </div>
      <div className="landing-right">
        <video
          className="landing-video"
          autoPlay
          muted
          loop
          playsInline
          poster="/assets/poster.jpg"
        >
          <source src="/assets/background.mp4" type="video/mp4" />
        </video>
        <div className="page-overlay" />
      </div>
    </div>
  );
}
