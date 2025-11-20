#!/usr/bin/env python3
"""
Bursty Rate-Limit Controller
EMA-based feedback control for stable throughput under Reddit's bursty API behavior.
Based on reference_books/adaptive_scheduler_reference.ipynb
"""

import math
from typing import Optional


class RateController:
    """
    Exponential moving average (EMA) based rate controller.
    
    Adjusts global gain 'g' to maintain target throughput while allowing
    controlled lateness for better coverage.
    
    Target: ~600 requests/min (10 rps) baseline, scalable with capacity.
    """
    
    def __init__(self, 
                 target_rps: float = 10.0,
                 ema_alpha: float = 0.03,
                 eta: float = 0.05,
                 eta_l: float = 0.02,
                 g_min: float = 0.5,
                 g_max: float = 3.0):
        """
        Initialize rate controller.
        
        Args:
            target_rps: Target requests per second (default 10.0 = 600/min)
            ema_alpha: EMA smoothing factor (default 0.03, slower = more stable)
            eta: Rate error gain (default 0.05)
            eta_l: Lateness error gain (default 0.02)
            g_min: Minimum global gain (default 0.5, compresses intervals)
            g_max: Maximum global gain (default 3.0, stretches intervals)
        """
        self.target = target_rps
        self.alpha = ema_alpha
        self.eta = eta
        self.eta_l = eta_l
        self.g_min = g_min
        self.g_max = g_max
        
        # State
        self.g = 1.0  # Global gain (multiplier for all intervals)
        self.rate_ema = target_rps  # Initialize to target
        
        # Metrics tracking
        self.total_updates = 0
        self.last_instantaneous_rps = 0.0
        self.last_rate_error = 0.0
        self.last_lateness_error = 0.0
    
    def update(self, 
               instantaneous_rps: float,
               queue_lateness: Optional[float] = None,
               lateness_setpoint: Optional[float] = None) -> float:
        """
        Update global gain based on observed throughput and lateness.
        
        Control equation:
            rate_ema = α * rps + (1-α) * rate_ema
            e_r = (rate_ema / target) - 1.0
            e_l = queue_lateness - lateness_setpoint
            g *= exp(η * e_r + η_l * e_l)
            g = clamp(g, g_min, g_max)
        
        Args:
            instantaneous_rps: Observed requests per second this tick
            queue_lateness: Optional average lateness fraction across queue
            lateness_setpoint: Optional target lateness (e.g., 0.15 for 15%)
        
        Returns:
            Updated global gain g
        """
        # Update EMA of achieved rate with floor to prevent collapse
        raw_ema = self.alpha * instantaneous_rps + (1 - self.alpha) * self.rate_ema
        self.rate_ema = max(raw_ema, 0.2 * self.target)  # Floor at 20% of target
        
        # Compute rate error (normalized)
        e_r = (self.rate_ema / self.target) - 1.0
        self.last_rate_error = e_r
        
        # Compute adjustment from rate error
        d = self.eta * e_r
        
        # Optional: Add lateness pressure term
        # This encourages running "slightly late on purpose" for better coverage
        if queue_lateness is not None and lateness_setpoint is not None:
            e_l = queue_lateness - lateness_setpoint
            self.last_lateness_error = e_l
            d += self.eta_l * e_l
        else:
            self.last_lateness_error = 0.0
        
        # Exponential update (multiplicative)
        self.g *= math.exp(d)
        
        # Clamp for stability
        self.g = max(self.g_min, min(self.g_max, self.g))
        
        # Track metrics
        self.total_updates += 1
        self.last_instantaneous_rps = instantaneous_rps
        
        return self.g
    
    def set_target(self, new_target_rps: float):
        """
        Update target throughput (for capacity scaling).
        
        Use this when adding/removing VMs or adjusting rate limits.
        
        Args:
            new_target_rps: New target requests per second
        """
        self.target = new_target_rps
    
    def reset(self):
        """
        Reset controller state to initial conditions.
        Useful for testing or after major system changes.
        """
        self.g = 1.0
        self.rate_ema = self.target
        self.total_updates = 0
        self.last_instantaneous_rps = 0.0
        self.last_rate_error = 0.0
        self.last_lateness_error = 0.0
    
    def get_status(self) -> dict:
        """
        Get current controller status for monitoring/logging.
        
        Returns:
            Dict with current state and metrics
        """
        return {
            "global_gain": self.g,
            "target_rps": self.target,
            "rate_ema": self.rate_ema,
            "last_instantaneous_rps": self.last_instantaneous_rps,
            "rate_error": self.last_rate_error,
            "lateness_error": self.last_lateness_error,
            "total_updates": self.total_updates,
            "utilization_pct": (self.rate_ema / self.target * 100) if self.target > 0 else 0.0,
        }
    
    def __repr__(self) -> str:
        return (f"RateController(target={self.target:.1f} rps, "
                f"g={self.g:.3f}, ema={self.rate_ema:.2f} rps, "
                f"util={self.rate_ema/self.target*100:.1f}%)")


if __name__ == '__main__':
    # Demonstration with simulated burst/stall scenario
    import random
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    
    print("="*80)
    print("🎛️  RATE CONTROLLER - Burst/Stall Simulation")
    print("="*80)
    print()
    
    controller = RateController(target_rps=10.0)
    
    # Simulate 300 seconds (5 minutes) with bursty behavior
    seconds = 300
    target_rps = 10.0
    
    instant_rps_hist = []
    ema_hist = []
    gain_hist = []
    
    burst_timer = 0
    stall_timer = 0
    
    print("Simulating bursty throughput...")
    print()
    
    for t in range(seconds):
        # Simulate burst/stall events
        if burst_timer == 0 and stall_timer == 0:
            if random.random() < 0.02:  # 2% chance per second
                burst_timer = random.randint(5, 15)
            elif random.random() < 0.01:  # 1% chance per second
                stall_timer = random.randint(30, 90)
        
        # Determine instantaneous RPS based on mode
        if stall_timer > 0:
            instant_rps = 0.0
            stall_timer -= 1
        elif burst_timer > 0:
            instant_rps = random.uniform(20, 40)
            burst_timer -= 1
        else:
            # Normal operation with noise
            instant_rps = target_rps + random.gauss(0, 2)
            instant_rps = max(0, instant_rps)
        
        # Update controller (without lateness term for simplicity)
        controller.update(instant_rps)
        
        # Record history
        instant_rps_hist.append(instant_rps)
        ema_hist.append(controller.rate_ema)
        gain_hist.append(controller.g)
    
    # Display summary
    print(f"Simulation complete: {seconds} seconds")
    print()
    print(f"Final state:")
    status = controller.get_status()
    for key, val in status.items():
        print(f"  ├─ {key}: {val}")
    print()
    
    # Plot results
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    t_array = list(range(len(instant_rps_hist)))
    
    # Top plot: Throughput
    ax1.plot(t_array, instant_rps_hist, color='gray', alpha=0.3, label='Instantaneous RPS')
    ax1.plot(t_array, ema_hist, color='blue', linewidth=2, label='EMA RPS')
    ax1.axhline(target_rps, color='red', linestyle='--', label='Target')
    ax1.set_xlabel('Time (seconds)')
    ax1.set_ylabel('Requests/second')
    ax1.set_title('Throughput Tracking (Burst/Stall Scenario)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Bottom plot: Global gain
    ax2.plot(t_array, gain_hist, color='green', linewidth=2)
    ax2.axhline(1.0, color='black', linestyle=':', label='Nominal (g=1.0)')
    ax2.set_xlabel('Time (seconds)')
    ax2.set_ylabel('Global Gain (g)')
    ax2.set_title('Adaptive Gain Response')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    output_file = 'rate_controller_simulation.png'
    plt.savefig(output_file, dpi=150)
    print(f"📊 Plot saved to: {output_file}")
    print()
    
    print("="*80)

