"use strict";

// Claim the first launch in the same browser store used for remembered state.
// An existing database belongs to a visitor who has already launched the app.
(() => {
  let isNew = false;
  let hasOlderState;
  try { hasOlderState = Object.keys(localStorage).some(key => /^wavefinity[.-]/i.test(key)); }
  catch (_error) { return; }
  let request;
  try { request = indexedDB.open("wavefinity-browser-files", 1); }
  catch (_error) { return; }
  request.onupgradeneeded = () => {
    isNew = true;
    request.result.createObjectStore("spaces");
  };
  request.onsuccess = () => {
    const database = request.result;
    try {
      const transaction = database.transaction("spaces", "readwrite");
      transaction.objectStore("spaces").put(true, "first-launch-seen");
      transaction.oncomplete = () => {
        database.close();
        const cover = document.getElementById("startup-cover");
        if (!isNew || !cover || cover.hidden) return;
        // Older versions may have stored state before the database existed.
        if (hasOlderState) return;
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
          card.querySelector(".startup-logo").hidden = true;
          card.querySelector("p").textContent = "Loading...";
          video.hidden = false;
          const observer = new MutationObserver(() => {
            if (cover.hidden) { video.pause(); observer.disconnect(); }
          });
          observer.observe(cover, { attributes: true, attributeFilter: ["hidden"] });
        }).catch(showFallback);
      };
      transaction.onerror = transaction.onabort = () => database.close();
    } catch (_error) { database.close(); }
  };
})();
