import { Navigate, Route, Routes } from "react-router-dom";

import { HomeRedirect } from "./components/HomeRedirect";
import { Layout } from "./components/Layout";
import { ChatPage } from "./pages/ChatPage";
import { IndexingPage } from "./pages/IndexingPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { SearchPage } from "./pages/SearchPage";
import { SourcesPage } from "./pages/SourcesPage";
import { UsersPage } from "./pages/UsersPage";
import { ViewerPage } from "./pages/ViewerPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<HomeRedirect />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:conversationId" element={<ChatPage />} />
        <Route path="/viewer/:documentId/:page" element={<ViewerPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/indexing" element={<IndexingPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
