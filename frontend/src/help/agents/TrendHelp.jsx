import React from "react";

export const TrendHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">O que é Trend Following?</h3>
      <p>
        <strong>Trend Following</strong> é uma estratégia que identifica e segue tendências de mercado.
        Compra quando deteta uma tendência de alta e vende quando deteta reversão ou atinge objetivos.
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Como funciona?</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Analisa indicadores técnicos (médias móveis, momentum)</li>
        <li>Quando deteta sinal de entrada, abre posição</li>
        <li>Define <strong>Stop Loss</strong> para limitar perdas</li>
        <li>Define <strong>Take Profit</strong> para garantir ganhos</li>
        <li>Usa <strong>Trailing Stop</strong> para proteger lucros em tendências longas</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Parâmetros</h3>
      <ul className="space-y-2">
        <li><strong>Stop Loss %:</strong> Perda máxima aceite (ex: 5% = fecha se cair 5%)</li>
        <li><strong>Take Profit %:</strong> Objetivo de lucro (ex: 15% = fecha se subir 15%)</li>
        <li><strong>Trailing Stop %:</strong> Protege lucros seguindo o preço (ex: 3% abaixo do máximo)</li>
      </ul>
    </section>

    <section className="bg-blue-500/10 border border-blue-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-blue-400 mb-2">🎯 Seletividade</h3>
      <p>
        Este agente é <strong>seletivo</strong>: faz poucos trades mas com alta convicção.
        Pode passar dias sem operar, esperando pelo sinal certo. 
        <strong>Não forçar entradas</strong> é parte da estratégia.
      </p>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p>
        Combine com o DCA: enquanto o Trend espera por sinais, o DCA acumula lentamente.
        Isto dá-lhe exposição ao mercado sem depender apenas de timing.
      </p>
    </section>
  </div>
);

export const TrendPresets = {
  conservative: {
    tooltip: "Stop apertado, take profit moderado. Protege capital.",
    values: {
      stop_loss_pct: 3,
      take_profit_pct: 10,
      trailing_stop_pct: 2,
      trade_size_eur: 5,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre risco e recompensa.",
    values: {
      stop_loss_pct: 5,
      take_profit_pct: 15,
      trailing_stop_pct: 3,
      trade_size_eur: 8,
    },
  },
  aggressive: {
    tooltip: "Stop mais largo, objetivo maior. Para tendências fortes.",
    values: {
      stop_loss_pct: 8,
      take_profit_pct: 25,
      trailing_stop_pct: 5,
      trade_size_eur: 12,
    },
  },
};

export const TrendTooltips = {
  stop_loss: "Perda máxima aceite. Fecha posição se preço cair este %.",
  take_profit: "Objetivo de lucro. Fecha posição se preço subir este %.",
  trailing_stop: "Segue o preço. Protege lucros fechando se cair X% do máximo atingido.",
  position_size: "Tamanho da posição em % do capital alocado.",
};

export default { TrendHelpContent, TrendPresets, TrendTooltips };
