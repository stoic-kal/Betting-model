/**
 * main.tsx — Vite entry point
 *
 * Mounts React into #root with StrictMode.
 * Imports global CSS before anything else renders.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Providers } from './app/providers';
import { App } from './app/App';
import './styles/global.css';

const root = document.getElementById('root');

if (!root) {
  throw new Error(
    '[Athena] #root element not found. Check public/index.html.'
  );
}

createRoot(root).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>
);
