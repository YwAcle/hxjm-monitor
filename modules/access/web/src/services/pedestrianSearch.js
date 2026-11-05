export function getPedestrianSearchResult(payload) {
  for (const result of [payload?.data, payload]) {
    if (['pedestrian_search', 'pedestrian_selection'].includes(result?.type)) return result;
  }
  return null;
}

export function getPendingPedestrianSelection(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    // 新图提交后，旧截图的编号不能再用于选择。
    if (message.type === 'user' && message.image) return null;
    const result = message.pedestrianSearch;
    if (result) {
      return result.type === 'pedestrian_selection' && result.status === 'selection_required'
        ? message
        : null;
    }
  }
  return null;
}

export function getPedestrianSearchStatus(result) {
  switch (result.status) {
    case 'not_configured':
      return '登记库检索服务尚未配置，本次未执行匹配。';
    case 'no_compatible_features':
      return '登记库没有兼容的特征，本次无法完成匹配；不代表未找到此人。';
    case 'missing_image':
      return '请在本轮上传单人裁剪图后重新检索。';
    case 'invalid_image':
      return '查询图片无法解析，请重新上传单人裁剪图。';
    case 'no_person':
      return '截图中未检测到行人，请重新上传截图或裁剪单人人像后重试。';
    case 'selection_expired':
      return '待选择截图已过期或不存在，请重新上传截图。';
    case 'cancelled':
      return '已取消本次截图选择。';
    default:
      return Array.isArray(result.candidates) && result.candidates.length > 0
        ? ''
        : '本次检查的登记照片中暂无候选，不能据此排除该人员。';
  }
}

export function getRegistrationImageSrc(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  const image = value.trim();
  if (/^data:image\/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=\s]+$/i.test(image)) {
    return image;
  }
  if (/^[A-Za-z0-9+/=\s]+$/.test(image)) {
    return `data:image/jpeg;base64,${image.replace(/\s/g, '')}`;
  }
  return null;
}
