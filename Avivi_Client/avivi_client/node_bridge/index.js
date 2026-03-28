/**
 * Avivi WhatsApp bridge: prints JSON lines to stdout.
 * Simulation mode if whatsapp-web.js is not installed.
 * Install: npm install
 */
const path = require("path");

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function simulation() {
  const tinyPng = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
  emit({ type: "qr", data: tinyPng });
  setTimeout(() => {
    emit({ type: "ready", identity: "Demo Business (simulation)" });
  }, 1500);
  setInterval(() => {}, 60000);
}

try {
  const wweb = require("whatsapp-web.js");
  const qrcode = require("qrcode-terminal");
  const { Client, LocalAuth } = wweb;
  const client = new Client({
    authStrategy: new LocalAuth({ dataPath: path.join(process.env.USERPROFILE || ".", ".avivi-wweb") }),
    puppeteer: { headless: true, args: ["--no-sandbox"] },
  });
  client.on("qr", (qr) => {
    qrcode.generate(qr, { small: true });
    emit({ type: "qr", data: Buffer.from(qr, "utf8").toString("base64") });
  });
  client.on("ready", () => {
    const info = client.info;
    emit({ type: "ready", identity: (info && info.pushname) || "WhatsApp" });
  });
  client.on("message", async (msg) => {
    emit({ type: "message", from: msg.from, body: msg.body || "" });
  });
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    for (const line of chunk.split("\n")) {
      if (!line.trim()) continue;
      try {
        const cmd = JSON.parse(line);
        if (cmd.cmd === "send" && cmd.to && cmd.body) {
          client.sendMessage(cmd.to, cmd.body).catch(() => {});
        }
      } catch (_) {}
    }
  });
  client.initialize();
} catch (e) {
  simulation();
}
