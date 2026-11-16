// Renders public/app-icon.svg to the PNG sizes iPhones and Android need (development only).
//   CHROME=/path/to/chrome node scripts/make-icons.mjs        (needs playwright-core and a Chromium)
import { chromium } from "playwright-core";
import { readFileSync, writeFileSync } from "node:fs";

const svg = readFileSync(new URL("../public/app-icon.svg", import.meta.url), "utf8");
const sizes = { "icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180 };
const browser = await chromium.launch({ executablePath: process.env.CHROME, args: ["--no-sandbox"] });
for (const [file, size] of Object.entries(sizes)) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(`<style>html,body{margin:0}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
  writeFileSync(new URL(`../public/${file}`, import.meta.url), await page.screenshot({ type: "png" }));
  await page.close();
}
await browser.close();
console.log("icons written");
