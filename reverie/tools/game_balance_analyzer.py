from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import statistics
import math

from .base import BaseTool, ToolResult
from .game_data_loader import load_table_data


class GameBalanceAnalyzerTool(BaseTool):
    """
    Game Balance Analyzer - Deep statistical analysis of game balance data.
    
    Analyzes:
    - Combat systems (DPS, survivability, attack/defense ratios)
    - Economy systems (cost/reward balance, inflation detection)
    - Progression curves (difficulty scaling, XP pacing)
    - Loot tables (drop rate fairness, rarity distribution)
    - Crafting (cost-benefit analysis, recipe balance)
    - Difficulty curves (normalized difficulty progression)
    - Any dataset (descriptive stats, distributions, outliers)
    
    Provides: Statistical summaries, balance issues identification, AI recommendations.
    """
    
    name = "game_balance_analyzer"
    description = "Advanced game balance analysis: combat, economy, progression, loot, difficulty, crafting, and stat distributions with recommendations."

    parameters = {
        "type": "object",
        "properties": {
            "analysis_type": {
                "type": "string",
                "enum": [
                    "combat",
                    "economy",
                    "difficulty_curve",
                    "stat_distribution",
                    "progression",
                    "loot_table",
                    "crafting"
                ],
                "description": "Type of balance analysis"
            },
            "data_source": {
                "type": "string",
                "description": "Path to game data file (JSON/CSV)"
            },
            "data_key": {
                "type": "string",
                "description": "For JSON dicts: key containing list data"
            },
            "verbose": {
                "type": "boolean",
                "description": "Include detailed recommendations (default: true)"
            }
        },
        "required": ["analysis_type", "data_source"]
    }

    # Balance thresholds for recommendations
    BALANCE_THRESHOLDS = {
        "cv_high": 0.5,           # Coefficient of variation > 50% = unbalanced
        "outlier_z": 2.5,         # Z-score > 2.5 = critical outlier
        "ttk_min": 2.0,           # Time-to-kill should be at least 2 hits
        "ttk_max": 20.0,          # Time-to-kill shouldn't exceed 20 hits
        "ratio_min": 0.8,         # Attack/defense ratio should be between 0.8-1.2
        "ratio_max": 1.2,
        "progression_ratio_min": 1.1,  # XP growth should be 1.1x-1.5x per level
        "progression_ratio_max": 1.5,
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        analysis_type = kwargs.get("analysis_type")
        data_source = kwargs.get("data_source")
        data_key = kwargs.get("data_key")
        verbose = kwargs.get("verbose", True)

        if not data_source:
            return ToolResult.fail("data_source is required")

        path = Path(data_source)
        if not path.is_absolute():
            path = self.project_root / path

        try:
            rows = load_table_data(path, data_key=data_key)
        except Exception as exc:
            return ToolResult.fail(f"Failed to load data: {str(exc)}")

        if not rows:
            return ToolResult.fail("Data source is empty")

        try:
            if analysis_type == "combat":
                report = self._analyze_combat(rows, verbose)
            elif analysis_type == "economy":
                report = self._analyze_economy(rows, verbose)
            elif analysis_type == "difficulty_curve":
                report = self._analyze_difficulty(rows, verbose)
            elif analysis_type == "progression":
                report = self._analyze_progression(rows, verbose)
            elif analysis_type == "loot_table":
                report = self._analyze_loot_table(rows, verbose)
            elif analysis_type == "crafting":
                report = self._analyze_crafting(rows, verbose)
            else:
                report = self._analyze_distribution(rows, verbose)

            return ToolResult.ok(report, {"analysis_type": analysis_type, "row_count": len(rows)})
        except Exception as e:
            return ToolResult.fail(f"Analysis error: {str(e)}")

    def _numeric_columns(self, rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
        """Extract numeric columns from rows"""
        columns: Dict[str, List[float]] = {}
        for row in rows:
            for key, value in row.items():
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                columns.setdefault(key, []).append(number)
        return columns

    def _basic_stats(self, key: str, values: List[float]) -> Dict[str, float]:
        """Calculate comprehensive statistics for a dataset"""
        if not values:
            return {}
        
        mean = statistics.mean(values)
        median = statistics.median(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        cv = (stdev / mean) if mean != 0 else 0.0  # Coefficient of variation
        
        sorted_vals = sorted(values)
        q1 = sorted_vals[len(sorted_vals) // 4]
        q3 = sorted_vals[3 * len(sorted_vals) // 4]
        iqr = q3 - q1
        
        return {
            "count": len(values),
            "mean": mean,
            "median": median,
            "stdev": stdev,
            "cv": cv,  # Important for balance assessment
            "min": min(values),
            "max": max(values),
            "range": max(values) - min(values),
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
        }

    def _analyze_combat(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze combat system balance"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "COMBAT BALANCE ANALYSIS", "=" * 60]
        
        attack = columns.get("attack", [])
        defense = columns.get("defense", [])
        hp = columns.get("hp", columns.get("health", []))
        speed = columns.get("speed", [])
        
        issues = []
        
        # Health analysis
        if hp:
            hp_stats = self._basic_stats("HP", hp)
            lines.append(f"\nHP Statistics:")
            lines.append(f"  Mean: {hp_stats['mean']:.1f} | Median: {hp_stats['median']:.1f}")
            lines.append(f"  Range: {hp_stats['min']:.1f} - {hp_stats['max']:.1f}")
            lines.append(f"  Std Dev: {hp_stats['stdev']:.2f} (CV: {hp_stats['cv']:.1%})")
        
        # Attack analysis
        if attack:
            attack_stats = self._basic_stats("Attack", attack)
            lines.append(f"\nAttack Statistics:")
            lines.append(f"  Mean: {attack_stats['mean']:.1f} | Median: {attack_stats['median']:.1f}")
            lines.append(f"  Range: {attack_stats['min']:.1f} - {attack_stats['max']:.1f}")
            lines.append(f"  Std Dev: {attack_stats['stdev']:.2f} (CV: {attack_stats['cv']:.1%})")
        
        # Defense analysis
        if defense:
            defense_stats = self._basic_stats("Defense", defense)
            lines.append(f"\nDefense Statistics:")
            lines.append(f"  Mean: {defense_stats['mean']:.1f} | Median: {defense_stats['median']:.1f}")
            lines.append(f"  Range: {defense_stats['min']:.1f} - {defense_stats['max']:.1f}")
            lines.append(f"  Std Dev: {defense_stats['stdev']:.2f} (CV: {defense_stats['cv']:.1%})")
        
        # Combat ratios
        if attack and defense:
            ratio = attack_stats['mean'] / max(defense_stats['mean'], 0.1)
            lines.append(f"\nCombat Ratios:")
            lines.append(f"  Mean Attack/Defense: {ratio:.2f}")
            
            if ratio < self.BALANCE_THRESHOLDS["ratio_min"] or ratio > self.BALANCE_THRESHOLDS["ratio_max"]:
                issues.append(f"⚠️ Attack/Defense ratio {ratio:.2f} is outside ideal range [0.8-1.2]")
        
        # Time-to-kill
        if hp and attack:
            ttk = hp_stats['mean'] / max(attack_stats['mean'], 0.1)
            lines.append(f"  Average Time-to-Kill: {ttk:.1f} hits")
            
            if ttk < self.BALANCE_THRESHOLDS["ttk_min"]:
                issues.append(f"⚠️ TTK {ttk:.1f} is too fast (recommended: {self.BALANCE_THRESHOLDS['ttk_min']}-{self.BALANCE_THRESHOLDS['ttk_max']} hits)")
            elif ttk > self.BALANCE_THRESHOLDS["ttk_max"]:
                issues.append(f"⚠️ TTK {ttk:.1f} is too slow (recommended: {self.BALANCE_THRESHOLDS['ttk_min']}-{self.BALANCE_THRESHOLDS['ttk_max']} hits)")
        
        # Speed analysis
        if speed:
            speed_stats = self._basic_stats("Speed", speed)
            lines.append(f"\nSpeed Statistics:")
            lines.append(f"  Mean: {speed_stats['mean']:.1f} | Range: {speed_stats['min']:.1f} - {speed_stats['max']:.1f}")
        
        # Outliers
        if attack and defense:
            attack_outliers = self._find_outliers(attack)
            defense_outliers = self._find_outliers(defense)
            if attack_outliers or defense_outliers:
                lines.append(f"\n⚠️ Outliers Detected:")
                if attack_outliers:
                    lines.append(f"  Attack outliers: {len(attack_outliers)}")
                if defense_outliers:
                    lines.append(f"  Defense outliers: {len(defense_outliers)}")
                issues.append(f"Found {len(attack_outliers) + len(defense_outliers)} outliers (possible balance breakers)")
        
        # Recommendations
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_economy(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze economy system balance"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "ECONOMY BALANCE ANALYSIS", "=" * 60]
        
        cost = columns.get("cost", [])
        reward = columns.get("reward", columns.get("value", []))
        drop = columns.get("drop_rate", [])
        
        issues = []
        
        if cost:
            cost_stats = self._basic_stats("Cost", cost)
            lines.append(f"\nCost Statistics:")
            lines.append(f"  Mean: {cost_stats['mean']:.1f} | CV: {cost_stats['cv']:.1%}")
            if cost_stats['cv'] > self.BALANCE_THRESHOLDS["cv_high"]:
                issues.append(f"⚠️ Cost variation is high ({cost_stats['cv']:.1%}), prices are inconsistent")
        
        if reward:
            reward_stats = self._basic_stats("Reward", reward)
            lines.append(f"\nReward Statistics:")
            lines.append(f"  Mean: {reward_stats['mean']:.1f} | CV: {reward_stats['cv']:.1%}")
        
        if cost and reward:
            roi = reward_stats['mean'] / max(cost_stats['mean'], 0.1)
            lines.append(f"\nEconomy Ratio:")
            lines.append(f"  Mean Reward/Cost: {roi:.2f}")
            if roi < 0.8 or roi > 1.2:
                issues.append(f"⚠️ Reward/Cost ratio {roi:.2f} is unbalanced (aim for ~1.0)")
        
        if drop:
            drop_stats = self._basic_stats("Drop Rate", drop)
            total_drop = sum(drop)
            lines.append(f"\nDrop Rate Statistics:")
            lines.append(f"  Mean: {drop_stats['mean']:.2%} | Total: {total_drop:.2%}")
            if abs(total_drop - 1.0) > 0.1:
                issues.append(f"⚠️ Drop rates sum to {total_drop:.2%}, should be 1.0 (100%)")
        
        # Inflation check
        if reward and cost:
            if reward_stats['mean'] > cost_stats['mean'] * 1.5:
                issues.append(f"⚠️ Rewards significantly exceed costs (ROI: {roi:.2f}), may cause inflation")
        
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_difficulty(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze difficulty curve progression"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "DIFFICULTY CURVE ANALYSIS", "=" * 60]
        
        level = columns.get("level", [])
        power = columns.get("enemy_power", columns.get("power", []))
        
        issues = []
        
        if level and power and len(level) == len(power):
            # Sort by level
            paired = sorted(zip(level, power))
            sorted_level = [p[0] for p in paired]
            sorted_power = [p[1] for p in paired]
            
            slope = self._linear_slope(sorted_level, sorted_power)
            lines.append(f"\nDifficulty Slope: {slope:.4f}")
            lines.append(f"  (Higher = steeper difficulty curve)")
            
            # Consistency check
            power_stats = self._basic_stats("Power", sorted_power)
            cv = power_stats['cv']
            lines.append(f"\nDifficulty Consistency: CV = {cv:.1%}")
            if cv > 0.3:
                issues.append(f"⚠️ Difficulty curve is inconsistent (CV: {cv:.1%})")
            
            # Check for power creep
            first_third_mean = statistics.mean(sorted_power[:len(sorted_power)//3])
            last_third_mean = statistics.mean(sorted_power[-len(sorted_power)//3:])
            creep_ratio = last_third_mean / max(first_third_mean, 0.1)
            
            lines.append(f"\nPower Creep Check:")
            lines.append(f"  Early average power: {first_third_mean:.1f}")
            lines.append(f"  Late average power: {last_third_mean:.1f}")
            lines.append(f"  Growth multiplier: {creep_ratio:.2f}x")
            
            if creep_ratio > 3.0:
                issues.append(f"⚠️ Severe power creep (late game is {creep_ratio:.1f}x harder)")
            elif creep_ratio == 1.0:
                issues.append(f"⚠️ No difficulty progression (flat curve)")
        
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_progression(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze progression system balance"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "PROGRESSION CURVE ANALYSIS", "=" * 60]
        
        level = columns.get("level", [])
        xp = columns.get("xp", columns.get("exp", []))
        
        issues = []
        
        if level and xp and len(level) == len(xp):
            # Sort by level
            paired = sorted(zip(level, xp))
            sorted_level = [p[0] for p in paired]
            sorted_xp = [p[1] for p in paired]
            
            lines.append(f"\nProgression Curve:")
            lines.append(f"  Total XP required: {sorted_xp[-1]:.0f}")
            lines.append(f"  Levels: {int(sorted_level[0])} - {int(sorted_level[-1])}")
            
            # Calculate growth ratios
            ratios = []
            for idx in range(1, len(sorted_xp)):
                if sorted_xp[idx - 1] > 0:
                    ratios.append(sorted_xp[idx] / sorted_xp[idx - 1])
            
            if ratios:
                avg_ratio = statistics.mean(ratios)
                ratio_stdev = statistics.pstdev(ratios) if len(ratios) > 1 else 0
                
                lines.append(f"\nXP Growth Ratios:")
                lines.append(f"  Average ratio: {avg_ratio:.3f}x per level")
                lines.append(f"  Std Dev: {ratio_stdev:.3f}")
                
                ideal_min = self.BALANCE_THRESHOLDS["progression_ratio_min"]
                ideal_max = self.BALANCE_THRESHOLDS["progression_ratio_max"]
                
                if avg_ratio < ideal_min or avg_ratio > ideal_max:
                    issues.append(f"⚠️ XP growth ratio {avg_ratio:.2f}x is outside ideal [{ideal_min:.1f}x-{ideal_max:.1f}x]")
                
                # Check for inconsistent progression
                if ratio_stdev > 0.2:
                    issues.append(f"⚠️ XP curve is inconsistent (std dev: {ratio_stdev:.2f}), may cause pacing issues")
        
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_loot_table(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze loot table fairness"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "LOOT TABLE ANALYSIS", "=" * 60]
        
        drop_rate = columns.get("drop_rate", [])
        weight = columns.get("weight", [])
        
        issues = []
        
        if drop_rate:
            total_drop = sum(drop_rate)
            lines.append(f"\nDrop Rates:")
            lines.append(f"  Total sum: {total_drop:.2%}")
            lines.append(f"  Item count: {len(drop_rate)}")
            
            if abs(total_drop - 1.0) > 0.01:
                issues.append(f"⚠️ Drop rates sum to {total_drop:.2%}, should be 1.0")
            
            # Fairness check (Gini coefficient)
            if len(drop_rate) > 1:
                sorted_rates = sorted(drop_rate)
                gini = self._calculate_gini(sorted_rates)
                lines.append(f"  Fairness (Gini): {gini:.2f} (0=equal, 1=unequal)")
                if gini > 0.4:
                    issues.append(f"⚠️ Loot drops are very unequal (Gini: {gini:.2f})")
        
        if weight:
            total_weight = sum(weight)
            lines.append(f"\nItem Weights:")
            lines.append(f"  Total weight: {total_weight:.0f}")
            
            normalized = [w / total_weight for w in weight]
            if len(weight) > 1:
                gini = self._calculate_gini(sorted(normalized))
                lines.append(f"  Fairness (Gini): {gini:.2f}")
        
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_crafting(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze crafting system balance"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "CRAFTING ECONOMY ANALYSIS", "=" * 60]
        
        cost = columns.get("cost", [])
        output_value = columns.get("output_value", columns.get("value", []))
        
        issues = []
        
        if cost and output_value:
            cost_stats = self._basic_stats("Cost", cost)
            value_stats = self._basic_stats("Output Value", output_value)
            ratio = value_stats['mean'] / max(cost_stats['mean'], 0.1)
            
            lines.append(f"\nCrafting Cost Analysis:")
            lines.append(f"  Cost - Mean: {cost_stats['mean']:.1f}, CV: {cost_stats['cv']:.1%}")
            lines.append(f"\nOutput Value Analysis:")
            lines.append(f"  Value - Mean: {value_stats['mean']:.1f}, CV: {value_stats['cv']:.1%}")
            
            lines.append(f"\nCrafting ROI:")
            lines.append(f"  Mean Output/Cost: {ratio:.2f}")
            
            if ratio < 0.9:
                issues.append(f"⚠️ Crafting is unprofitable (ROI: {ratio:.2f})")
            elif ratio > 2.0:
                issues.append(f"⚠️ Crafting is overpowered (ROI: {ratio:.2f}), may break economy")
            
            # Check consistency
            if cost_stats['cv'] > 0.5 or value_stats['cv'] > 0.5:
                issues.append(f"⚠️ Crafting recipes have inconsistent costs/values")
        
        if verbose and issues:
            lines.append(f"\n{'-' * 60}")
            lines.append("RECOMMENDATIONS:")
            for issue in issues:
                lines.append(f"  {issue}")
        
        return "\n".join(lines)

    def _analyze_distribution(self, rows: List[Dict[str, Any]], verbose: bool) -> str:
        """Analyze general stat distributions"""
        columns = self._numeric_columns(rows)
        
        lines = ["=" * 60, "STAT DISTRIBUTION ANALYSIS", "=" * 60]
        
        for key in sorted(columns.keys()):
            values = columns[key]
            stats = self._basic_stats(key, values)
            
            lines.append(f"\n{key}:")
            lines.append(f"  Count: {int(stats['count'])}")
            lines.append(f"  Mean: {stats['mean']:.2f} | Median: {stats['median']:.2f}")
            lines.append(f"  Range: {stats['min']:.2f} - {stats['max']:.2f}")
            lines.append(f"  Std Dev: {stats['stdev']:.2f} (CV: {stats['cv']:.1%})")
            
            outliers = self._find_outliers(values)
            if outliers:
                lines.append(f"  ⚠️ Outliers: {len(outliers)}")
        
        return "\n".join(lines)

    def _find_outliers(self, values: List[float], threshold: float = 2.5) -> List[float]:
        """Find outliers using Z-score"""
        if len(values) < 2:
            return []
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values)
        if stdev == 0:
            return []
        return [v for v in values if abs(v - mean) / stdev > threshold]

    def _linear_slope(self, x: List[float], y: List[float]) -> float:
        """Calculate linear regression slope"""
        n = len(x)
        if n < 2:
            return 0.0
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        den = sum((xi - x_mean) ** 2 for xi in x)
        return num / den if den else 0.0

    def _calculate_gini(self, values: List[float]) -> float:
        """Calculate Gini coefficient (0=equal, 1=unequal)"""
        if not values or len(values) < 2:
            return 0.0
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        cumsum = 0
        for i, val in enumerate(sorted_vals):
            cumsum += (n - i) * val
        
        return (2 * cumsum) / (n * sum(sorted_vals)) - (n + 1) / n


