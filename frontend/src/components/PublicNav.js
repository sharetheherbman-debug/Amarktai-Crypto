import { Link, NavLink } from 'react-router-dom';

export default function PublicNav() {
  return (
    <nav className="public-nav">
      <Link to="/" className="brand">
        <img src="/assets/logo.png" alt="Amarktai Crypto" />
        <span>Amarktai Crypto</span>
      </Link>
      <div className="nav-links">
        <NavLink to="/features">Features</NavLink>
        <NavLink to="/about">About</NavLink>
        <NavLink to="/terms">Terms</NavLink>
        <NavLink to="/privacy">Privacy</NavLink>
      </div>
      <div className="nav-actions">
        <Link className="secondary-button" to="/login">Sign In</Link>
        <Link className="primary-button" to="/register">Get Started</Link>
      </div>
    </nav>
  );
}
