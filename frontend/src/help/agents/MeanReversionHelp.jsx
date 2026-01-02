import React from "react";

export const MeanReversionHelpContent = () => (
  <div className="space-y-4 text-zinc-300">
    <section>
      <h3 className="text-lg font-semibold text-white mb-2">O que é Mean Reversion?</h3>
      <p>
        <strong>Mean Reversion</strong> é uma estratégia baseada na ideia de que os preços tendem a
        voltar à sua média. Compra quando o preço está "barato" (oversold) e vende quando está "caro" (overbought).
      </p>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Como funciona?</h3>
      <ol className="list-decimal list-inside space-y-2">
        <li>Monitoriza o RSI e as Bandas de Bollinger</li>
        <li><strong>Compra</strong> quando: RSI &lt; 30 (oversold) + Preço na banda inferior</li>
        <li><strong>Vende</strong> quando: RSI &gt; 70 (overbought) + Preço na banda superior</li>
        <li>Fecha posição quando o preço volta à <strong>banda média</strong> (média móvel)</li>
        <li>Só opera em mercados <strong>laterais</strong> (ADX baixo)</li>
      </ol>
    </section>

    <section>
      <h3 className="text-lg font-semibold text-white mb-2">Parâmetros</h3>
      <ul className="space-y-2">
        <li><strong>RSI Oversold:</strong> Nível abaixo do qual considera "oversold" (default: 30)</li>
        <li><strong>RSI Overbought:</strong> Nível acima do qual considera "overbought" (default: 70)</li>
        <li><strong>Max ADX:</strong> ADX máximo para operar. Acima disto = tendência forte, não opera</li>
        <li><strong>Stop Loss %:</strong> Perda máxima aceite por trade</li>
      </ul>
    </section>

    <section className="bg-yellow-500/10 border border-yellow-500/30 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-yellow-400 mb-2">⚠️ Importante</h3>
      <p>
        Esta estratégia funciona melhor em <strong>mercados laterais</strong> (ranging).
        Em tendências fortes, o preço pode continuar a subir/cair sem reverter.
        O filtro ADX ajuda a evitar operar em tendências.
      </p>
    </section>

    <section className="bg-zinc-800/50 p-4 rounded-lg">
      <h3 className="text-lg font-semibold text-white mb-2">💡 Dica</h3>
      <p>
        Combine com o agente de Trend: enquanto o Mean Reversion opera em mercados
        laterais, o Trend captura os movimentos direcionais. Juntos cobrem mais cenários.
      </p>
    </section>
  </div>
);

export const MeanReversionPresets = {
  conservative: {
    tooltip: "RSI extremos, ADX baixo. Poucos trades, alta probabilidade.",
    values: {
      rsi_oversold: 25,
      rsi_overbought: 75,
      max_adx: 20,
      stop_loss_pct: 2,
      position_size_pct: 3,
    },
  },
  moderate: {
    tooltip: "Equilíbrio entre frequência e qualidade de sinais.",
    values: {
      rsi_oversold: 30,
      rsi_overbought: 70,
      max_adx: 25,
      stop_loss_pct: 2.5,
      position_size_pct: 5,
    },
  },
  aggressive: {
    tooltip: "RSI mais relaxados, mais trades. Para mercados muito laterais.",
    values: {
      rsi_oversold: 35,
      rsi_overbought: 65,
      max_adx: 30,
      stop_loss_pct: 3,
      position_size_pct: 8,
    },
  },
};

export const MeanReversionTooltips = {
  rsi_oversold: "RSI abaixo deste valor = preço 'barato', sinal de compra potencial.",
  rsi_overbought: "RSI acima deste valor = preço 'caro', sinal de venda potencial.",
  max_adx: "ADX máximo para operar. Valores altos = tendência forte, evitar.",
  stop_loss: "Perda máxima aceite por trade. Fecha posição se atingir.",
  position_size: "Tamanho da posição em % do capital alocado.",
};

export default { MeanReversionHelpContent, MeanReversionPresets, MeanReversionTooltips };
