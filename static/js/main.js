// ─── Auto-dismiss flash messages ────────────────────────────────────────────
document.querySelectorAll(".flash").forEach(el => {
    setTimeout(() => {
        el.style.transition = "opacity 0.5s";
        el.style.opacity = "0";
        setTimeout(() => el.remove(), 500);
    }, 4000);
});

// ─── Star Rating Input ────────────────────────────────────────────────────────
const stars = document.querySelectorAll(".star");
const ratingVal = document.getElementById("ratingVal");

if (stars.length && ratingVal) {
    stars.forEach(star => {
        star.addEventListener("click", () => {
            const val = parseInt(star.dataset.val);
            ratingVal.value = val;
            stars.forEach(s => {
                s.classList.toggle("active", parseInt(s.dataset.val) <= val);
            });
        });
        star.addEventListener("mouseover", () => {
            const val = parseInt(star.dataset.val);
            stars.forEach(s => {
                s.style.color = parseInt(s.dataset.val) <= val ? "#f59e0b" : "";
            });
        });
    });
    document.querySelector(".star-input")?.addEventListener("mouseleave", () => {
        const cur = parseInt(ratingVal.value || 3);
        stars.forEach(s => {
            s.style.color = "";
            s.classList.toggle("active", parseInt(s.dataset.val) <= cur);
        });
    });
}

// ─── Character Counter ────────────────────────────────────────────────────────
const reviewText = document.getElementById("reviewText");
const charCount = document.getElementById("charCount");

if (reviewText && charCount) {
    const update = () => charCount.textContent = reviewText.value.length;
    reviewText.addEventListener("input", () => { update(); liveAnalyze(); });
    update();
}

// ─── Live Signal Detection ────────────────────────────────────────────────────
const liveSignals = document.getElementById("liveSignals");
const signalTags = document.getElementById("signalTags");

function liveAnalyze() {
    if (!reviewText || !liveSignals || !signalTags) return;
    const text = reviewText.value;
    if (text.length < 10) { liveSignals.style.display = "none"; return; }

    const signals = [];
    const lower = text.toLowerCase();
    const words = lower.split(/\s+/);

    if ((text.match(/!/g) || []).length >= 3) signals.push("⚠ Excessive !");
    if ((text.match(/[A-Z]{3,}/g) || []).length >= 2) signals.push("⚠ All-caps");
    if (/(.)\1{2,}/.test(text)) signals.push("⚠ Repeated chars");

    const sups = ["best","amazing","perfect","excellent","fantastic","outstanding","superb","incredible"];
    const supCount = words.filter(w => sups.includes(w)).length;
    if (supCount >= 2) signals.push(`⚠ ${supCount} superlatives`);

    if (/\b(buy now|order now|must buy|limited stock)\b/i.test(text)) signals.push("⚠ Urgency language");
    if (/\b(sponsored|gifted|paid|affiliate)\b/i.test(text)) signals.push("⚠ Sponsored");

    const wordFreq = {};
    words.forEach(w => { if (w.length > 3) wordFreq[w] = (wordFreq[w] || 0) + 1; });
    const repeated = Object.keys(wordFreq).filter(w => wordFreq[w] >= 3);
    if (repeated.length) signals.push(`⚠ Repeated: "${repeated[0]}"`);

    if (signals.length > 0) {
        liveSignals.style.display = "block";
        signalTags.innerHTML = signals.map(s =>
            `<span class="signal-tag">${s}</span>`
        ).join("");
    } else {
        liveSignals.style.display = "none";
    }
}

// ─── Meter animation on page load ────────────────────────────────────────────
window.addEventListener("load", () => {
    document.querySelectorAll(".meter-fill").forEach(el => {
        const target = el.style.width;
        el.style.width = "0%";
        setTimeout(() => { el.style.width = target; }, 100);
    });
});
