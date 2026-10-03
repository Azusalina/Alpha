/** 中文文案；键集合由 en.ts 定义，类型保证每个键都有。 */

import type { Key } from './en';

export const zh: Record<Key, string> = {
  'lang.switch': '切换语言：English / 中文',

  'param.value.autonomy': '自主',
  'param.value.fairness': '公平',
  'param.value.care': '关怀',
  'param.value.truth': '真实',
  'param.value.security': '安全',
  'param.value.growth': '成长',
  'param.value.achievement': '成就',
  'param.value.connection': '陪伴 / 联结',
  'param.affect.disappointment': '失望',
  'param.affect.sadness': '难过',
  'param.affect.happiness': '开心',
  'param.affect.anger': '生气',
  'param.expression.less_initiative': '更少主动联系',

  'ball.title': '模型拟合',
  'ball.sub': '示例数据 · 尚未连接你的模型',
  'ball.back': '← 返回',
  'ball.back.aria': '返回粒子大脑',
  'ball.divider': '回到大脑 ↻',
  'ball.look.aria': '切换效果（当前效果 {n}）',
  'ball.look.1': '切换到效果 2（{name}）',
  'ball.look.2': '切换到效果 1（单色线条）',
  'ball.look.name.dark': '暗金',
  'ball.look.name.light': '黑色轮廓',
  'ball.dash.aria': '仪表盘（示例数据）',
  'ball.legend.ripple': '波纹',
  'ball.legend.ripple.note': '模型在这里对你的拟合程度',
  'ball.legend.spike': '尖刺',
  'ball.legend.spike.note': '拟合集中在少数强烈的陈述上',
  'ball.cell.fitted': '已拟合方面',
  'ball.cell.spikes': '尖刺数',
  'ball.cell.mean': '平均拟合',
  'ball.cell.thin': '证据偏少',
  'ball.tip.ripple': '波纹 {pct}%：模型在「{name}」上对你的拟合程度。认可的输入越多，波纹越强。',
  'ball.tip.ripple.none': '还没有波纹：模型对「{name}」没有任何证据。',
  'ball.tip.spike': '尖刺 {pct}%：这里的拟合集中在少数强烈的陈述上，而不是分散在许多陈述里。',
  'ball.tip.nospike': '没有尖刺：这里的拟合是均匀分布的。',
  'ball.hint.drag': '悬停波纹或尖刺查看含义 · 拖动倾斜',
  'ball.demo': '示例',

  'fx.skip': '跳过',
};
