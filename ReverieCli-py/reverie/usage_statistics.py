"""Token dashboards and user-supplied price estimates over local request ledgers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
import csv
import io
import json
import math
import sqlite3

from .session.workspace_stats import WorkspaceStatsManager


def _pricing_path(app_root: Path) -> Path:
    return Path(app_root) / '.reverie' / 'token_prices.sqlite3'


def model_token_prices(app_root: Path) -> dict:
    path = _pricing_path(app_root)
    if not path.exists():
        return {}
    with sqlite3.connect(path, timeout=30) as database:
        return {row[0]: json.loads(row[1]) for row in database.execute('SELECT model_key, payload FROM prices')}


def set_model_token_price(app_root: Path, model_key: str, price: dict) -> dict:
    key = str(model_key or '').strip()
    if not key:
        raise ValueError('Select a model before saving its prices.')
    currency = str(price.get('currency') or '').upper()
    if currency not in {'USD', 'CNY'}:
        raise ValueError('Currency must be USD or CNY.')
    rates = {}
    for field in ('input', 'cached_input', 'output'):
        try:
            value = float(price[field])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Enter an input, cached input and output price per million tokens.') from None
        if not math.isfinite(value) or value < 0:
            raise ValueError('Token prices must be finite, nonnegative numbers.')
        rates[field] = value
    saved = {**rates, 'currency': currency, 'per_tokens': 1000000, 'updated_at': datetime.now(timezone.utc).isoformat()}
    path = _pricing_path(app_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as database:
        database.execute('CREATE TABLE IF NOT EXISTS prices (model_key TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        database.execute('INSERT INTO prices VALUES (?, ?) ON CONFLICT(model_key) DO UPDATE SET payload=excluded.payload', (key, json.dumps(saved)))
    return saved


def _empty_totals() -> dict:
    return {**{key: 0 for key in ('calls', 'input_tokens', 'uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'total_tokens',
                                  'api_calls', 'mixed_calls', 'local_calls', 'historical_calls', 'unknown_cache_calls', 'unpriced_calls')}, 'costs': {}}


def _add(totals: dict, row: dict) -> None:
    calls = row.get('calls', 1)
    for key in ('input_tokens', 'uncached_input_tokens', 'output_tokens', 'total_tokens'):
        totals[key] += row[key]
    totals['calls'] += calls
    totals['cached_input_tokens'] += row.get('cached_input_tokens') or 0
    totals[row['usage_source'] + '_calls'] += calls
    if row.get('cached_input_tokens') is None:
        totals['unknown_cache_calls'] += calls
    if row['estimated_cost'] is None:
        totals['unpriced_calls'] += calls
    else:
        currency = row['currency']
        totals['costs'][currency] = totals['costs'].get(currency, 0) + row['estimated_cost']


def build_usage_report(app_root: Path, *, current: WorkspaceStatsManager | None = None, filters: dict | None = None) -> dict:
    filters = {key: str(value or '').strip() for key, value in (filters or {}).items() if key in {'start', 'end', 'project', 'session', 'model'}}
    for key in ('start', 'end'):
        if filters.get(key):
            try:
                date.fromisoformat(filters[key])
            except ValueError:
                raise ValueError('Dates must use YYYY-MM-DD (UTC).') from None
    if filters.get('start') and filters.get('end') and filters['start'] > filters['end']:
        raise ValueError('Start date must precede end date.')
    managers = {str(current.database_path): current} if current is not None else {}
    warnings = []
    for workspace in WorkspaceStatsManager.discover_workspaces(app_root):
        path = str(Path(workspace['cache_dir']) / 'workspace_stats.sqlite3')
        if path not in managers:
            try:
                managers[path] = WorkspaceStatsManager.from_cache_dir(Path(workspace['cache_dir']))
            except (OSError, sqlite3.Error, ValueError):
                warnings.append('Could not read workspace statistics: ' + workspace['cache_dir'])
    prices = model_token_prices(app_root)
    records = []
    projects, sessions, model_options = {}, {}, {}
    for manager in managers.values():
        project_id = manager.state.workspace_id
        project_name = manager.state.workspace_name
        projects[project_id] = {'id': project_id, 'name': project_name, 'path': manager.state.workspace_path}
        for entry in manager.model_requests():
            model_key = entry['provider'] + '::' + entry['model']
            model_options[model_key] = {'id': model_key, 'name': entry['model_display_name'] or entry['model'], 'provider': entry['provider']}
            session_key = project_id + '::' + entry['session_id'] if entry.get('session_id') else ''
            if session_key:
                sessions[session_key] = {'id': session_key, 'session_id': entry['session_id'], 'name': entry.get('session_name') or entry['session_id'], 'project_id': project_id, 'project_name': project_name}
            cached = entry.get('cached_input_tokens')
            uncached = max(entry['input_tokens'] - (cached or 0), 0)
            price = prices.get(model_key)
            cost = (uncached * price['input'] + (cached or 0) * price['cached_input'] + entry['output_tokens'] * price['output']) / 1000000 if price else None
            records.append({**entry, 'model_key': model_key, 'project_id': project_id, 'project_name': project_name,
                            'session_key': session_key, 'uncached_input_tokens': uncached, 'currency': price['currency'] if price else '', 'estimated_cost': cost})
    totals, models, daily = _empty_totals(), {}, {}
    selected = []
    excluded_historical_calls = 0
    for row in records:
        if filters.get('project') and filters['project'] != row['project_id']:
            continue
        if filters.get('model') and filters['model'] != row['model_key']:
            continue
        if row['usage_source'] == 'historical' and any(filters.get(key) for key in ('start', 'end', 'session')):
            excluded_historical_calls += row['calls']
            continue
        if filters.get('session') and filters['session'] not in {row['session_id'], row['session_key']}:
            continue
        day = str(row.get('occurred_at') or '')[:10]
        if filters.get('start') and day < filters['start'] or filters.get('end') and day > filters['end']:
            continue
        selected.append(row)
        _add(totals, row)
        model = models.setdefault(row['model_key'], {**_empty_totals(), 'model_key': row['model_key'], 'model': row['model'],
                                                    'name': row['model_display_name'] or row['model'], 'provider': row['provider'], 'price': prices.get(row['model_key'])})
        _add(model, row)
        if day:
            _add(daily.setdefault(day, {**_empty_totals(), 'date': day}), row)
    return {'filters': filters, 'totals': totals, 'models': sorted(models.values(), key=lambda item: (-item['total_tokens'], item['model_key'])),
            'daily': sorted(daily.values(), key=lambda item: item['date']), 'records': selected, 'prices': prices,
            'options': {'projects': sorted(projects.values(), key=lambda item: item['name']),
                        'sessions': sorted(sessions.values(), key=lambda item: (item['project_name'], item['name'])),
                        'models': sorted(model_options.values(), key=lambda item: (item['name'], item['provider']))},
            'excluded_historical_calls': excluded_historical_calls, 'warnings': warnings, 'timezone': 'UTC'}


def usage_csv(report: dict) -> str:
    fields = ('occurred_at', 'project_name', 'project_id', 'session_name', 'session_id', 'provider', 'model', 'model_display_name',
              'calls', 'input_tokens', 'uncached_input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_tokens', 'cache_creation_tokens',
              'total_tokens', 'usage_source', 'input_source', 'output_source', 'total_source', 'currency', 'estimated_cost')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in report['records']:
        cells = {field: row.get(field) for field in fields}
        for key, value in cells.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                cells[key] = "'" + value
        writer.writerow(cells)
    return output.getvalue()
