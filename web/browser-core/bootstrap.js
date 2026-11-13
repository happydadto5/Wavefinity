// Deferred scripts execute in order; initialization itself is shared by all callers.
window.WFBrowserCore = { init: () => window.WFLocalAPI.init() };
