import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import AuthPage from './auth/AuthPage';
import { RequireAuth } from './auth/RequireAuth';
import { getToken } from './auth/token';
import AppShell from './shell/AppShell';
import { ThemeProvider } from './theme/ThemeProvider';

function LoginRoute() {
  if (getToken()) return <Navigate to="/" replace />;
  return <AuthPage />;
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<AppShell />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
