#!/usr/bin/env bun

import { readdir } from "fs/promises";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

const TARBALL_DIR = "data/tarballs";
const SAMPLE_SIZE = 300; // Larger sample for better statistics
const TMP_DIR = "/tmp/arxiv_analysis";

type TarballAnalysis = {
  tarballName: string;
  isPDF: boolean;
  files: string[];
  texFiles: string[];
  mainFile: string | null;
  sectionHeaders: string[];
  fileStructure: "modular" | "single-file" | "multi-file" | "unknown";
  fileExtensions: Record<string, number>;
  hasAbstract: boolean;
  texFileCount: number;
};

async function analyzeTarball(tarballPath: string): Promise<TarballAnalysis> {
  const tarballName = tarballPath.split("/").pop() ?? "";

  // Check if it's actually a PDF
  let isPDF = false;
  try {
    const { stdout: fileType } = await execAsync(`file -b "${tarballPath}"`);
    isPDF = fileType.toLowerCase().includes("pdf");
  } catch {
    // Ignore
  }

  if (isPDF) {
    return {
      tarballName,
      isPDF: true,
      files: [],
      texFiles: [],
      mainFile: null,
      sectionHeaders: [],
      fileStructure: "unknown",
      fileExtensions: { ".pdf": 1 },
      hasAbstract: false,
      texFileCount: 0,
    };
  }

  // List files in tarball
  const { stdout: fileList } = await execAsync(`tar -tf "${tarballPath}"`);
  const files = fileList.trim().split("\n").filter(f => f.length > 0);

  // Count file extensions
  const fileExtensions: Record<string, number> = {};
  for (const file of files) {
    const ext = file.includes(".") ? file.substring(file.lastIndexOf(".")) : "(no ext)";
    fileExtensions[ext] = (fileExtensions[ext] ?? 0) + 1;
  }

  // Find .tex files
  const texFiles = files.filter(f => f.endsWith(".tex") && !f.includes("/"));

  // Identify main file
  let mainFile: string | null = null;
  const mainCandidates = ["main.tex", "paper.tex", "root.tex", "manuscript.tex", "article.tex"];
  for (const candidate of mainCandidates) {
    if (texFiles.includes(candidate)) {
      mainFile = candidate;
      break;
    }
  }

  // Check for template names
  if (!mainFile) {
    const templatePatterns = [
      /acl.*\.tex$/,
      /ieee.*\.tex$/i,
      /iclr.*\.tex$/i,
      /neurips.*\.tex$/i,
    ];
    for (const pattern of templatePatterns) {
      const match = texFiles.find(f => pattern.test(f));
      if (match) {
        mainFile = match;
        break;
      }
    }
  }

  // If no standard main file, use the first one
  if (!mainFile && texFiles.length > 0) {
    mainFile = texFiles[0];
  }

  // Extract and analyze section headers
  const sectionHeaders: string[] = [];
  let hasAbstract = false;
  if (mainFile) {
    try {
      const { stdout: content } = await execAsync(
        `tar -xOf "${tarballPath}" "${mainFile}" 2>/dev/null || echo ""`
      );

      // Check for abstract
      hasAbstract = /\\begin\{abstract\}/.test(content);

      // Find \section{...}, \subsection{...}, etc.
      const sectionRegex = /\\(section|subsection|subsubsection)\{([^}]+)\}/g;
      let match;
      while ((match = sectionRegex.exec(content)) !== null) {
        sectionHeaders.push(match[2]);
      }
    } catch (error) {
      // Ignore extraction errors
    }
  }

  // Determine structure
  let fileStructure: "modular" | "single-file" | "multi-file" | "unknown" = "unknown";
  const hasNumberedSections = texFiles.some(f => /^\d\d-/.test(f));
  if (hasNumberedSections) {
    fileStructure = "modular";
  } else if (texFiles.length === 1) {
    fileStructure = "single-file";
  } else if (texFiles.length >= 2 && texFiles.length <= 10) {
    fileStructure = "multi-file";
  } else if (texFiles.length > 10) {
    fileStructure = "modular";
  }

  return {
    tarballName,
    isPDF,
    files,
    texFiles,
    mainFile,
    sectionHeaders,
    fileStructure,
    fileExtensions,
    hasAbstract,
    texFileCount: texFiles.length,
  };
}

async function main() {
  console.log("Analyzing arXiv tarballs...\n");

  // Get list of tarballs
  const allFiles = await readdir(TARBALL_DIR);
  const tarballs = allFiles.filter(f => f.endsWith(".tar")).slice(0, SAMPLE_SIZE);

  console.log(`Analyzing ${tarballs.length} tarballs...\n`);

  const analyses: TarballAnalysis[] = [];

  for (let i = 0; i < tarballs.length; i++) {
    const tarball = tarballs[i];
    console.log(`[${i + 1}/${tarballs.length}] Analyzing ${tarball}...`);

    try {
      const analysis = await analyzeTarball(`${TARBALL_DIR}/${tarball}`);
      analyses.push(analysis);
    } catch (error) {
      console.error(`  Error: ${error}`);
    }
  }

  // Generate statistics
  console.log("\n=== ANALYSIS RESULTS ===\n");
  console.log(`Total tarballs analyzed: ${analyses.length}\n`);

  // PDF vs LaTeX
  const pdfCount = analyses.filter(a => a.isPDF).length;
  const latexCount = analyses.length - pdfCount;
  console.log("Content Type Distribution:");
  console.log(`  LaTeX source: ${latexCount} (${Math.round(latexCount / analyses.length * 100)}%)`);
  console.log(`  PDF only: ${pdfCount} (${Math.round(pdfCount / analyses.length * 100)}%)`);

  // File structure patterns (for LaTeX papers only)
  const latexAnalyses = analyses.filter(a => !a.isPDF);
  const structureCounts = {
    modular: latexAnalyses.filter(a => a.fileStructure === "modular").length,
    "single-file": latexAnalyses.filter(a => a.fileStructure === "single-file").length,
    "multi-file": latexAnalyses.filter(a => a.fileStructure === "multi-file").length,
    unknown: latexAnalyses.filter(a => a.fileStructure === "unknown").length,
  };

  console.log("\nFile Structure Distribution (LaTeX papers only):");
  console.log(`  Modular (10+ files or numbered): ${structureCounts.modular} (${Math.round(structureCounts.modular / latexAnalyses.length * 100)}%)`);
  console.log(`  Single-file (1 .tex): ${structureCounts["single-file"]} (${Math.round(structureCounts["single-file"] / latexAnalyses.length * 100)}%)`);
  console.log(`  Multi-file (2-10 .tex): ${structureCounts["multi-file"]} (${Math.round(structureCounts["multi-file"] / latexAnalyses.length * 100)}%)`);
  console.log(`  Unknown: ${structureCounts.unknown} (${Math.round(structureCounts.unknown / latexAnalyses.length * 100)}%)`);

  // Main file naming patterns
  console.log("\nMain File Names:");
  const mainFileNames = analyses.map(a => a.mainFile).filter(f => f !== null);
  const mainFileCounts: Record<string, number> = {};
  for (const name of mainFileNames) {
    mainFileCounts[name] = (mainFileCounts[name] ?? 0) + 1;
  }
  for (const [name, count] of Object.entries(mainFileCounts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${name}: ${count}`);
  }

  // Abstract presence
  const abstractCount = latexAnalyses.filter(a => a.hasAbstract).length;
  console.log("\nAbstract Presence (LaTeX papers only):");
  console.log(`  Has abstract: ${abstractCount} (${Math.round(abstractCount / latexAnalyses.length * 100)}%)`);
  console.log(`  No abstract: ${latexAnalyses.length - abstractCount} (${Math.round((latexAnalyses.length - abstractCount) / latexAnalyses.length * 100)}%)`);

  // Section header analysis
  console.log("\nCommon Section Headers:");
  const allHeaders = latexAnalyses.flatMap(a => a.sectionHeaders);
  const headerCounts: Record<string, number> = {};
  for (const header of allHeaders) {
    const normalized = header.toLowerCase().trim();
    headerCounts[normalized] = (headerCounts[normalized] ?? 0) + 1;
  }

  const topHeaders = Object.entries(headerCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 30);

  for (const [header, count] of topHeaders) {
    const percentage = Math.round((count / latexAnalyses.length) * 100);
    console.log(`  "${header}": ${count} (${percentage}%)`);
  }

  // Common file extensions
  console.log("\nMost Common File Extensions:");
  const allExtensions: Record<string, number> = {};
  for (const analysis of latexAnalyses) {
    for (const [ext, count] of Object.entries(analysis.fileExtensions)) {
      allExtensions[ext] = (allExtensions[ext] ?? 0) + count;
    }
  }
  const topExtensions = Object.entries(allExtensions)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15);
  for (const [ext, count] of topExtensions) {
    console.log(`  ${ext}: ${count} files`);
  }

  // Sample detailed outputs
  console.log("\n=== SAMPLE DETAILED ANALYSES ===\n");
  for (const analysis of analyses.slice(0, 5)) {
    console.log(`Tarball: ${analysis.tarballName}`);
    console.log(`  Structure: ${analysis.fileStructure}`);
    console.log(`  Main file: ${analysis.mainFile}`);
    console.log(`  .tex files (${analysis.texFiles.length}): ${analysis.texFiles.slice(0, 5).join(", ")}${analysis.texFiles.length > 5 ? "..." : ""}`);
    console.log(`  Section headers: ${analysis.sectionHeaders.slice(0, 3).join(", ")}${analysis.sectionHeaders.length > 3 ? "..." : ""}`);
    console.log();
  }
}

main().catch(console.error);
