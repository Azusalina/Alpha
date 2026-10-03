/**
 * English strings (the default language, D67). The key set is defined here;
 * `zh.ts` must provide every key (the type enforces it). Keys are grouped by
 * the part of the UI that shows them.
 */

export const en = {
  'lang.switch': 'Switch language: English / 中文',

  // parameters (the 13 the model fits)
  'param.value.autonomy': 'Autonomy',
  'param.value.fairness': 'Fairness',
  'param.value.care': 'Care',
  'param.value.truth': 'Truth',
  'param.value.security': 'Security',
  'param.value.growth': 'Growth',
  'param.value.achievement': 'Achievement',
  'param.value.connection': 'Connection',
  'param.affect.disappointment': 'Disappointment',
  'param.affect.sadness': 'Sadness',
  'param.affect.happiness': 'Happiness',
  'param.affect.anger': 'Anger',
  'param.expression.less_initiative': 'Less initiative',

  // the ball page
  'ball.title': 'Model fit',
  'ball.sub': 'Example data · not connected to your model yet',
  'ball.back': '← Back',
  'ball.back.aria': 'Back to the particle brain',
  'ball.divider': 'Back to the brain ↻',
  'ball.look.aria': 'Switch look (current look {n})',
  'ball.look.1': 'Switch to look 2 ({name})',
  'ball.look.2': 'Switch to look 1 (monochrome lines)',
  'ball.look.name.dark': 'dark gold',
  'ball.look.name.light': 'black outline',
  'ball.dash.aria': 'Dashboard (example data)',
  'ball.legend.ripple': 'Ripples',
  'ball.legend.ripple.note': 'How well the model fits you here',
  'ball.legend.spike': 'Spikes',
  'ball.legend.spike.note': 'Fit concentrated in a few strong statements',
  'ball.cell.fitted': 'Facets fitted',
  'ball.cell.spikes': 'Spikes',
  'ball.cell.mean': 'Mean fit',
  'ball.cell.thin': 'Thin evidence',
  'ball.tip.ripple': 'Ripples {pct}%: how well the model fits you on “{name}”. The more approved inputs back it, the stronger the ripples.',
  'ball.tip.ripple.none': 'No ripples yet: the model has no evidence about “{name}”.',
  'ball.tip.spike': 'Spike {pct}%: here the fit is concentrated in a few strong statements rather than spread over many.',
  'ball.tip.nospike': 'No spike: the fit here is spread evenly.',
  'ball.hint.drag': 'Hover a ripple or a spike to read it · drag to tilt',
  'ball.demo': 'EXAMPLE',

  // transition
  'fx.skip': 'Skip',
} as const;

export type Key = keyof typeof en;
