import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useAuthStore } from '../store/auth';
import { t } from '../i18n';
import './AuthCallback.css';

const errorKeyMap: Record<string, string> = {
  missing_code: 'authCallback.missingCode',
  state_mismatch: 'authCallback.stateMismatch',
  token_failed: 'authCallback.tokenFailed',
  userinfo_failed: 'authCallback.userinfoFailed',
  access_denied: 'authCallback.accessDenied',
};

export default function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setToken, fetchUser } = useAuthStore();
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  const token = searchParams.get('token');
  const oauthError = searchParams.get('error');
  const errorDesc = searchParams.get('error_description');

  // Derive error from URL params during render
  const urlError = oauthError
    ? (errorKeyMap[oauthError] ? t(errorKeyMap[oauthError]) : (errorDesc || oauthError))
    : (!token ? t('authCallback.authFailed') : null);
  const error = runtimeError || urlError;

  useEffect(() => {
    if (!token || oauthError) return;
    setToken(token);
    fetchUser()
      .then(() => {
        navigate('/', { replace: true });
      })
      .catch(() => {
        setRuntimeError(t('authCallback.authFailed'));
      });
  }, [token, oauthError, setToken, fetchUser, navigate]);

  if (error) {
    return (
      <div className="auth-callback-page">
        <div className="auth-callback-card">
          <div className="auth-callback-icon">✕</div>
          <h2>{t('authCallback.authFailed')}</h2>
          <p className="auth-callback-error">{error}</p>
          <Link to="/login" className="btn btn-primary">{t('authCallback.backToLogin')}</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-callback-page" aria-live="polite">
      <div className="auth-callback-card">
        <div className="auth-callback-spinner" />
        <p>{t('authCallback.authenticating')}</p>
      </div>
    </div>
  );
}
