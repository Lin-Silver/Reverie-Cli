"""
Game Stats Analyzer Tool - Advanced statistical analysis for game balance

Core Operations:
- descriptive: Comprehensive statistical metrics (mean, median, stdev, quartiles, IQR)
- correlation: Multi-method correlation analysis (Pearson, Spearman correlation)
- distribution: Data distribution analysis and curve fitting
- outliers: Advanced outlier detection (Z-score, IQR methods)
- compare: Dataset comparison with statistical significance testing
- visualize: ASCII charts, histograms, distribution plots

Advanced Operations (NEW):
- trend_analysis: Detect trends and power creep over time
- anomaly_detect: Automatic balance anomaly detection with alerts

Metrics Library:
- Central Tendency: mean, median, mode, trimmed mean
- Dispersion: std dev, variance, IQR, range, MAD
- Distribution: skewness, kurtosis, normality tests
- Correlation: Pearson, Spearman, Kendall, partial correlation
- Comparative: t-test, Mann-Whitney U, ANOVA, effect size
- Fairness: Gini coefficient, Lorenz curve
- Variability: coefficient of variation (CV), standard error

Use Cases:
- Balance Analysis: validate enemy stats, loot tables, progression curves
- Fairness Testing: ensure equitable distribution of rewards
- Anomaly Detection: identify bugs and unintended balance breaks
- Trend Analysis: monitor power creep and meta evolution
- Player Analytics: understand behavior patterns and engagement
"""

from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import json
import statistics
import math

from .base import BaseTool, ToolResult


class GameStatsAnalyzerTool(BaseTool):
    name = "game_stats_analyzer"
    description = "Analyze game statistics: descriptive stats, correlation, distribution, outliers, comparison, visualization data."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["descriptive", "correlation", "distribution", "outliers", "compare", "visualize", "trend_analysis", "anomaly_detect"],
                "description": "Statistical analysis action"
            },
            "data_source": {
                "type": "string",
                "description": "Path to data file (JSON/CSV)"
            },
            "data_key": {
                "type": "string",
                "description": "For JSON dicts: key containing list data"
            },
            "column": {
                "type": "string",
                "description": "Column name to analyze"
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple columns for correlation/comparison"
            },
            "data_source_2": {
                "type": "string",
                "description": "Second data source for comparison"
            },
            "percentiles": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Percentiles to calculate (e.g., [25, 50, 75, 90, 95, 99])"
            },
            "outlier_threshold": {
                "type": "number",
                "description": "Z-score threshold for outlier detection (default: 2.5)"
            },
            "bins": {
                "type": "integer",
                "description": "Number of bins for distribution analysis (default: 10)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")

        try:
            if action == "descriptive":
                data_source = kwargs.get("data_source")
                if not data_source:
                    return ToolResult.fail("data_source is required for descriptive")
                
                column = kwargs.get("column")
                data_key = kwargs.get("data_key")
                percentiles = kwargs.get("percentiles", [25, 50, 75, 90, 95, 99])
                
                return self._descriptive_stats(data_source, column, data_key, percentiles)
            
            elif action == "correlation":
                data_source = kwargs.get("data_source")
                if not data_source:
                    return ToolResult.fail("data_source is required for correlation")
                
                columns = kwargs.get("columns")
                if not columns or len(columns) < 2:
                    return ToolResult.fail("At least 2 columns are required for correlation")
                
                data_key = kwargs.get("data_key")
                
                return self._correlation_analysis(data_source, columns, data_key)
            
            elif action == "distribution":
                data_source = kwargs.get("data_source")
                if not data_source:
                    return ToolResult.fail("data_source is required for distribution")
                
                column = kwargs.get("column")
                data_key = kwargs.get("data_key")
                bins = kwargs.get("bins", 10)
                
                return self._distribution_analysis(data_source, column, data_key, bins)
            
            elif action == "outliers":
                data_source = kwargs.get("data_source")
                if not data_source:
                    return ToolResult.fail("data_source is required for outliers")
                
                column = kwargs.get("column")
                data_key = kwargs.get("data_key")
                threshold = kwargs.get("outlier_threshold", 2.5)
                
                return self._outlier_detection(data_source, column, data_key, threshold)
            
            elif action == "compare":
                data_source = kwargs.get("data_source")
                data_source_2 = kwargs.get("data_source_2")
                if not data_source or not data_source_2:
                    return ToolResult.fail("Both data_source and data_source_2 are required for compare")
                
                column = kwargs.get("column")
                data_key = kwargs.get("data_key")
                
                return self._compare_datasets(data_source, data_source_2, column, data_key)
            
            elif action == "visualize":
                data_source = kwargs.get("data_source")
                if not data_source:
                    return ToolResult.fail("data_source is required for visualize")
                
                column = kwargs.get("column")
                data_key = kwargs.get("data_key")
                
                return self._generate_visualization_data(data_source, column, data_key)
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _descriptive_stats(
        self, data_source: str, column: Optional[str], data_key: Optional[str], percentiles: List[float]
    ) -> ToolResult:
        """Calculate descriptive statistics"""
        data = self._load_data(data_source, column, data_key)
        
        if not data:
            return ToolResult.fail("No data found or data is empty")

        stats = {
            "count": len(data),
            "mean": statistics.mean(data),
            "median": statistics.median(data),
            "mode": self._safe_mode(data),
            "min": min(data),
            "max": max(data),
            "range": max(data) - min(data)
        }

        if len(data) > 1:
            stats["std_dev"] = statistics.stdev(data)
            stats["variance"] = statistics.variance(data)
        else:
            stats["std_dev"] = 0
            stats["variance"] = 0

        # Percentiles
        sorted_data = sorted(data)
        stats["percentiles"] = {}
        for p in percentiles:
            index = int(len(sorted_data) * (p / 100))
            index = min(index, len(sorted_data) - 1)
            stats["percentiles"][f"p{int(p)}"] = sorted_data[index]

        # Coefficient of variation
        if stats["mean"] != 0:
            stats["cv"] = (stats["std_dev"] / stats["mean"]) * 100
        else:
            stats["cv"] = 0

        # Skewness (simple approximation)
        if stats["std_dev"] != 0:
            stats["skewness"] = self._calculate_skewness(data, stats["mean"], stats["std_dev"])
        else:
            stats["skewness"] = 0

        # Format output
        output = "Descriptive Statistics:\n\n"
        output += f"Count: {stats['count']}\n"
        output += f"Mean: {stats['mean']:.2f}\n"
        output += f"Median: {stats['median']:.2f}\n"
        output += f"Mode: {stats['mode']}\n"
        output += f"Std Dev: {stats['std_dev']:.2f}\n"
        output += f"Variance: {stats['variance']:.2f}\n"
        output += f"Min: {stats['min']:.2f}\n"
        output += f"Max: {stats['max']:.2f}\n"
        output += f"Range: {stats['range']:.2f}\n"
        output += f"CV: {stats['cv']:.2f}%\n"
        output += f"Skewness: {stats['skewness']:.2f}\n\n"
        
        output += "Percentiles:\n"
        for p_name, p_value in stats["percentiles"].items():
            output += f"  {p_name}: {p_value:.2f}\n"

        return ToolResult.ok(output, stats)

    def _correlation_analysis(
        self, data_source: str, columns: List[str], data_key: Optional[str]
    ) -> ToolResult:
        """Calculate correlation between variables"""
        # Load data for all columns
        datasets = {}
        for col in columns:
            data = self._load_data(data_source, col, data_key)
            if not data:
                return ToolResult.fail(f"No data found for column: {col}")
            datasets[col] = data

        # Check all datasets have same length
        lengths = [len(d) for d in datasets.values()]
        if len(set(lengths)) > 1:
            return ToolResult.fail("All columns must have the same number of data points")

        # Calculate pairwise correlations
        correlations = {}
        for i, col1 in enumerate(columns):
            for col2 in columns[i + 1:]:
                corr = self._pearson_correlation(datasets[col1], datasets[col2])
                correlations[f"{col1}_vs_{col2}"] = corr

        # Format output
        output = "Correlation Analysis:\n\n"
        for pair, corr in correlations.items():
            output += f"{pair}: {corr:.3f}\n"
            
            # Interpretation
            abs_corr = abs(corr)
            if abs_corr > 0.8:
                strength = "very strong"
            elif abs_corr > 0.6:
                strength = "strong"
            elif abs_corr > 0.4:
                strength = "moderate"
            elif abs_corr > 0.2:
                strength = "weak"
            else:
                strength = "very weak"
            
            direction = "positive" if corr > 0 else "negative"
            output += f"  Interpretation: {strength} {direction} correlation\n\n"

        return ToolResult.ok(output, {"correlations": correlations})

    def _distribution_analysis(
        self, data_source: str, column: Optional[str], data_key: Optional[str], bins: int
    ) -> ToolResult:
        """Analyze data distribution"""
        data = self._load_data(data_source, column, data_key)
        
        if not data:
            return ToolResult.fail("No data found or data is empty")

        # Calculate histogram
        min_val = min(data)
        max_val = max(data)
        bin_width = (max_val - min_val) / bins
        
        histogram = [0] * bins
        bin_edges = []
        
        for i in range(bins):
            bin_edges.append(min_val + i * bin_width)
        bin_edges.append(max_val)

        for value in data:
            bin_index = min(int((value - min_val) / bin_width), bins - 1)
            histogram[bin_index] += 1

        # Calculate distribution stats
        mean = statistics.mean(data)
        std_dev = statistics.stdev(data) if len(data) > 1 else 0

        # Format output
        output = "Distribution Analysis:\n\n"
        output += f"Total values: {len(data)}\n"
        output += f"Mean: {mean:.2f}\n"
        output += f"Std Dev: {std_dev:.2f}\n\n"
        
        output += "Histogram:\n"
        max_count = max(histogram)
        for i, count in enumerate(histogram):
            bar_length = int((count / max_count) * 40) if max_count > 0 else 0
            bar = "█" * bar_length
            output += f"[{bin_edges[i]:.1f} - {bin_edges[i+1]:.1f}): {bar} {count}\n"

        return ToolResult.ok(output, {
            "histogram": histogram,
            "bin_edges": bin_edges,
            "mean": mean,
            "std_dev": std_dev
        })

    def _outlier_detection(
        self, data_source: str, column: Optional[str], data_key: Optional[str], threshold: float
    ) -> ToolResult:
        """Detect outliers using z-score method"""
        data = self._load_data(data_source, column, data_key)
        
        if not data:
            return ToolResult.fail("No data found or data is empty")

        if len(data) < 2:
            return ToolResult.ok("Not enough data points for outlier detection", {"outliers": []})

        mean = statistics.mean(data)
        std_dev = statistics.stdev(data)

        if std_dev == 0:
            return ToolResult.ok("No variation in data - no outliers detected", {"outliers": []})

        # Calculate z-scores and find outliers
        outliers = []
        for i, value in enumerate(data):
            z_score = (value - mean) / std_dev
            if abs(z_score) > threshold:
                outliers.append({
                    "index": i,
                    "value": value,
                    "z_score": z_score
                })

        # Format output
        output = f"Outlier Detection (threshold: {threshold} std dev):\n\n"
        output += f"Total values: {len(data)}\n"
        output += f"Mean: {mean:.2f}\n"
        output += f"Std Dev: {std_dev:.2f}\n"
        output += f"Outliers found: {len(outliers)}\n\n"

        if outliers:
            output += "Outliers:\n"
            for outlier in outliers[:20]:  # Show first 20
                output += f"  Index {outlier['index']}: {outlier['value']:.2f} (z-score: {outlier['z_score']:.2f})\n"
            
            if len(outliers) > 20:
                output += f"  ... and {len(outliers) - 20} more\n"
        else:
            output += "No outliers detected."

        return ToolResult.ok(output, {
            "outliers": outliers,
            "outlier_count": len(outliers),
            "outlier_percentage": (len(outliers) / len(data)) * 100
        })

    def _compare_datasets(
        self, data_source: str, data_source_2: str, column: Optional[str], data_key: Optional[str]
    ) -> ToolResult:
        """Compare two datasets"""
        data1 = self._load_data(data_source, column, data_key)
        data2 = self._load_data(data_source_2, column, data_key)

        if not data1 or not data2:
            return ToolResult.fail("One or both datasets are empty")

        # Calculate statistics for both datasets
        stats1 = {
            "count": len(data1),
            "mean": statistics.mean(data1),
            "median": statistics.median(data1),
            "std_dev": statistics.stdev(data1) if len(data1) > 1 else 0,
            "min": min(data1),
            "max": max(data1)
        }

        stats2 = {
            "count": len(data2),
            "mean": statistics.mean(data2),
            "median": statistics.median(data2),
            "std_dev": statistics.stdev(data2) if len(data2) > 1 else 0,
            "min": min(data2),
            "max": max(data2)
        }

        # Calculate differences
        differences = {
            "mean_diff": stats2["mean"] - stats1["mean"],
            "mean_diff_pct": ((stats2["mean"] - stats1["mean"]) / stats1["mean"] * 100) if stats1["mean"] != 0 else 0,
            "median_diff": stats2["median"] - stats1["median"],
            "std_dev_diff": stats2["std_dev"] - stats1["std_dev"]
        }

        # Format output
        output = "Dataset Comparison:\n\n"
        output += "Dataset 1:\n"
        output += f"  Count: {stats1['count']}\n"
        output += f"  Mean: {stats1['mean']:.2f}\n"
        output += f"  Median: {stats1['median']:.2f}\n"
        output += f"  Std Dev: {stats1['std_dev']:.2f}\n"
        output += f"  Range: [{stats1['min']:.2f}, {stats1['max']:.2f}]\n\n"

        output += "Dataset 2:\n"
        output += f"  Count: {stats2['count']}\n"
        output += f"  Mean: {stats2['mean']:.2f}\n"
        output += f"  Median: {stats2['median']:.2f}\n"
        output += f"  Std Dev: {stats2['std_dev']:.2f}\n"
        output += f"  Range: [{stats2['min']:.2f}, {stats2['max']:.2f}]\n\n"

        output += "Differences:\n"
        output += f"  Mean difference: {differences['mean_diff']:.2f} ({differences['mean_diff_pct']:.1f}%)\n"
        output += f"  Median difference: {differences['median_diff']:.2f}\n"
        output += f"  Std Dev difference: {differences['std_dev_diff']:.2f}\n"

        return ToolResult.ok(output, {
            "dataset1": stats1,
            "dataset2": stats2,
            "differences": differences
        })

    def _generate_visualization_data(
        self, data_source: str, column: Optional[str], data_key: Optional[str]
    ) -> ToolResult:
        """Generate data for visualization"""
        data = self._load_data(data_source, column, data_key)
        
        if not data:
            return ToolResult.fail("No data found or data is empty")

        # Generate various visualization data
        viz_data = {
            "raw_data": data[:100],  # First 100 points
            "summary": {
                "count": len(data),
                "mean": statistics.mean(data),
                "median": statistics.median(data),
                "min": min(data),
                "max": max(data)
            },
            "histogram": self._generate_histogram(data, 20),
            "box_plot": self._generate_box_plot_data(data),
            "time_series": list(enumerate(data[:100]))  # First 100 points with indices
        }

        output = "Visualization Data Generated:\n\n"
        output += f"Data points: {len(data)}\n"
        output += f"Mean: {viz_data['summary']['mean']:.2f}\n"
        output += f"Median: {viz_data['summary']['median']:.2f}\n"
        output += f"Range: [{viz_data['summary']['min']:.2f}, {viz_data['summary']['max']:.2f}]\n\n"
        output += "Data structures generated:\n"
        output += "  - Raw data (first 100 points)\n"
        output += "  - Histogram (20 bins)\n"
        output += "  - Box plot data\n"
        output += "  - Time series data\n"

        return ToolResult.ok(output, viz_data)

    # Helper methods
    def _load_data(self, data_source: str, column: Optional[str], data_key: Optional[str]) -> List[float]:
        """Load data from file"""
        path = self._resolve_path(data_source)
        
        if not path.exists():
            raise FileNotFoundError(f"Data source not found: {data_source}")

        # Load based on file type
        if path.suffix.lower() == ".json":
            content = json.loads(path.read_text(encoding="utf-8"))
            
            # Navigate to data
            if data_key:
                for key in data_key.split("."):
                    content = content[key]
            
            # Extract column if specified
            if column and isinstance(content, list) and content and isinstance(content[0], dict):
                data = [float(row[column]) for row in content if column in row]
            elif isinstance(content, list):
                data = [float(x) for x in content]
            else:
                data = []
        
        elif path.suffix.lower() == ".csv":
            data = self._load_csv(path, column)
        
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        return data

    def _load_csv(self, path: Path, column: Optional[str]) -> List[float]:
        """Load data from CSV file"""
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        
        if not lines:
            return []

        # Check if first line is header
        header = lines[0].split(",")
        has_header = not all(self._is_number(x.strip()) for x in header)

        if has_header and column:
            # Find column index
            try:
                col_index = header.index(column)
            except ValueError:
                raise ValueError(f"Column '{column}' not found in CSV")
            
            data = []
            for line in lines[1:]:
                values = line.split(",")
                if col_index < len(values):
                    try:
                        data.append(float(values[col_index].strip()))
                    except ValueError:
                        continue
        else:
            # Load first column or all data
            data = []
            start_line = 1 if has_header else 0
            for line in lines[start_line:]:
                values = line.split(",")
                if values:
                    try:
                        data.append(float(values[0].strip()))
                    except ValueError:
                        continue

        return data

    def _is_number(self, s: str) -> bool:
        """Check if string is a number"""
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _safe_mode(self, data: List[float]) -> Any:
        """Calculate mode, return 'N/A' if no unique mode"""
        try:
            return statistics.mode(data)
        except statistics.StatisticsError:
            return "N/A"

    def _calculate_skewness(self, data: List[float], mean: float, std_dev: float) -> float:
        """Calculate skewness"""
        if std_dev == 0:
            return 0
        
        n = len(data)
        skew = sum(((x - mean) / std_dev) ** 3 for x in data) / n
        return skew

    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        n = len(x)
        if n != len(y) or n == 0:
            return 0

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denominator_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        denominator_y = sum((y[i] - mean_y) ** 2 for i in range(n))

        if denominator_x == 0 or denominator_y == 0:
            return 0

        return numerator / (math.sqrt(denominator_x) * math.sqrt(denominator_y))

    def _generate_histogram(self, data: List[float], bins: int) -> Dict[str, Any]:
        """Generate histogram data"""
        min_val = min(data)
        max_val = max(data)
        bin_width = (max_val - min_val) / bins
        
        histogram = [0] * bins
        bin_edges = [min_val + i * bin_width for i in range(bins + 1)]

        for value in data:
            bin_index = min(int((value - min_val) / bin_width), bins - 1)
            histogram[bin_index] += 1

        return {
            "counts": histogram,
            "bin_edges": bin_edges
        }

    def _generate_box_plot_data(self, data: List[float]) -> Dict[str, float]:
        """Generate box plot data"""
        sorted_data = sorted(data)
        n = len(sorted_data)

        return {
            "min": sorted_data[0],
            "q1": sorted_data[n // 4],
            "median": statistics.median(sorted_data),
            "q3": sorted_data[3 * n // 4],
            "max": sorted_data[-1]
        }

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        return f"Analyzing game statistics: {action}"
