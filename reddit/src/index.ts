import { spawn } from "child_process";
import { join } from "path";

console.log("Reddit Monitor (Shim)");
console.log("---------------------");
console.log("This module currently wraps the Python-based 'reddit-adaptive-sampler'.");

// Path to the legacy Python scraper
// process.cwd() is the root of the reddit module
const PYTHON_SCRIPT = join(process.cwd(), "reddit-adaptive-sampler/unified_scraper.py");

// Check if python3 is available
const PYTHON_CMD = "/usr/bin/python3";
const checkPython = spawn(PYTHON_CMD, ["--version"]);

checkPython.on("error", () => {
  console.error(`Error: '${PYTHON_CMD}' not found. Please ensure Python 3 is installed.`);
  process.exit(1);
});

console.log(`Starting Python Scraper: ${PYTHON_SCRIPT}`);
console.log("---------------------------------------------------");

// Spawn the python process inheriting stdio so output streams directly to console
// Forward any arguments passed to this script (e.g. duration)
const args = [PYTHON_SCRIPT, ...process.argv.slice(2)];

const pythonProcess = spawn(PYTHON_CMD, args, {
  stdio: "inherit",
  cwd: join(process.cwd(), "reddit-adaptive-sampler") // Set CWD so python imports work
});

pythonProcess.on("close", (code) => {
  console.log(`Python scraper process exited with code ${code}`);
});
