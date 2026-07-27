import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom';
import AuthPage from './auth/AuthPage';
import { RequireAuth } from './auth/RequireAuth';
import { getToken } from './auth/token';
import { PortfolioProvider } from './portfolio/PortfolioProvider';
import AppShell from './shell/AppShell';
import { ToastProvider } from './shell/ToastProvider';
import { ThemeProvider } from './theme/ThemeProvider';

function LoginRoute() {
  if (getToken()) return <Navigate to="/" replace />;
  return <AuthPage />;
}

function AuthenticatedApp() {
  const navigate = useNavigate();
  return (
    <ToastProvider>
      <PortfolioProvider onUnauthorized={() => navigate('/login', { replace: true })}>
        <AppShell />
      </PortfolioProvider>
    </ToastProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<AuthenticatedApp />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
