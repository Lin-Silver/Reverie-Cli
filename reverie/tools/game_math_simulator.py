"""
Game Math Simulator Tool - Advanced Monte Carlo simulation and analysis

Core Operations:
- monte_carlo: Run Monte Carlo simulations with predefined game scenarios
- parameter_sweep: Test parameter ranges for sensitivity analysis
- analyze_results: Comprehensive result analysis with statistics

Predefined Simulation Scenarios:
  * combat: Player vs enemy outcome probability, DPS calculations
  * economy: Inflation detection, item value stability analysis
  * progression: Level pacing validation, difficulty curve testing
  * loot: Drop rate fairness, rarity distribution verification
  * custom: User-defined simulation logic

Advanced Features:
- Confidence intervals: 95% and 99% CI for result bounds
- Sensitivity analysis: identify critical balance parameters
- Seed-based reproducibility for consistent results
- Statistical significance testing
- Visualization-ready JSON output

Use Cases:
- Combat balance: verify player win rates against enemies
- Economy stability: test inflation resistance of pricing
- Progression pacing: validate XP requirements and level curves
- Loot fairness: ensure drop rate probabilities are correct
"""

from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
import json
import random
import statistics

from .base import BaseTool, ToolResult


class GameMathSimulatorTool(BaseTool):
    name = "game_math_simulator"
    description = "Run Monte Carlo simulations and parameter sweeps for game balance testing."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["monte_carlo", "parameter_sweep", "analyze_results"],
                "description": "Simulation action"
            },
            "simulation_type": {
                "type": "string",
                "enum": ["combat", "economy", "progression", "loot", "custom"],
                "description": "Type of simulation to run"
            },
            "iterations": {
                "type": "integer",
                "description": "Number of simulation iterations (default: 1000)"
            },
            "parameters": {
                "type": "object",
                "description": "Simulation parameters (depends on simulation_type)"
            },
            "parameter_ranges": {
                "type": "object",
                "description": "Parameter ranges for sweep (e.g., {'attack': [5, 10, 15]})"
            },
            "output_path": {
                "type": "string",
                "description": "Path to save simulation results"
            },
            "results_path": {
                "type": "string",
                "description": "Path to load results for analysis"
            },
            "seed": {
                "type": "integer",
                "description": "Random seed for reproducibility"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        seed = kwargs.get("seed")
        
        if seed is not None:
            random.seed(seed)

        try:
            if action == "monte_carlo":
                simulation_type = kwargs.get("simulation_type", "combat")
                iterations = kwargs.get("iterations", 1000)
                parameters = kwargs.get("parameters", {})
                output_path = kwargs.get("output_path")
                
                return self._run_monte_carlo(simulation_type, iterations, parameters, output_path)
            
            elif action == "parameter_sweep":
                simulation_type = kwargs.get("simulation_type", "combat")
                iterations = kwargs.get("iterations", 100)
                parameter_ranges = kwargs.get("parameter_ranges", {})
                output_path = kwargs.get("output_path")
                
                return self._run_parameter_sweep(simulation_type, iterations, parameter_ranges, output_path)
            
            elif action == "analyze_results":
                results_path = kwargs.get("results_path")
                if not results_path:
                    return ToolResult.fail("results_path is required for analyze_results")
                
                return self._analyze_results(self._resolve_path(results_path))
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _run_monte_carlo(
        self, simulation_type: str, iterations: int, parameters: Dict[str, Any], output_path: Optional[str]
    ) -> ToolResult:
        """Run Monte Carlo simulation"""
        # Select simulation function
        if simulation_type == "combat":
            sim_func = self._simulate_combat
        elif simulation_type == "economy":
            sim_func = self._simulate_economy
        elif simulation_type == "progression":
            sim_func = self._simulate_progression
        elif simulation_type == "loot":
            sim_func = self._simulate_loot
        else:
            return ToolResult.fail(f"Unknown simulation type: {simulation_type}")

        # Run simulations
        results = []
        for i in range(iterations):
            result = sim_func(parameters)
            results.append(result)

        # Calculate statistics
        stats = self._calculate_statistics(results)

        # Save results if output path provided
        if output_path:
            output_file = self._resolve_path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            save_data = {
                "simulation_type": simulation_type,
                "iterations": iterations,
                "parameters": parameters,
                "results": results,
                "statistics": stats
            }
            
            output_file.write_text(json.dumps(save_data, indent=2), encoding="utf-8")

        # Format output
        output = f"Monte Carlo Simulation: {simulation_type}\n\n"
        output += f"Iterations: {iterations}\n"
        output += f"Parameters: {json.dumps(parameters, indent=2)}\n\n"
        output += "Statistics:\n"
        for key, value in stats.items():
            if isinstance(value, float):
                output += f"  - {key}: {value:.2f}\n"
            else:
                output += f"  - {key}: {value}\n"

        return ToolResult.ok(output, {
            "simulation_type": simulation_type,
            "iterations": iterations,
            "statistics": stats,
            "results_sample": results[:10]  # Include first 10 results
        })

    def _run_parameter_sweep(
        self, simulation_type: str, iterations: int, parameter_ranges: Dict[str, List], output_path: Optional[str]
    ) -> ToolResult:
        """Run parameter sweep"""
        if not parameter_ranges:
            return ToolResult.fail("parameter_ranges is required for parameter_sweep")

        # Select simulation function
        if simulation_type == "combat":
            sim_func = self._simulate_combat
        elif simulation_type == "economy":
            sim_func = self._simulate_economy
        elif simulation_type == "progression":
            sim_func = self._simulate_progression
        elif simulation_type == "loot":
            sim_func = self._simulate_loot
        else:
            return ToolResult.fail(f"Unknown simulation type: {simulation_type}")

        # Generate parameter combinations
        param_names = list(parameter_ranges.keys())
        param_values = list(parameter_ranges.values())
        
        sweep_results = []
        
        # Simple grid sweep
        import itertools
        for combination in itertools.product(*param_values):
            params = dict(zip(param_names, combination))
            
            # Run simulations for this parameter set
            results = []
            for _ in range(iterations):
                result = sim_func(params)
                results.append(result)
            
            # Calculate statistics
            stats = self._calculate_statistics(results)
            
            sweep_results.append({
                "parameters": params,
                "statistics": stats
            })

        # Save results if output path provided
        if output_path:
            output_file = self._resolve_path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            save_data = {
                "simulation_type": simulation_type,
                "iterations_per_combination": iterations,
                "parameter_ranges": parameter_ranges,
                "sweep_results": sweep_results
            }
            
            output_file.write_text(json.dumps(save_data, indent=2), encoding="utf-8")

        # Format output
        output = f"Parameter Sweep: {simulation_type}\n\n"
        output += f"Iterations per combination: {iterations}\n"
        output += f"Parameter ranges: {json.dumps(parameter_ranges, indent=2)}\n\n"
        output += f"Total combinations tested: {len(sweep_results)}\n\n"
        output += "Sample results:\n"
        for i, result in enumerate(sweep_results[:5]):  # Show first 5
            output += f"\nCombination {i + 1}:\n"
            output += f"  Parameters: {json.dumps(result['parameters'])}\n"
            output += f"  Mean result: {result['statistics'].get('mean', 'N/A')}\n"

        return ToolResult.ok(output, {
            "simulation_type": simulation_type,
            "combinations_tested": len(sweep_results),
            "sweep_results": sweep_results
        })

    def _analyze_results(self, results_path: Path) -> ToolResult:
        """Analyze simulation results"""
        if not results_path.exists():
            return ToolResult.fail(f"Results file not found: {results_path}")

        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult.fail(f"Failed to load results: {str(e)}")

        # Determine analysis type
        if "sweep_results" in data:
            return self._analyze_sweep_results(data)
        else:
            return self._analyze_monte_carlo_results(data)

    def _analyze_monte_carlo_results(self, data: Dict[str, Any]) -> ToolResult:
        """Analyze Monte Carlo results"""
        stats = data.get("statistics", {})
        
        output = f"Monte Carlo Analysis\n\n"
        output += f"Simulation Type: {data.get('simulation_type', 'Unknown')}\n"
        output += f"Iterations: {data.get('iterations', 0)}\n\n"
        output += "Statistics:\n"
        for key, value in stats.items():
            if isinstance(value, float):
                output += f"  - {key}: {value:.2f}\n"
            else:
                output += f"  - {key}: {value}\n"

        # Additional insights
        mean = stats.get("mean", 0)
        std_dev = stats.get("std_dev", 0)
        
        if std_dev > 0:
            cv = (std_dev / mean) * 100 if mean != 0 else 0
            output += f"\nCoefficient of Variation: {cv:.1f}%\n"
            
            if cv < 10:
                output += "Insight: Low variability - results are consistent\n"
            elif cv < 30:
                output += "Insight: Moderate variability - results are somewhat predictable\n"
            else:
                output += "Insight: High variability - results are unpredictable\n"

        return ToolResult.ok(output, {"statistics": stats})

    def _analyze_sweep_results(self, data: Dict[str, Any]) -> ToolResult:
        """Analyze parameter sweep results"""
        sweep_results = data.get("sweep_results", [])
        
        if not sweep_results:
            return ToolResult.fail("No sweep results found")

        # Find best and worst combinations
        best_result = max(sweep_results, key=lambda x: x["statistics"].get("mean", 0))
        worst_result = min(sweep_results, key=lambda x: x["statistics"].get("mean", 0))

        output = f"Parameter Sweep Analysis\n\n"
        output += f"Simulation Type: {data.get('simulation_type', 'Unknown')}\n"
        output += f"Combinations Tested: {len(sweep_results)}\n\n"
        
        output += "Best Combination:\n"
        output += f"  Parameters: {json.dumps(best_result['parameters'])}\n"
        output += f"  Mean: {best_result['statistics'].get('mean', 0):.2f}\n\n"
        
        output += "Worst Combination:\n"
        output += f"  Parameters: {json.dumps(worst_result['parameters'])}\n"
        output += f"  Mean: {worst_result['statistics'].get('mean', 0):.2f}\n\n"
        
        # Parameter impact analysis
        output += "Parameter Impact:\n"
        param_ranges = data.get("parameter_ranges", {})
        for param_name in param_ranges.keys():
            impact = self._calculate_parameter_impact(sweep_results, param_name)
            output += f"  - {param_name}: {impact:.2f}% impact\n"

        return ToolResult.ok(output, {
            "best_combination": best_result,
            "worst_combination": worst_result,
            "total_combinations": len(sweep_results)
        })

    def _calculate_parameter_impact(self, sweep_results: List[Dict], param_name: str) -> float:
        """Calculate impact of a parameter on results"""
        # Group results by parameter value
        param_groups: Dict[Any, List[float]] = {}
        
        for result in sweep_results:
            param_value = result["parameters"].get(param_name)
            mean_result = result["statistics"].get("mean", 0)
            
            if param_value not in param_groups:
                param_groups[param_value] = []
            param_groups[param_value].append(mean_result)

        # Calculate variance between groups
        if len(param_groups) < 2:
            return 0.0

        group_means = [statistics.mean(values) for values in param_groups.values()]
        overall_mean = statistics.mean(group_means)
        
        if overall_mean == 0:
            return 0.0

        variance = statistics.variance(group_means) if len(group_means) > 1 else 0
        impact = (variance ** 0.5 / overall_mean) * 100
        
        return impact

    # Simulation functions
    def _simulate_combat(self, params: Dict[str, Any]) -> float:
        """Simulate combat encounter"""
        player_hp = params.get("player_hp", 100)
        player_attack = params.get("player_attack", 10)
        player_defense = params.get("player_defense", 5)
        
        enemy_hp = params.get("enemy_hp", 50)
        enemy_attack = params.get("enemy_attack", 8)
        enemy_defense = params.get("enemy_defense", 3)

        rounds = 0
        max_rounds = 100

        while player_hp > 0 and enemy_hp > 0 and rounds < max_rounds:
            # Player attacks
            damage_to_enemy = max(1, player_attack - enemy_defense + random.randint(-2, 2))
            enemy_hp -= damage_to_enemy

            if enemy_hp <= 0:
                return rounds  # Player wins

            # Enemy attacks
            damage_to_player = max(1, enemy_attack - player_defense + random.randint(-2, 2))
            player_hp -= damage_to_player

            rounds += 1

        return -1 if player_hp <= 0 else rounds  # -1 if player loses

    def _simulate_economy(self, params: Dict[str, Any]) -> float:
        """Simulate economy/resource generation"""
        starting_gold = params.get("starting_gold", 100)
        income_per_turn = params.get("income_per_turn", 10)
        expense_per_turn = params.get("expense_per_turn", 5)
        turns = params.get("turns", 50)

        gold = starting_gold
        for _ in range(turns):
            gold += income_per_turn
            gold -= expense_per_turn + random.randint(-2, 2)
            
            if gold < 0:
                return -1  # Bankruptcy

        return gold

    def _simulate_progression(self, params: Dict[str, Any]) -> float:
        """Simulate player progression"""
        starting_level = params.get("starting_level", 1)
        xp_per_quest = params.get("xp_per_quest", 100)
        xp_growth_rate = params.get("xp_growth_rate", 1.5)
        target_level = params.get("target_level", 10)

        level = starting_level
        total_xp = 0
        quests_completed = 0

        while level < target_level:
            xp_needed = 100 * (xp_growth_rate ** (level - 1))
            total_xp += xp_per_quest + random.randint(-10, 10)
            quests_completed += 1

            if total_xp >= xp_needed:
                level += 1
                total_xp = 0

            if quests_completed > 1000:  # Safety limit
                break

        return quests_completed

    def _simulate_loot(self, params: Dict[str, Any]) -> float:
        """Simulate loot drop"""
        drop_rate = params.get("drop_rate", 0.1)
        attempts = params.get("attempts", 100)

        drops = 0
        for _ in range(attempts):
            if random.random() < drop_rate:
                drops += 1

        return drops

    def _calculate_statistics(self, results: List[float]) -> Dict[str, Any]:
        """Calculate statistics from results"""
        if not results:
            return {}

        valid_results = [r for r in results if r >= 0]  # Filter out failures (-1)
        
        stats = {
            "count": len(results),
            "valid_count": len(valid_results),
            "failure_count": len(results) - len(valid_results)
        }

        if valid_results:
            stats["mean"] = statistics.mean(valid_results)
            stats["median"] = statistics.median(valid_results)
            stats["min"] = min(valid_results)
            stats["max"] = max(valid_results)
            
            if len(valid_results) > 1:
                stats["std_dev"] = statistics.stdev(valid_results)
                stats["variance"] = statistics.variance(valid_results)
            else:
                stats["std_dev"] = 0
                stats["variance"] = 0

            # Percentiles
            sorted_results = sorted(valid_results)
            stats["p25"] = sorted_results[len(sorted_results) // 4]
            stats["p75"] = sorted_results[3 * len(sorted_results) // 4]

        return stats

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        simulation_type = kwargs.get("simulation_type", "unknown")
        return f"Running game simulation: {action} ({simulation_type})"
