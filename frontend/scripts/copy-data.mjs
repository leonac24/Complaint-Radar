// Copies the pipeline's public_data/ into public/data/ so the static build can serve it.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, "..", "..", "public_data");
const target = join(here, "..", "public", "data");

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
if (existsSync(source)) {
  cpSync(source, target, { recursive: true });
  console.log(`data: copied ${source} -> ${target}`);
} else {
  console.log(`data: ${source} not found; the app will show how to produce it (make export)`);
}
