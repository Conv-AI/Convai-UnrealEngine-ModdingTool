/* Convai Modding Tool — the whole front end.

   The UI knows no Python. It sends frozen v1 commands and listens for frozen v1 events;
   everything else on this page is presentation. There is no fetch, no XHR, no socket and
   no file access anywhere in this file.

       send(command, params)  -> Promise<data>, rejects with { code, message }
       window.convai.onEvent  <- called by Python, routed to subscribers here
*/

/* ============================ transport ============================ */

const bus = {
  handlers: {},
  on(event, fn) { (this.handlers[event] || (this.handlers[event] = [])).push(fn); },
  emit(event, data) { (this.handlers[event] || []).forEach((fn) => fn(data || {})); },
};

// Python's only way in. It may hand over the envelope as an object or as JSON text.
window.convai = {
  onEvent(payload) {
    try {
      const message = typeof payload === 'string' ? JSON.parse(payload) : payload;
      if (message && message.type === 'event' && message.event) bus.emit(message.event, message.data);
    } catch (error) {
      console.error('Convai UI: unreadable event', payload, error);
    }
  },
};

const newId = () => (window.crypto && crypto.randomUUID
  ? crypto.randomUUID()
  : 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));

/* pywebview injects its api after the document has started, so the choice of transport
   waits for `pywebviewready`. No event means no host: that is the browser, and the demo
   transport below is what lets index.html be opened straight from disk for design work. */
const transportReady = new Promise((resolve) => {
  const pick = () => resolve(window.pywebview && window.pywebview.api ? nativeTransport() : demoTransport());
  if (window.pywebview && window.pywebview.api) return pick();
  window.addEventListener('pywebviewready', pick, { once: true });
  setTimeout(pick, 700);
});

function nativeTransport() {
  const api = window.pywebview.api;
  // The host names the entry point; any of these is the same in-process call.
  const call = api.send || api.call || api.command || api.dispatch || api.invoke;
  return async (envelope) => {
    if (typeof call !== 'function') {
      return { id: envelope.id, ok: false, error: { code: 'unknown', message: 'The tool could not reach its own backend.' } };
    }
    const reply = await call.call(api, envelope);
    return typeof reply === 'string' ? JSON.parse(reply) : reply;
  };
}

async function send(command, params) {
  const transport = await transportReady;
  const reply = await transport({ id: newId(), command, params: params || {} });
  if (reply && reply.ok) return reply.data || {};
  const error = (reply && reply.error) || {};
  throw { code: error.code || 'unknown', message: error.message || 'Something went wrong. Try again.' };
}

/* ============================ demo transport ============================ */

function demoTransport() {
  console.info('Convai UI: no Python bridge — using the built-in demo transport.');

  const emit = (event, data) => window.convai.onEvent({ type: 'event', event, data });
  const later = (ms, fn) => setTimeout(fn, ms);

  const account = { signedIn: false, name: null, email: '' };
  const engines = {
    current: { versionType: 'current', version: '5.4', path: 'E:\\Epic Games\\UE_5.4', ready: true, reason: null },
    target: { versionType: 'target', version: '5.5', path: null, ready: false, reason: 'Unreal Engine 5.5 was not found on this computer.' },
  };
  const projects = [
    {
      dir: 'E:\\Convai\\CityGuide', name: 'CityGuide', ue: '5.5', assetType: 'Scene', isMetahuman: false,
      migratable: false, target: '5.5', state: 'Ready to update', stateTone: 'ok', meta: 'UE 5.5', connected: false,
    },
    {
      dir: 'E:\\Convai\\MetaHost', name: 'MetaHost', ue: '5.3', assetType: 'Avatar', isMetahuman: true,
      migratable: true, target: '5.5', state: 'Needs migration → UE 5.5', stateTone: 'warn', meta: 'UE 5.3', connected: false,
    },
  ];
  const withAccount = () => projects.map((project) => ({ ...project, connected: account.signedIn }));

  const signIn = (name, email) => {
    Object.assign(account, { signedIn: true, name, email });
    emit('accountChanged', { account: { ...account } });
    return { account: { ...account } };
  };

  let runSeq = 0;
  const fakeRun = (titles, subject, folder, fail) => {
    const runId = `demo-run-${++runSeq}`;
    const steps = titles.map((title) => ({ title, state: 'pending' }));
    later(150, () => {
      steps[0].state = 'active';
      emit('steps', { runId, steps: steps.map((step) => ({ ...step })) });
      emit('log', { runId, line: `[12:00:00] Starting ${subject}...` });
    });
    titles.forEach((title, index) => {
      later(900 * (index + 1), () => {
        if (fail && index === titles.length - 2) {
          emit('log', { runId, line: `[12:00:0${index}] ERROR: the build could not be started.` });
          emit('runFinished', {
            runId, ok: false, subject, folder, notes: null, uproject: null,
            error: 'The project could not be built. Unreal Engine reported a compile error.',
            rebuild: folder ? { folder, enginePath: 'C:\Program Files\Epic Games\UE_5.8' } : null,
          });
          return;
        }
        steps[index].state = 'done';
        if (steps[index + 1]) steps[index + 1].state = 'active';
        emit('steps', { runId, steps: steps.map((step) => ({ ...step })) });
        emit('log', { runId, line: `[12:00:0${index}] ${title}... done` });
        if (index === titles.length - 1) {
          emit('runFinished', {
            runId, ok: true, subject, folder, error: null,
            uproject: folder ? `${folder}\${subject}.uproject` : null,
            rebuild: null,
            notes: folder && folder.includes('_5.5')
              ? 'Engine version set to 5.5. Convai plugin rebuilt against the new engine. Target.cs files patched.'
              : null,
          });
        }
      });
    });
    return { runId };
  };

  const answers = {
    boot() {
      ['config', 'version', 'projects'].forEach((stage, index) => {
        later(120 * index + 60, () => emit('bootStage', { stage, state: 'active' }));
        later(120 * index + 160, () => emit('bootStage', { stage, state: 'done' }));
      });
      return { version: '1.4.2', upToDate: true, requiredVersion: '1.4.2', account: { ...account } };
    },
    'projects.list': () => ({ projects: withAccount() }),
    'project.rebuild': ({ folder }) => fakeRun(['Building project'], 'Demo', folder, false),
    'project.validateName': ({ name }) => {
      const trimmed = (name || '').trim();
      if (!trimmed) return { problem: 'Enter a project name.' };
      if (!/^[A-Za-z0-9_]+$/.test(trimmed)) return { problem: 'Use letters, digits, and underscores only.' };
      if (projects.some((project) => project.name.toLowerCase() === trimmed.toLowerCase())) {
        return { problem: `A folder called ${trimmed} is already beside this tool.` };
      }
      return { problem: null };
    },
    'account.status': () => ({ account: { ...account } }),
    'account.signInGoogle': () => signIn('Alex Chen', 'alex.chen@example.com'),
    'account.signInKey': ({ key }) => {
      if (!key || key.length < 8) throw { code: 'invalidKey', message: "We couldn't verify that API key. Check it and try again." };
      return signIn('Convai account', '');
    },
    'account.signOut': () => {
      Object.assign(account, { signedIn: false, name: null, email: '' });
      emit('accountChanged', { account: { ...account } });
      return { account: { ...account } };
    },
    'account.dashboard': () => ({}),
    'engine.status': () => ({
      current: { ...engines.current },
      target: { ...engines.target },
      sameVersion: engines.current.version === engines.target.version,
    }),
    'engine.choose': ({ versionType }) => {
      const engine = engines[versionType] || engines.current;
      Object.assign(engine, { path: `E:\\Epic Games\\UE_${engine.version}`, ready: true, reason: null });
      return { engine: { ...engine } };
    },
    'migration.preflight': ({ dir }) => {
      const project = projects.find((entry) => entry.dir === dir) || projects[1];
      return {
        destinationName: `${project.name}_${project.target}`,
        destinationDir: `E:\\Convai\\${project.name}_${project.target}`,
        exists: false,
        currentVersion: project.ue,
        targetVersion: project.target,
        needed: project.migratable,
      };
    },
    'project.create': ({ name }) => fakeRun(
      ['Validating Unreal Engine', 'Setting up project', 'Downloading Convai dependencies', 'Configuring assets', 'Building project'],
      name, `E:\\Convai\\${name}`),
    'project.update': ({ dir }) => {
      const project = projects.find((entry) => entry.dir === dir) || projects[0];
      return fakeRun(
        ['Reading the project', 'Checking Unreal Engine', 'Updating Convai plugins', 'Configuring project assets', 'Building project'],
        project.name, project.dir);
    },
    'project.migrate': ({ dir }) => {
      const project = projects.find((entry) => entry.dir === dir) || projects[1];
      const name = `${project.name}_${project.target}`;
      return fakeRun(
        ['Checking what the migration needs', 'Updating the source project', 'Copying the project', 'Updating the engine version', 'Building the copy'],
        name, `E:\\Convai\\${name}`);
    },
    'path.open': () => ({}),
    'log.save': () => ({ path: 'E:\\Convai\\demo-run.log' }),
    'toolchain.install': () => {
      emit('toolchain', { state: 'installing', message: 'Installing, this can take several minutes…' });
      later(1800, () => emit('toolchain', { state: 'done', message: 'Toolchain ready.' }));
      return { installed: true };
    },
    'packaging.status': () => ({ linuxEnabled: false, engineVersion: engines.current.version }),
    'updates.check': () => ({ upToDate: true, latest: '1.4.2' }),
    'updates.download': () => ({}),
    'app.quit': () => ({}),
  };

  return (envelope) => new Promise((resolve) => later(140, () => {
    const answer = answers[envelope.command];
    if (!answer) {
      return resolve({ id: envelope.id, ok: false, error: { code: 'notFound', message: `The demo transport has no answer for ${envelope.command}.` } });
    }
    try {
      resolve({ id: envelope.id, ok: true, data: answer(envelope.params || {}) });
    } catch (error) {
      resolve({ id: envelope.id, ok: false, error: { code: error.code || 'unknown', message: error.message || 'Demo failure.' } });
    }
  }));
}

/* ============================ state ============================ */

const state = {
  screen: 'boot',
  version: '',
  account: { signedIn: false, name: null, email: '' },
  engine: { current: null, target: null, sameVersion: true },
  ready: false,          // boot finished; the chrome is usable
  running: false,        // a run owns the window

  boot: { config: 'pending', version: 'pending', projects: 'pending' },
  blocked: null,         // { outdated, title, cause, detail, installed, required }

  projects: [],
  selectedDir: null,
  query: '',
  scanning: false,
  scanError: null,
  scanned: false,

  form: { name: '', assetType: 'Scene', isMetahuman: false, step: 0, error: null, touched: false },
  review: null,          // { kind, project, preflight }
  run: null,             // { runId, title, subject, folder, steps, lines, finished, logOpen, retry }
  settings: null,
  signIn: null,          // { view, status, tone, busy, error, resume }
  menuOpen: false,

  primary: null,         // what Enter does on this screen
  escape: null,          // what Escape does on this screen
};

/* ============================ small helpers ============================ */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function on(selector, event, handler, root = document) {
  const element = $(selector, root);
  if (element) element.addEventListener(event, handler);
  return element;
}

/* Everything interpolated into markup goes through this: project names, paths, engine
   reasons and log lines are data from disk, not markup. */
function esc(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const CHECK_SVG = '<svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const WARNING_SVG = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3.5l9 16H3l9-16z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 10v4.5M12 17.4v.2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
const UPDATE_SVG = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 19V6M12 5l-5.5 5.5M12 5l5.5 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '?';
  return (parts[0][0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
}

function setStatus(text) {
  const element = $('#status-right');
  if (element) element.textContent = text || '';
}

function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(() => execCopy(text));
      return true;
    }
  } catch (error) { /* fall through to the selection copy */ }
  return execCopy(text);
}

function execCopy(text) {
  const holder = document.createElement('textarea');
  holder.value = text;
  holder.setAttribute('readonly', '');
  holder.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
  document.body.appendChild(holder);
  holder.select();
  let copied = false;
  try { copied = document.execCommand('copy'); } catch (error) { copied = false; }
  holder.remove();
  return copied;
}

// A failed command always has a sentence fit to show; this is where it lands.
const failure = (error) => (error && error.message) || 'Something went wrong. Try again.';

/* ============================ chrome ============================ */

const CRUMBS = {
  boot: 'Starting', blocked: 'Start', shelf: 'Projects',
  newProject: 'New project', review: 'Review', run: 'Activity',
};

function renderChrome() {
  $('#crumb').textContent = '/ ' + (CRUMBS[state.screen] || 'Projects');
  $('#status-version').textContent = state.version ? `v${state.version}` : 'Convai Modding Tool';

  const navigable = state.ready && !state.running;
  $('#home-button').disabled = !navigable;
  $('#settings-button').disabled = !navigable;
  $('#account-button').disabled = !navigable;
  $('#settings-button').hidden = !state.ready;
  $('#account-button').hidden = !state.ready;

  const account = state.account;
  $('#account-avatar').textContent = account.signedIn ? initials(account.name || account.email) : '?';
  $('#account-label').textContent = account.signedIn
    ? (account.name || account.email || 'Convai account').split(' ')[0]
    : 'Sign in';
  $('#account-button').title = account.signedIn
    ? [account.name, account.email].filter(Boolean).join(' — ')
    : 'Sign in to Convai';

}

/* ============================ router ============================ */

const screens = {
  boot: renderBoot,
  blocked: renderBlocked,
  shelf: renderShelf,
  newProject: renderNewProject,
  review: renderReview,
  run: renderRun,
};

function show(screen) {
  state.screen = screen;
  render();
}

function render() {
  state.primary = null;
  state.escape = null;
  renderChrome();
  const page = $('#page');
  page.scrollTop = 0;
  screens[state.screen](page);
  renderOverlay();
}

/* ============================ boot ============================ */

function renderBoot(page) {
  const stage = (key, label) => {
    const value = state.boot[key];
    return `<li class="${value}"><span class="marker">${value === 'done' ? CHECK_SVG : ''}</span><span>${label}</span></li>`;
  };
  page.innerHTML = `
    <div class="boot-layout">
      <section class="panel boot-card">
        <h2>Convai Modding Tool</h2>
        <p class="intro">Getting things ready</p>
        <ul class="steplist">
          ${stage('config', 'Checking configuration')}
          ${stage('version', 'Checking version')}
          ${stage('projects', 'Opening projects')}
        </ul>
        <div class="progress" style="margin-top:24px" role="progressbar" aria-label="Starting"></div>
      </section>
    </div>`;
}

function startBoot() {
  state.boot = { config: 'active', version: 'pending', projects: 'pending' };
  state.ready = false;
  state.blocked = null;
  show('boot');

  send('boot').then((data) => {
    state.version = data.version || '';
    state.account = data.account || state.account;

    if (data.upToDate === false) {
      state.blocked = {
        outdated: true,
        title: 'A newer version is required',
        cause: 'Update Convai Modding Tool to continue creating, updating, and migrating projects.',
        detail: '',
        installed: data.version || '',
        required: data.requiredVersion || '',
      };
      return show('blocked');
    }

    // `upToDate: null` is a check that could not be made, not an outdated build: the tool
    // opens, and the status bar says the check did not happen.
    state.ready = true;
    if (data.upToDate === null) setStatus("Couldn't check for updates this time.");
    return loadEngine().then(() => showShelf());
  }).catch((error) => {
    state.blocked = {
      outdated: false,
      title: "We couldn't start the tool",
      cause: failure(error),
      detail: `${error && error.code ? error.code : 'unknown'}: ${failure(error)}`,
      installed: '', required: '',
    };
    show('blocked');
  });
}

bus.on('bootStage', (data) => {
  if (!data.stage || !(data.stage in state.boot)) return;
  state.boot[data.stage] = data.state === 'done' ? 'done' : 'active';
  if (state.screen === 'boot') renderBoot($('#page'));
});

/* ============================ blocked start ============================ */

function renderBlocked(page) {
  const blocked = state.blocked || {};
  const versions = blocked.outdated ? `
      <section class="panel">
        <div class="version-compare">
          <div><span>INSTALLED</span><strong>${blocked.installed ? 'v' + esc(blocked.installed) : 'unknown'}</strong></div>
          <div><span>REQUIRED</span><strong>${blocked.required ? 'v' + esc(blocked.required) : 'latest'}</strong></div>
        </div>
        <p class="intro" style="margin-top:14px;font-size:12px">Updating protects compatibility with the current Convai plugins and Unreal Engine workflow.</p>
      </section>` : `
      <section class="panel">
        <button class="quiet flat-left" id="details-toggle" type="button" aria-expanded="false">Show details</button>
        <div class="details-box" id="details-box" hidden><pre>${esc(blocked.detail || 'No details were reported.')}</pre></div>
      </section>`;

  page.innerHTML = `
    <div class="blocked-layout">
      <div class="blocked-icon ${blocked.outdated ? '' : 'danger'}">${blocked.outdated ? UPDATE_SVG : WARNING_SVG}</div>
      <span class="chip ${blocked.outdated ? 'warn' : 'danger'}"><span class="dot"></span>${blocked.outdated ? 'Update required' : 'Start-up blocked'}</span>
      <h1>${esc(blocked.title)}</h1>
      <p class="intro">${esc(blocked.cause)}</p>
      ${versions}
      <div class="blocked-actions">
        ${blocked.outdated
          ? '<button class="primary tall" id="blocked-download" type="button">Download latest version</button><button class="tall" id="blocked-retry" type="button">Check again</button>'
          : '<button class="primary tall" id="blocked-retry" type="button">Try again</button>'}
        <button class="quiet tall" id="blocked-quit" type="button">Quit</button>
      </div>
    </div>`;

  on('#blocked-download', 'click', () => send('updates.download').catch((error) => setStatus(failure(error))));
  on('#blocked-retry', 'click', startBoot);
  on('#blocked-quit', 'click', () => send('app.quit').catch(() => {}));
  on('#details-toggle', 'click', (event) => {
    const box = $('#details-box');
    box.hidden = !box.hidden;
    event.currentTarget.textContent = box.hidden ? 'Show details' : 'Hide details';
    event.currentTarget.setAttribute('aria-expanded', String(!box.hidden));
  });

  const first = $('#blocked-download') || $('#blocked-retry');
  if (first) first.focus();
  state.primary = () => (first ? first.click() : null);
}

/* ============================ engine + projects ============================ */

function loadEngine() {
  return send('engine.status').then((data) => {
    state.engine = { current: data.current || null, target: data.target || null, sameVersion: !!data.sameVersion };
    renderChrome();
  }).catch((error) => setStatus(failure(error)));
}

function loadProjects() {
  state.scanning = true;
  state.scanError = null;
  updateRefreshButtons();
  return send('projects.list').then((data) => {
    state.projects = data.projects || [];
    state.scanned = true;
    const known = state.projects.some((project) => project.dir === state.selectedDir);
    if (!known) state.selectedDir = state.projects.length ? state.projects[0].dir : null;
  }).catch((error) => {
    state.projects = [];
    state.scanned = true;
    state.scanError = failure(error);
  }).then(() => {
    state.scanning = false;
    if (state.screen === 'shelf') renderShelf($('#page'));
  });
}

function showShelf(selectDir) {
  if (selectDir) state.selectedDir = selectDir;
  show('shelf');
  loadProjects();
}

const visibleProjects = () => {
  const query = state.query.trim().toLowerCase();
  return query ? state.projects.filter((project) => project.name.toLowerCase().includes(query)) : state.projects;
};

const selectedProject = () => state.projects.find((project) => project.dir === state.selectedDir) || null;

function updateRefreshButtons() {
  $$('.refresh-button').forEach((button) => {
    button.disabled = state.scanning;
    button.textContent = state.scanning ? 'Refreshing…' : 'Refresh';
  });
}

/* ============================ shelf ============================ */

function renderShelf(page) {
  const signedOut = !state.account.signedIn;
  page.innerHTML = `
    <div class="title-row">
      <div>
        <h1>Projects</h1>
        <p class="intro">Create, update, and migrate the Unreal projects beside this tool.</p>
      </div>
      <span class="spacer"></span>
      <button class="quiet tall refresh-button" id="refresh" type="button">Refresh</button>
      <button class="primary tall" id="new-project" type="button">+ New project</button>
    </div>
    ${signedOut ? `
    <div class="home-auth">
      <span>Sign in to create or manage Convai projects.</span>
      <button class="quiet" id="banner-signin" type="button">Sign in</button>
    </div>` : ''}
    <div id="shelf-body"></div>`;

  on('#refresh', 'click', loadProjects);
  on('#new-project', 'click', openNewProject);
  on('#banner-signin', 'click', () => openSignIn());
  updateRefreshButtons();
  renderShelfBody();

  state.primary = () => { const project = selectedProject(); if (project) startUpdate(project); };
}

function renderShelfBody() {
  const body = $('#shelf-body');
  if (!body) return;

  if (state.scanned && !state.scanError && !state.projects.length) {
    body.innerHTML = `
      <section class="panel empty">
        <h2>No modding projects here yet</h2>
        <p>The tool lists the Unreal projects that sit in the same folder as this tool. Create one and it appears here.</p>
        <div class="row">
          <button class="primary tall" id="empty-create" type="button">Create a project</button>
          <button class="quiet tall refresh-button" id="empty-refresh" type="button">Refresh</button>
        </div>
      </section>`;
    on('#empty-create', 'click', openNewProject);
    on('#empty-refresh', 'click', loadProjects);
    updateRefreshButtons();
    return;
  }

  body.innerHTML = `
    <div class="grid">
      <section class="panel">
        <div class="panel-head">
          <span class="section-label" id="project-count">PROJECTS</span>
          <input class="search" id="search" type="search" autocomplete="off" aria-label="Search projects" placeholder="Search projects…" value="${esc(state.query)}">
        </div>
        <div class="projects" id="project-list" role="listbox" aria-label="Projects"></div>
      </section>
      <aside class="panel detail" id="inspector"></aside>
    </div>`;

  const search = $('#search');
  search.addEventListener('input', (event) => {
    state.query = event.target.value;
    renderProjectList();
    renderInspector();
  });
  search.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      moveSelection(event.key === 'ArrowDown' ? 1 : -1);
    }
  });

  renderProjectList();
  renderInspector();
}

function renderProjectList() {
  const host = $('#project-list');
  if (!host) return;
  const matches = visibleProjects();
  const count = $('#project-count');
  if (count) count.textContent = `PROJECTS (${matches.length})`;

  if (state.scanError) {
    host.innerHTML = `<div class="list-note danger">Couldn't read the folder beside this tool: ${esc(state.scanError)}</div>
      <button class="quiet flat-left" id="scan-retry" type="button">Try again</button>`;
    on('#scan-retry', 'click', loadProjects);
    return;
  }
  if (!state.scanned) {
    host.innerHTML = '<div class="list-note">Looking for projects…</div>';
    return;
  }
  if (!matches.length) {
    host.innerHTML = `<div class="list-note">No projects match “${esc(state.query.trim())}”.</div>
      <button class="quiet flat-left" id="clear-search" type="button">Clear search</button>`;
    on('#clear-search', 'click', () => {
      state.query = '';
      renderShelfBody();
      const search = $('#search');
      if (search) search.focus();
    });
    return;
  }

  if (!matches.some((project) => project.dir === state.selectedDir)) state.selectedDir = matches[0].dir;

  host.innerHTML = matches.map((project) => `
    <button class="project ${project.dir === state.selectedDir ? 'selected' : ''}" type="button" role="option"
            aria-selected="${project.dir === state.selectedDir}" data-dir="${esc(project.dir)}">
      <span class="project-main">
        <span style="min-width:0">
          <span class="project-title"><span class="name">${esc(project.name)}</span>${project.assetType ? `<span class="kind">${esc(project.assetType)}</span>` : ''}</span>
          <span class="project-meta">${esc(project.meta)}<span aria-hidden="true">•</span>${project.connected ? 'Connected' : 'Sign in to manage'}</span>
        </span>
      </span>
      <span class="state ${project.stateTone === 'ok' ? '' : esc(project.stateTone)}">${esc(project.state)}</span>
    </button>`).join('');

  $$('.project', host).forEach((row) => {
    row.addEventListener('click', () => selectProject(row.dataset.dir));
    row.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        moveSelection(event.key === 'ArrowDown' ? 1 : -1, true);
      }
    });
  });
}

function selectProject(dir) {
  state.selectedDir = dir;
  renderProjectList();
  renderInspector();
}

function moveSelection(delta, keepFocus) {
  const matches = visibleProjects();
  if (!matches.length) return;
  const current = matches.findIndex((project) => project.dir === state.selectedDir);
  const next = Math.max(0, Math.min(matches.length - 1, (current < 0 ? 0 : current + delta)));
  selectProject(matches[next].dir);
  const row = $(`.project[data-dir="${CSS.escape(matches[next].dir)}"]`);
  if (row) {
    row.scrollIntoView({ block: 'nearest' });
    if (keepFocus) row.focus();
  }
}

/* Empty when migration can run; otherwise the sentence shown beside the button. */
function migrateReason(project) {
  if (!project.ue) return "Migration is unavailable: this project's engine version was not detected.";
  if (!project.migratable) return `Migration is unavailable: this project already uses UE ${project.target}.`;
  const target = state.engine.target;
  if (!target || !target.ready) return target && target.reason
    ? target.reason
    : `Choose a UE ${project.target} installation in Settings.`;
  return '';
}

function renderInspector() {
  const host = $('#inspector');
  if (!host) return;
  const project = selectedProject();
  if (!project) {
    host.innerHTML = '<span class="section-label">SELECTED PROJECT</span><p class="intro" style="margin-top:12px">Select a project to see what you can do with it.</p>';
    return;
  }

  const reason = migrateReason(project);
  host.innerHTML = `
    <span class="section-label">SELECTED PROJECT</span>
    <div class="project-title"><h2>${esc(project.name)}</h2>${project.assetType ? `<span class="kind">${esc(project.assetType)}</span>` : ''}</div>
    <div class="project-meta">
      <span class="${project.ue ? '' : 'warn-text'}">${esc(project.meta)}</span>
      <span aria-hidden="true">•</span>
      <span class="${project.connected ? 'ok-text' : 'warn-text'}">${project.connected ? 'Connected' : 'Sign in to manage'}</span>
    </div>
    <div class="path" title="${esc(project.dir)}">${esc(project.dir)}</div>
    <button class="quiet flat-left" id="copy-path" type="button">Copy path</button>
    <p>Keep this project current with the latest Convai integration.</p>
    <div class="actions">
      <button class="primary" id="do-update" type="button" aria-describedby="update-help">Update project</button>
      <span class="helper" id="update-help">Updates Convai plugins and project settings. Your content stays in place.</span>
      <button id="do-migrate" type="button" aria-describedby="migrate-help" ${reason ? 'disabled' : ''}>Migrate to UE ${esc(project.target)}</button>
      <span class="helper ${reason ? 'warn' : ''}" id="migrate-help">${esc(reason || 'Creates a copy beside this one. The original project is not changed.')}</span>
    </div>`;

  on('#copy-path', 'click', (event) => {
    if (!copyText(project.dir)) return setStatus("Couldn't copy the path.");
    const button = event.currentTarget;
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = 'Copy path'; }, 1500);
  });
  on('#do-update', 'click', () => startUpdate(project));
  on('#do-migrate', 'click', () => startMigrate(project));
}

/* ============================ new project ============================ */

const FORM_STEPS = ['Project details', 'Project type', 'Unreal Engine'];

function openNewProject() {
  if (!requireAccount(openNewProject)) return;
  show('newProject');
}

function renderNewProject(page) {
  const form = state.form;
  const stepper = FORM_STEPS.map((title, index) => {
    const status = index === form.step ? 'active' : (index < form.step ? 'done' : '');
    return `<span class="step ${status}"><b>${index < form.step ? '✓' : index + 1}</b>${esc(title)}</span>`;
  }).join('<span class="step-line"></span>');

  page.innerHTML = `
    <div class="form-layout">
      <div class="title-row">
        <div>
          <h1>New project</h1>
          <p class="intro">Start with an Unreal project configured for Convai.</p>
        </div>
        <span class="spacer"></span>
        <span class="chip neutral">Step ${form.step + 1} of 3</span>
      </div>
      <div class="stepper" aria-label="New project progress">${stepper}</div>
      <section class="panel form-card" id="form-body"></section>
    </div>`;

  ([renderFormDetails, renderFormType, renderFormEngine])[form.step]($('#form-body'));
  state.escape = () => showShelf();
}

function renderFormDetails(host) {
  const form = state.form;
  const signedIn = state.account.signedIn;
  host.innerHTML = `
    <h2>Project details</h2>
    <div class="field ${form.error ? 'invalid' : ''}">
      <label for="project-name">Project name</label>
      <input id="project-name" autocomplete="off" placeholder="e.g. CityGuide" value="${esc(form.name)}"
             aria-describedby="name-help name-error" ${form.error ? 'aria-invalid="true"' : ''}>
      <small id="name-help">Letters, digits, and underscores only.</small>
      <span class="error" id="name-error" role="alert">${esc(form.error || '')}</span>
    </div>
    <p class="privacy ${signedIn ? '' : 'warn'}">
      <strong>${signedIn ? 'Signed in with Convai' : 'Sign in to continue'}</strong>
      ${signedIn
        ? `This project will be created with ${esc(state.account.name || state.account.email || 'your Convai account')}. Change accounts from the profile menu beside Settings.`
        : "Creating a project needs a Convai account. Continue and we'll ask you to sign in."}
    </p>
    <div class="form-actions">
      <button id="cancel" class="tall" type="button">Cancel</button>
      <button class="primary tall" id="continue" type="button">Continue</button>
    </div>`;

  const input = $('#project-name');
  let timer = null;
  input.addEventListener('input', (event) => {
    state.form.name = event.target.value;
    if (!state.form.touched) return;
    clearTimeout(timer);
    timer = setTimeout(() => validateName().then(setNameError), 250);
  });
  input.addEventListener('blur', () => {
    state.form.touched = true;
    validateName().then(setNameError);
  });
  input.addEventListener('keydown', (event) => { if (event.key === 'Enter') continueFromDetails(); });

  on('#cancel', 'click', () => showShelf());
  on('#continue', 'click', continueFromDetails);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
  state.primary = continueFromDetails;
}

const validateName = () => send('project.validateName', { name: state.form.name.trim() })
  .then((data) => data.problem || null)
  .catch((error) => failure(error));

function setNameError(problem) {
  state.form.error = problem;
  const field = $('#project-name');
  if (!field) return;
  $('#name-error').textContent = problem || '';
  field.parentElement.classList.toggle('invalid', !!problem);
  if (problem) field.setAttribute('aria-invalid', 'true'); else field.removeAttribute('aria-invalid');
}

function continueFromDetails() {
  state.form.touched = true;
  validateName().then((problem) => {
    setNameError(problem);
    if (problem) return $('#project-name').focus();
    // The sign-in resumes on the step Continue asked for, so the click is not thrown away.
    if (!requireAccount(() => { state.form.step = 1; show('newProject'); })) return;
    state.form.step = 1;
    show('newProject');
  });
}

function renderFormType(host) {
  const form = state.form;
  host.innerHTML = `
    <h2>What are you creating?</h2>
    <p class="intro">Choose the starting point that best fits your project.</p>
    <div class="choice-grid" role="radiogroup" aria-label="Project type">
      <button class="choice ${form.assetType === 'Scene' ? 'selected' : ''}" type="button" role="radio"
              aria-checked="${form.assetType === 'Scene'}" data-type="Scene">
        <strong>Scene</strong><span>Environment or gameplay project.</span>
      </button>
      <button class="choice ${form.assetType === 'Avatar' ? 'selected' : ''}" type="button" role="radio"
              aria-checked="${form.assetType === 'Avatar'}" data-type="Avatar">
        <strong>Avatar</strong><span>Character project with an interactive persona.</span>
      </button>
    </div>
    <label class="checkbox-row" id="metahuman-row" ${form.assetType === 'Avatar' ? '' : 'hidden'}>
      <input id="metahuman" type="checkbox" ${form.isMetahuman ? 'checked' : ''}>
      <span><strong>This is a MetaHuman avatar</strong><br>Adds the MetaHuman-specific setup so the character's face, body and animation blueprints work with Convai.</span>
    </label>
    <div class="form-actions">
      <button class="back tall" id="back" type="button">Back</button>
      <button class="primary tall" id="continue" type="button">Continue</button>
    </div>`;

  $$('.choice', host).forEach((tile) => tile.addEventListener('click', () => {
    state.form.assetType = tile.dataset.type;
    // MetaHuman is an Avatar-only choice; leaving Avatar unsets it.
    if (state.form.assetType !== 'Avatar') state.form.isMetahuman = false;
    renderFormType(host);
  }));
  on('#metahuman', 'change', (event) => { state.form.isMetahuman = event.target.checked; });
  on('#back', 'click', () => { state.form.step = 0; show('newProject'); });
  on('#continue', 'click', () => { state.form.step = 2; show('newProject'); });
  state.primary = () => { state.form.step = 2; show('newProject'); };
}

function renderFormEngine(host) {
  const form = state.form;
  const engine = state.engine.current || { version: '', ready: false, reason: 'Unreal Engine was not found on this computer.', path: null };
  const ready = !!engine.ready;

  host.innerHTML = `
    <h2>Unreal Engine setup</h2>
    <p class="intro">Confirm the Unreal Engine installation for this project.</p>
    <div class="engine-card ${ready ? '' : 'warn'}">
      <span class="dot"></span>
      <div>
        <strong>${ready ? `Unreal Engine ${esc(engine.version)} detected` : `Unreal Engine ${esc(engine.version)} is required`}</strong>
        <span>${esc(ready ? engine.path : (engine.reason || `Choose the folder where Unreal Engine ${engine.version} is installed.`))}</span>
      </div>
      <button class="${ready ? 'quiet' : 'primary'}" id="choose-engine" type="button">Choose folder</button>
    </div>
    <div class="summary">
      <strong>Project summary</strong>
      <dl>
        <dt>Project</dt><dd>${esc(form.name.trim() || 'Not named yet')}</dd>
        <dt>Type</dt><dd>${esc(form.assetType)}</dd>
        ${form.assetType === 'Avatar' ? `<dt>MetaHuman</dt><dd>${form.isMetahuman ? 'Included' : 'Not included'}</dd>` : ''}
        <dt>Engine</dt><dd>${ready ? `Unreal Engine ${esc(engine.version)}` : 'Not chosen yet'}</dd>
      </dl>
    </div>
    <div class="form-actions">
      <button class="back tall" id="back" type="button">Back</button>
      ${ready ? '' : `<span class="reason" id="create-reason">Choose an Unreal Engine ${esc(engine.version)} folder to continue.</span>`}
      <button class="primary tall" id="create" type="button" ${ready ? '' : 'disabled aria-describedby="create-reason"'}>Create project</button>
    </div>`;

  on('#choose-engine', 'click', () => chooseEngine('current').then(() => renderFormEngine(host)));
  on('#back', 'click', () => { state.form.step = 1; show('newProject'); });
  on('#create', 'click', createProject);
  if (ready) state.primary = createProject;
}

function chooseEngine(versionType) {
  return send('engine.choose', { versionType }).then((data) => {
    if (data.engine) state.engine[versionType] = data.engine;
    renderChrome();
    setStatus('');
  }).catch((error) => setStatus(failure(error)));
}

function createProject() {
  const engine = state.engine.current;
  if (!engine || !engine.ready) return;
  if (!requireAccount(createProject)) return;

  const name = state.form.name.trim();
  send('project.create', {
    name,
    assetType: state.form.assetType,
    isMetahuman: !!state.form.isMetahuman,
    enginePath: engine.path,
  }).then((data) => {
    // Only once the run owns the values: every path that returns to the form -- an
    // invalid name, a lost session -- is a rejection, and keeps what was typed.
    state.form = { name: '', assetType: 'Scene', isMetahuman: false, step: 0, error: null, touched: false };
    startRun(data.runId, `Creating ${name}`, name, null);
  }).catch((error) => {
      if (error.code === 'invalidName' || error.code === 'destinationExists') {
        state.form.step = 0;
        state.form.touched = true;
        state.form.error = failure(error);
        return show('newProject');
      }
      setStatus(failure(error));
    });
}

/* ============================ action review ============================ */

function startUpdate(project) {
  if (!requireAccount(() => startUpdate(project))) return;
  state.review = { kind: 'update', project, preflight: null };
  show('review');
}

function startMigrate(project) {
  if (migrateReason(project)) return;
  if (!requireAccount(() => startMigrate(project))) return;
  state.review = { kind: 'migrate', project, preflight: null, loading: true };
  show('review');
  send('migration.preflight', { dir: project.dir }).then((data) => {
    state.review.preflight = data;
    state.review.loading = false;
    if (state.screen === 'review') render();
  }).catch((error) => {
    state.review.loading = false;
    state.review.error = failure(error);
    if (state.screen === 'review') render();
  });
}

function engineRow(label, versionType) {
  const engine = state.engine[versionType];
  const version = engine ? engine.version : '';
  const ready = engine && engine.ready;
  return `
    <div class="detail-row">
      <span class="label">${esc(label)}</span>
      <div class="value ${ready ? '' : 'warn'}">
        <span>${ready
          ? `Unreal Engine ${esc(version)} · <span class="mono">${esc(engine.path)}</span>`
          : esc((engine && engine.reason) || `Unreal Engine ${version} was not found on this computer.`)}</span>
        <button type="button" data-choose="${esc(versionType)}">${ready ? 'Change' : 'Choose folder'}</button>
      </div>
    </div>`;
}

function detailRow(label, value, mono, tone) {
  return `<div class="detail-row"><span class="label">${esc(label)}</span>
    <div class="value ${tone || ''}"><span class="${mono ? 'mono' : ''}">${esc(value)}</span></div></div>`;
}

function renderReview(page) {
  const review = state.review;
  if (!review) return showShelf();
  page.innerHTML = review.kind === 'migrate' ? migrateReviewMarkup(review) : updateReviewMarkup(review);

  $$('[data-choose]', page).forEach((button) => button.addEventListener('click', () => {
    chooseEngine(button.dataset.choose).then(() => render());
  }));
  on('#review-back', 'click', () => showShelf(review.project.dir));
  on('#review-confirm', 'click', confirmReview);
  on('#open-destination', 'click', () => {
    send('path.open', { path: review.preflight.destinationDir }).catch((error) => setStatus(failure(error)));
  });

  const confirm = $('#review-confirm');
  if (confirm && !confirm.disabled) { confirm.focus(); state.primary = confirmReview; }
  state.escape = () => showShelf(review.project.dir);
}

function reviewBlockers(review) {
  const reasons = [];
  const current = state.engine.current;
  if (!current || !current.ready) {
    reasons.push(`Choose your Unreal Engine ${current ? current.version : ''} installation above. ` +
      (review.kind === 'migrate' ? 'The source project is updated with it before it is copied.' : 'The update is built with it.'));
  }
  if (review.kind === 'migrate') {
    const target = state.engine.target;
    if (!target || !target.ready) reasons.push(`Choose your Unreal Engine ${target ? target.version : review.project.target} installation above. The copy is built with it.`);
    if (review.error) reasons.push(review.error);
    if (review.loading) reasons.push('Checking the destination folder…');
    if (review.preflight && review.preflight.exists) reasons.push(`Free the name ${review.preflight.destinationName} before migrating.`);
    if (review.preflight && review.preflight.needed === false) reasons.push('This project does not need migrating.');
    if (!review.preflight && !review.loading && !review.error) reasons.push('The destination has not been checked yet.');
  }
  return reasons;
}

function actionsMarkup(review, confirmText) {
  const reasons = reviewBlockers(review);
  return `
    ${reasons.length ? `<ul class="reasons">${reasons.map((reason) => `<li>${esc(reason)}</li>`).join('')}</ul>` : ''}
    <div class="page-actions">
      <button class="tall" id="review-back" type="button">Back</button>
      <span class="spacer"></span>
      <button class="primary tall" id="review-confirm" type="button" ${reasons.length ? 'disabled' : ''}>${esc(confirmText)}</button>
    </div>`;
}

function updateReviewMarkup(review) {
  const project = review.project;
  return `
    <div class="review-layout">
      <h1>Update ${esc(project.name)}</h1>
      <p class="intro" style="margin-bottom:24px">Nothing changes until you start the update.</p>
      <section class="panel">
        <div class="card-title"><span class="section-label">TARGET PROJECT</span></div>
        <div class="card-body">
          ${detailRow('Project', project.name)}
          ${detailRow('Location', project.dir, true)}
          ${engineRow('Unreal Engine used for this update', 'current')}
        </div>
      </section>
      <section class="panel">
        <div class="card-title"><span class="section-label">WHAT THIS UPDATE DOES</span></div>
        <div class="card-body">
          <ul class="bullets">
            <li>Replaces the Convai plugin in this project with the current release.</li>
            <li>Reapplies the project's Convai configuration and asset setup.</li>
            <li>Rebuilds the project so the new plugin compiles.</li>
          </ul>
          <p class="ok-text" style="margin:12px 0 0">Your content and original project folder remain in place.</p>
        </div>
      </section>
      ${actionsMarkup(review, 'Update project')}
    </div>`;
}

function migrateReviewMarkup(review) {
  const project = review.project;
  const preflight = review.preflight;
  const conflict = preflight && preflight.exists ? `
      <div class="blocker">
        <strong>${esc(preflight.destinationName)} already exists</strong>
        <span>The tool would have to write over a folder it did not create, so the migration cannot start. Rename or move the existing folder, then come back.</span>
        <div class="row">
          <button type="button" id="open-destination">Open existing folder</button>
        </div>
      </div>` : '';

  return `
    <div class="review-layout">
      <h1>Migrate ${esc(project.name)} to UE ${esc(project.target)}</h1>
      <p class="intro" style="margin-bottom:24px">The tool copies the project into a new folder and leaves the original alone.</p>
      ${conflict}
      <section class="panel">
        <div class="card-title"><span class="section-label">SOURCE PROJECT</span></div>
        <div class="card-body">
          ${detailRow('Project', project.name)}
          ${detailRow('Location', project.dir, true)}
          ${detailRow('Current Unreal Engine version',
            project.ue ? `Unreal Engine ${project.ue}` : 'Not detected in the project file', false,
            project.ue ? '' : 'warn')}
          ${engineRow('Unreal Engine used to update the source project', 'current')}
        </div>
      </section>
      <section class="panel">
        <div class="card-title"><span class="section-label">TARGET UNREAL ENGINE</span></div>
        <div class="card-body">${engineRow(`Unreal Engine ${project.target} installation`, 'target')}</div>
      </section>
      <section class="panel">
        <div class="card-title"><span class="section-label">DESTINATION</span></div>
        <div class="card-body">
          ${preflight
            ? detailRow('New folder', preflight.destinationName) + detailRow('Created beside this tool', preflight.destinationDir, true)
            : `<p class="intro">${esc(review.error || 'Checking where the copy will be created…')}</p>`}
          <p class="ok-text" style="margin:12px 0 0">The original project will not be changed.</p>
        </div>
      </section>
      <section class="panel">
        <div class="card-title"><span class="section-label">WHAT HAPPENS, IN ORDER</span></div>
        <div class="card-body">
          <ol class="steps-ordered">
            <li>Update the source project's Convai plugin and configuration.</li>
            <li>Copy the project into ${esc(preflight ? preflight.destinationName : `${project.name}_${project.target}`)}.</li>
            <li>Point the copy at Unreal Engine ${esc(project.target)} and patch it for that version.</li>
            <li>Build the copy with the target engine.</li>
          </ol>
        </div>
      </section>
      ${actionsMarkup(review, 'Create migrated copy')}
    </div>`;
}

function confirmReview() {
  const review = state.review;
  if (!review || reviewBlockers(review).length) return;
  const project = review.project;

  if (review.kind === 'migrate') {
    const subject = review.preflight.destinationName;
    // No retry offered: a second attempt would meet the copy the first one left behind.
    send('project.migrate', {
      dir: project.dir,
      enginePath: state.engine.current.path,
      targetEnginePath: state.engine.target.path,
    }).then((data) => startRun(data.runId, `Migrating ${project.name}`, subject, review.preflight.destinationDir))
      .catch((error) => setStatus(failure(error)));
    return;
  }

  send('project.update', { dir: project.dir, enginePath: state.engine.current.path })
    .then((data) => startRun(data.runId, `Updating ${project.name}`, project.name, project.dir,
      () => startUpdate(project)))
    .catch((error) => setStatus(failure(error)));
}

/* ============================ activity / run ============================ */

const LOG_LIMIT = 5000;

function startRun(runId, title, subject, folder, retry) {
  state.run = { runId, title, subject, folder, steps: [], lines: [], finished: null, logOpen: false, retry: retry || null };
  state.running = true;
  show('run');
}

function renderRun(page) {
  const run = state.run;
  if (!run) return showShelf();
  const finished = run.finished;
  const stateChip = !finished
    ? '<span class="chip neutral"><span class="dot"></span>In progress</span>'
    : (finished.ok
      ? '<span class="chip"><span class="dot"></span>Done</span>'
      : '<span class="chip danger"><span class="dot"></span>Failed</span>');

  page.innerHTML = `
    <div class="run-layout">
      <div class="title-row">
        <div>
          <h1>${esc(run.title)}</h1>
          ${finished ? '' : `<p class="intro" id="run-current">${esc(currentStepTitle(run) || 'Starting')}</p>`}
        </div>
        <span class="spacer"></span>
        ${stateChip}
      </div>
      ${finished ? '' : '<div class="progress" role="progressbar" aria-label="Working"></div>'}
      <ol class="steplist" id="run-steps"></ol>
      <div id="run-result"></div>
      <section class="log-section">
        <div class="log-head">
          <span class="section-label">TECHNICAL LOG</span>
          <button class="quiet" id="log-toggle" type="button" aria-expanded="${run.logOpen}" aria-controls="log-box">
            ${run.logOpen ? 'Hide technical log' : 'Show technical log'}
          </button>
          <span class="spacer"></span>
          <button class="quiet" id="log-copy" type="button">Copy</button>
          <button class="quiet" id="log-save" type="button">Save as…</button>
        </div>
        <div class="log-box" id="log-box" ${run.logOpen ? '' : 'hidden'}><pre id="log-text"></pre></div>
      </section>
    </div>`;

  $('#log-text').textContent = run.lines.join('\n') + (run.lines.length ? '\n' : '');
  scrollLogToEnd();
  renderRunSteps();
  if (finished) renderRunResult();

  on('#log-toggle', 'click', () => {
    state.run.logOpen = !state.run.logOpen;
    const box = $('#log-box');
    box.hidden = !state.run.logOpen;
    const toggle = $('#log-toggle');
    toggle.textContent = state.run.logOpen ? 'Hide technical log' : 'Show technical log';
    toggle.setAttribute('aria-expanded', String(state.run.logOpen));
    if (state.run.logOpen) scrollLogToEnd();
  });
  on('#log-copy', 'click', () => setStatus(copyText(run.lines.join('\n'))
    ? 'Technical log copied' : "Couldn't copy the log."));
  on('#log-save', 'click', () => send('log.save', { runId: run.runId })
    .then((data) => setStatus(data.path ? `Log saved to ${data.path.split(/[\\/]/).pop()}` : ''))
    .catch((error) => setStatus(failure(error))));
}

const currentStepTitle = (run) => {
  const active = run.steps.find((step) => step.state === 'active');
  return active ? active.title : '';
};

function renderRunSteps() {
  const host = $('#run-steps');
  if (!host || !state.run) return;
  host.innerHTML = state.run.steps.map((step) => `
    <li class="${esc(step.state)}"><span class="marker">${step.state === 'done' ? CHECK_SVG : ''}</span><span>${esc(step.title)}</span></li>`).join('');
}

function scrollLogToEnd() {
  const box = $('#log-box');
  if (box) box.scrollTop = box.scrollHeight;
}

function renderRunResult() {
  const run = state.run;
  const finished = run.finished;
  const host = $('#run-result');
  const openable = !!finished.folder;
  const launchable = !!finished.uproject;
  // A compile failure leaves a project that is set up and only needs building again, so it
  // gets its own wording and a retry that skips the download the whole flow would redo.
  const rebuild = finished.rebuild || null;

  host.innerHTML = finished.ok ? `
    <div class="result ok">
      <h2>${esc(finished.subject || run.subject)} is ready.</h2>
      ${finished.notes ? `
        <button class="quiet flat-left" id="notes-toggle" type="button" aria-expanded="false" style="margin-top:10px">What changed</button>
        <div class="details-box" id="notes-box" hidden><pre>${esc(finished.notes)}</pre></div>` : ''}
    </div>
    <div class="page-actions">
      ${launchable ? '<button class="primary tall" id="open-project" type="button">Open project</button>' : ''}
      ${openable ? `<button class="${launchable ? '' : 'primary'} tall" id="open-folder" type="button">Open project folder</button>` : ''}
      <button class="${launchable || openable ? '' : 'primary'} tall" id="back-to-projects" type="button">Back to projects</button>
      ${openable ? '' : '<span class="helper">The project folder is no longer there.</span>'}
    </div>` : `
    <div class="result fail">
      <h2>${rebuild
        ? `${esc(finished.subject || run.subject)} did not compile.`
        : `${esc(finished.subject || run.subject)} was not completed.`}</h2>
      <p>${esc(finished.error || 'The run stopped before it finished.')}</p>
      ${rebuild ? '<p class="helper">Everything else is in place. Compiling again is all that is left.</p>' : ''}
      <button class="quiet flat-left" id="show-log" type="button" style="margin-top:10px">View technical details</button>
    </div>
    <div class="page-actions">
      ${rebuild ? '<button class="primary tall" id="run-rebuild" type="button">Retry compilation</button>' : ''}
      ${run.retry && !rebuild ? '<button class="primary tall" id="run-retry" type="button">Try again</button>' : ''}
      <button class="${run.retry || rebuild ? '' : 'primary'} tall" id="back-to-projects" type="button">Back to projects</button>
    </div>`;

  on('#notes-toggle', 'click', (event) => {
    const box = $('#notes-box');
    box.hidden = !box.hidden;
    event.currentTarget.setAttribute('aria-expanded', String(!box.hidden));
    event.currentTarget.textContent = box.hidden ? 'What changed' : 'Hide what changed';
  });
  on('#open-project', 'click', () => send('path.open', { path: finished.uproject }).catch((error) => setStatus(failure(error))));
  on('#open-folder', 'click', () => send('path.open', { path: finished.folder }).catch((error) => setStatus(failure(error))));
  on('#back-to-projects', 'click', () => showShelf(finished.folder || run.folder));
  on('#run-retry', 'click', () => { const retry = run.retry; state.run = null; retry(); });
  on('#run-rebuild', 'click', () => {
    const subject = finished.subject || run.subject;
    send('project.rebuild', rebuild)
      .then((data) => startRun(data.runId, `Compiling ${subject}`, subject, rebuild.folder))
      .catch((error) => setStatus(failure(error)));
  });
  on('#show-log', 'click', () => {
    state.run.logOpen = true;
    $('#log-box').hidden = false;
    const toggle = $('#log-toggle');
    toggle.textContent = 'Hide technical log';
    toggle.setAttribute('aria-expanded', 'true');
    scrollLogToEnd();
  });

  const primary = $('#open-project') || $('#open-folder') || $('#run-rebuild')
    || $('#run-retry') || $('#back-to-projects');
  if (primary) { primary.focus(); state.primary = () => primary.click(); }
}

bus.on('log', (data) => {
  const run = state.run;
  if (!run || data.runId !== run.runId) return;
  run.lines.push(data.line);
  if (run.lines.length > LOG_LIMIT) run.lines.splice(0, run.lines.length - LOG_LIMIT);
  const box = $('#log-box');
  const text = $('#log-text');
  if (!box || !text) return;
  // Follow the tail only when the user is already there; otherwise they are reading
  // something further up and a jump would lose their place.
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 8;
  text.appendChild(document.createTextNode(data.line + '\n'));
  if (atBottom) scrollLogToEnd();
});

bus.on('steps', (data) => {
  const run = state.run;
  if (!run || data.runId !== run.runId) return;
  run.steps = data.steps || [];
  renderRunSteps();
  const current = $('#run-current');
  if (current && !run.finished) current.textContent = currentStepTitle(run) || 'Working';
});

bus.on('runFinished', (data) => {
  const run = state.run;
  if (!run || data.runId !== run.runId) return;
  run.finished = data;
  if (data.ok) run.steps = run.steps.map((step) => ({ ...step, state: 'done' }));
  state.running = false;
  if (state.screen === 'run') render();
});

/* ============================ account ============================ */

bus.on('accountChanged', (data) => {
  state.account = data.account || state.account;
  renderChrome();
  if (state.screen === 'shelf') renderShelf($('#page'));
  else if (state.screen === 'newProject') renderNewProject($('#page'));
});

/* Gate a protected action behind sign-in. True means go ahead now; otherwise the modal
   is open and `resume` runs once sign-in succeeds, so no entered value is lost. */
function requireAccount(resume) {
  if (state.account.signedIn) return true;
  openSignIn(resume);
  return false;
}

function openSignIn(resume) {
  state.signIn = { view: 'choice', status: '', tone: '', busy: false, error: '', resume: resume || null };
  renderOverlay();
}

function closeSignIn() {
  state.signIn = null;
  renderOverlay();
}

function signInSucceeded(data) {
  const resume = state.signIn && state.signIn.resume;
  state.account = data.account || state.account;
  state.signIn = null;
  renderOverlay();
  renderChrome();
  if (resume) resume();
  else render();
}

function renderSignIn(host) {
  const modal = state.signIn;
  const body = modal.view === 'choice' ? `
      <h2>Sign in to Convai</h2>
      <p class="intro">Connect once to create, update, and manage projects.</p>
      <button class="google" id="google-signin" type="button" ${modal.busy ? 'disabled' : ''}>
        <span class="google-mark" aria-hidden="true">G</span>Continue with Google
      </button>
      <div class="modal-divider">or</div>
      <button style="width:100%" class="tall" id="show-api" type="button" ${modal.busy ? 'disabled' : ''}>Use an API key instead</button>
      <p class="modal-status ${modal.tone}" role="status">${esc(modal.status)}</p>
      <div class="modal-foot">
        <button class="quiet" id="signin-later" type="button">Not now</button>
        <button class="quiet" id="signin-dashboard" type="button">Open Convai dashboard</button>
      </div>` : `
      <button class="quiet flat-left" id="signin-back" type="button">&larr; Back</button>
      <h2>Sign in with an API key</h2>
      <p class="intro">For existing users who prefer to connect with a key.</p>
      <div class="api-form">
        <input id="api-key" type="password" autocomplete="off" placeholder="Paste your Convai API key" aria-label="Convai API key"
               aria-describedby="api-error" ${modal.busy ? 'disabled' : ''}>
        <button class="primary tall" id="api-signin" type="button" ${modal.busy ? 'disabled' : ''}>${modal.busy ? 'Verifying…' : 'Sign in'}</button>
      </div>
      <p class="modal-status danger" id="api-error" role="alert">${esc(modal.error)}</p>
      <p class="privacy">Your key is stored on this computer only, for this tool. It never appears in project screens or logs.</p>
      <div class="modal-foot">
        <button class="quiet" id="signin-later" type="button">Not now</button>
        <button class="quiet" id="signin-dashboard" type="button">Open Convai dashboard</button>
      </div>`;

  host.innerHTML = `<div class="modal-layer"><section class="modal" role="dialog" aria-modal="true" aria-label="Sign in to Convai">${body}</section></div>`;

  on('#signin-later', 'click', closeSignIn);
  on('#signin-dashboard', 'click', () => send('account.dashboard').catch((error) => setStatus(failure(error))));
  on('#show-api', 'click', () => { state.signIn.view = 'key'; renderOverlay(); });
  on('#signin-back', 'click', () => { state.signIn.view = 'choice'; state.signIn.error = ''; renderOverlay(); });

  on('#google-signin', 'click', () => {
    state.signIn.busy = true;
    state.signIn.tone = '';
    state.signIn.status = 'Opening your browser… complete the sign-in there, then come back.';
    renderOverlay();
    send('account.signInGoogle').then(signInSucceeded).catch((error) => {
      if (!state.signIn) return;
      state.signIn.busy = false;
      state.signIn.tone = 'danger';
      state.signIn.status = failure(error);
      renderOverlay();
    });
  });

  const submitKey = () => {
    const field = $('#api-key');
    const key = field.value.trim();
    if (!key) {
      state.signIn.error = 'Enter your Convai API key.';
      renderOverlay();
      return;
    }
    state.signIn.busy = true;
    state.signIn.error = '';
    state.signIn.key = key;
    renderOverlay();
    send('account.signInKey', { key }).then(signInSucceeded).catch((error) => {
      if (!state.signIn) return;
      state.signIn.busy = false;
      state.signIn.error = failure(error);
      renderOverlay();
    });
  };
  on('#api-signin', 'click', submitKey);
  const key = $('#api-key');
  if (key) {
    // The value survives a failed attempt, still masked, with the field focused.
    key.value = state.signIn.key || '';
    key.addEventListener('keydown', (event) => { if (event.key === 'Enter') submitKey(); });
    if (!modal.busy) key.focus();
  } else {
    const google = $('#google-signin');
    if (google && !modal.busy) google.focus();
  }
}

function renderAccountMenu(host) {
  const account = state.account;
  const anchor = $('#account-button').getBoundingClientRect();
  const menu = document.createElement('aside');
  menu.className = 'account-menu';
  menu.setAttribute('aria-label', 'Convai account menu');
  menu.innerHTML = `
    <div class="identity">
      <strong>${esc(account.name || account.email || 'Convai account')}</strong>
      ${account.email ? `<span>${esc(account.email)}</span>` : ''}
    </div>
    <button type="button" id="menu-dashboard">Open Convai dashboard</button>
    <button type="button" id="menu-switch">Switch account</button>
    <button type="button" id="menu-logout">Log out</button>`;
  host.appendChild(menu);
  menu.style.top = `${Math.round(anchor.bottom + 6)}px`;
  menu.style.left = `${Math.max(8, Math.round(anchor.right - menu.offsetWidth))}px`;

  on('#menu-dashboard', 'click', () => { closeMenu(); send('account.dashboard').catch((error) => setStatus(failure(error))); });
  // Sign out only once a replacement sign-in succeeds, or a cancelled modal leaves the
  // user signed out of the account they still had.
  on('#menu-switch', 'click', () => { closeMenu(); openSignIn(); });
  on('#menu-logout', 'click', () => {
    closeMenu();
    send('account.signOut').then((data) => {
      state.account = data.account || { signedIn: false, name: null, email: '' };
      renderChrome();
      showShelf();
    }).catch((error) => setStatus(failure(error)));
  });
  $('#menu-dashboard').focus();
}

const closeMenu = () => { state.menuOpen = false; renderOverlay(); };

/* ============================ settings ============================ */

function openSettings() {
  state.settings = { packaging: null, toolchain: '', toolchainTone: '', busy: false, updates: '', updatesTone: '', outdated: false, checking: false };
  renderOverlay();
  loadEngine().then(() => renderOverlay());
  send('packaging.status').then((data) => {
    if (!state.settings) return;
    state.settings.packaging = data;
    renderOverlay();
  }).catch((error) => {
    if (!state.settings) return;
    state.settings.toolchain = failure(error);
    state.settings.toolchainTone = 'danger';
    renderOverlay();
  });
}

const closeSettings = () => { state.settings = null; renderOverlay(); };

function settingsEngineRow(versionType) {
  const engine = state.engine[versionType];
  if (!engine) return '';
  const ready = !!engine.ready;
  return `
    <div class="setting-row">
      <div>
        <div class="head">
          <strong>Unreal Engine ${esc(engine.version)}</strong>
          <span class="chip ${ready ? '' : 'warn'}"><span class="dot"></span>${ready ? 'Ready' : 'Not found'}</span>
        </div>
        <span class="status ${ready ? 'ready' : 'warn'}">${ready ? `Ready · ${esc(engine.path)}` : esc(engine.reason || 'This installation was not found.')}</span>
      </div>
      <button type="button" data-choose="${esc(versionType)}">Choose folder</button>
    </div>`;
}

function renderSettings(host) {
  const settings = state.settings;
  const packaging = settings.packaging;
  host.innerHTML = `
    <div class="modal-layer">
      <section class="modal wide" role="dialog" aria-modal="true" aria-label="Settings">
        <div class="title-row" style="margin-bottom:18px">
          <div>
            <h2 style="font-size:22px">Settings</h2>
            <p class="intro">Configure the local tools your projects are built with.</p>
          </div>
          <span class="spacer"></span>
          <button id="close-settings" type="button">Close</button>
        </div>

        <section class="panel setting-panel">
          <h2>Unreal Engine</h2>
          <p>Used when creating, updating and migrating projects.</p>
          ${settingsEngineRow('current')}
          ${state.engine.sameVersion ? '' : settingsEngineRow('target')}
        </section>

        <section class="panel setting-panel">
          <h2>Packaging</h2>
          <p>Only needed when an asset uploader packages projects for Linux.</p>
          <div class="setting-row">
            <div>
              <strong>${packaging ? `Linux packaging is ${packaging.linuxEnabled ? 'on' : 'off'}` : 'Linux packaging'}</strong>
              <span class="status ${esc(settings.toolchainTone)}">${esc(settings.toolchain || (packaging
                ? (packaging.linuxEnabled
                  ? `Packaging builds a Linux target, which needs the cross-compilation toolchain for UE ${packaging.engineVersion}.`
                  : 'The Linux toolchain is not needed unless packaging is turned on.')
                : 'Reading the packaging configuration…'))}</span>
            </div>
            <button type="button" id="install-toolchain" ${settings.busy ? 'disabled' : ''}>Install Linux toolchain</button>
          </div>
        </section>

        <section class="panel setting-panel">
          <h2>About</h2>
          <div class="setting-row">
            <div>
              <strong>Convai Modding Tool ${state.version ? 'v' + esc(state.version) : ''}</strong>
              <span class="status ${esc(settings.updatesTone)}">${esc(settings.updates || 'Updates are checked each time the tool starts.')}</span>
            </div>
            ${settings.outdated ? '<button type="button" id="download-update">Download</button>' : ''}
            <button class="quiet" type="button" id="check-updates" ${settings.checking ? 'disabled' : ''}>${settings.checking ? 'Checking…' : 'Check for updates'}</button>
          </div>
        </section>
      </section>
    </div>`;

  on('#close-settings', 'click', closeSettings);
  $$('[data-choose]', host).forEach((button) => button.addEventListener('click', () => {
    chooseEngine(button.dataset.choose).then(() => {
      renderOverlay();
      if (state.screen === 'shelf') renderShelfBody();
      if (state.screen === 'review') render();
    });
  }));

  on('#install-toolchain', 'click', () => {
    state.settings.busy = true;
    state.settings.toolchain = 'Installing, this can take several minutes…';
    state.settings.toolchainTone = '';
    renderOverlay();
    send('toolchain.install').catch((error) => {
      if (!state.settings) return;
      state.settings.busy = false;
      state.settings.toolchain = failure(error);
      state.settings.toolchainTone = 'danger';
      renderOverlay();
    });
  });

  on('#check-updates', 'click', () => {
    state.settings.checking = true;
    state.settings.updates = 'Checking…';
    state.settings.updatesTone = '';
    state.settings.outdated = false;
    renderOverlay();
    send('updates.check').then((data) => {
      if (!state.settings) return;
      state.settings.checking = false;
      if (data.upToDate === null) {
        // The check failed rather than answered; offering a download would send the user
        // off to fix a problem they may not have.
        Object.assign(state.settings, { updates: "Couldn't check for updates. Try again.", updatesTone: 'danger', outdated: false });
      } else if (data.upToDate) {
        Object.assign(state.settings, { updates: 'This is the latest version.', updatesTone: 'ready', outdated: false });
      } else {
        Object.assign(state.settings, {
          updates: `A newer version is available${data.latest ? ` (v${data.latest})` : ''}.`,
          updatesTone: 'warn', outdated: true,
        });
      }
      renderOverlay();
    }).catch((error) => {
      if (!state.settings) return;
      state.settings.checking = false;
      Object.assign(state.settings, { updates: failure(error), updatesTone: 'danger' });
      renderOverlay();
    });
  });

  on('#download-update', 'click', () => send('updates.download').catch((error) => setStatus(failure(error))));
  $('#close-settings').focus();
}

bus.on('toolchain', (data) => {
  if (!state.settings) return;
  state.settings.busy = data.state === 'installing';
  state.settings.toolchain = data.message || '';
  state.settings.toolchainTone = data.state === 'failed' ? 'danger' : (data.state === 'done' ? 'ready' : '');
  renderOverlay();
});

/* ============================ overlays ============================ */

function renderOverlay() {
  const host = $('#overlay');
  host.innerHTML = '';
  if (state.signIn) return renderSignIn(host);
  if (state.settings) return renderSettings(host);
  if (state.menuOpen) return renderAccountMenu(host);
}

/* ============================ keyboard and chrome wiring ============================ */

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if (state.signIn) return closeSignIn();
    if (state.settings) return closeSettings();
    if (state.menuOpen) return closeMenu();
    if (state.escape && !state.running) state.escape();
    return;
  }

  if (event.key.toLowerCase() === 'n' && (event.ctrlKey || event.metaKey)) {
    if (state.screen === 'shelf' && !state.running && !state.signIn && !state.settings) {
      event.preventDefault();
      openNewProject();
    }
    return;
  }

  if (event.key === 'Enter' && state.primary && !state.signIn && !state.settings && !state.menuOpen) {
    const target = event.target;
    const tag = target && target.tagName;
    // Buttons and links handle their own Enter; a field's own handler has already run.
    if (tag === 'BUTTON' || tag === 'A' || tag === 'TEXTAREA') return;
    if (tag === 'INPUT' && target.type !== 'search') return;
    state.primary();
    return;
  }

  if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && state.screen === 'shelf'
      && !state.signIn && !state.settings && !state.menuOpen) {
    const tag = event.target && event.target.tagName;
    if (tag === 'INPUT') return;   // the search box moves the selection through its own handler
    event.preventDefault();
    moveSelection(event.key === 'ArrowDown' ? 1 : -1, true);
  }
});

// A click outside the account menu closes it.
document.addEventListener('mousedown', (event) => {
  if (!state.menuOpen) return;
  if (event.target.closest('.account-menu') || event.target.closest('#account-button')) return;
  closeMenu();
});

$('#home-button').addEventListener('click', () => { if (state.ready && !state.running) showShelf(); });
$('#settings-button').addEventListener('click', () => { if (!state.running) openSettings(); });
$('#account-button').addEventListener('click', () => {
  if (state.running) return;
  if (state.account.signedIn) { state.menuOpen = !state.menuOpen; renderOverlay(); }
  else openSignIn();
});

/* Opened straight from disk for design work, `#screen=<name>` jumps past boot to one
   screen on the demo transport's data -- also how the screens get screenshotted. It is
   inert under the host, where there is a real boot to run. */
function startFromHash() {
  const wanted = (location.hash.match(/screen=([a-zA-Z]+)/) || [])[1];
  if (!wanted || !screens[wanted]) return false;
  state.ready = true;
  state.version = '3.0.6';
  Promise.all([send('account.status'), send('projects.list'), send('engine.status')])
    .then(([account, projects, engine]) => {
      Object.assign(state, { account: account.account, projects: projects.projects, engine });
      state.selected = state.projects[0] || null;
      if (wanted === 'review') state.review = { kind: 'migrate', project: state.selected };
      if (wanted === 'run') {
        state.run = { runId: 'demo', title: `Updating ${state.selected.name}`, subject: state.selected.name,
                      steps: [], lines: [], finished: null };
      }
      show(wanted);
    });
  return true;
}

if (!(window.pywebview && window.pywebview.api) && startFromHash()) {
  // the hash took over
} else {
  startBoot();
}
