export class RateLimiter {
  private tokens: number;
  private maxTokens: number;
  private refillRate: number; // tokens per second
  private lastRefill: number;

  constructor(maxTokens: number = 600, refillRate: number = 10) {
    this.tokens = maxTokens;
    this.maxTokens = maxTokens;
    this.refillRate = refillRate; // 10 RPS (600/min)
    this.lastRefill = Date.now();
  }

  public async wait(cost: number = 1): Promise<void> {
    this.refill();
    
    if (this.tokens >= cost) {
      this.tokens -= cost;
      return;
    }

    // Calculate wait time
    const deficit = cost - this.tokens;
    const waitTime = (deficit / this.refillRate) * 1000;
    
    console.log(`⏳ Rate Limit: Waiting ${(waitTime/1000).toFixed(1)}s...`);
    await new Promise(r => setTimeout(r, waitTime));
    
    // Recurse to consume (and refill again during wait)
    return this.wait(cost);
  }

  private refill() {
    const now = Date.now();
    const deltaSeconds = (now - this.lastRefill) / 1000;
    
    if (deltaSeconds > 0) {
      const added = deltaSeconds * this.refillRate;
      this.tokens = Math.min(this.maxTokens, this.tokens + added);
      this.lastRefill = now;
    }
  }
}
