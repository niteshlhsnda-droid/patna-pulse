/* Patna Pulse — light-theme renderer with thumbnails + story detail view.
   Reads data.json with `brief` and `image`. */
(function () {
  "use strict";

  var TYPE_ICONS = { news: "📰", facebook: "📘", instagram: "📸", youtube: "▶️", x: "𝕏", threads: "🧵" };
  var TYPE_LABELS = { news: "News site", facebook: "Facebook", instagram: "Instagram", youtube: "YouTube", x: "X", threads: "Threads" };
  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  var GENUINE_EXPLAIN = {
    verified: "Reported by 3 or more independent outlets. Corroboration means multiple outlets reported it — it is not proof the story is true.",
    corroborated: "Reported by 2 independent outlets. Corroboration means multiple outlets reported it — it is not proof the story is true.",
    single: "Reported by a single outlet so far — treat with caution. Always open the source link and judge for yourself."
  };

  var state = { q: "", topic: "all", badge: "all", data: null, byId: {} };

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];
    });
  }

  /* Strip a trailing " - Outlet" / " | Outlet" suffix when it names a known
     outlet (keeps display headlines clean). ALL_OUTLETS is built from the
     full dataset once data.json loads. */
  var ALL_OUTLETS = {};
  function normOutlet(o) { return String(o || "").trim().toLowerCase().replace(/^the\s+/, ""); }
  function cleanHeadline(headline) {
    var h = String(headline || "").trim();
    function stripTail() {
      var m = /\s+[|\-–—]\s+(.{1,60})$/.exec(h);
      if (!m) return false;
      var tail = normOutlet(m[1]).replace(/^facebook\s*\(|\)$/g, "");
      for (var o in ALL_OUTLETS) {
        if (tail === o || o.indexOf(tail) >= 0 || tail.indexOf(o) >= 0) {
          h = h.slice(0, m.index).trim();
          return true;
        }
      }
      return false;
    }
    while (stripTail()) {}
    return h;
  }

  /* De-duplicate the source list by outlet (keep first link per outlet). */
  function uniqSources(story) {
    var seen = {}, out = [];
    ((story && story.sources) || []).forEach(function (s) {
      var k = String(s.outlet || "").trim().toLowerCase();
      if (!k || seen[k]) return;
      seen[k] = true;
      out.push(s);
    });
    return out;
  }

  function fmtDate(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return esc(iso || "");
    return parseInt(m[3], 10) + " " + MONTHS[parseInt(m[2], 10) - 1] + " " + m[1];
  }

  function badgeHtml(g) {
    var label = g === "verified" ? "✓ Verified"
      : g === "corroborated" ? "◐ Corroborated" : "○ Single source";
    return '<span class="badge b-' + esc(g) + '">' + label + "</span>";
  }

  function metaHtml(story) {
    var n = uniqSources(story).length;
    return '<span class="card-date">' + fmtDate(story.date) + "</span>" +
      '<span class="card-date">' + n + " outlet" + (n === 1 ? "" : "s") + "</span>";
  }

  function topicsHtml(story) {
    return (story.topics || []).map(function (t) {
      return '<span class="topic">' + esc(t) + "</span>";
    }).join("");
  }

  function thumbHtml(story, cls) {
    if (!story.image) return "";
    var alt = esc(cleanHeadline(story.headline));
    return '<div class="' + cls + '"><img src="' + esc(story.image) +
      '" alt="' + alt + '" loading="lazy"></div>';
  }

  function sourcesHtml(story) {
    var srcs = uniqSources(story);
    var items = srcs.map(function (s) {
      var icon = TYPE_ICONS[s.type] || "🔗";
      return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
        icon + " " + esc(s.outlet) + "</a></li>";
    }).join("");
    return '<div class="card-sources"><div class="sources-label">Sources</div>' +
      '<ul class="source-list">' + items + "</ul></div>";
  }

  function cardHtml(story) {
    return '<article class="card" data-story="' + esc(story.id) + '" tabindex="0" role="button" aria-label="Read full story: ' + esc(cleanHeadline(story.headline)) + '">' +
      thumbHtml(story, "card-thumb") +
      '<div class="card-top">' + badgeHtml(story.genuineness) +
      '<div style="display:flex;gap:10px">' + metaHtml(story) + "</div></div>" +
      "<h3>" + esc(cleanHeadline(story.headline)) + "</h3>" +
      (story.brief ? '<p class="card-brief">' + esc(story.brief) + "</p>" : "") +
      (story.topics && story.topics.length ? '<div class="card-topics">' + topicsHtml(story) + "</div>" : "") +
      '<div class="read-more">Read full story →</div>' +
      "</article>";
  }

  function leadHtml(story) {
    return '<article class="lead-card" data-story="' + esc(story.id) + '" tabindex="0" role="button" aria-label="Read full story: ' + esc(cleanHeadline(story.headline)) + '">' +
      '<div class="lead-kicker">Top story</div>' +
      '<div class="lead-grid">' +
      thumbHtml(story, "lead-thumb") +
      '<div class="lead-body">' +
      '<div class="card-top" style="margin-bottom:10px">' + badgeHtml(story.genuineness) +
      '<div style="display:flex;gap:10px">' + metaHtml(story) + "</div></div>" +
      "<h2>" + esc(cleanHeadline(story.headline)) + "</h2>" +
      (story.brief ? '<p class="lead-brief">' + esc(story.brief) + "</p>" : "") +
      (story.topics && story.topics.length ? '<div class="card-topics" style="margin-bottom:10px">' + topicsHtml(story) + "</div>" : "") +
      '<div class="read-more">Read full story →</div>' +
      "</div></div></article>";
  }

  function detailHtml(story) {
    var srcs = uniqSources(story);
    var items = srcs.map(function (s) {
      var icon = TYPE_ICONS[s.type] || "🔗";
      var typeLabel = TYPE_LABELS[s.type] || "Link";
      return '<li><span class="src-type" title="' + esc(typeLabel) + '">' + icon + "</span> " +
        '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.outlet) + "</a></li>";
    }).join("");
    var imgCredit = "";
    if (story.image) {
      if (story.image_kind === "placeholder") {
        imgCredit = '<p class="img-credit">🎨 Illustrative graphic — the real story photos are at the source links below.</p>';
      } else if (story.image_credit) {
        var firstUrl = (srcs[0] && srcs[0].url) || "#";
        imgCredit = '<p class="img-credit">📷 Thumbnail: ' + esc(story.image_credit) +
          ' — <a href="' + esc(firstUrl) + '" target="_blank" rel="noopener">see the original article</a></p>';
      }
    }
    return '<div class="modal-backdrop" id="modal-backdrop">' +
      '<div class="modal" role="dialog" aria-modal="true" aria-label="' + esc(cleanHeadline(story.headline)) + '">' +
      '<button class="modal-close" id="modal-close" aria-label="Close">✕</button>' +
      thumbHtml(story, "modal-thumb") + imgCredit +
      '<div class="modal-top">' + badgeHtml(story.genuineness) +
      '<div style="display:flex;gap:10px">' + metaHtml(story) + "</div></div>" +
      "<h2>" + esc(cleanHeadline(story.headline)) + "</h2>" +
      '<p class="genuine-note">' + esc(GENUINE_EXPLAIN[story.genuineness] || "") + "</p>" +
      (story.topics && story.topics.length ? '<div class="card-topics">' + topicsHtml(story) + "</div>" : "") +
      (story.summary ? '<p class="modal-summary">' + esc(story.summary) + "</p>" : "") +
      (story.brief && story.brief !== story.summary ? '<p class="modal-brief"><strong>In brief:</strong> ' + esc(story.brief) + "</p>" : "") +
      '<div class="modal-sources"><div class="sources-label">All sources (' + srcs.length + ")</div>" +
      '<ul class="source-list modal-source-list">' + items + "</ul></div>" +
      '<p class="modal-fine">News belongs to its publishers — open the source links and judge for yourself.</p>' +
      "</div></div>";
  }

  function openStory(id) {
    var story = state.byId[id];
    if (!story) return;
    var root = document.getElementById("modal-root");
    root.innerHTML = detailHtml(story);
    document.body.style.overflow = "hidden";
    document.getElementById("modal-close").addEventListener("click", closeStory);
    document.getElementById("modal-backdrop").addEventListener("click", function (e) {
      if (e.target.id === "modal-backdrop") closeStory();
    });
    document.addEventListener("keydown", escHandler);
    if (history.replaceState) history.replaceState(null, "", "#story=" + encodeURIComponent(id));
  }

  function closeStory() {
    document.getElementById("modal-root").innerHTML = "";
    document.body.style.overflow = "";
    document.removeEventListener("keydown", escHandler);
    if (history.replaceState) history.replaceState(null, "", location.pathname + location.search);
  }

  function escHandler(e) {
    if (e.key === "Escape") closeStory();
  }

  function bindCardClicks(scope) {
    var els = scope.querySelectorAll ? scope.querySelectorAll("[data-story]") : [];
    els.forEach(function (el) {
      el.addEventListener("click", function (e) {
        if (e.target.closest("a")) return;  // let source links work
        openStory(el.getAttribute("data-story"));
      });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openStory(el.getAttribute("data-story")); }
      });
    });
  }

  function matches(story) {
    if (state.badge !== "all" && story.genuineness !== state.badge) return false;
    if (state.topic !== "all" && (story.topics || []).indexOf(state.topic) < 0) return false;
    if (state.q) {
      var hay = (story.headline + " " + (story.brief || "") + " " + (story.summary || "")).toLowerCase();
      if (hay.indexOf(state.q) < 0) return false;
    }
    return true;
  }

  function render() {
    var data = state.data;
    var leadEl = document.getElementById("lead");
    var listEl = document.getElementById("stories");
    var emptyEl = document.getElementById("empty");
    if (!data) return;
    var stories = (data.stories || []).slice().filter(matches);
    if (state.badge === "all" && state.topic === "all" && !state.q && stories.length) {
      leadEl.innerHTML = leadHtml(stories[0]);
      listEl.innerHTML = stories.slice(1).map(cardHtml).join("");
    } else {
      leadEl.innerHTML = "";
      listEl.innerHTML = stories.map(cardHtml).join("");
    }
    bindCardClicks(leadEl);
    bindCardClicks(listEl);
    emptyEl.hidden = stories.length > 0;
  }

  function buildTopicChips(stories) {
    var counts = {};
    stories.forEach(function (s) {
      (s.topics || []).forEach(function (t) { counts[t] = (counts[t] || 0) + 1; });
    });
    var topics = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; });
    var html = '<button class="chip active" data-topic="all">All topics</button>' +
      topics.map(function (t) {
        return '<button class="chip" data-topic="' + esc(t) + '">' + esc(t) + " (" + counts[t] + ")</button>";
      }).join("");
    document.getElementById("topic-chips").innerHTML = html;
    document.querySelectorAll("#topic-chips .chip").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll("#topic-chips .chip").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        state.topic = btn.getAttribute("data-topic");
        render();
      });
    });
  }

  document.querySelectorAll("#badge-chips .chip").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("#badge-chips .chip").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
      state.badge = btn.getAttribute("data-badge");
      render();
    });
  });

  document.getElementById("search").addEventListener("input", function (e) {
    state.q = e.target.value.trim().toLowerCase();
    render();
  });

  fetch("data.json").then(function (r) {
    if (!r.ok) throw new Error("data.json fetch failed: " + r.status);
    return r.json();
  }).then(function (data) {
    state.data = data;
    (data.stories || []).forEach(function (s) {
      state.byId[s.id] = s;
      ((s.sources) || []).forEach(function (src) {
        ALL_OUTLETS[normOutlet(src.outlet)] = true;
      });
    });
    document.getElementById("last-updated").textContent = data.generated_at_ist || "";
    document.getElementById("story-count").textContent = (data.stories || []).length + " stories";
    buildTopicChips(data.stories || []);
    render();
    // deep-link: #story=<id> opens the detail view on load
    var m = /#story=([^&]+)/.exec(location.hash || "");
    if (m) openStory(decodeURIComponent(m[1]));
  }).catch(function (err) {
    document.getElementById("stories").innerHTML =
      '<p class="empty">Could not load data.json — ' + esc(String(err.message || err)) + "</p>";
  });
})();
