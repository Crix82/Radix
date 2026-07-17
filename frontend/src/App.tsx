import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { t } from "./i18n";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/search" replace />} />
        <Route
          path="/search"
          element={
            <PlaceholderPage
              title={t.pages.search.title}
              subtitle={t.pages.search.subtitle}
              note={t.pages.search.placeholder}
            />
          }
        />
        <Route
          path="/chat"
          element={
            <PlaceholderPage
              title={t.pages.chat.title}
              subtitle={t.pages.chat.subtitle}
              note={t.pages.chat.placeholder}
            />
          }
        />
        <Route
          path="/sources"
          element={
            <PlaceholderPage
              title={t.pages.sources.title}
              subtitle={t.pages.sources.subtitle}
              note={t.pages.sources.placeholder}
            />
          }
        />
        <Route
          path="/indexing"
          element={
            <PlaceholderPage
              title={t.pages.indexing.title}
              subtitle={t.pages.indexing.subtitle}
              note={t.pages.indexing.placeholder}
            />
          }
        />
        <Route
          path="/users"
          element={
            <PlaceholderPage
              title={t.pages.users.title}
              subtitle={t.pages.users.subtitle}
              note={t.pages.users.placeholder}
            />
          }
        />
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
