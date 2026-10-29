// One collector for ordinary response aliases and ordered SSE tool results.
export function collectAgentResults(payload, previous = []) {
  const results = [...previous];
  const add = value => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return;
    if (Array.isArray(value.results)) value.results.forEach(add);
    if (typeof value.type === 'string' && !['normal', 'agent'].includes(value.type)) {
      const result = value.data && typeof value.data === 'object' && !Array.isArray(value.data)
        ? { ...value.data, ...value } : value;
      // data/result aliases are the same tool result, not another list item.
      if (!results.some(item => JSON.stringify(item) === JSON.stringify(result))) results.push(result);
    } else {
      add(value.data);
      add(value.result);
    }
  };
  add(payload);
  return results;
}

export function agentResultItems(result) {
  if (result?.type === 'person_query') return Array.isArray(result.state === 'waiting_input' ? result.candidates : result.hits)
    ? (result.state === 'waiting_input' ? result.candidates : result.hits) : [];
  for (const key of ['items', 'segments', 'candidates', 'hits', 'sources']) {
    if (Array.isArray(result?.[key])) return result[key];
  }
  return [];
}

export function agentResultTitle(result) {
  return ({ person_query: '图片查人', person_selection: '已选查询目标',
    person_activities: '人员活动', person_route: '人员路线报告', person_playback: '录像回放',
    person_directory: '人员名单', person_tracklets: '人员轨迹', report_search: '报告',
    event_search: '事件', business_selection: '已选对象', sources: '视频来源',
    time_parse: '查询时间', super_resolution: '图片放大', business_error: '查询未完成' })[result?.type];
}
