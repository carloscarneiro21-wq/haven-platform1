import React from "react";

export const BreakoutHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">O que é Breakout Trading?</h3>
      <p>
        <strong>Breakout Trading</strong> é uma estratégia que identifica quando o preço
        "rompe" níveis importantes de suporte ou resistência. Estes rompimentos podem
        indicar o início de um movimento direcional forte.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Como funciona?</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Identifica níveis de <strong>resistência</strong> (máximos recentes) e <strong>suporte</strong> (mínimos recentes)</li>
        <li><strong>Compra</strong> quando: Preço rompe acima da resistência + Momentum positivo (MACD, ADX)</li>
        <li><strong>Vende</strong> quando: Preço rompe abaixo do suporte + Momentum negativo</li>
        <li>Usa <strong>ATR</strong> para definir stops e targets dinâmicos</li>
        <li><strong>Trailing Stop</strong> para maximizar ganhos em movimentos fortes</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Parâmetros</h3>
      <ul className="space-y-2">
        <li><strong>Lookback Periods:</strong> Quantos períodos analisar para encontrar níveis (default: 20)</li>
        <li><strong>Breakout Threshold %:</strong> % acima/abaixo do nível para confirmar rompimento</li>
        <li><strong>Min ADX:</strong> ADX mínimo para confirmar tendência (momentum)</li>
        <li><strong>Stop Loss ATR:</strong> Stop a X vezes o ATR do preço de entrada</li>
        <li><strong>Take Profit ATR:</strong> Target a X vezes o ATR</li>
      </ul>
    </section>

    <section className="bg-purple-500/10 border border-purple-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-purple-400 mb-2">🚀 Momentum</h3>
      <p>
        Este agente funciona melhor com <strong>momentum forte</strong>. Confirma breakouts
        com indicadores como MACD e ADX. Falsos breakouts são filtrados pelo requisito de
        momentum mínimo.
      </p>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p>
        Breakouts funcionam melhor após períodos de consolidação (baixa volatilidade).
        Quando o mercado está "comprimido", um breakout tende a ser mais explosivo.
        Combine com análise de volume para melhor confirmação.
      </p>
    </section>
  </div>
);

export const BreakoutPresets = {
  conservative: {
    tooltip: "Threshold alto, confirma bem antes de entrar. Menos falsos sinais.",
    values: {
      lookback_periods: 30,
      breakout_threshold_pct: 1.5,
      min_adx: 25,
      stop_loss_atr_mult: 2.5,
      take_profit_atr_mult: 4,
      position_size_pct: 3,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre capturar breakouts e evitar falsos sinais.",
    values: {
      lookback_periods: 20,
      breakout_threshold_pct: 1.0,
      min_adx: 20,
      stop_loss_atr_mult: 2,
      take_profit_atr_mult: 3,
      position_size_pct: 5,
    },
  },
  aggressive: {
    tooltip: "Entrada rápida em breakouts. Mais trades, mais risco.",
    values: {
      lookback_periods: 14,
      breakout_threshold_pct: 0.5,
      min_adx: 15,
      stop_loss_atr_mult: 1.5,
      take_profit_atr_mult: 2.5,
      position_size_pct: 8,
    },
  },
};

export const BreakoutTooltips = {
  lookback_periods: "Quantos períodos para identificar níveis de suporte/resistência.",
  breakout_threshold: "% acima/abaixo do nível para confirmar o breakout.",
  min_adx: "ADX mínimo para confirmar momentum. Filtra breakouts fracos.",
  stop_loss_atr: "Stop loss em múltiplos do ATR. Ex: 2 = stop a 2x ATR do entry.",
  take_profit_atr: "Target em múltiplos do ATR. Ex: 3 = target a 3x ATR do entry.",
  position_size: "Tamanho da posição em % do capital alocado.",
};

export default { BreakoutHelpContent, BreakoutPresets, BreakoutTooltips };
