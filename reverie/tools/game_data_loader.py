"""
Game Data Loader - Utilities for loading game data from various formats

Supports:
- JSON files with nested key navigation
- CSV files with automatic type conversion
- Multi-format data loading for balance analysis and stats

Used by: GameBalanceAnalyzerTool, GameStatsAnalyzerTool
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import csv


def load_table_data(
    file_path: Path,
    data_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Load table data from JSON or CSV file.
    
    Args:
        file_path: Path to data file
        data_key: For JSON dicts, key containing list data (supports dot notation for nested keys)
    
    Returns:
        List of dictionaries representing table rows
    
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is unsupported
    
    Examples:
        >>> # Load CSV file
        >>> rows = load_table_data(Path("enemies.csv"))
        
        >>> # Load JSON with nested key
        >>> rows = load_table_data(Path("data.json"), data_key="game.enemies")
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Data file not found: {file_path}")
    
    suffix = file_path.suffix.lower()
    
    if suffix == ".json":
        return _load_json_table(file_path, data_key)
    elif suffix == ".csv":
        return _load_csv_table(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")


def _load_json_table(file_path: Path, data_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load table data from JSON file"""
    content = json.loads(file_path.read_text(encoding="utf-8"))
    
    # Navigate to data using key path
    if data_key:
        for key in data_key.split("."):
            if isinstance(content, dict):
                content = content.get(key, [])
            else:
                break
    
    # Ensure we have a list
    if not isinstance(content, list):
        return []
    
    # Convert to list of dicts if needed
    result = []
    for item in content:
        if isinstance(item, dict):
            result.append(item)
        else:
            # Convert primitive to dict
            result.append({"value": item})
    
    return result


def _load_csv_table(file_path: Path) -> List[Dict[str, Any]]:
    """Load table data from CSV file"""
    rows = []
    
    with open(file_path, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric strings to numbers
            converted_row = {}
            for key, value in row.items():
                converted_row[key] = _try_convert_number(value)
            rows.append(converted_row)
    
    return rows


def _try_convert_number(value: str) -> Any:
    """Try to convert string to number, return original if not possible"""
    try:
        # Try int first
        if '.' not in value:
            return int(value)
        # Try float
        return float(value)
    except (ValueError, AttributeError):
        return value
