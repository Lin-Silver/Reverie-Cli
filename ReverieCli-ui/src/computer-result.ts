export type ComputerResult = { label: string; target: string; retry: string; path?: string; error: boolean };

export function parseComputerResult(text: string): ComputerResult | null {
  try {
    const value = JSON.parse(text.replace(/^Error:\s*/, '').split('\nMedia:')[0]);
    if (value.version !== '2.6' || typeof value.ok !== 'boolean') return null;
    const data = value.ok ? value.data : value.error;
    if (!data || typeof data !== 'object') return null;
    const disposition = data.disposition || data.after_action?.disposition;
    const labels: Record<string, string> = {
      delivered_verified: '已验证操作效果', delivered_unverified: '已发送，尚未验证',
      delivery_uncertain: '操作结果不确定', unknown: '操作结果不确定', not_delivered: '未发送操作',
    };
    const observation = /^(status|permissions|list-|snapshot|find|get$|is$|screenshot|wait|clipboard-get)/.test(value.command || '');
    const label = labels[disposition?.delivery] || (value.ok ? (observation ? '已获取界面信息' : '操作已返回，需验证效果') : '执行失败');
    const target = data.window?.title || data.target?.title || data.surfaces?.[0]?.title || data.target?.ref || data.target?.window_id || data.target?.kind || data.app || '';
    return { label, target: String(target), retry: String(disposition?.retry || ''),
      path: typeof data.path === 'string' && /\.png$/i.test(data.path) ? data.path : undefined, error: !value.ok };
  } catch { return null; }
}
