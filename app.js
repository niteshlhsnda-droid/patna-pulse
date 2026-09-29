/* Patna Pulse — staged light-theme renderer (A2). Reads data.json with `brief`. */
(function () {
  "use strict";

  var TYPE_ICONS = { news: "📰", facebook: "📘", instagram: "📸", youtube: "▶️", x: "𝕏", threads: "🧵" };
  var TYPE_LABELS = { news: "News site", facebook: "Facebook", instagram: "Instagram", youtube: "YouTube", x: "X", threads: "Threads" };
  var MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  var state = { q: "", topic: "all", badge: "all", data: null };

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

  function sourcesHtml(story) {
    var srcs = uniqSources(story);
    var items = srcs.map(function (s) {
      var icon = TYPE_ICONS[s.type] || "🔗";
      return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener">' +
        icon + " " + esc(s.outlet) + "</a></li>";
    }).join("");
    var firstType = (srcs[0] && TYPE_LABELS[srcs[0].type]) || "News";
    return '<div class="card-sources"><div class="sources-label">Sources</div>' +
      '<ul class="source-list">' + items + "</ul></div>";
  }

  function cardHtml(story) {
    return '<article class="card">' +
      '<div class="card-top">' + badgeHtml(story.genuineness) +
      '<div style="display:flex;gap:10px">' + metaHtml(story) + "</div></div>" +
      "<h3>" + esc(cleanHeadline(story.headline)) + "</h3>" +
      (story.brief ? '<p class="card-brief">' + esc(story.brief) + "</p>" : "") +
      (story.topics && story.topics.length ? '<div class="card-topics">' + topicsHtml(story) + "</div>" : "") +
      sourcesHtml(story) +
      "</article>";
  }

  function leadHtml(story) {
    return '<article class="lead-card">' +
      '<div class="lead-kicker">Top story</div>' +
      '<div class="card-top" style="margin-bottom:10px">' + badgeHtml(story.genuineness) +
      '<div style="display:flex;gap:10px">' + metaHtml(story) + "</div></div>" +
      "<h2>" + esc(cleanHeadline(story.headline)) + "</h2>" +
      (story.brief ? '<p class="lead-brief">' + esc(story.brief) + "</p>" : "") +
      (story.topics && story.topics.length ? '<div class="card-topics" style="margin-bottom:10px">' + topicsHtml(story) + "</div>" : "") +
      sourcesHtml(story) +
      "</article>";
  }

  function matches(story) {
    if (state.badge !== "all" && story.genuineness !== state.badge) return false;
    if (state.topic !== "all" && (story.topics || []).indexOf(state.topic) < 0) return false;
    if (state.q) {
      var hay = (story.headline + " " + (story.brief || "")).toLowerCase();
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
      ((s.sources) || []).forEach(function (src) {
        ALL_OUTLETS[normOutlet(src.outlet)] = true;
      });
    });
    document.getElementById("last-updated").textContent = data.generated_at_ist || "";
    document.getElementById("story-count").textContent = (data.stories || []).length + " stories";
    buildTopicChips(data.stories || []);
    render();
  }).catch(function (err) {
    document.getElementById("stories").innerHTML =
      '<p class="empty">Could not load data.json — ' + esc(String(err.message || err)) + "</p>";
  });
})();
