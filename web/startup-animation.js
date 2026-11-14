"use strict";

// Show the welcome animation exactly once per browser, on the first launch
// that actually gets to play it. A separate flag keeps it independent of any
// older saved state, so an existing user still sees it one time.
(() => {
  const SEEN_KEY = "wavefinity-welcome-animation-seen";
  try { if (localStorage.getItem(SEEN_KEY)) return; }
  catch (_error) { return; }
  const cover = document.getElementById("startup-cover");
  if (!cover || cover.hidden) return;
  const card = cover.querySelector(".startup-cover-card");
  const video = document.createElement("video");
  video.className = "startup-animation";
  video.src = "/images/Welcome%20Animation.mp4";
  video.muted = true;
  video.loop = true;
  video.playsInline = true;
  video.hidden = true;
  const showFallback = () => {
    video.pause();
    video.remove();
    card.querySelector(".startup-logo").hidden = false;
    card.querySelector("p").textContent = "Opening Wavefinity…";
  };
  video.addEventListener("error", showFallback, { once: true });
  card.prepend(video);
  const playback = video.play();
  if (playback) playback.then(() => {
    if (cover.hidden) { video.pause(); return; }
    try { localStorage.setItem(SEEN_KEY, "1"); } catch (_error) { /* storage unavailable */ }
    card.querySelector(".startup-logo").hidden = true;
    card.querySelector("p").textContent = "Loading...";
    video.hidden = false;
    const observer = new MutationObserver(() => {
      if (cover.hidden) { video.pause(); observer.disconnect(); }
    });
    observer.observe(cover, { attributes: true, attributeFilter: ["hidden"] });
  }).catch(showFallback);
})();
