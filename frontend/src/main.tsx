import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/atkinson-hyperlegible-next';
import '@fontsource/atkinson-hyperlegible-mono/400.css';
import '@fontsource-variable/source-serif-4/opsz-italic.css';
import './design/tokens.css';
import './design/app.css';
import { I18nProvider } from './i18n/I18n';
import { App } from './app/App';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </React.StrictMode>,
);
