import { appendFileSync, existsSync, writeFileSync } from "fs";
import { join } from "path";

export interface TelemetryEvent {
  timestamp: string;
  threadId: string;
  timeSinceLastScrape: number; // seconds
  
  // Deltas
  newNodes: number;
  updatedNodes: number;
  scoreDelta: number;
  textDeltaChars: number;
  
  // Depth Analysis of NEW items
  newAtDepth0: number;
  newAtDepth1: number;
  newAtDepth2Plus: number;
  
  // Cost
  tokensUsed: number;
  durationMs: number;
}

export class Telemetry {
  private filePath: string;

  constructor() {
    this.filePath = join(process.cwd(), "reddit/data/telemetry.jsonl");
  }

  public log(event: TelemetryEvent) {
    const line = JSON.stringify(event) + "\n";
    appendFileSync(this.filePath, line);
  }
}
