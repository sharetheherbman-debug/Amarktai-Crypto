import { useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import SiteFooter from '../components/SiteFooter';
import Brand from '../components/Brand';
import { Volume2, VolumeX } from 'lucide-react';
import './Auth.css';
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
    <div className="auth-container landing-container">
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

      {/* LEFT — Brand + CTAs */}
      <div className="auth-left">
        <div className="landing-particles" aria-hidden="true">
          {[
            {left:'8%',  top:'72%', size:5,  dur:9,  delay:0,    drift:-140, op:0.65},
            {left:'18%', top:'80%', size:3,  dur:7,  delay:1.2,  drift:-110, op:0.5},
            {left:'28%', top:'65%', size:7,  dur:11, delay:0.5,  drift:-160, op:0.75},
            {left:'38%', top:'85%', size:4,  dur:8,  delay:2.1,  drift:-130, op:0.6},
            {left:'50%', top:'75%', size:6,  dur:10, delay:0.8,  drift:-150, op:0.7},
            {left:'62%', top:'70%', size:3,  dur:7,  delay:3.0,  drift:-100, op:0.45},
            {left:'72%', top:'82%', size:5,  dur:9,  delay:1.5,  drift:-135, op:0.65},
            {left:'82%', top:'60%', size:8,  dur:12, delay:0.3,  drift:-170, op:0.8},
            {left:'12%', top:'40%', size:4,  dur:8,  delay:4.0,  drift:-120, op:0.55},
            {left:'45%', top:'55%', size:3,  dur:6,  delay:2.5,  drift:-90,  op:0.4},
            {left:'88%', top:'88%', size:6,  dur:10, delay:1.0,  drift:-145, op:0.7},
            {left:'55%', top:'92%', size:4,  dur:8,  delay:3.5,  drift:-115, op:0.55},
          ].map((p, i) => (
            <span
              key={i}
              className="landing-particle"
              style={{
                left: p.left,
                top: p.top,
                width: p.size,
                height: p.size,
                '--dur': `${p.dur}s`,
                '--delay': `${p.delay}s`,
                '--drift': `${p.drift}px`,
                '--max-opacity': p.op,
              }}
            />
          ))}
        </div>
        <div className="auth-content landing-hero-content">
          <img src="/assets/logo.png" alt="Amarktai Crypto" className="auth-logo landing-logo-lg" />
          <h1 className="landing-headline">
            <Brand size="lg" />
            {' '}Crypto
          </h1>
          <p className="landing-subheadline">Self-learning, self-healing AI trading bots that reinvest daily for maximum growth.</p>
          <div className="landing-cta">
            <Button onClick={() => navigate('/login')} className="auth-submit-btn landing-cta-btn landing-primary-btn">
              Login
            </Button>
            <Button onClick={() => navigate('/register')} className="auth-submit-btn landing-cta-btn landing-register-btn">
              Create Account
            </Button>
          </div>
        </div>
      </div>

      {/* RIGHT — Video */}
      <div className="auth-right">
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

      <SiteFooter />
    </div>
  );
}
