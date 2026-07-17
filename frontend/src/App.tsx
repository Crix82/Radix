import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { t } from "./i18n";
import { ChatPage } from "./pages/ChatPage";
import { IndexingPage } from "./pages/IndexingPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SearchPage } from "./pages/SearchPage";
import { SourcesPage } from "./pages/SourcesPage";
import { ViewerPage } from "./pages/ViewerPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/search" replace />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/viewer/:documentId/:page" element={<ViewerPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/indexing" element={<IndexingPage />} />
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
