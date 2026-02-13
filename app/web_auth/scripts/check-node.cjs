function parseMajor(version) {
  // version like "22.17.0"
  var parts = String(version || "").split(".");
  var major = parseInt(parts[0], 10);
  return Number.isFinite(major) ? major : NaN;
}

var requiredMajor = 18;
var detected = (process && process.versions && process.versions.node) || "unknown";
var major = parseMajor(detected);

if (!Number.isFinite(major) || major < requiredMajor) {
  console.error("");
  console.error("[web-auth] Node.js " + requiredMajor + "+ is required to run Vite.");
  console.error("[web-auth] Detected: " + detected);
  console.error("");
  console.error("Fix:");
  console.error("- Upgrade Node.js (recommended: 20 LTS or newer) and re-run:");
  console.error("  npm ci && npm run dev");
  console.error("");
  process.exit(1);
}

