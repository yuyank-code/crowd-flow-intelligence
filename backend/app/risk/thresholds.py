class RiskThresholds:
    density_moderate=.45
    density_high=.65
    density_critical=.8
    density_emergency=.92
    utilization_high=.75
    utilization_critical=.9
    bottleneck_persistence=2

    def classify(self, density):
        if density >= self.density_emergency: return 'CRITICAL'
        if density >= self.density_critical: return 'CRITICAL'
        if density >= self.density_high: return 'HIGH'
        if density >= self.density_moderate: return 'MODERATE'
        return 'LOW'

THRESHOLDS=RiskThresholds()
