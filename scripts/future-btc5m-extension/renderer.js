// Loaded only after the operator approves the manifest's debugger permission.
// One fixed visibility/focus command; never reads cookies, screenshots or page content,
// evaluates scripts, sends input, or submits orders.
(() => {
  const leases = new Map();
  const tabPorts = new Map();
  const stoppedTabs = new Set();
  const pendingChecks = new Map();
  const command = (tabId, enabled) => chrome.debugger.sendCommand({tabId},
    'Emulation.setFocusEmulationEnabled', {enabled});
  const announce = (lease, state) => {
    for (const port of lease.ports) {
      try { port.postMessage({type: 'FUTURE_BTC5M_RENDERER_STATUS', state}); } catch {}
    }
  };

  function release(lease) {
    if (lease.done) return lease.done;
    lease.disposed = true;
    lease.done = (async () => {
      await lease.setup;
      if (lease.attached) {
        if (lease.focusRequested) {
          try { await command(lease.tabId, false); } catch {}
        }
        try { await chrome.debugger.detach({tabId: lease.tabId}); } catch {}
        lease.attached = false;
      }
      if (leases.get(lease.tabId) === lease && !tabPorts.has(lease.tabId)) leases.delete(lease.tabId);
    })();
    return lease.done;
  }

  async function begin(lease, previousCleanup) {
    if (previousCleanup) await previousCleanup;
    if (lease.disposed) return;
    try {
      await chrome.debugger.attach({tabId: lease.tabId}, '1.3');
      lease.attached = true;
      if (lease.disposed) return;
      lease.focusRequested = true;
      await command(lease.tabId, true);
      if (!lease.disposed) {
        lease.active = true;
        announce(lease, 'ACTIVE');
      }
    } catch {
      if (!lease.disposed) announce(lease, 'ERROR');
      // Do not detach a target when attach failed: another debugger may own it.
      void release(lease);
    }
  }

  function ensureLease(tabId) {
    const ports = tabPorts.get(tabId);
    if (!ports?.size) return;
    if (stoppedTabs.has(tabId)) {
      announce({ports}, 'STOPPED');
      return;
    }
    let lease = leases.get(tabId);
    if (!lease || lease.disposed) {
      const previousCleanup = lease?.done;
      lease = {tabId, ports, attached: false, disposed: false, active: false, focusRequested: false};
      leases.set(tabId, lease);
      lease.setup = begin(lease, previousCleanup);
    }
    return lease;
  }

  chrome.runtime.onConnect.addListener((port) => {
    const sender = port.sender;
    const tabId = sender?.tab?.id;
    if (port.name !== 'FUTURE_BTC5M_RUNTIME' || sender?.frameId !== 0 ||
        !Number.isSafeInteger(tabId) || tabId < 0 || !marketPage(sender.url) ||
        !marketPage(sender.tab.url ?? sender.url)) return;
    const ports = tabPorts.get(tabId) ?? new Set();
    tabPorts.set(tabId, ports);
    ports.add(port);
    const lease = ensureLease(tabId);
    if (lease?.active) port.postMessage({type: 'FUTURE_BTC5M_RENDERER_STATUS', state: 'ACTIVE'});
    port.onMessage.addListener((message) => {
      const checkedAt = pendingChecks.get(port);
      if (checkedAt === undefined || !message || Object.keys(message).length !== 3 ||
          message.type !== 'FUTURE_BTC5M_RENDERER_PAGE' || message.checkedAt !== checkedAt ||
          !Number.isFinite(checkedAt) || Math.abs(Date.now() / 1000 - checkedAt) > 3 ||
          !tabPorts.get(tabId)?.has(port) || stoppedTabs.has(tabId)) return;
      const page = marketPage(message.marketUrl);
      if (!page || message.marketUrl !== page.origin + page.pathname) return;
      pendingChecks.delete(port);
      ensureLease(tabId);
    });
    port.onDisconnect.addListener(() => {
      pendingChecks.delete(port);
      ports.delete(port);
      if (!ports.size && tabPorts.get(tabId) === ports) {
        tabPorts.delete(tabId);
        const current = leases.get(tabId);
        if (current) void release(current);
      }
    });
  });

  chrome.debugger.onDetach.addListener(({tabId}, reason) => {
    const lease = leases.get(tabId);
    if (!lease || lease.disposed) return;
    console.warn('FUTURE_BTC5M_RENDERER_DETACHED:' +
      (reason === 'canceled_by_user' ? 'CANCELED_BY_USER' : 'TARGET_CLOSED'));
    lease.attached = false;
    stoppedTabs.add(tabId);
    announce(lease, 'STOPPED');
    void release(lease);
  });
  chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
    const lease = leases.get(tabId);
    // Release on loading before any cross-origin document commits, even if its
    // URL is hidden by Chrome's host-permission rules. New trusted ports may reacquire.
    if (change.status === 'loading' || change.url && !marketPage(change.url)) {
      for (const port of tabPorts.get(tabId) ?? []) pendingChecks.delete(port);
      if (lease) {
        announce(lease, 'STOPPED');
        void release(lease);
      }
    }
    // An SPA or the initial load can report loading without replacing the content
    // port. Reacquire only after Chrome confirms a trusted current market URL.
    if (change.status === 'complete') {
      if (tab?.url !== undefined) {
        if (marketPage(tab.url)) ensureLease(tabId);
      } else if (!stoppedTabs.has(tabId)) {
        // Chrome can omit tab.url without host access. Ask only the already
        // trusted live content port for its current public origin/path.
        for (const port of tabPorts.get(tabId) ?? []) {
          const checkedAt = Date.now() / 1000;
          pendingChecks.set(port, checkedAt);
          try { port.postMessage({type: 'FUTURE_BTC5M_RENDERER_CHECK', checkedAt}); }
          catch { pendingChecks.delete(port); }
        }
      }
    }
  });
  chrome.tabs.onRemoved.addListener((tabId) => {
    const lease = leases.get(tabId);
    if (lease) void release(lease);
    for (const port of tabPorts.get(tabId) ?? []) pendingChecks.delete(port);
    tabPorts.delete(tabId);
    stoppedTabs.delete(tabId);
  });
})();
